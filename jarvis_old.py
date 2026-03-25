from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from datetime import datetime
import sys
import subprocess
import json
import os
import logging
from fastapi.staticfiles import StaticFiles

# === BASE DIR ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = BASE_DIR

from tools import json_manager
from tools.smart_json_dispatcher import orchestrate_write
from system_guard import validate_action, ContractViolation

# === Init ===
app = FastAPI()

SYSTEM_REGISTRY = f"{BASE_DIR}/system_settings.ndjson"
WORKING_MEMORY_PATH = f"{BASE_DIR}/data/working_memory.json"
UNLOCK_STATUS_PATH = os.path.join(BASE_DIR, "data", "unlock_status.json")
TOOL_UI_PATH = os.path.join(BASE_DIR, "data", "orchestrate_tool_ui.json")
NGROK_CONFIG_PATH = os.path.join(BASE_DIR, "data", "ngrok.json")
EXEC_HUB_PATH = f"{BASE_DIR}/execution_hub.py"
REFERRAL_PATH = os.path.join(BASE_DIR, "container_state", "referrals.json")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# === Dropzone Mount ===
DROPZONE_DIR = os.path.expanduser("~/Documents/Orchestrate/dropzone")
if os.path.exists(DROPZONE_DIR):
    app.mount("/dropzone", StaticFiles(directory=DROPZONE_DIR), name="dropzone")
else:
    logging.warning(f"⚠️ Dropzone directory not found: {DROPZONE_DIR}")

# === System Identity Mount ===
STATE_DIR = "/Library/Application Support/OrchestrateOS"
if not os.path.exists(STATE_DIR):
    STATE_DIR = os.path.expanduser("~/Library/Application Support/OrchestrateOS")
if os.path.exists(STATE_DIR):
    app.mount("/state", StaticFiles(directory=STATE_DIR), name="state")
else:
    logging.warning(f"⚠️ State directory not found, skipping mount")

# === Semantic Memory Mount ===
SEMANTIC_MEMORY_DIR = os.path.join(BASE_DIR, "semantic_memory")
if os.path.exists(SEMANTIC_MEMORY_DIR):
    app.mount("/semantic_memory", StaticFiles(directory=SEMANTIC_MEMORY_DIR, html=True), name="semantic_memory")
else:
    os.makedirs(SEMANTIC_MEMORY_DIR, exist_ok=True)
    app.mount("/semantic_memory", StaticFiles(directory=SEMANTIC_MEMORY_DIR, html=True), name="semantic_memory")
    logging.info(f"📁 Created semantic_memory directory: {SEMANTIC_MEMORY_DIR}")

# === Merge Logic (in-memory, no file writes) ===
def get_merged_tool_ui():
    """Merge tool UI with unlock status in memory. No file writes."""
    try:
        with open(TOOL_UI_PATH, "r") as f:
            raw = json.load(f)
            tool_ui = raw.get("entries", {})

        if os.path.exists(UNLOCK_STATUS_PATH):
            with open(UNLOCK_STATUS_PATH, "r") as f:
                unlock_data = json.load(f)
                unlocked = set(unlock_data.get("tools_unlocked", []))
        else:
            unlocked = set()

        merged = []
        for tool_name, meta in tool_ui.items():
            merged.append({
                "name": tool_name,
                "label": meta.get("label", tool_name),
                "description": meta.get("description", ""),
                "priority": meta.get("priority", 0),
                "referral_unlock_cost": meta.get("referral_unlock_cost", 0),
                "locked": tool_name not in unlocked
            })

        return merged

    except Exception as e:
        logging.warning(f"⚠️ Failed to merge tool UI: {e}")
        return []

# === Repo Sync + Registry Merge ===
def sync_repo_and_merge_registry():
    try:
        logging.info("🔄 Syncing Orchestrate repo...")
        subprocess.run(["git", "-C", BASE_DIR, "pull"], check=True)

        with open(SYSTEM_REGISTRY, "r") as f:
            updated_registry = [json.loads(line.strip()) for line in f if line.strip()]

        unlocked_tools = set()
        if os.path.exists(REFERRAL_PATH):
            with open(REFERRAL_PATH, "r") as f:
                referral_data = json.load(f)
            unlocked_tools = set(referral_data.get("tools_unlocked", []))

        for entry in updated_registry:
            if entry.get("tool") in unlocked_tools:
                entry["unlocked"] = True

        with open(SYSTEM_REGISTRY, "w") as f:
            for entry in updated_registry:
                f.write(json.dumps(entry) + "\n")

        repo_path = os.path.join(BASE_DIR, "data", "update_messages.json")
        git_path = os.path.join(BASE_DIR, ".git", "..", "data", "update_messages.json")
        if os.path.exists(git_path):
            subprocess.run(["cp", git_path, repo_path])
            logging.info("📢 update_messages.json refreshed from git.")

        logging.info("✅ Repo + registry sync complete.")

    except Exception as e:
        logging.error(f"❌ Repo sync failed: {e}")

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

# === Startup Hook ===
@app.on_event("startup")
def startup_routines():
    logging.info("🔥 FASTAPI STARTUP HOOK TRIGGERED")

    try:
        sync_repo_and_merge_registry()
    except Exception as e:
        logging.warning(f"⚠️ Startup sync failed: {e}")

    try:
        if os.path.exists(NGROK_CONFIG_PATH):
            with open(NGROK_CONFIG_PATH) as f:
                cfg = json.load(f)
                token = cfg.get("token")
                domain = cfg.get("domain")

            running = subprocess.getoutput("pgrep -f 'ngrok http'")
            if not running:
                subprocess.Popen(["ngrok", "config", "add-authtoken", token])
                subprocess.Popen(["ngrok", "http", "--domain=" + domain, "8000"])
                logging.info("🚀 ngrok tunnel relaunched.")
            else:
                logging.info("🔁 ngrok already running.")
    except Exception as e:
        logging.warning(f"⚠️ Ngrok relaunch failed: {e}")

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

# === Supported Actions + Messages ===
@app.get("/get_supported_actions")
def get_supported_actions():
    try:
        sync_repo_and_merge_registry()
        with open(SYSTEM_REGISTRY, "r") as f:
            entries = [json.loads(line.strip()) for line in f if line.strip()]

        for entry in entries:
            if entry.get("action") == "__tool__":
                is_locked = entry.get("locked", True)
                entry["🔒 Lock State"] = "✅ Unlocked" if not is_locked else "❌ Locked"

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
        logging.error(f"🚨 Failed to load registry or update messages: {e}")
        raise HTTPException(status_code=500, detail="Could not load registry or update messages.")

# === Memory Loader ===
@app.post("/load_memory")
def load_memory():
    try:
        with open(WORKING_MEMORY_PATH, "r", encoding="utf-8") as f:
            memory = json.load(f)
        return {
            "status": "success",
            "loaded": len(memory),
            "memory": memory
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail={
            "error": "Cannot load working_memory.json",
            "details": str(e)
        })

# === Dashboard Rendering ===
DASHBOARD_INDEX_PATH = os.path.join(BASE_DIR, "data/dashboard_index.json")

def load_dashboard_data():
    try:
        with open(DASHBOARD_INDEX_PATH, 'r', encoding='utf-8') as f:
            dashboard_config = json.load(f)

        dashboard_data = {}

        for item in dashboard_config.get("dashboard_items", []):
            key = item.get("key")
            source_type = item.get("source")

            try:
                if source_type == "file":
                    filepath = os.path.join(BASE_DIR, item.get("file"))

                    if filepath.endswith('.ndjson'):
                        with open(filepath, 'r', encoding='utf-8') as f:
                            data = [json.loads(line.strip()) for line in f if line.strip()]
                            dashboard_data[key] = data
                    else:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            dashboard_data[key] = data

                elif source_type == "tool_action":
                    tool_name = item.get("tool")
                    action = item.get("action")
                    params = item.get("params", {})
                    result = run_script(tool_name, action, params)
                    dashboard_data[key] = result

            except Exception as e:
                dashboard_data[key] = {"error": f"Could not load {key}: {str(e)}"}

        formatted_output = format_dashboard_display(dashboard_data, dashboard_config)

        return {
            "status": "success",
            "dashboard_data": formatted_output
        }

    except Exception as e:
        return {"error": f"Failed to load dashboard: {str(e)}"}

def format_dashboard_display(data, config):
    formatted = {}

    for item in config.get("dashboard_items", []):
        key = item.get("key")
        formatter = item.get("formatter")

        if key not in data:
            continue

        raw_data = data[key]

        if formatter == "toolkit_list":
            formatted[key] = format_toolkit_list(raw_data, item.get("limit", 50))
        elif formatter == "app_store_list":
            formatted[key] = format_app_store_list(raw_data, item.get("limit", 10))
        elif formatter == "calendar_list":
            formatted[key] = format_calendar_events(raw_data)
        elif formatter == "thread_log_list":
            formatted[key] = format_thread_log(raw_data, item.get("limit", 5))
        elif formatter == "ideas_list":
            formatted[key] = format_ideas_reminders(raw_data, item.get("limit", 10))
        else:
            formatted[key] = raw_data

    return formatted

def format_toolkit_list(data, limit=50):
    if not data:
        return {"display_table": "No tools available", "tools": []}

    if isinstance(data, str):
        entries = [json.loads(line.strip()) for line in data.split('\n') if line.strip()]
    elif isinstance(data, list):
        entries = data
    else:
        return {"display_table": "Error loading toolkit", "tools": []}

    tools = [e for e in entries if e.get("action") == "__tool__"]

    if not tools:
        return {"display_table": "No tools available", "tools": []}

    # Merge with unlock_status.json to get accurate unlock state
    unlocked_tools = set()
    if os.path.exists(UNLOCK_STATUS_PATH):
        try:
            with open(UNLOCK_STATUS_PATH, 'r') as f:
                unlock_data = json.load(f)
                unlocked_tools = set(unlock_data.get("tools_unlocked", []))
        except Exception:
            pass

    # Apply unlock status from unlock_status.json
    for tool in tools:
        tool_name = tool.get("tool", "")
        if tool_name in unlocked_tools:
            tool["locked"] = False
        # Also respect the existing locked field if already unlocked
        elif not tool.get("locked", True):
            pass  # Keep unlocked

    unlocked = sorted([t for t in tools if not t.get("locked", True)],
                     key=lambda x: x.get("tool", "").lower())
    locked = sorted([t for t in tools if t.get("locked", True)],
                   key=lambda x: x.get("referral_unlock_cost", 999))

    table = "| Status | Tool | Description | Unlock Cost |\n"
    table += "|--------|------|-------------|-------------|\n"

    for tool in unlocked[:limit]:
        name = tool.get("tool", "Unknown")
        desc = tool.get("description", "")[:60]
        table += f"| ✅ | **{name}** | {desc} | - |\n"

    for tool in locked[:limit]:
        name = tool.get("tool", "Unknown")
        desc = tool.get("description", "")[:60]
        cost = tool.get("referral_unlock_cost", "?")
        table += f"| 🔒 | {name} | {desc} | {cost} credits |\n"

    return {"display_table": table, "tools": tools}

def format_app_store_list(data, limit=10):
    if not isinstance(data, dict):
        return {"display_table": "Error loading app store", "tools": {}}

    entries = data.get("entries", {})
    if not entries:
        return {"display_table": "No tools available", "tools": {}}

    sorted_tools = sorted(entries.items(), key=lambda x: x[1].get("priority", 999))

    table = "| Tool | Cost | Description |\n"
    table += "|------|------|-------------|\n"

    for tool_name, meta in sorted_tools[:limit]:
        label = meta.get("label", tool_name)
        desc = meta.get("description", "")[:80]
        cost = meta.get("referral_unlock_cost", "?")
        table += f"| **{label}** | {cost} credits | {desc} |\n"

    return {"display_table": table, "tools": entries}

def format_calendar_events(data):
    events = []

    if isinstance(data, dict):
        if "events" in data:
            events = data["events"]
        elif "data" in data:
            events = data["data"]
    elif isinstance(data, list):
        events = data

    if events:
        cal_list = "📅 **Calendar Events:**\n\n"
        for event in events[:5]:
            title = event.get("title", "No title")
            when = event.get("when", {})
            start_time = when.get("start_time", when.get("start", ""))
            if isinstance(start_time, (int, float)):
                start_time = datetime.fromtimestamp(start_time).strftime("%m/%d %H:%M")

            participants = event.get("participants", [])
            user_email = "srinirao"

            other_participants = [
                p for p in participants
                if p.get("email") != user_email
            ]

            participant_names = []
            for p in other_participants:
                name = p.get("name") or p.get("email", "")
                if name:
                    participant_names.append(name)

            if participant_names:
                participants_str = " + ".join(participant_names)
                cal_list += f"• **{start_time}**: {title} (with {participants_str})\n"
            else:
                cal_list += f"• **{start_time}**: {title}\n"

        return cal_list
    else:
        return "📅 **Calendar Events:** No upcoming events"

def format_thread_log(data, limit=5):
    if not isinstance(data, dict):
        return "📋 **Thread Log:** No entries"

    entries_data = data.get("entries", data)
    if entries_data:
        thread_list = "📋 **Thread Log:**\n\n"
        for key, entry in list(entries_data.items())[-limit:]:
            status = entry.get("status", "unknown").upper()
            goal = entry.get("context_goal", key)[:60]
            thread_list += f"• **{status}**: {goal}\n"
        return thread_list
    else:
        return "📋 **Thread Log:** No entries"

def format_ideas_reminders(data, limit=10):
    if not isinstance(data, dict):
        return "💡 **Ideas & Reminders:** No entries"

    entries_data = data.get("entries", data)
    if entries_data:
        ideas_list = "💡 **Ideas & Reminders:**\n\n"
        for key, item in list(entries_data.items())[-limit:]:
            if isinstance(item, dict):
                item_type = item.get("type", "idea")
                title = item.get("title", item.get("content", key))[:60]
                ideas_list += f"• **{item_type.title()}**: {title}\n"
            else:
                ideas_list += f"• **Idea**: {str(item)[:60]}\n"
        return ideas_list
    else:
        return "💡 **Ideas & Reminders:** No entries"

@app.get("/get_dashboard_file/{file_key}")
def get_dashboard_file(file_key: str):
    if file_key == "full_dashboard":
        dashboard = load_dashboard_data()
        return dashboard

    file_map = {
        "phrase_promotions": "data/phrase_insight_promotions.json",
        "runtime_contract": "orchestrate_runtime_contract.json",
        "tool_build_protocol": "data/tool_build_protocol.json",
        "podcast_prep_rules": "podcast_prep_guidelines.json",
        "thread_log_full": "data/thread_log.json",
        "ideas_and_reminders_full": "data/ideas_reminders.json"
    }

    if file_key not in file_map:
        raise HTTPException(status_code=404, detail=f"File key '{file_key}' not found")

    try:
        filepath = file_map[file_key]
        abs_path = os.path.join(BASE_DIR, filepath)

        with open(abs_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        return {
            "status": "success",
            "file_key": file_key,
            "data": data
        }

    except Exception as e:
        return JSONResponse(status_code=500, content={
            "error": f"Could not load {file_key}",
            "details": str(e)
        })

@app.get("/")
def root():
    return {"status": "Jarvis core is online."}

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

# ============ DOC ENDPOINTS ============
DOCS_FILE = os.path.join(BASE_DIR, "data", "docs.json")
_docs_cache = {"data": None, "mtime": 0}

def load_docs():
    if not os.path.exists(DOCS_FILE):
        return {"docs": {}}
    mtime = os.path.getmtime(DOCS_FILE)
    if _docs_cache["data"] is not None and mtime == _docs_cache["mtime"]:
        return _docs_cache["data"]
    with open(DOCS_FILE, 'r') as f:
        data = json.load(f)
    _docs_cache["data"] = data
    _docs_cache["mtime"] = mtime
    return data

def save_docs(data):
    with open(DOCS_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    _docs_cache["data"] = data
    _docs_cache["mtime"] = os.path.getmtime(DOCS_FILE)

@app.get("/docs/list")
async def list_docs():
    """List all docs"""
    import re
    data = load_docs()
    docs_list = []
    for doc_id, doc in data.get("docs", {}).items():
        # Calculate word count from content (strip HTML tags)
        content = doc.get("content", "")
        text = re.sub(r'<[^>]*>', ' ', content) if content else ""
        words = [w for w in text.split() if w]
        word_count = len(words)

        docs_list.append({
            "id": doc_id,
            "title": doc.get("title", "Untitled"),
            "collection": doc.get("collection", ""),
            "updated_at": doc.get("updated_at", ""),
            "created_at": doc.get("created_at", ""),
            "word_count": word_count,
            "description": doc.get("description", ""),
            "status": doc.get("status", ""),
            "campaign_id": doc.get("campaign_id", ""),
            "published_url": doc.get("published_url", "")
        })
    return {"status": "success", "docs": docs_list}

@app.get("/docs/get/{doc_id}")
async def get_doc(doc_id: str):
    """Get single doc by ID"""
    data = load_docs()
    doc = data.get("docs", {}).get(doc_id)
    if not doc:
        return {"status": "error", "message": "Doc not found"}
    return {"status": "success", "doc": doc}

@app.post("/docs/save")
async def save_doc(request: Request):
    """Save/update doc"""
    body = await request.json()
    doc_id = body.get("id")

    data = load_docs()

    if not doc_id:
        # New doc
        import uuid
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"

    existing_doc = data.get("docs", {}).get(doc_id, {})
    data["docs"][doc_id] = {
        "id": doc_id,
        "title": body.get("title", existing_doc.get("title", "Untitled")),
        "content": body.get("content", existing_doc.get("content", "")),
        "collection": body.get("collection", existing_doc.get("collection", "Notes")),
        "description": body.get("description", existing_doc.get("description", "")),
        "status": body.get("status", existing_doc.get("status", "")),
        "campaign_id": body.get("campaign_id", existing_doc.get("campaign_id", "")),
        "published_url": body.get("published_url", existing_doc.get("published_url", "")),
        "created_at": existing_doc.get("created_at", datetime.now().isoformat()),
        "updated_at": datetime.now().isoformat()
    }
    
    save_docs(data)
    return {"status": "success", "doc_id": doc_id}

@app.delete("/docs/delete/{doc_id}")
async def delete_doc(doc_id: str):
    """Delete doc"""
    data = load_docs()
    if doc_id in data.get("docs", {}):
        del data["docs"][doc_id]
        save_docs(data)
        return {"status": "success"}
    return {"status": "error", "message": "Doc not found"}

@app.get("/docs/backlinks/{doc_id}")
async def get_backlinks(doc_id: str):
    """Get backlinks for a doc"""
    data = load_docs()
    doc = data.get("docs", {}).get(doc_id)
    if not doc:
        return {"status": "error", "message": "Doc not found"}
    
    backlinks = []
    for bl_id in doc.get("backlinks", []):
        bl_doc = data.get("docs", {}).get(bl_id)
        if bl_doc:
            backlinks.append({
                "doc_id": bl_id,
                "title": bl_doc.get("title", "Untitled"),
                "collection": bl_doc.get("collection", "")
            })
    
    return {"status": "success", "backlinks": backlinks}

@app.post("/docs/link")
async def create_doc_link(request: Request):
    """Create bidirectional link between docs"""
    body = await request.json()
    source_doc_id = body.get("source_doc_id")
    target_doc_id = body.get("target_doc_id")
    
    if not source_doc_id or not target_doc_id:
        return {"status": "error", "message": "source_doc_id and target_doc_id required"}
    
    data = load_docs()
    
    source_doc = data.get("docs", {}).get(source_doc_id)
    target_doc = data.get("docs", {}).get(target_doc_id)
    
    if not source_doc or not target_doc:
        return {"status": "error", "message": "One or both docs not found"}
    
    # Initialize links/backlinks arrays if missing
    if "links" not in source_doc:
        source_doc["links"] = []
    if "backlinks" not in target_doc:
        target_doc["backlinks"] = []
    
    # Add link if not already present
    if target_doc_id not in source_doc["links"]:
        source_doc["links"].append(target_doc_id)
    if source_doc_id not in target_doc["backlinks"]:
        target_doc["backlinks"].append(source_doc_id)
    
    save_docs(data)
    return {"status": "success", "message": f"Linked {source_doc_id} -> {target_doc_id}"}


# ============== DOC EDITOR BETA ROUTES ==============
# Mirrors /docs/ routes but uses docs_beta.json for isolated testing

DOCS_BETA_FILE = os.path.join(BASE_DIR, "data", "docs_beta.json")

def load_docs_beta():
    if not os.path.exists(DOCS_BETA_FILE):
        return {"docs": {}}
    mtime = os.path.getmtime(DOCS_BETA_FILE)
    if _docs_beta_cache["data"] is not None and mtime == _docs_beta_cache["mtime"]:
        return _docs_beta_cache["data"]
    with open(DOCS_BETA_FILE, 'r') as f:
        data = json.load(f)
    _docs_beta_cache["data"] = data
    _docs_beta_cache["mtime"] = mtime
    return data

def save_docs_beta(data):
    with open(DOCS_BETA_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    _docs_beta_cache["data"] = data
    _docs_beta_cache["mtime"] = os.path.getmtime(DOCS_BETA_FILE)

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
        # Handle both absolute and relative paths
        if os.path.isabs(path):
            resolved_path = os.path.realpath(path)
        else:
            resolved_path = os.path.realpath(os.path.join(PROJECT_ROOT, path))

        # Normalize project root for comparison
        normalized_root = os.path.realpath(PROJECT_ROOT)

        # Check if resolved path is within project root
        if not resolved_path.startswith(normalized_root + os.sep) and resolved_path != normalized_root:
            return {"status": "error", "message": f"Path '{path}' is outside project root. Access denied."}

        # Ensure parent directory exists
        parent_dir = os.path.dirname(resolved_path)
        if not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        # Write the file
        with open(resolved_path, 'w', encoding='utf-8') as f:
            f.write(content)

        return {"status": "success", "path": resolved_path}

    except json.JSONDecodeError:
        return {"status": "error", "message": "Invalid JSON body"}
    except PermissionError:
        return {"status": "error", "message": f"Permission denied writing to '{path}'"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# 🔗 Dynamic URL Aliases - catch-all route (MUST be LAST - after all other routes)