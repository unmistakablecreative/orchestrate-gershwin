from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
import subprocess, json, os, logging, time, sys, signal, atexit
import threading
import asyncio
from pathlib import Path
from collections import defaultdict
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from tools import json_manager
from tools.smart_json_dispatcher import orchestrate_write
from system_guard import validate_action, ContractViolation

app = FastAPI()

# Builds Index - tracks files written to semantic_memory
BUILDS_INDEX_PATH = os.path.join(os.path.dirname(__file__), "data", "builds_index.json")
BUILDS_EXCLUDE_LIST = [
    "command_center.html",
    "task_board.html",
    "crm_dashboard_v2.html",
    "bullet_journal.html",
    "content_calendar_dashboard.html",
    "test_runner.html",
    "public_image_generator.html"
]

def add_to_builds_index(filename: str, url: str, task_description: str = ""):
    """Add an entry to builds_index.json when a file is written to semantic_memory"""
    if filename in BUILDS_EXCLUDE_LIST:
        return

    try:
        # Load existing index
        if os.path.exists(BUILDS_INDEX_PATH):
            with open(BUILDS_INDEX_PATH, 'r') as f:
                index = json.load(f)
        else:
            index = []

        # Create new entry
        entry = {
            "filename": filename,
            "url": url,
            "created_at": datetime.now().isoformat(),
            "task_description": task_description
        }

        # Remove existing entry for same filename if present
        index = [e for e in index if e.get("filename") != filename]

        # Add new entry at the beginning
        index.insert(0, entry)

        # Cap at 50 entries
        index = index[:50]

        # Save
        with open(BUILDS_INDEX_PATH, 'w') as f:
            json.dump(index, f, indent=2)

    except Exception as e:
        logging.error(f"Failed to update builds_index: {e}")

# URL Aliases - short URLs to semantic_memory paths
URL_ALIASES_PATH = os.path.join(os.path.dirname(__file__), "data", "url_aliases.json")

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

# NDJSON execution logging
LOGS_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "logs.db")
TASKS_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "tasks.db")

def _log_execution_sync(tool_name: str, action: str, params_str: str, status: str):
    """Internal sync function that runs in background thread."""
    import sqlite3
    try:
        conn = sqlite3.connect(LOGS_DB_PATH)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")

        # Ensure table exists with correct schema
        conn.execute("""
            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                action TEXT NOT NULL,
                params_json TEXT,
                status TEXT NOT NULL,
                source TEXT NOT NULL,
                output_json TEXT,
                duration_ms INTEGER,
                session_id TEXT
            )
        """)

        conn.execute(
            """INSERT INTO system_logs (timestamp, tool_name, action, params_json, status, source)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                datetime.now().isoformat(),
                tool_name,
                action,
                params_str,
                status,
                "claude_ai"
            )
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logging.warning(f"Failed to log execution: {e}")

def log_execution(tool_name: str, action: str, params: dict, status: str):
    """Log execution to logs.db system_logs table (SQLite) - async via background thread."""
    try:
        # Serialize params now (in main thread) to avoid race conditions
        params_str = json.dumps(params)

        # Fire the SQLite write in a background thread so it never blocks request completion
        thread = threading.Thread(
            target=_log_execution_sync,
            args=(tool_name, action, params_str, status),
            daemon=True
        )
        thread.start()
    except Exception as e:
        logging.warning(f"Failed to start log execution thread: {e}")



app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)




# File watcher for SSE dashboard updates
file_change_event = asyncio.Event()
image_change_event = asyncio.Event()  # SSE for public_images
last_file_change = {"timestamp": time.time(), "file": None}
last_image_change = {"timestamp": time.time(), "filename": None}
main_event_loop = None  # Will be set when app starts

class TaskFileHandler(FileSystemEventHandler):
    def on_modified(self, event):
        # Watch tasks.db for real-time task state changes (SSE push)
        if event.src_path.endswith('tasks.db'):
            last_file_change["timestamp"] = time.time()
            last_file_change["type"] = "task_update"
            last_file_change["file"] = "tasks.db"
            # Use the stored main event loop reference
            if main_event_loop and main_event_loop.is_running():
                main_event_loop.call_soon_threadsafe(file_change_event.set)

class ImageFileHandler(FileSystemEventHandler):
    """Watches public_images folder for new image files (SSE push)"""
    def on_created(self, event):
        # Only trigger for image files, not temp files
        if event.is_directory:
            return
        filename = os.path.basename(event.src_path)
        if filename.endswith(('.png', '.jpg', '.jpeg', '.webp')) and not filename.startswith('.'):
            last_image_change["timestamp"] = time.time()
            last_image_change["filename"] = filename
            if main_event_loop and main_event_loop.is_running():
                main_event_loop.call_soon_threadsafe(image_change_event.set)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# File watcher instances
file_observer = None
image_observer = None

def start_file_watcher():
    global file_observer, image_observer
    # Task DB watcher
    event_handler = TaskFileHandler()
    file_observer = Observer()
    data_path = os.path.join(BASE_DIR, "data")
    file_observer.schedule(event_handler, data_path, recursive=False)
    file_observer.start()
    logging.info("📁 File watcher started for task queue changes")

    # Public images watcher for SSE push
    image_handler = ImageFileHandler()
    image_observer = Observer()
    images_path = os.path.join(BASE_DIR, "semantic_memory", "public_images")
    if os.path.exists(images_path):
        image_observer.schedule(image_handler, images_path, recursive=False)
        image_observer.start()
        logging.info("🖼️ Image watcher started for public_images SSE")

def stop_file_watcher():
    global file_observer, image_observer
    if file_observer:
        file_observer.stop()
        file_observer.join()
        logging.info("📁 File watcher stopped")
    if image_observer:
        image_observer.stop()
        image_observer.join()
        logging.info("🖼️ Image watcher stopped")

# 🔧 Engine Management
engine_processes = []
ENGINE_REGISTRY_PATH = os.path.join(BASE_DIR, "data/engine_registry.json")

def kill_existing_engines():
    """Kill any existing engine processes before starting fresh ones"""
    import subprocess as sp
    try:
        result = sp.run(['pgrep', '-f', 'run_engine'], capture_output=True, text=True)
        if result.stdout.strip():
            pids = result.stdout.strip().split('\n')
            for pid in pids:
                try:
                    os.kill(int(pid), 9)
                    logging.info(f"🔪 Killed stale engine PID {pid}")
                except:
                    pass
    except:
        pass

def start_engines():
    """Start all engines as subprocesses when server starts"""
    global engine_processes

    # Kill any existing engines first to prevent duplicates
    kill_existing_engines()

    if not os.path.exists(ENGINE_REGISTRY_PATH):
        logging.warning(f"⚠️  Engine registry not found at {ENGINE_REGISTRY_PATH}")
        return

    # Ensure logs directory exists
    logs_dir = os.path.join(BASE_DIR, "logs")
    os.makedirs(logs_dir, exist_ok=True)

    try:
        with open(ENGINE_REGISTRY_PATH, 'r') as f:
            registry = json.load(f)

        engines = registry.get('engines', [])

        for engine_file in engines:
            engine_path = os.path.join(BASE_DIR, "tools", engine_file)
            
            if not os.path.exists(engine_path):
                logging.warning(f"⚠️  Engine not found: {engine_path}")
                continue
            
            try:
                log_path = os.path.join(logs_dir, f"{engine_file}.log")
                log_file = open(log_path, 'a')
                
                # Write startup marker
                log_file.write(f"\n{'='*60}\n")
                log_file.write(f"Started: {datetime.now().isoformat()}\n")
                log_file.write(f"{'='*60}\n\n")
                log_file.flush()
                
                proc = subprocess.Popen(
                    [sys.executable, engine_path, "run_engine"],
                    cwd=BASE_DIR,
                    stdout=log_file,
                    stderr=log_file,
                    start_new_session=False
                )
                engine_processes.append({
                    'name': engine_file,
                    'process': proc,
                    'pid': proc.pid,
                    'log_file': log_file
                })
                logging.info(f"✅ Started {engine_file} (PID: {proc.pid})")
            except Exception as e:
                logging.error(f"❌ Failed to start {engine_file}: {e}")
        
        logging.info(f"🚀 Started {len(engine_processes)} engine(s)")
        
    except Exception as e:
        logging.error(f"❌ Failed to load engine registry: {e}")


def stop_engines():
    """Stop all engines when server shuts down"""
    global engine_processes
    
    if not engine_processes:
        return
    
    logging.info("🛑 Stopping engines...")
    
    for engine in engine_processes:
        try:
            proc = engine['process']
            name = engine['name']
            
            # Graceful shutdown
            proc.terminate()
            
            try:
                proc.wait(timeout=5)
                logging.info(f"✅ Stopped {name}")
            except subprocess.TimeoutExpired:
                # Force kill if not responding
                proc.kill()
                proc.wait()
                logging.warning(f"⚠️  Force killed {name}")
                
        except Exception as e:
            logging.error(f"❌ Error stopping {engine['name']}: {e}")
    
    engine_processes = []
    logging.info("✅ All engines stopped")


def handle_shutdown(signum, frame):
    """Handle shutdown signals"""
    logging.info(f"Received signal {signum}, shutting down...")
    stop_file_watcher()
    stop_engines()
    sys.exit(0)


# Register shutdown handlers
signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)
atexit.register(stop_engines)
atexit.register(stop_file_watcher)


async def engine_watchdog():
    """Background task to restart dead engines every 60 seconds"""
    while True:
        await asyncio.sleep(60)
        for engine in engine_processes:
            proc = engine['process']
            if proc.poll() is not None:  # Process is dead
                name = engine['name']
                logging.warning(f"🔄 Engine {name} died (exit={proc.returncode}), restarting...")
                try:
                    # Close old log file handle before opening new one
                    old_log = engine.get("log_file")
                    if old_log:
                        try:
                            old_log.close()
                        except Exception:
                            pass

                    engine_path = os.path.join(BASE_DIR, "tools", name)
                    log_path = os.path.join(BASE_DIR, "logs", f"{name}.log")
                    log_file = open(log_path, 'a')
                    log_file.write(f"\n{'='*60}\n")
                    log_file.write(f"Restarted by watchdog: {datetime.now().isoformat()}\n")
                    log_file.write(f"{'='*60}\n\n")
                    log_file.flush()
                    new_proc = subprocess.Popen(
                        [sys.executable, engine_path, "run_engine"],
                        cwd=BASE_DIR,
                        stdout=log_file,
                        stderr=log_file,
                        start_new_session=False
                    )
                    engine['process'] = new_proc
                    engine['pid'] = new_proc.pid
                    engine['log_file'] = log_file
                    logging.info(f"✅ Restarted {name} (PID: {new_proc.pid})")
                except Exception as e:
                    logging.error(f"❌ Failed to restart {name}: {e}")


@app.on_event("startup")
async def startup_event():
    """Start engines when FastAPI server starts"""
    global main_event_loop
    main_event_loop = asyncio.get_running_loop()  # Capture event loop for SSE
    logging.info("🚀 Starting OrchestrateOS...")
    start_engines()
    start_file_watcher()
    asyncio.create_task(engine_watchdog())  # Start watchdog
    asyncio.create_task(health_stats_logger())  # Start health stats logger


@app.on_event("shutdown")
async def shutdown_event():
    """Stop engines when FastAPI server shuts down"""
    stop_file_watcher()
    stop_engines()


# 📡 SSE endpoint for dashboard real-time updates
@app.get("/api/task-updates")
async def task_updates():
    """Server-Sent Events for task state changes from tasks.db"""
    import sqlite3

    def get_current_tasks():
        """Fetch current active tasks and recent results for SSE payload"""
        try:
            db_path = os.path.join(BASE_DIR, "data", "tasks.db")
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Get active tasks
            cursor.execute("""
                SELECT task_id, description, status, created_at, started_at
                FROM tasks
                WHERE status IN ('pending', 'in_progress')
                ORDER BY created_at DESC
            """)
            active = [dict(row) for row in cursor.fetchall()]

            # Get recent completed (last 10)
            cursor.execute("""
                SELECT task_id, description, status, completed_at, actions_taken, source
                FROM task_results
                ORDER BY completed_at DESC
                LIMIT 10
            """)
            recent = [dict(row) for row in cursor.fetchall()]

            conn.close()
            return {"active": active, "recent": recent}
        except Exception as e:
            return {"error": str(e), "active": [], "recent": []}

    async def event_generator():
        while True:
            try:
                # Wait for file change event or timeout after 30s
                try:
                    await asyncio.wait_for(file_change_event.wait(), timeout=30.0)
                    file_change_event.clear()
                    # On change, send full task state
                    tasks = get_current_tasks()
                    payload = {
                        "type": "task_update",
                        "timestamp": time.time(),
                        "tasks": tasks
                    }
                    yield f"data: {json.dumps(payload)}\n\n"
                except asyncio.TimeoutError:
                    # Send heartbeat
                    yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': time.time()})}\n\n"
            except asyncio.CancelledError:
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*"
        }
    )


# 🖼️ SSE endpoint for image generation updates
@app.get("/api/image-updates")
async def image_updates():
    """Server-Sent Events for public_images folder changes - replaces polling"""

    async def event_generator():
        while True:
            try:
                # Wait for image file created event or timeout after 30s
                try:
                    await asyncio.wait_for(image_change_event.wait(), timeout=30.0)
                    image_change_event.clear()
                    # On new image, push the filename
                    payload = {
                        "type": "image_ready",
                        "filename": last_image_change.get("filename"),
                        "timestamp": last_image_change.get("timestamp")
                    }
                    yield f"data: {json.dumps(payload)}\n\n"
                except asyncio.TimeoutError:
                    # Send heartbeat
                    yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': time.time()})}\n\n"
            except asyncio.CancelledError:
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*"
        }
    )


# 🗑️ Clear Queue endpoint for dashboard
@app.post("/api/clear-queue")
async def clear_queue():
    """Clear all tasks from all task queues (3-queue system)"""
    try:
        cleared_count = 0
        # Clear all 3 queue files
        for i in range(1, 4):
            queue_path = os.path.join(BASE_DIR, f"data/claude_task_q{i}.json")
            if os.path.exists(queue_path):
                with open(queue_path, 'r') as f:
                    try:
                        data = json.load(f)
                        cleared_count += len(data.get("tasks", {}))
                    except:
                        pass
                with open(queue_path, 'w') as f:
                    json.dump({"tasks": {}}, f)
        
        # Also clear the old single queue file if it exists
        old_queue = os.path.join(BASE_DIR, "data/claude_task_queue.json")
        if os.path.exists(old_queue):
            with open(old_queue, 'w') as f:
                json.dump({"tasks": {}}, f)
        
        # Remove lockfile if present
        lockfile = os.path.join(BASE_DIR, "data/execute_queue.lock")
        if os.path.exists(lockfile):
            os.remove(lockfile)
        
        return {"status": "success", "message": f"Cleared {cleared_count} tasks from all queues"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 📸 Screenshot save endpoint for Dev HUD
@app.post("/api/screenshot")
async def save_screenshot(request: Request):
    """Save base64 screenshot from Dev HUD to semantic_memory/images/"""
    import base64
    import uuid
    from datetime import datetime

    try:
        data = await request.json()
        image_data = data.get("image_data", "")

        if not image_data:
            return {"status": "error", "message": "No image data provided"}

        # Remove data URL prefix if present
        if "," in image_data:
            image_data = image_data.split(",", 1)[1]

        # Decode base64
        image_bytes = base64.b64decode(image_data)

        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"devhud_{timestamp}_{uuid.uuid4().hex[:8]}.png"

        # Save to semantic_memory/images
        images_dir = os.path.join(BASE_DIR, "semantic_memory/images")
        os.makedirs(images_dir, exist_ok=True)
        filepath = os.path.join(images_dir, filename)

        with open(filepath, "wb") as f:
            f.write(image_bytes)

        return {"status": "success", "path": filepath, "filename": filename}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# 📤 File Upload endpoint - accepts multipart form data, kills base64 nonsense
from fastapi import UploadFile, File, Form

@app.post("/upload_file")
async def upload_file(
    file: UploadFile = File(...),
    destination: str = Form(default=""),
    subfolder: str = Form(default=""),
    context: str = Form(default="")
):
    """Upload a file via multipart form data.

    - destination: full path like 'semantic_memory/images/foo.png'
    - subfolder: just the directory like 'semantic_memory/images' (filename from upload)
    - context: optional description/context for the upload
    - If neither provided, saves to data/uploads/
    """
    try:
        if destination:
            # Full path provided
            save_path = os.path.join(BASE_DIR, destination)
        elif subfolder:
            # Directory + original filename
            save_path = os.path.join(BASE_DIR, subfolder, file.filename)
        else:
            # Default to data/uploads/
            uploads_dir = os.path.join(BASE_DIR, "data", "uploads")
            os.makedirs(uploads_dir, exist_ok=True)
            save_path = os.path.join(uploads_dir, file.filename)

        # Ensure parent directory exists
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        # Write file
        contents = await file.read()
        with open(save_path, "wb") as f:
            f.write(contents)

        # Hook: Add to builds_index if file is in semantic_memory and is HTML
        if "semantic_memory" in save_path and file.filename.endswith(".html"):
            # Extract relative URL from save_path
            rel_path = save_path.split("semantic_memory")[-1]
            url = f"/semantic_memory{rel_path}"
            add_to_builds_index(file.filename, url)

        # Hook: Track uploads to semantic_memory/uploads/ in maverick_uploads.json
        if "semantic_memory/uploads" in save_path:
            import json
            from datetime import datetime
            import hashlib
            uploads_json_path = os.path.join(BASE_DIR, "data", "maverick_uploads.json")

            # Load existing uploads (json_manager format: {"entries": {...}})
            if os.path.exists(uploads_json_path):
                with open(uploads_json_path, 'r') as uf:
                    uploads_data = json.load(uf)
            else:
                uploads_data = {"entries": {}}

            # Ensure entries key exists
            if "entries" not in uploads_data:
                uploads_data = {"entries": {}}

            # Generate unique key for this upload
            timestamp = datetime.now().isoformat()
            entry_key = hashlib.md5(f"{file.filename}_{timestamp}".encode()).hexdigest()[:8]

            # Add new upload entry
            uploads_data["entries"][entry_key] = {
                "name": file.filename,
                "context": context,
                "timestamp": timestamp,
                "size": len(contents),
                "path": save_path
            }

            # Save updated uploads
            with open(uploads_json_path, 'w') as uf:
                json.dump(uploads_data, uf, indent=2)

        return {
            "status": "success",
            "filename": file.filename,
            "path": save_path,
            "size": len(contents),
            "content_type": file.content_type
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# 📋 Get Maverick Uploads - returns list of uploaded files from maverick_uploads.json
@app.get("/api/maverick_uploads")
def get_maverick_uploads():
    """Get list of files uploaded via Maverick Hub"""
    import json
    uploads_json_path = os.path.join(BASE_DIR, "data", "maverick_uploads.json")

    if os.path.exists(uploads_json_path):
        with open(uploads_json_path, 'r') as uf:
            data = json.load(uf)
            # Handle json_manager format (object with entries) or plain array
            if isinstance(data, dict) and 'entries' in data:
                # Convert entries object to array sorted by timestamp (newest first)
                entries = list(data['entries'].values())
                entries.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
                return entries
            elif isinstance(data, list):
                return data
            return []
    return []


# 🩺 Engine Health Check
@app.get("/health/engines")
def engine_health():
    """Check status of all engines"""
    status = []

    for engine in engine_processes:
        proc = engine['process']
        name = engine['name']
        pid = engine['pid']

        # Check if still running
        if proc.poll() is None:
            status.append({
                'name': name,
                'pid': pid,
                'status': 'running'
            })
        else:
            status.append({
                'name': name,
                'pid': pid,
                'status': 'dead',
                'exit_code': proc.returncode
            })

    running_count = sum(1 for e in status if e['status'] == 'running')

    return {
        'total_engines': len(status),
        'running': running_count,
        'engines': status,
        'health': 'healthy' if running_count == len(status) else 'degraded'
    }


# Server start time for uptime calculation
_server_start_time = time.time()

def _get_health_stats():
    """Gather health stats: PID, file handles, memory, uptime, restart counts"""
    import os as _os

    stats = {
        "timestamp": datetime.now().isoformat(),
        "uvicorn_pid": _os.getpid(),
        "open_file_handles": 0,
        "rss_memory_mb": 0.0,
        "uptime_hours": 0.0,
        "engine_restart_counts": {}
    }

    # File handle count via lsof
    try:
        result = subprocess.run(
            ["lsof", "-p", str(_os.getpid())],
            capture_output=True, text=True, timeout=5
        )
        # Count lines minus header
        lines = result.stdout.strip().split('\n')
        stats["open_file_handles"] = max(0, len(lines) - 1)
    except Exception as e:
        logging.warning(f"Failed to get file handle count: {e}")

    # RSS memory in MB via ps
    try:
        result = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(_os.getpid())],
            capture_output=True, text=True, timeout=5
        )
        rss_kb = int(result.stdout.strip())
        stats["rss_memory_mb"] = round(rss_kb / 1024, 2)
    except Exception as e:
        logging.warning(f"Failed to get RSS memory: {e}")

    # Uptime in hours
    stats["uptime_hours"] = round((time.time() - _server_start_time) / 3600, 2)

    # Engine restart counts from nohup_logs
    nohup_logs_dir = _os.path.join(BASE_DIR, "logs")
    try:
        for log_file in _os.listdir(nohup_logs_dir):
            if log_file.endswith(".py.log"):
                engine_name = log_file.replace(".log", "")
                log_path = _os.path.join(nohup_logs_dir, log_file)
                try:
                    with open(log_path, 'r') as f:
                        content = f.read()
                    # Count "Restarted by watchdog" occurrences
                    restart_count = content.count("Restarted by watchdog")
                    stats["engine_restart_counts"][engine_name] = restart_count
                except Exception:
                    pass
    except Exception as e:
        logging.warning(f"Failed to read engine logs: {e}")

    return stats


@app.get("/health/stats")
def health_stats():
    """Health check endpoint: PID, file handles, memory, uptime, restart counts"""
    return _get_health_stats()


async def health_stats_logger():
    """Background task: log health stats to logs/health_stats.log every 60 minutes"""
    logs_dir = os.path.join(BASE_DIR, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    log_path = os.path.join(logs_dir, "health_stats.log")

    while True:
        await asyncio.sleep(3600)  # 60 minutes
        try:
            stats = _get_health_stats()
            log_line = json.dumps(stats) + "\n"
            with open(log_path, 'a') as f:
                f.write(log_line)
            logging.info(f"Health stats logged: FH={stats['open_file_handles']}, RSS={stats['rss_memory_mb']}MB")
        except Exception as e:
            logging.error(f"Failed to log health stats: {e}")


# 🚦 Rate limiting state (in-memory)
rate_limit_state = defaultdict(list)
RATE_LIMITS = {
    "/execute_task": {"requests": 60, "window_seconds": 60},
    "/get_supported_actions": {"requests": 10, "window_seconds": 60}
}

# 🔒 System paths
SYSTEM_REGISTRY = os.path.join(BASE_DIR, "system_settings.ndjson")
WORKING_MEMORY_PATH = os.path.join(BASE_DIR, "data/working_memory.json")
EXEC_HUB_PATH = os.path.join(BASE_DIR, "execution_hub.py")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# 📦 Static mounts
app.mount(
    "/semantic_memory",
    StaticFiles(directory=os.path.join(BASE_DIR, "semantic_memory")),
    name="semantic_memory"
)

app.mount(
    "/landing_page_template_thumbnails",
    StaticFiles(directory=os.path.join(BASE_DIR, "landing_page_template_thumbnails")),
    name="landing_page_template_thumbnails"
)

app.mount(
    "/data",
    StaticFiles(directory=os.path.join(BASE_DIR, "data")),
    name="data"
)

@app.get("/data-nocache/{filename:path}")
async def get_data_nocache(filename: str):
    """Serve data files with no-cache headers"""
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

app.mount(
    "/dashboard",
    StaticFiles(directory=os.path.join(BASE_DIR, "semantic_memory/execution_dashboard"), html=True),
    name="dashboard"
)

app.mount("/tools", StaticFiles(directory=os.path.join(BASE_DIR, "tools")), name="tools")

# 🚦 Rate limiting middleware
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


# 🛠 Run a tool action via subprocess (async - does not block event loop)
async def run_script(tool_name, action, params):
    command = [
        sys.executable, EXEC_HUB_PATH, "execute_task", "--params", json.dumps({
            "tool_name": tool_name,
            "action": action,
            "params": params
        })
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=90)
        return json.loads(stdout.decode().strip())
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return {"error": "Execution timed out", "details": "Task exceeded 90s limit"}
    except Exception as e:
        return {"error": "Execution failed", "details": str(e)}


# 🎯 Execute a tool via HTTP POST
@app.post("/execute_task")
async def execute_task(request: Request):
    client_id = request.client.host if request.client else "unknown"
    if not check_rate_limit("/execute_task", client_id):
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "message": "Too many requests. Limit: 60 req/min per client.",
                "retry_after": 60
            }
        )

    try:
        request_data = await request.json()
        tool_name = request_data.get("tool_name")
        action_name = request_data.get("action")
        params = request_data.get("params", {})

        if not tool_name or not action_name:
            raise HTTPException(status_code=400, detail="Missing tool_name or action.")

        if tool_name == "system_control" and action_name == "load_orchestrate_os":
            proc = await asyncio.create_subprocess_exec(
                sys.executable, EXEC_HUB_PATH, "load_orchestrate_os",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
            log_execution(tool_name, action_name, params, "success")
            return json.loads(stdout.decode().strip())

        if tool_name == "json_manager" and action_name == "orchestrate_write":
            log_execution(tool_name, action_name, params, "success")
            return orchestrate_write(**params)

        if tool_name == "docs" and action_name == "search_docs":
            log_execution(tool_name, action_name, params, "success")
            return _import_doc_editor().search_docs(**params)

        params = validate_action(tool_name, action_name, params)
        result = await run_script(tool_name, action_name, params)

        if "error" in result:
            # execution_hub already logs this - no duplicate logging
            raise HTTPException(status_code=500, detail=result)

        # execution_hub already logs this - no duplicate logging
        return result

    except ContractViolation as e:
        # execution_hub already logs this - no duplicate logging
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        # execution_hub already logs this - no duplicate logging
        return JSONResponse(status_code=500, content={
            "error": "Execution failed",
            "details": str(e)
        })


@app.get("/task_status")
async def task_status():
    """Return active tasks and recent results in a single response - direct DB query, no subprocess."""
    import sqlite3
    try:
        conn = sqlite3.connect(TASKS_DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get active tasks (queued or in_progress)
        cursor.execute("""
            SELECT task_id, description, status, priority, agent_id, batch_id, context,
                   card_title, card_stat, pid, created_at, started_at, processing_started_at, updated_at
            FROM tasks
            WHERE status IN ('queued', 'in_progress')
            ORDER BY
                CASE status WHEN 'in_progress' THEN 0 ELSE 1 END,
                created_at DESC
        """)
        active_tasks = [dict(row) for row in cursor.fetchall()]

        # Get recent results (last 20 completed)
        cursor.execute("""
            SELECT task_id, status, description, actions_taken, output, output_summary, errors,
                   execution_time_seconds, card_title, card_stat, test_results, tokens, token_cost,
                   batch_id, batch_position, started_at, processing_started_at, completed_at, source
            FROM task_results
            ORDER BY completed_at DESC
            LIMIT 20
        """)
        recent_results = [dict(row) for row in cursor.fetchall()]

        conn.close()

        return {
            "status": "success",
            "active_tasks": active_tasks,
            "recent_results": recent_results
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/get_supported_actions")
def get_supported_actions(request: Request, offset: int = 0, limit: int = 999):
    """Return all actions (default limit=999 returns full schema in one call)"""
    client_id = request.client.host if request.client else "unknown"
    if not check_rate_limit("/get_supported_actions", client_id):
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "message": "Too many requests. Limit: 10 req/min per client.",
                "retry_after": 60
            }
        )

    try:
        with open(SYSTEM_REGISTRY, "r") as f:
            entries = [json.loads(line.strip()) for line in f if line.strip()]
        
        lean_actions = []
        for entry in entries:
            if entry.get("action") == "__tool__":
                continue
            
            lean_entry = {
                "tool": entry.get("tool"),
                "action": entry.get("action"),
                "params": entry.get("params", []),
                "description": entry.get("description", "")[:100]
            }
            lean_actions.append(lean_entry)
        
        total = len(lean_actions)
        paginated = lean_actions[offset:offset+limit]
        
        return {
            "status": "success",
            "supported_actions": paginated,
            "pagination": {
                "total": total,
                "offset": offset,
                "limit": limit,
                "returned": len(paginated),
                "has_more": (offset + limit) < total,
                "next_offset": offset + limit if (offset + limit) < total else None
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))





@app.get("/")
def root():
    return {"status": "Jarvis core is online."}


@app.get("/api/recent_builds")
def get_recent_builds():
    """Return the builds index JSON for Command Center"""
    try:
        if os.path.exists(BUILDS_INDEX_PATH):
            with open(BUILDS_INDEX_PATH, 'r') as f:
                index = json.load(f)
            return {"status": "success", "builds": index}
        return {"status": "success", "builds": []}
    except Exception as e:
        return {"status": "error", "message": str(e), "builds": []}




@app.get("/unsubscribe")
async def unsubscribe(email: str):
    """Handle unsubscribe requests from email links"""
    try:
        result = await run_script("newsletter_tool", "unsubscribe_contact", {"email": email})
        
        if result.get("status") == "success":
            html = """
<!DOCTYPE html>
<html>
<head>
    <title>Unsubscribed</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; text-align: center; }
        h1 { font-size: 28px; margin-bottom: 20px; }
        p { color: #666; margin-bottom: 30px; }
    </style>
</head>
<body>
    <h1>✓ You've Been Unsubscribed</h1>
    <p>You won't receive any more emails from us.</p>
</body>
</html>
"""
            return HTMLResponse(content=html)
        else:
            raise HTTPException(status_code=400, detail=result.get("message", "Failed to unsubscribe"))
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# === Beta Signup ===
class BetaSignup(BaseModel):
    full_name: str
    email: str
    use_case: str
    excited_tools: str  # Comma-separated string from form
    ai_experience: str
    why_early_access: str
    gpt_plus: str = ""
    claude_sub: str = ""
    os: str = ""

BETA_FILE = f"{BASE_DIR}/data/orchestrate_private_beta.json"

@app.get("/beta/signup", response_class=HTMLResponse)
async def beta_signup_page():
    """Serve the beta signup form"""
    html_path = os.path.join(BASE_DIR, "semantic_memory/html/beta-signup.html")
    with open(html_path, 'r') as f:
        return HTMLResponse(content=f.read())

@app.post("/beta/signup")
async def beta_signup_submit(signup: BetaSignup):
    """Handle beta signup form submission.

    Saves entry to orchestrate_private_beta.json. Lead scoring and triage
    is handled separately by automation rule that triggers Claude Code.
    """
    try:
        # Check for duplicate
        if os.path.exists(BETA_FILE):
            with open(BETA_FILE, 'r') as f:
                existing = json.load(f)
            if signup.email in existing.get("entries", {}):
                return {"status": "error", "message": "This email is already registered for beta access."}
        else:
            existing = {"entries": {}, "created_at": datetime.now().isoformat()}

        # Parse comma-separated tools from form
        tools = [t.strip() for t in signup.excited_tools.split(",") if t.strip()]

        new_entry = {
            "name": signup.full_name,
            "email": signup.email,
            "os": signup.os if hasattr(signup, 'os') and signup.os else "Unknown",
            "tools": tools,
            "gpt_user": signup.gpt_plus.lower() == "yes" if signup.gpt_plus else False,
            "claude_user": signup.claude_sub.lower() == "yes" if signup.claude_sub else False,
            "feedback_opt_in": True,
            "use_case": signup.use_case,
            "why_early_access": signup.why_early_access,
            "ai_experience": signup.ai_experience,
            "signup_timestamp": datetime.now().isoformat()
        }

        # Add entry to beta file
        existing["entries"][signup.email] = new_entry

        with open(BETA_FILE, 'w') as f:
            json.dump(existing, f, indent=4)

        logging.info(f"New beta signup: {signup.email}")
        return {"status": "success", "message": "Application received!"}

    except Exception as e:
        logging.error(f"Beta signup error: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/beta/thanks", response_class=HTMLResponse)
async def beta_thanks_page():
    """Serve the thank you page"""
    html_path = os.path.join(BASE_DIR, "semantic_memory/html/beta-thanks.html")
    with open(html_path, 'r') as f:
        return HTMLResponse(content=f.read())




async def handle_new_email_webhook(data):
    """Handle incoming email from Nylas webhook - update inbox_summary.json in real-time."""
    import sys
    sys.path.insert(0, os.path.join(BASE_DIR, "tools"))
    from nylas_inboxv2 import clean_email_content, auto_tag_email, archive_email

    try:
        msg_obj = data.get("data", {}).get("object", {})

        message_id = msg_obj.get("id", "")
        subject = msg_obj.get("subject", "")
        sender = msg_obj.get("from", [{}])[0].get("email", "")
        body_raw = msg_obj.get("body", "") or msg_obj.get("snippet", "")

        if not message_id:
            return {"status": "success", "message": "No message_id in payload"}

        # Clean body and get intent tag
        body = clean_email_content(body_raw)
        tags = auto_tag_email(subject, sender, body)
        intent = tags[0] if tags else "ARCHIVE"

        logging.info(f"Nylas webhook: {sender} - {subject[:50]} -> {intent}")

        # If ARCHIVE, archive immediately and done
        if intent == "ARCHIVE":
            archive_email({"message_id": message_id})
            return {"status": "success", "intent": "ARCHIVE", "action": "archived"}

        # Add to inbox_summary.json
        summary_file = os.path.join(BASE_DIR, "data/inbox_summary.json")

        # Initialize if doesn't exist
        if not os.path.exists(summary_file):
            summary_data = {"signal": [], "action": [], "meta": {"total_processed": 0, "signal_count": 0, "action_count": 0, "auto_archived_count": 0}}
        else:
            with open(summary_file, "r") as f:
                summary_data = json.load(f)

        # Build email entry
        email_entry = {
            "message_id": message_id,
            "sender": sender,
            "subject": subject,
            "body": body[:500] if len(body) > 500 else body,
            "date": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        # Add to appropriate list
        if intent == "SIGNAL":
            summary_data["signal"].append(email_entry)
            summary_data["meta"]["signal_count"] = len(summary_data["signal"])
        elif intent == "ACTION":
            summary_data["action"].append(email_entry)
            summary_data["meta"]["action_count"] = len(summary_data["action"])

        summary_data["meta"]["total_processed"] = summary_data["meta"].get("total_processed", 0) + 1

        with open(summary_file, "w") as f:
            json.dump(summary_data, f, indent=2)

        return {"status": "success", "intent": intent, "message_id": message_id}

    except Exception as e:
        logging.error(f"handle_new_email_webhook error: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/webhook/nylas")
async def nylas_webhook_verify(request: Request):
    """Handle Nylas webhook verification challenge"""
    from fastapi.responses import PlainTextResponse
    challenge = request.query_params.get("challenge")
    if challenge:
        return PlainTextResponse(content=challenge)  # Return exact challenge value as plain text
    return {"status": "ok"}


@app.post("/webhook/nylas")
async def nylas_webhook(request: Request):
    """Handle Nylas webhook events:
    - message.created: Process new incoming emails for inbox dashboard
    - message.opened, message.link_clicked, thread.replied: Investor tracking
    """
    import hmac
    import hashlib
    
    # Validate webhook signature
    try:
        with open(os.path.join(BASE_DIR, "tools/credentials.json"), "r") as f:
            creds = json.load(f)
        webhook_secret = creds.get("nylas_webhook_secret", "")
        
        if webhook_secret:
            signature = request.headers.get("X-Nylas-Signature", "")
            body = await request.body()
            expected_sig = hmac.new(
                webhook_secret.encode(),
                body,
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(signature, expected_sig):
                logging.warning(f"Nylas webhook: Invalid signature")
                return {"status": "error", "message": "Invalid signature"}
            
            # Re-parse body as JSON after validation
            data = json.loads(body)
        else:
            data = await request.json()
    except Exception as e:
        logging.error(f"Nylas webhook signature validation error: {e}")
        data = await request.json()
    
    try:
        event_type = data.get("type", "")

        # Handle message.created - new email arrived, process for inbox dashboard
        if event_type in ["message.created", "message.created.truncated"]:
            return await handle_new_email_webhook(data)

        # Handle investor email tracking (existing logic)
        events = data if isinstance(data, list) else [data]

        crm_file = os.path.join(BASE_DIR, "data/orchestrate_fundraise_crm.json")
        if not os.path.exists(crm_file):
            logging.warning("Nylas webhook: CRM file not found")
            return {"status": "success"}  # Return success to avoid retries

        with open(crm_file, "r") as f:
            crm_data = json.load(f)

        updated = False

        for event in events:
            event_type = event.get("type")  # message.opened, message.link_clicked, thread.replied
            # Try both possible label paths (Nylas v3 uses data.object.label)
            label = event.get("data", {}).get("object", {}).get("label", "") or event.get("data", {}).get("label", "")

            # Label format: investor_{investor_key}_{email_type}
            # email_type is always last part (initial or followup1)
            if not label.startswith("investor_"):
                continue

            # Split from the right to handle investor_keys with underscores
            # e.g. "investor_john_smith_initial" -> key="john_smith", type="initial"
            without_prefix = label[9:]  # Remove "investor_"
            last_underscore = without_prefix.rfind("_")
            if last_underscore == -1:
                continue

            investor_key = without_prefix[:last_underscore]
            email_type = without_prefix[last_underscore + 1:]  # initial or followup1

            if investor_key not in crm_data:
                continue

            now = datetime.now().isoformat()

            if event_type == "message.opened":
                crm_data[investor_key][f"{email_type}_opened"] = True
                crm_data[investor_key][f"{email_type}_opened_at"] = now
                updated = True
            elif event_type == "message.link_clicked":
                crm_data[investor_key][f"{email_type}_clicked"] = True
                crm_data[investor_key][f"{email_type}_clicked_at"] = now
                updated = True
            elif event_type == "thread.replied":
                crm_data[investor_key][f"{email_type}_replied"] = True
                crm_data[investor_key][f"{email_type}_replied_at"] = now
                updated = True

        if updated:
            with open(crm_file, "w") as f:
                json.dump(crm_data, f, indent=2)

        return {"status": "success"}

    except Exception as e:
        logging.error(f"Nylas webhook error: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/resend_webhook")
async def resend_webhook(request: Request):
    """Handle Resend email events for newsletter tracking."""
    import sqlite3
    try:
        data = await request.json()
        event_type = data.get("type", "")
        event_data = data.get("data", {})
        # Use broadcast_id if present (for broadcast emails), else fall back to email_id (transactional)
        tracking_id = event_data.get("broadcast_id") or event_data.get("email_id", "")

        if not tracking_id:
            return {"status": "ok"}

        db_path = os.path.join(BASE_DIR, "data/marketing_hub.db")
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        if event_type == "email.delivered":
            cur.execute("INSERT OR IGNORE INTO newsletter_events (broadcast_id, total_sent) VALUES (?, 0)", (tracking_id,))
            cur.execute("UPDATE newsletter_events SET total_sent = total_sent + 1 WHERE broadcast_id = ?", (tracking_id,))
        elif event_type == "email.opened":
            cur.execute("UPDATE newsletter_events SET opens = COALESCE(opens, 0) + 1 WHERE broadcast_id = ?", (tracking_id,))
        elif event_type == "email.clicked":
            cur.execute("UPDATE newsletter_events SET clicks = COALESCE(clicks, 0) + 1 WHERE broadcast_id = ?", (tracking_id,))
        elif event_type == "email.bounced":
            logging.warning(f"Resend bounce: {event_data.get('to', 'unknown')}")

        # Recalculate open_rate and ctr
        cur.execute("""
            UPDATE newsletter_events
            SET open_rate = CASE WHEN total_sent > 0 THEN ROUND(100.0 * opens / total_sent, 2) ELSE 0 END,
                ctr = CASE WHEN total_sent > 0 THEN ROUND(100.0 * clicks / total_sent, 2) ELSE 0 END
            WHERE broadcast_id = ?
        """, (tracking_id,))

        conn.commit()
        conn.close()
        return {"status": "ok"}
    except Exception as e:
        logging.error(f"Resend webhook error: {e}")
        return {"status": "ok"}


# ============================================================
# NATIVE DOC EDITOR ENDPOINTS (SQLite via doc_editor.py)
# ============================================================
_docs_beta_cache = {"data": None, "mtime": 0}

def _import_doc_editor():
    """Lazy import doc_editor (now SQLite-backed)"""
    import importlib
    if 'doc_editor' in sys.modules:
        return sys.modules['doc_editor']
    sys.path.insert(0, os.path.join(BASE_DIR, "tools"))
    return importlib.import_module('doc_editor')

# YouTube Dashboard Endpoints
YOUTUBE_QUEUE_FILE = Path(__file__).parent / "data" / "youtube_upload_queue.json"

@app.get("/youtube/list")
async def list_youtube_uploads():
    """List all YouTube uploads from queue"""
    try:
        if not YOUTUBE_QUEUE_FILE.exists():
            return {"status": "success", "uploads": [], "total": 0}
        with open(YOUTUBE_QUEUE_FILE, 'r') as f:
            data = json.load(f)
        uploads = data.get('uploads', [])
        return {"status": "success", "uploads": uploads, "total": len(uploads)}
    except Exception as e:
        return {"status": "error", "message": str(e)}

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

@app.get("/docs/search")
async def search_docs(q: str = "", collection: str = None, max_results: int = 15):
    """Search docs in SQLite"""
    try:
        de = _import_doc_editor()
        result = de.search_docs(query=q, collection=collection, max_results=max_results)
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/docs/save")
async def save_doc(request: Request):
    """Save/update doc via SQLite"""
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

                db = de.get_db()
                now = datetime.now().isoformat()

                if "content" in body:
                    word_count = de._count_words(content)
                    _, meta_desc = de._extract_meta_description(content)
                    db.execute(
                        "UPDATE docs SET title=?, collection=?, content=?, word_count=?, meta_description=?, updated_at=? WHERE id=?",
                        (title, collection, content, word_count, meta_desc, now, doc_id)
                    )
                else:
                    db.execute(
                        "UPDATE docs SET title=?, collection=?, updated_at=? WHERE id=?",
                        (title, collection, now, doc_id)
                    )
                db.commit()

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

@app.post("/docs/bulk-delete")
async def bulk_delete_docs(request: Request):
    """Bulk delete multiple docs from SQLite"""
    try:
        body = await request.json()
        doc_ids = body.get("doc_ids", [])
        if not doc_ids:
            return {"status": "error", "message": "doc_ids array required"}
        de = _import_doc_editor()
        return de.bulk_delete_docs(doc_ids)
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

@app.get("/docs-beta/list")
async def list_docs_beta():
    """List all beta docs - lightweight"""
    data = load_docs_beta()
    docs_list = []
    for doc_id, doc in data.get("docs", {}).items():
        docs_list.append({
            "id": doc_id,
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

@app.get("/docs-beta/get/{doc_id}")
async def get_doc_beta(doc_id: str):
    """Get single beta doc by ID"""
    data = load_docs_beta()
    doc = data.get("docs", {}).get(doc_id)
    if not doc:
        return {"status": "error", "message": "Doc not found"}
    return {"status": "success", "doc": doc}

@app.post("/docs-beta/save")
async def save_doc_beta(request: Request):
    """Save/update beta doc"""
    body = await request.json()
    doc_id = body.get("id")
    
    data = load_docs_beta()
    
    if not doc_id:
        import uuid
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
    
    existing_doc = data.get("docs", {}).get(doc_id, {})
    data["docs"][doc_id] = {
        "id": doc_id,
        "title": body.get("title", "Untitled"),
        "content": body.get("content", existing_doc.get("content", "")),
        "collection": body.get("collection", "Notes"),
        "description": body.get("description", existing_doc.get("description", "")),
        "status": body.get("status", existing_doc.get("status", "")),
        "campaign_id": body.get("campaign_id", existing_doc.get("campaign_id", "")),
        "published_url": body.get("published_url", existing_doc.get("published_url", "")),
        "created_at": existing_doc.get("created_at", datetime.now().isoformat()),
        "updated_at": datetime.now().isoformat()
    }
    
    save_docs_beta(data)
    return {"status": "success", "doc_id": doc_id}

@app.delete("/docs-beta/delete/{doc_id}")
async def delete_doc_beta(doc_id: str):
    """Delete beta doc"""
    data = load_docs_beta()
    if doc_id in data.get("docs", {}):
        del data["docs"][doc_id]
        save_docs_beta(data)
        return {"status": "success"}
    return {"status": "error", "message": "Doc not found"}

@app.get("/docs-beta/backlinks/{doc_id}")
async def get_backlinks_beta(doc_id: str):
    """Get backlinks for a beta doc"""
    data = load_docs_beta()
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

@app.post("/docs-beta/link")
async def create_doc_link_beta(request: Request):
    """Create bidirectional link between beta docs"""
    body = await request.json()
    source_doc_id = body.get("source_doc_id")
    target_doc_id = body.get("target_doc_id")
    
    if not source_doc_id or not target_doc_id:
        return {"status": "error", "message": "source_doc_id and target_doc_id required"}
    
    data = load_docs_beta()
    
    source_doc = data.get("docs", {}).get(source_doc_id)
    target_doc = data.get("docs", {}).get(target_doc_id)
    
    if not source_doc or not target_doc:
        return {"status": "error", "message": "One or both docs not found"}
    
    if "links" not in source_doc:
        source_doc["links"] = []
    if "backlinks" not in target_doc:
        target_doc["backlinks"] = []
    
    if target_doc_id not in source_doc["links"]:
        source_doc["links"].append(target_doc_id)
    if source_doc_id not in target_doc["backlinks"]:
        target_doc["backlinks"].append(source_doc_id)
    
    save_docs_beta(data)
    return {"status": "success", "message": f"Linked {source_doc_id} -> {target_doc_id}"}




# Slack Events API Webhook
@app.post("/slack/events")
async def slack_events_webhook(request: Request):
    """Handle Slack Events API webhooks for client hub messaging"""
    import hmac
    import hashlib
    from tools import client_hub_manager
    
    try:
        body = await request.body()
        body_str = body.decode('utf-8')
        data = json.loads(body_str)
        
        # Handle Slack's URL verification challenge (one-time handshake)
        if data.get('type') == 'url_verification':
            return {'challenge': data.get('challenge', '')}
        
        # Load credentials and validate signature
        with open(os.path.join(BASE_DIR, "tools/credentials.json"), "r") as f:
            creds = json.load(f)
        
        signing_secret = creds.get('slack', {}).get('signing_secret', '')
        if not signing_secret:
            logging.error("Slack webhook: No signing_secret configured")
            return {'status': 'error', 'message': 'Signing secret not configured'}
        
        # Get Slack signature headers
        timestamp = request.headers.get('X-Slack-Request-Timestamp', '')
        slack_signature = request.headers.get('X-Slack-Signature', '')
        
        # Replay protection: reject if timestamp older than 5 minutes
        import time as time_module
        if abs(time_module.time() - int(timestamp)) > 300:
            logging.warning("Slack webhook: Request timestamp too old (replay protection)")
            return {'status': 'error', 'message': 'Request timestamp too old'}
        
        # Compute expected signature
        sig_basestring = f'v0:{timestamp}:{body_str}'
        expected_sig = 'v0=' + hmac.new(
            signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(slack_signature, expected_sig):
            logging.warning("Slack webhook: Invalid signature")
            return {'status': 'error', 'message': 'Invalid signature'}
        
        # Process event_callback events
        if data.get('type') == 'event_callback':
            event = data.get('event', {})
            
            # Only process direct messages (im) and private channels (group)
            if event.get('type') != 'message' or event.get('channel_type') not in ('im', 'group'):
                return {'status': 'ignored', 'reason': 'not a direct message or private channel'}

            # Skip bot messages and edits/deletes
            if event.get('bot_id') or event.get('subtype') in ('bot_message', 'message_changed', 'message_deleted'):
                return {'status': 'ignored', 'reason': 'bot or edited message'}

            slack_user_id = event.get('user', '')
            text = event.get('text', '')
            slack_ts = event.get('ts', '')
            thread_ts = event.get('thread_ts')
            channel_id = event.get('channel', '')

            # Load user mapping early for mention resolution
            user_mapping = creds.get('slack', {}).get('user_to_client', {})

            # Resolve Slack user mention tokens to readable names
            def resolve_mentions(raw_text, user_map):
                import re
                def replace_mention(m):
                    uid = m.group(1)
                    info = user_map.get(uid)
                    if info:
                        return f"@{info['sender_name']}"
                    return f"@user"
                return re.sub(r'<@([A-Z0-9]+)>', replace_mention, raw_text)

            text = resolve_mentions(text, user_mapping)

            # Route based on channel type
            channel_mapping = creds.get('slack', {}).get('channel_to_client', {})

            if event.get('channel_type') == 'im':
                # Direct message - look up by user
                user_info = user_mapping.get(slack_user_id)
                if not user_info:
                    logging.info(f'Slack webhook: Unmapped user {slack_user_id}')
                    return {'status': 'ignored', 'reason': 'unmapped user'}
                client_slug = user_info.get('client_slug')
                sender_name = user_info.get('sender_name')
            else:
                # Private channel - look up by channel, then by user for sender name
                channel_info = channel_mapping.get(channel_id)
                if not channel_info:
                    logging.info(f'Slack webhook: Unmapped channel {channel_id}')
                    return {'status': 'ignored', 'reason': 'unmapped channel'}
                client_slug = channel_info.get('client_slug')
                user_info = user_mapping.get(slack_user_id)
                if not user_info:
                    logging.info(f'Slack webhook: Unmapped user {slack_user_id} in channel {channel_id}')
                    return {'status': 'ignored', 'reason': 'unmapped user in channel'}
                sender_name = user_info.get('sender_name')

            # Noise filter - skip acks and low-value messages
            def is_noise(text):
                if not text:
                    return True
                stripped = text.strip()
                # Skip if under 20 chars (catches most acks)
                if len(stripped) < 20:
                    return True
                # Skip if only a mention with no other content
                import re
                no_mentions = re.sub(r'<@[A-Z0-9]+>', '', stripped).strip()
                if len(no_mentions) < 20:
                    return True
                # Skip common ack phrases (case-insensitive match on stripped lowercase)
                ack_phrases = {
                    'thanks', 'thank you', 'thanks!', 'thank you!',
                    'ok', 'okay', 'ok!', 'okay!',
                    'got it', 'got it!', 'gotcha',
                    'sounds good', 'sounds good!',
                    'great', 'great!', 'perfect', 'perfect!',
                    'awesome', 'awesome!', 'cool', 'cool!',
                    'yep', 'yes', 'yeah', 'no', 'nope', 'sure',
                    'nice', 'nice!', 'excellent', 'ty', 'thx',
                    'done', 'done!', 'k', 'kk'
                }
                lowered = stripped.lower().rstrip('.!?')
                if lowered in ack_phrases:
                    return True
                return False

            if is_noise(text):
                logging.info(f'Slack webhook: Filtered noise message from {sender_name}: {text[:50]}')
                return {'status': 'filtered', 'reason': 'noise'}

            # Load/create thread mapping file
            ts_map_path = os.path.join(BASE_DIR, f"data/{client_slug}_slack_ts_map.json")
            if os.path.exists(ts_map_path):
                with open(ts_map_path, 'r') as f:
                    ts_map = json.load(f)
            else:
                ts_map = {'slack_to_entry': {}, 'entry_to_slack': {}}
            
            entry_key = None
            
            # Handle threaded reply
            if thread_ts and thread_ts in ts_map.get('slack_to_entry', {}):
                parent_entry_key = ts_map['slack_to_entry'][thread_ts]
                result = client_hub_manager.add_thread_reply({
                    'client_slug': client_slug,
                    'parent_message_key': parent_entry_key,
                    'sender': sender_name,
                    'text': text
                })
                entry_key = result.get('reply_key') if isinstance(result, dict) else None
            else:
                # Top-level message
                result = client_hub_manager.post_message({
                    'client_slug': client_slug,
                    'sender': sender_name,
                    'text': text
                })
                entry_key = result.get('entry_key') if isinstance(result, dict) else None
            
            # Store bidirectional mapping
            if entry_key:
                ts_map.setdefault('slack_to_entry', {})[slack_ts] = entry_key
                ts_map.setdefault('entry_to_slack', {})[entry_key] = slack_ts
                with open(ts_map_path, 'w') as f:
                    json.dump(ts_map, f, indent=2)
            
            return {'status': 'success', 'entry_key': entry_key}
        
        return {'status': 'ignored', 'reason': 'unhandled event type'}
        
    except Exception as e:
        logging.error(f"Slack webhook error: {e}")
        return {'status': 'error', 'message': str(e)}


# 🩺 System Health Check
@app.get("/system_check")
async def system_check():
    """Run full Gershwin environment health check. Returns pass/fail per check."""
    try:
        result = subprocess.run(
            ["python3", os.path.join(BASE_DIR, "tools", "gershwin_tester.py"), "run_system_check", "--params", "{}"],
            capture_output=True, text=True, timeout=30
        )
        return json.loads(result.stdout)
    except Exception as e:
        return {"status": "error", "message": str(e)}


# 🔗 Dynamic URL Aliases - catch-all route (MUST be LAST - after all other routes)
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
        target_path = aliases[full_path]
        # Preserve query params by passing through as redirect
        if request.url.query:
            target = "/" + target_path + "?" + request.url.query
            return RedirectResponse(url=target, status_code=302)
        
        # No query params: serve file directly to keep clean URL
        file_path = os.path.join(BASE_DIR, target_path)
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                content = f.read()
            return HTMLResponse(content=content)
        else:
            raise HTTPException(status_code=404, detail=f"File not found: {target_path}")
    
    raise HTTPException(status_code=404, detail="Alias not found")