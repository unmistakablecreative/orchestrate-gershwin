#!/usr/bin/env python3
"""
Claude Execution Engine - Fixed Version

Key changes:
1. Checks for ACTUAL running claude processes (not just lockfile)
2. Only spawns if running_agents < queued_tasks
3. Added spawn cooldown to prevent rapid-fire spawning
4. Better stale lockfile cleanup
"""

import os
import json
import time
import subprocess
import argparse
import sys
from datetime import datetime

# 3-queue parallel execution system
NUM_QUEUES = 3
QUEUE_FILES = [f'data/claude_task_q{i}.json' for i in range(1, NUM_QUEUES + 1)]
CHECK_INTERVAL = 5  # Increased from 2 to 5 seconds
SPAWN_COOLDOWN = 30  # Don't spawn again within 30 seconds


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
        return {}
    except Exception as e:
        log(f"❌ Error reading {path}: {e}")
        return {}


def count_running_claude_agents():
    """
    Count ACTUAL running claude processes (not lockfile PIDs).
    Uses pgrep to find claude processes with 'process_queue' in cmdline.
    """
    try:
        result = subprocess.run(
            ['pgrep', '-f', 'claude.*process_queue'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0 and result.stdout.strip():
            pids = result.stdout.strip().split('\n')
            count = len([p for p in pids if p])
            log(f"🔍 Found {count} running claude agent(s)")
            return count
        else:
            return 0
            
    except subprocess.TimeoutExpired:
        log("⚠️  pgrep timeout - assuming 0 agents")
        return 0
    except Exception as e:
        log(f"⚠️  Error counting agents: {e}")
        return 0


def get_queued_tasks_from_all():
    """Get list of tasks with status=queued from ALL queue files"""
    queued = []
    for queue_file in QUEUE_FILES:
        if not os.path.exists(queue_file):
            continue
        queue_data = read_json(queue_file)
        tasks = queue_data.get("tasks", {})
        for task_id, task_data in tasks.items():
            if not isinstance(task_data, dict):
                continue
            status = task_data.get('status', 'queued')
            if status == 'queued':
                queued.append(task_id)
    return queued


def cleanup_stale_lockfile():
    """
    Remove lockfile if:
    1. It's older than 30 minutes, OR
    2. All PIDs in it are dead
    """
    lockfile = 'data/execute_queue.lock'
    
    if not os.path.exists(lockfile):
        return True  # No lockfile = OK to proceed
    
    try:
        with open(lockfile, 'r') as f:
            lock_data = json.load(f)
        
        # Check age
        created_at = lock_data.get("created_at")
        if created_at:
            try:
                lock_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                age_minutes = (datetime.now() - lock_time.replace(tzinfo=None)).total_seconds() / 60
                if age_minutes > 30:
                    log(f"🧹 Removing stale lockfile ({age_minutes:.1f} min old)")
                    os.remove(lockfile)
                    return True
            except:
                pass
        
        # Check PIDs
        pids = lock_data.get("pids", [])
        if not pids and lock_data.get("pid"):
            pids = [lock_data["pid"]]
        
        any_alive = False
        for pid in pids:
            try:
                os.kill(pid, 0)  # Check if process exists
                any_alive = True
                break
            except OSError:
                pass
        
        if not any_alive:
            log(f"🧹 Removing lockfile with dead PIDs")
            os.remove(lockfile)
            return True
        
        # Lockfile is valid - agents are running
        return False
        
    except Exception as e:
        log(f"⚠️  Error checking lockfile: {e}, removing it")
        try:
            os.remove(lockfile)
        except:
            pass
        return True


def trigger_execute_queue(parallel=3):
    """
    Call execute_queue via execution_hub.py
    Only called when we KNOW we need to spawn agents.
    """
    try:
        log(f"🚀 Triggering execute_queue with parallel={parallel}")

        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cmd = [
            sys.executable,
            os.path.join(repo_root, 'execution_hub.py'),
            'execute_task',
            '--params',
            json.dumps({
                "tool_name": "claude_assistant",
                "action": "execute_queue",
                "params": {"parallel": parallel}
            })
        ]

        env = os.environ.copy()
        env.pop('CLAUDECODE', None)

        result = subprocess.run(
            cmd,
            env=env,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=600
        )

        if result.returncode == 0:
            try:
                response = json.loads(result.stdout)
                status = response.get('status', 'unknown')

                if status in ['task_started', 'started']:
                    agents_spawned = len(response.get('agents', []))
                    log(f"✅ Spawned {agents_spawned} agent(s)")
                    return True
                elif status == 'already_running':
                    log(f"⏳ {response.get('message', 'Already running')}")
                    return False
                else:
                    log(f"⚠️  Execute queue returned: {status}")
                    return False
            except json.JSONDecodeError:
                log(f"✅ Execute queue completed")
                return True
        else:
            log(f"❌ Execute queue failed (exit code {result.returncode})")
            if result.stderr:
                log(f"   stderr: {result.stderr[:500]}")
            return False

    except subprocess.TimeoutExpired:
        log(f"⏰ Execute queue timed out")
        return False
    except Exception as e:
        log(f"❌ Error triggering execute_queue: {e}")
        return False


def engine_loop():
    """
    Main engine loop - watches queue and triggers execute_queue SMARTLY.
    
    Smart spawning logic:
    1. Check if there are queued tasks
    2. Count ACTUAL running agents (pgrep, not lockfile)
    3. Only spawn if running_agents < queued_tasks
    4. Respect spawn cooldown to prevent rapid-fire
    """
    log("⚡ Claude Execution Engine Started (3-QUEUE VERSION)")
    log(f"📁 Watching: {', '.join(QUEUE_FILES)}")
    log(f"🧠 Smart spawning: Only spawns when needed")
    log("")

    last_spawn_time = 0

    while True:
        try:
            # Clean up stale lockfile first
            cleanup_stale_lockfile()

            # Read from all queues
            queued_tasks = get_queued_tasks_from_all()
            queued_count = len(queued_tasks)

            if queued_count == 0:
                # No tasks - just wait
                time.sleep(CHECK_INTERVAL)
                continue

            # Count ACTUAL running agents
            running_agents = count_running_claude_agents()

            # Calculate if we need more agents
            # Cap parallel at 15 max (reasonable limit)
            max_parallel = min(queued_count, 15)
            needed_agents = max_parallel - running_agents

            if needed_agents <= 0:
                # We have enough agents already
                log(f"✓ {running_agents} agent(s) already working on {queued_count} task(s) - waiting")
                time.sleep(CHECK_INTERVAL)
                continue

            # Check spawn cooldown
            now = time.time()
            time_since_last_spawn = now - last_spawn_time

            if time_since_last_spawn < SPAWN_COOLDOWN:
                wait_time = int(SPAWN_COOLDOWN - time_since_last_spawn)
                log(f"⏳ Spawn cooldown: {wait_time}s remaining")
                time.sleep(CHECK_INTERVAL)
                continue

            # All checks passed - spawn agents
            log(f"📊 Status: {queued_count} queued, {running_agents} running, need {needed_agents} more")
            
            # Determine parallel count (how many to spawn)
            parallel_count = min(max_parallel, 3)  # Start with 3 for this batch
            
            success = trigger_execute_queue(parallel=parallel_count)
            
            if success:
                last_spawn_time = now
                log(f"⏱️  Spawn cooldown: Next spawn allowed in {SPAWN_COOLDOWN}s")
                time.sleep(10)  # Give agents time to start
            else:
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
        # Ensure all queue files exist
        for queue_file in QUEUE_FILES:
            if not os.path.exists(queue_file):
                os.makedirs(os.path.dirname(queue_file), exist_ok=True)
                with open(queue_file, 'w') as f:
                    json.dump({"tasks": {}}, f, indent=2)
                log(f"📝 Created empty queue file: {queue_file}")

        # Start engine loop
        engine_loop()
    else:
        print(f"Unknown action: {args.action}")
        sys.exit(1)


if __name__ == "__main__":
    main()