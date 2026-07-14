from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.middleware.cors import CORSMiddleware
from datetime import datetime
import sys
import subprocess
import json
import os
import logging
import time
import platform
import random
import asyncio
from collections import defaultdict
from fastapi.staticfiles import StaticFiles
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# === BASE DIR ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = BASE_DIR

from tools import json_manager
from tools.smart_json_dispatcher import orchestrate_write
from system_guard import validate_action, ContractViolation

# === Init ===
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

SYSTEM_REGISTRY = f"{BASE_DIR}/system_settings.ndjson"
WORKING_MEMORY_PATH = f"{BASE_DIR}/data/working_memory.json"
UNLOCK_STATUS_PATH = os.path.join(BASE_DIR, "data", "unlock_status.json")
TOOL_UI_PATH = os.path.join(BASE_DIR, "data", "orchestrate_tool_ui.json")
NGROK_CONFIG_PATH = os.path.join(BASE_DIR, "data", "ngrok.json")
EXEC_HUB_PATH = f"{BASE_DIR}/execution_hub.py"
TASKS_DB_PATH = os.path.join(BASE_DIR, "data", "tasks.db")
REFERRAL_PATH = os.path.join(BASE_DIR, "container_state", "referrals.json")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")



# === System Identity Mount ===
STATE_DIR = os.path.expanduser("~/Library/Application Support/OrchestrateOS")
if os.path.exists(STATE_DIR):
    app.mount("/state", StaticFiles(directory=STATE_DIR), name="state")
else:
    logging.warning(f"Warning: State directory not found, skipping mount")

# === Semantic Memory Mount ===
SEMANTIC_MEMORY_DIR = os.path.join(BASE_DIR, "semantic_memory")
if os.path.exists(SEMANTIC_MEMORY_DIR):
    app.mount("/semantic_memory", StaticFiles(directory=SEMANTIC_MEMORY_DIR, html=True), name="semantic_memory")
else:
    logging.warning(f"Warning: Semantic memory directory not found: {SEMANTIC_MEMORY_DIR}")

# === Data Mount ===
DATA_DIR = os.path.join(BASE_DIR, "data")
if os.path.exists(DATA_DIR):
    app.mount("/data", StaticFiles(directory=DATA_DIR), name="data")
else:
    logging.warning(f"Warning: Data directory not found: {DATA_DIR}")

# === URL Aliases ===
URL_ALIASES_PATH = os.path.join(BASE_DIR, "data", "url_aliases.json")

def load_url_aliases():
    """Load URL aliases from data/url_aliases.json"""
    if os.path.exists(URL_ALIASES_PATH):
        try:
            with open(URL_ALIASES_PATH, 'r') as f:
                data = json.load(f)
                return data.get("aliases", {})
        except:
            pass
    return {}

# === Rate Limiting ===
RATE_LIMITS = {
    "/docs/save": {"requests": 30, "window_seconds": 60},
    "/execute_task": {"requests": 100, "window_seconds": 60}
}
rate_limit_state = defaultdict(list)

def check_rate_limit(endpoint: str, client_id: str = "default"):
    """Check if request should be rate limited"""
    if endpoint not in RATE_LIMITS:
        return True

    config = RATE_LIMITS[endpoint]
    now = time.time()
    window_start = now - config["window_seconds"]

    key = f"{endpoint}:{client_id}"
    rate_limit_state[key] = [ts for ts in rate_limit_state[key] if ts > window_start]

    if len(rate_limit_state[key]) >= config["requests"]:
        return False

    rate_limit_state[key].append(now)
    return True

# === File Watcher (SSE) ===
file_change_event = asyncio.Event()
image_change_event = asyncio.Event()
last_file_change = {"timestamp": time.time(), "file": None}
last_image_change = {"timestamp": time.time(), "filename": None}
main_event_loop = None
file_observer = None

class TaskFileHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith('tasks.db'):
            last_file_change["timestamp"] = time.time()
            last_file_change["file"] = "tasks.db"
            if main_event_loop and main_event_loop.is_running():
                main_event_loop.call_soon_threadsafe(file_change_event.set)

class ImageFileHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        filename = os.path.basename(event.src_path)
        if filename.endswith(('.png', '.jpg', '.jpeg', '.webp')) and not filename.startswith('.'):
            last_image_change["timestamp"] = time.time()
            last_image_change["filename"] = filename
            if main_event_loop and main_event_loop.is_running():
                main_event_loop.call_soon_threadsafe(image_change_event.set)

def start_file_watcher():
    global file_observer
    file_observer = Observer()
    # Task DB watcher
    file_observer.schedule(TaskFileHandler(), os.path.join(BASE_DIR, "data"), recursive=False)
    # Public images watcher
    images_path = os.path.join(BASE_DIR, "semantic_memory", "public_images")
    if os.path.exists(images_path):
        file_observer.schedule(ImageFileHandler(), images_path, recursive=False)
    file_observer.start()
    logging.info("File watcher started")

def stop_file_watcher():
    global file_observer
    if file_observer:
        file_observer.stop()
        file_observer.join()
        logging.info("File watcher stopped")

# === Tool Executor ===
def run_script(tool_name, action, params):
    python_exe = sys.executable
    command = [python_exe, EXEC_HUB_PATH, "execute_task", "--params", json.dumps({
        "tool_name": tool_name,
        "action": action,
        "params": params
    })]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=90)
        return json.loads(result.stdout.strip())
    except Exception as e:
        return {"error": "Execution failed", "details": str(e)}

# === Execute Task ===
@app.post("/execute_task")
async def execute_task(request: Request):
    try:
        request_data = await request.json()
        tool_name = request_data.get("tool_name")
        action_name = request_data.get("action")
        params = request_data.get("params", {})

        if not tool_name or not action_name:
            raise HTTPException(status_code=400, detail="Missing tool_name or action.")

        if tool_name == "json_manager" and action_name == "orchestrate_write":
            return orchestrate_write(**params)

        params = validate_action(tool_name, action_name, params)
        result = run_script(tool_name, action_name, params)
        if "error" in result:
            raise HTTPException(status_code=500, detail=result)
        return result

    except ContractViolation as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Execution failed", "details": str(e)})

# === Supported Actions ===
@app.get("/get_supported_actions")
def get_supported_actions():
    try:
        with open(SYSTEM_REGISTRY, "r") as f:
            entries = [json.loads(line.strip()) for line in f if line.strip()]

        for entry in entries:
            if entry.get("action") == "__tool__":
                is_locked = entry.get("locked", True)
                entry["Lock State"] = "Unlocked" if not is_locked else "Locked"

        update_messages_path = os.path.join(BASE_DIR, "data", "update_messages.json")
        update_messages = []
        if os.path.exists(update_messages_path):
            with open(update_messages_path, "r") as f:
                obj = json.load(f)
                update_messages = obj if isinstance(obj, list) else [obj]

        return {
            "status": "success",
            "supported_actions": entries,
            "update_messages": update_messages
        }

    except Exception as e:
        logging.error(f"Failed to load registry or update messages: {e}")
        raise HTTPException(status_code=500, detail="Could not load registry or update messages.")

# === Tool Catalog Endpoint ===
@app.get("/get_tool_catalog")
def get_tool_catalog():
    """
    Unified tool catalog merging system_settings.ndjson + orchestrate_app_store.json.
    Returns single list with unlock status, metadata, and costs.
    """
    try:
        # Load system_settings.ndjson (user's installed tools)
        installed_tools = {}
        if os.path.exists(SYSTEM_REGISTRY):
            with open(SYSTEM_REGISTRY, "r") as f:
                for line in f:
                    if line.strip():
                        entry = json.loads(line.strip())
                        if entry.get("action") == "__tool__":
                            installed_tools[entry.get("tool")] = entry

        # Load orchestrate_app_store.json (marketplace) - try GitHub first for latest tools
        GITHUB_APP_STORE_URL = "https://raw.githubusercontent.com/unmistakablecreative/orchestrate-gershwin/main/data/orchestrate_app_store.json"
        app_store_path = os.path.join(BASE_DIR, "data", "orchestrate_app_store.json")
        app_store = {}

        # Try GitHub first (gets latest marketplace tools)
        try:
            import requests
            resp = requests.get(GITHUB_APP_STORE_URL, timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                app_store = data.get("entries", {})
        except:
            pass  # Fall through to local file

        # Fallback to local file if GitHub failed
        if not app_store and os.path.exists(app_store_path):
            with open(app_store_path, "r") as f:
                data = json.load(f)
                app_store = data.get("entries", {})

        # Load unlock_status.json
        unlocked_tools = set()
        if os.path.exists(UNLOCK_STATUS_PATH):
            with open(UNLOCK_STATUS_PATH, "r") as f:
                unlock_data = json.load(f)
                unlocked_tools = set(unlock_data.get("tools_unlocked", []))

        # Merge: app_store has metadata, system_settings has install status
        catalog = []

        # All tools from app_store (marketplace view)
        for tool_name, meta in app_store.items():
            is_installed = tool_name in installed_tools
            is_unlocked = tool_name in unlocked_tools or (is_installed and not installed_tools.get(tool_name, {}).get("locked", True))

            catalog.append({
                "name": tool_name,
                "label": meta.get("label", tool_name),
                "description": meta.get("description", ""),
                "priority": meta.get("priority", 99),
                "cost": meta.get("referral_unlock_cost", 0),
                "unlocked": is_unlocked,
                "installed": is_installed,
                "requires_credentials": meta.get("requires_credentials", False),
                "credential_fields": meta.get("credential_fields", []),
                "unlock_message": meta.get("unlock_message", ""),
                "post_unlock_nudge": meta.get("post_unlock_nudge", "")
            })

        # Add any installed tools not in app_store (core tools)
        for tool_name, entry in installed_tools.items():
            if tool_name not in app_store:
                is_unlocked = tool_name in unlocked_tools or not entry.get("locked", True)
                catalog.append({
                    "name": tool_name,
                    "label": tool_name.replace("_", " ").title(),
                    "description": entry.get("description", ""),
                    "priority": 999,
                    "cost": entry.get("referral_unlock_cost", 0),
                    "unlocked": is_unlocked,
                    "installed": True,
                    "requires_credentials": False,
                    "credential_fields": [],
                    "unlock_message": "",
                    "post_unlock_nudge": ""
                })

        # Sort by priority, then unlocked first
        catalog.sort(key=lambda x: (not x["unlocked"], x["priority"], x["name"]))

        return {
            "status": "success",
            "tools": catalog,
            "total": len(catalog),
            "unlocked_count": sum(1 for t in catalog if t["unlocked"])
        }

    except Exception as e:
        logging.error(f"Failed to build tool catalog: {e}")
        return {"status": "error", "message": str(e)}

# === Original Skill File Tools (hardcoded baseline) ===
ORIGINAL_SKILL_TOOLS = {
    "account", "buffer_engine", "check_credits", "claude_assistant", "doc_editor",
    "docs", "files", "github_tool_universal", "ideogram_tool", "json_manager",
    "knowledge_vault", "media_manager", "readwise_tool", "refer_user", "session_tool",
    "slide_designer", "spark_file", "system_settings", "terminal", "todolist", "unlock_tool"
}

@app.get("/new_tools")
def get_new_tools():
    """
    Returns JSON schema for tools in system_settings.ndjson that are NOT in the
    original skill file tool list. Claude calls this at session start for new tool discovery.
    """
    try:
        new_tools = []

        if not os.path.exists(SYSTEM_REGISTRY):
            return {"status": "success", "new_tools": []}

        with open(SYSTEM_REGISTRY, "r") as f:
            entries = [json.loads(line.strip()) for line in f if line.strip()]

        # Group entries by tool
        tools_data = {}
        for entry in entries:
            tool_name = entry.get("tool")
            if not tool_name:
                continue

            if tool_name not in tools_data:
                tools_data[tool_name] = {"tool": tool_name, "actions": []}

            if entry.get("action") == "__tool__":
                # Tool-level metadata
                tools_data[tool_name]["description"] = entry.get("description", "")
                tools_data[tool_name]["locked"] = entry.get("locked", True)
                tools_data[tool_name]["referral_unlock_cost"] = entry.get("referral_unlock_cost", 0)
            else:
                # Action entry
                action_entry = {
                    "action": entry.get("action"),
                    "params": entry.get("params", [])
                }
                if entry.get("description"):
                    action_entry["description"] = entry.get("description")
                tools_data[tool_name]["actions"].append(action_entry)

        # Filter to only new tools (not in original skill list)
        for tool_name, tool_data in tools_data.items():
            if tool_name not in ORIGINAL_SKILL_TOOLS:
                new_tools.append(tool_data)

        # Sort by tool name for consistency
        new_tools.sort(key=lambda x: x.get("tool", ""))

        return {"status": "success", "new_tools": new_tools}

    except Exception as e:
        logging.error(f"Failed to get new tools: {e}")
        return {"status": "error", "message": str(e), "new_tools": []}

@app.get("/")
def root():
    return {"status": "Jarvis core is online."}


@app.get("/task_status")
async def task_status():
    import sqlite3
    try:
        conn = sqlite3.connect(TASKS_DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT task_id, description, status, priority, agent_id, batch_id, context, card_title, card_stat, pid, created_at, started_at, processing_started_at, updated_at FROM tasks WHERE status IN ('queued', 'in_progress') ORDER BY CASE status WHEN 'in_progress' THEN 0 ELSE 1 END, created_at DESC")
        active_tasks = [dict(row) for row in cursor.fetchall()]
        cursor.execute("SELECT task_id, status, description, actions_taken, output, output_summary, errors, execution_time_seconds, card_title, card_stat, test_results, tokens, token_cost, batch_id, batch_position, started_at, processing_started_at, completed_at, source FROM task_results ORDER BY completed_at DESC LIMIT 20")
        recent_results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return {"status": "success", "active_tasks": active_tasks, "recent_results": recent_results}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/data-nocache/{filename:path}")
async def get_data_nocache(filename: str):
    """Serve data files with no-cache headers for real-time polling"""
    from fastapi.responses import FileResponse
    filepath = os.path.join(BASE_DIR, "data", filename)
    if not os.path.exists(filepath):
        return {"error": "File not found"}
    return FileResponse(
        filepath,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )

# ============ SQLITE DOC EDITOR ROUTES ============

def _import_doc_editor():
    """Lazy import doc_editor (SQLite-backed)"""
    import importlib
    if 'doc_editor' in sys.modules:
        return sys.modules['doc_editor']
    sys.path.insert(0, os.path.join(BASE_DIR, "tools"))
    return importlib.import_module('doc_editor')

@app.get("/docs/list")
async def list_docs():
    """List all docs from SQLite"""
    try:
        de = _import_doc_editor()
        result = de.list_docs()
        if result.get("status") == "success":
            docs_list = []
            for doc in result.get("docs", []):
                docs_list.append({
                    "id": doc.get("id", ""),
                    "title": doc.get("title", "Untitled"),
                    "collection": doc.get("collection", ""),
                    "updated_at": doc.get("updated_at", ""),
                    "created_at": doc.get("created_at", ""),
                    "word_count": doc.get("word_count", 0),
                    "description": doc.get("description", ""),
                    "status": doc.get("status", ""),
                    "campaign_id": doc.get("campaign_id", ""),
                    "published_url": doc.get("published_url", "")
                })
            return {"status": "success", "docs": docs_list}
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/docs/get/{doc_id}")
async def get_doc(doc_id: str):
    """Get single doc from SQLite"""
    try:
        de = _import_doc_editor()
        result = de.read_doc(doc_id)
        if result.get("status") == "success":
            return {"status": "success", "doc": result.get("doc", {})}
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/docs/save")
async def save_doc(request: Request):
    """Save/update doc via SQLite - uses direct SQL for title/collection/content updates"""
    try:
        body = await request.json()
        doc_id = body.get("id")
        de = _import_doc_editor()

        if doc_id:
            existing = de.read_doc(doc_id)
            if existing.get("status") == "success":
                existing_doc = existing.get("doc", {})
                title = body.get("title", existing_doc.get("title"))
                content = body.get("content", existing_doc.get("content", ""))
                collection = body.get("collection", existing_doc.get("collection"))

                # Direct SQL update for title, collection, and content
                db = de.get_db()
                word_count = de._count_words(content)
                # IMPORTANT: _extract_meta_description returns a tuple (cleaned_content, meta_desc)
                cleaned_content, meta_desc = de._extract_meta_description(content)
                db.execute(
                    "UPDATE docs SET title=?, collection=?, content=?, word_count=?, meta_description=?, updated_at=? WHERE id=?",
                    (title, collection, cleaned_content, word_count, meta_desc or "", datetime.now().isoformat(), doc_id)
                )
                db.commit()

                # Handle metadata fields separately
                meta_fields = {}
                for field in ["status", "description", "campaign_id", "published_url"]:
                    if field in body:
                        meta_fields[field] = body[field]
                if meta_fields:
                    de.update_metadata(doc_id, **meta_fields)

                return {"status": "success", "doc_id": doc_id}

        title = body.get("title", "Untitled")
        content = body.get("content", "")
        collection = body.get("collection", "Notes")
        result = de.create_doc(title=title, content=content, collection=collection, convert_markdown=False)
        return {"status": "success", "doc_id": result.get("doc_id", "")}

    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.delete("/docs/delete/{doc_id}")
async def delete_doc(doc_id: str):
    """Delete doc from SQLite"""
    try:
        de = _import_doc_editor()
        return de.delete_doc(doc_id)
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/docs/backlinks/{doc_id}")
async def get_backlinks(doc_id: str):
    """Get backlinks from SQLite"""
    try:
        de = _import_doc_editor()
        result = de.read_backlinks(doc_id)
        if result.get("status") == "success":
            return {"status": "success", "backlinks": result.get("backlinks", [])}
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/docs/link")
async def create_doc_link(request: Request):
    """Create bidirectional link in SQLite"""
    try:
        body = await request.json()
        source_doc_id = body.get("source_doc_id")
        target_doc_id = body.get("target_doc_id")
        if not source_doc_id or not target_doc_id:
            return {"status": "error", "message": "source_doc_id and target_doc_id required"}
        de = _import_doc_editor()
        return de.link_docs(source_doc_id, target_doc_id)
    except Exception as e:
        return {"status": "error", "message": str(e)}

# === File Upload ===
@app.post("/upload_file")
async def upload_file(request: Request):
    """Write file content to disk. Security: only allows paths within project root."""
    try:
        body = await request.json()
        path = body.get("path")
        content = body.get("content")

        if not path:
            return {"status": "error", "message": "Missing required field: path"}
        if content is None:
            return {"status": "error", "message": "Missing required field: content"}

        # Security: Resolve path and ensure it's within project root
        if os.path.isabs(path):
            resolved_path = os.path.realpath(path)
        else:
            resolved_path = os.path.realpath(os.path.join(PROJECT_ROOT, path))

        normalized_root = os.path.realpath(PROJECT_ROOT)

        if not resolved_path.startswith(normalized_root + os.sep) and resolved_path != normalized_root:
            return {"status": "error", "message": f"Path '{path}' is outside project root. Access denied."}

        parent_dir = os.path.dirname(resolved_path)
        if not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        with open(resolved_path, 'w', encoding='utf-8') as f:
            f.write(content)

        return {"status": "success", "path": resolved_path}

    except json.JSONDecodeError:
        return {"status": "error", "message": "Invalid JSON body"}
    except PermissionError:
        return {"status": "error", "message": f"Permission denied writing to '{path}'"}
    except Exception as e:
        return {"status": "error", "message": str(e)}



# === Identity Generation Endpoints ===
@app.post("/generate_identity")
async def generate_identity(request: Request):
    """Generate system_identity.json with user info"""
    try:
        body = await request.json()
        name = body.get("name")
        email = body.get("email")

        if not name or not email:
            return {"status": "error", "message": "Missing required fields: name and email"}

        # Generate user_id: name (lowercase, spaces to underscores) + random 4-digit number
        name_part = name.lower().replace(" ", "_").split("@")[0]
        user_id = f"{name_part}_{random.randint(1000, 9999)}"

        identity = {
            "user_id": user_id,
            "name": name,
            "email": email,
            "created_at": datetime.now().isoformat(),
            "device_name": platform.node(),
            "first_run_complete": False
        }

        identity_path = os.path.join(BASE_DIR, "data", "system_identity.json")
        os.makedirs(os.path.dirname(identity_path), exist_ok=True)

        with open(identity_path, 'w') as f:
            json.dump(identity, f, indent=4)

        return {"status": "success", "user_id": user_id}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/complete_setup")
async def complete_setup():
    """Mark first_run_complete as true in system_identity.json"""
    try:
        identity_path = os.path.join(BASE_DIR, "data", "system_identity.json")

        if not os.path.exists(identity_path):
            return {"status": "error", "message": "system_identity.json not found"}

        with open(identity_path, 'r') as f:
            identity = json.load(f)

        identity["first_run_complete"] = True

        with open(identity_path, 'w') as f:
            json.dump(identity, f, indent=4)

        return {"status": "success", "message": "Setup complete"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/get_identity")
async def get_identity():
    """Return system_identity.json contents"""
    try:
        identity_path = os.path.join(BASE_DIR, "data", "system_identity.json")
        if not os.path.exists(identity_path):
            return {"status": "error", "message": "system_identity.json not found"}
        with open(identity_path, "r") as f:
            identity = json.load(f)
        return identity
    except Exception as e:
        return {"status": "error", "message": str(e)}


# === SSE Endpoints ===
@app.get("/api/image-updates")
async def image_updates():
    async def event_generator():
        while True:
            try:
                try:
                    await asyncio.wait_for(image_change_event.wait(), timeout=30.0)
                    image_change_event.clear()
                    yield f"data: {json.dumps({'type': 'image_ready', 'filename': last_image_change.get('filename'), 'timestamp': last_image_change.get('timestamp')})}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': time.time()})}\n\n"
            except asyncio.CancelledError:
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "Access-Control-Allow-Origin": "*"})


# Dynamic URL Aliases - catch-all route (MUST be LAST - after all other routes)
@app.api_route("/{alias:path}", methods=["GET"])
async def dynamic_alias_handler(request: Request, alias: str):
    """Dynamic redirect based on url_aliases.json - preserves query params"""
    from fastapi.responses import RedirectResponse

    # Only handle single-segment paths (e.g., /editor, /crm, NOT /semantic_memory/foo.html)
    if "/" in alias:
        raise HTTPException(status_code=404, detail="Not found")

    full_path = f"/{alias}"
    aliases = load_url_aliases()

    if full_path in aliases:
        target = aliases[full_path]
        query_string = request.scope.get("query_string", b"").decode()
        if query_string:
            target = f"{target}?{query_string}"
        return RedirectResponse(url=target, status_code=302)

    raise HTTPException(status_code=404, detail=f"No alias found for '{alias}'")
