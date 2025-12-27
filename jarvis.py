from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from datetime import datetime
import subprocess, json, os, logging
from fastapi.staticfiles import StaticFiles

# === BASE DIR ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

from tools import json_manager
from tools.smart_json_dispatcher import orchestrate_write
from system_guard import validate_action, ContractViolation

# === Init ===
app = FastAPI()

SYSTEM_REGISTRY = f"{BASE_DIR}/system_settings.ndjson"
WORKING_MEMORY_PATH = f"{BASE_DIR}/data/working_memory.json"
UNLOCK_STATUS_PATH = os.path.join(BASE_DIR, "data", "unlock_status.json")
TOOL_UI_PATH = os.path.join(BASE_DIR, "data", "orchestrate_tool_ui.json")
MERGED_UI_PATH = os.path.join(BASE_DIR, "data", "merged_tool_ui.json")
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
# Try user-level path if system-level doesn't exist
if not os.path.exists(STATE_DIR):
    STATE_DIR = os.path.expanduser("~/Library/Application Support/OrchestrateOS")
if os.path.exists(STATE_DIR):
    app.mount("/state", StaticFiles(directory=STATE_DIR), name="state")
else:
    logging.warning(f"⚠️ State directory not found, skipping mount")

# === Merge Logic ===
def merge_tool_ui_with_unlocks():
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

        with open(MERGED_UI_PATH, "w") as out:
            json.dump(merged, out, indent=2)

        logging.info("✅ Merged tool UI written to merged_tool_ui.json")

    except Exception as e:
        logging.warning(f"⚠️ Failed to merge tool UI: {e}")

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

        # Force update of update_messages.json
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
    command = ["python3", EXEC_HUB_PATH, "execute_task", "--params", json.dumps({
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
    try:
        logging.info("🔥 FASTAPI STARTUP HOOK TRIGGERED")
        sync_repo_and_merge_registry()
        merge_tool_ui_with_unlocks()
    except Exception as e:
        logging.warning(f"⚠️ Startup routines failed: {e}")

    # === Start ngrok (if not already running) ===
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

    # === Start Claude Queue Processor ===
    try:
        from claude_queue_processor import ClaudeQueueProcessor
        processor = ClaudeQueueProcessor()
        processor.start_background()
        logging.info("✅ Claude Code queue processor started")
    except Exception as e:
        logging.warning(f"⚠️ Claude queue processor failed to start: {e}")

# === Start Referral Engine subprocess ===
try:
    referral_script = os.path.join(BASE_DIR, "tools", "referral_engine.py")
    subprocess.Popen(["python3", referral_script])
    logging.info("📣 Referral engine launched unconditionally.")
except Exception as e:
    logging.warning(f"⚠️ Failed to launch referral engine: {e}")

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
        merge_tool_ui_with_unlocks()

        with open(SYSTEM_REGISTRY, "r") as f:
            entries = [json.loads(line.strip()) for line in f if line.strip()]

        # 🔓 Inject readable lock status for display
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
    """Load dashboard using config-driven approach"""
    try:
        # Load dashboard configuration
        with open(DASHBOARD_INDEX_PATH, 'r', encoding='utf-8') as f:
            dashboard_config = json.load(f)

        dashboard_data = {}

        # Process each dashboard item
        for item in dashboard_config.get("dashboard_items", []):
            key = item.get("key")
            source_type = item.get("source")

            try:
                if source_type == "file":
                    # Load from file
                    filepath = os.path.join(BASE_DIR, item.get("file"))

                    # Handle NDJSON files (system_settings.ndjson)
                    if filepath.endswith('.ndjson'):
                        with open(filepath, 'r', encoding='utf-8') as f:
                            data = [json.loads(line.strip()) for line in f if line.strip()]
                            dashboard_data[key] = data
                    else:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            dashboard_data[key] = data

                elif source_type == "tool_action":
                    # Load from tool execution
                    tool_name = item.get("tool")
                    action = item.get("action")
                    params = item.get("params", {})
                    result = run_script(tool_name, action, params)
                    dashboard_data[key] = result

            except Exception as e:
                dashboard_data[key] = {"error": f"Could not load {key}: {str(e)}"}

        # Format the data for display using config
        formatted_output = format_dashboard_display(dashboard_data, dashboard_config)

        return {
            "status": "success",
            "dashboard_data": formatted_output
        }

    except Exception as e:
        return {"error": f"Failed to load dashboard: {str(e)}"}

def format_dashboard_display(data, config):
    """Convert JSON data to formatted output based on config"""
    formatted = {}

    for item in config.get("dashboard_items", []):
        key = item.get("key")
        formatter = item.get("formatter")
        display_type = item.get("display_type")

        if key not in data:
            continue

        raw_data = data[key]

        # Apply formatter (beta formatters: toolkit + app store)
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
            # Default: just pass through
            formatted[key] = raw_data

    return formatted

# Dashboard formatters (beta formatters)
def format_toolkit_list(data, limit=50):
    """Format system_settings.ndjson as markdown table"""
    if not data:
        return {"display_table": "No tools available", "tools": []}

    # Parse NDJSON - data could be list of objects or raw string
    if isinstance(data, str):
        entries = [json.loads(line.strip()) for line in data.split('\n') if line.strip()]
    elif isinstance(data, list):
        entries = data
    else:
        return {"display_table": "Error loading toolkit", "tools": []}

    # Filter for actual tools (action: __tool__)
    tools = [e for e in entries if e.get("action") == "__tool__"]

    if not tools:
        return {"display_table": "No tools available", "tools": []}

    # Sort: unlocked alphabetically, locked by cost
    unlocked = sorted([t for t in tools if not t.get("locked", True)],
                     key=lambda x: x.get("tool", "").lower())
    locked = sorted([t for t in tools if t.get("locked", True)],
                   key=lambda x: x.get("referral_unlock_cost", 999))

    # Build markdown table
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
    """Format orchestrate_app_store.json as markdown table"""
    if not isinstance(data, dict):
        return {"display_table": "Error loading app store", "tools": {}}

    entries = data.get("entries", {})
    if not entries:
        return {"display_table": "No tools available", "tools": {}}

    # Sort by priority
    sorted_tools = sorted(entries.items(), key=lambda x: x[1].get("priority", 999))

    # Build markdown table
    table = "| Tool | Cost | Description |\n"
    table += "|------|------|-------------|\n"

    for tool_name, meta in sorted_tools[:limit]:
        label = meta.get("label", tool_name)
        desc = meta.get("description", "")[:80]
        cost = meta.get("referral_unlock_cost", "?")
        table += f"| **{label}** | {cost} credits | {desc} |\n"

    return {"display_table": table, "tools": entries}

# Dashboard formatters (jarvis-local only, not used in beta)
def format_calendar_events(data):
    """Format calendar events as list with participants"""
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

            # Extract participants and show who the meeting is with (excluding user)
            participants = event.get("participants", [])
            user_email = "srinirao"  # Current user's email

            # Filter out the user's own email from participants
            other_participants = [
                p for p in participants
                if p.get("email") != user_email
            ]

            # Build list of participant names to display
            participant_names = []
            for p in other_participants:
                # Prefer name over email for display
                name = p.get("name") or p.get("email", "")
                if name:
                    participant_names.append(name)

            # Format the event line with participants if any
            if participant_names:
                participants_str = " + ".join(participant_names)
                cal_list += f"• **{start_time}**: {title} (with {participants_str})\n"
            else:
                cal_list += f"• **{start_time}**: {title}\n"

        return cal_list
    else:
        return "📅 **Calendar Events:** No upcoming events"

def format_thread_log(data, limit=5):
    """Format thread log as list"""
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
    """Format ideas and reminders as list"""
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

# Dashboard endpoint
@app.get("/get_dashboard_file/{file_key}")
def get_dashboard_file(file_key: str):
    """Load specific dashboard files when needed or full dashboard"""

    # Special case: full dashboard
    if file_key == "full_dashboard":
        dashboard = load_dashboard_data()
        return dashboard

    # Individual files
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

# === Health Check ===
@app.get("/")
def root():
    return {"status": "Jarvis core is online."}
