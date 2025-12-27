#!/usr/bin/env python3
"""
Claude Execution Engine

Monitors data/claude_task_queue.json for new tasks with status=queued.
When detected, calls execute_queue via execution_hub.py to spawn ONE Claude session
that processes all queued tasks in batch.

This runs as a managed engine (starts with jarvis.py via engine_registry.json).
Separate from automation_engine.py to prevent race conditions:
- automation_engine.py: Outline docs, emails, time-based triggers
- claude_execution_engine.py: Claude task execution ONLY

Usage:
    python3 tools/claude_execution_engine.py run_engine
"""

import os
import json
import time
import subprocess
import argparse
import sys
from datetime import datetime

QUEUE_FILE = 'data/claude_task_queue.json'
CHECK_INTERVAL = 2  # seconds


def log(message):
    """Log with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def read_json(path):
    """Read JSON file"""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        # File might be mid-write
        return {}
    except Exception as e:
        log(f"❌ Error reading {path}: {e}")
        return {}


def get_queued_tasks(queue_data):
    """Get list of tasks with status=queued"""
    tasks = queue_data.get("tasks", {})
    queued = []
    for task_id, task_data in tasks.items():
        if not isinstance(task_data, dict):
            continue
        status = task_data.get('status', 'queued')
        if status == 'queued':
            queued.append(task_id)
    return queued


def trigger_execute_queue():
    """Call execute_queue via execution_hub.py"""
    try:
        log("🚀 Triggering execute_queue via execution_hub.py")

        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cmd = [
            '/Users/srinivas/venv/bin/python3',
            os.path.join(repo_root, 'execution_hub.py'),
            'execute_task',
            '--params',
            json.dumps({
                "tool_name": "claude_assistant",
                "action": "execute_queue",
                "params": {}
            })
        ]

        # Run with env -u CLAUDECODE to prevent nested session detection
        env = os.environ.copy()
        env.pop('CLAUDECODE', None)

        result = subprocess.run(
            cmd,
            env=env,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )

        if result.returncode == 0:
            try:
                response = json.loads(result.stdout)
                status = response.get('status', 'unknown')

                if status == 'success':
                    log(f"✅ Execute queue completed successfully")
                    log(f"   Tasks processed: {response.get('task_count', 'unknown')}")
                    return True
                elif status == 'already_running':
                    log(f"⏳ {response.get('message', 'Queue already processing')}")
                    return False
                else:
                    log(f"⚠️  Execute queue returned: {status}")
                    log(f"   Message: {response.get('message', 'No message')}")
                    return False
            except json.JSONDecodeError:
                log(f"✅ Execute queue completed (raw output)")
                return True
        else:
            log(f"❌ Execute queue failed (exit code {result.returncode})")
            if result.stderr:
                log(f"   stderr: {result.stderr[:500]}")
            return False

    except subprocess.TimeoutExpired:
        log(f"⏰ Execute queue timed out after 10 minutes")
        return False
    except Exception as e:
        log(f"❌ Error triggering execute_queue: {e}")
        return False


def engine_loop():
    """Main engine loop - watches queue and triggers execute_queue"""
    log("⚡ Claude Execution Engine Started")
    log(f"📁 Watching: {QUEUE_FILE}")
    log("💡 GPT assigns task → Watcher triggers execute_queue → Claude processes batch")
    log("")

    last_queued_tasks = set()
    LOCKFILE = 'data/execute_queue.lock'

    while True:
        try:
            # Check if lockfile exists (batch already processing)
            if os.path.exists(LOCKFILE):
                # Validate lockfile - remove if stale
                should_remove = False
                try:
                    with open(LOCKFILE, 'r') as f:
                        lock_data = json.load(f)
                        pid = lock_data.get("pid")
                        created_at = lock_data.get("created_at")

                    # Check if lock is older than 30 minutes
                    if created_at:
                        try:
                            lock_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                            age_minutes = (datetime.now() - lock_time.replace(tzinfo=None)).total_seconds() / 60
                            if age_minutes > 30:
                                log(f"⚠️  Removing stale lockfile (created {age_minutes:.1f} minutes ago)")
                                should_remove = True
                        except:
                            pass

                    # Check if PID is still alive
                    if not should_remove and pid:
                        try:
                            os.kill(pid, 0)  # Signal 0 just checks if process exists
                        except OSError:
                            # Process is dead - remove stale lockfile
                            log(f"⚠️  Removing stale lockfile (PID {pid} not found)")
                            should_remove = True

                    if should_remove:
                        os.remove(LOCKFILE)
                        log("✅ Stale lockfile removed, continuing...")
                    else:
                        # Valid lock - skip this check
                        time.sleep(CHECK_INTERVAL)
                        continue

                except Exception as e:
                    log(f"⚠️  Error reading lockfile: {e}, removing...")
                    try:
                        os.remove(LOCKFILE)
                    except:
                        pass

            # Read queue
            queue_data = read_json(QUEUE_FILE)
            queued_tasks = get_queued_tasks(queue_data)
            current_tasks = set(queued_tasks)

            # FIXED: Only spawn if there are queued tasks AND no session running
            # Don't track "new" vs "old" - just check if queue has work and no active session
            if current_tasks:
                log(f"🆕 Found {len(current_tasks)} queued task(s): {', '.join(list(current_tasks)[:3])}")
                success = trigger_execute_queue()
                if success:
                    # Wait for session to start processing before next check
                    time.sleep(10)

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            log("")
            log("🛑 Stopping Claude Execution Engine...")
            break
        except Exception as e:
            log(f"❌ Error in engine loop: {e}")
            time.sleep(CHECK_INTERVAL)

    log("✅ Claude Execution Engine stopped")


def main():
    """Main entry point with argparse"""
    parser = argparse.ArgumentParser(description="Claude Execution Engine")
    parser.add_argument('action', choices=['run_engine'], help='Action to perform')
    args = parser.parse_args()

    if args.action == 'run_engine':
        # Ensure queue file exists
        if not os.path.exists(QUEUE_FILE):
            os.makedirs(os.path.dirname(QUEUE_FILE), exist_ok=True)
            with open(QUEUE_FILE, 'w') as f:
                json.dump({"tasks": {}}, f, indent=2)
            log("📝 Created empty queue file")

        # Start engine loop
        engine_loop()
    else:
        print(f"Unknown action: {args.action}")
        sys.exit(1)


if __name__ == "__main__":
    main()
