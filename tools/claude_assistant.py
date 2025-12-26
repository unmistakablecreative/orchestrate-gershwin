#!/usr/bin/env python3
"""
Claude Assistant

Auto-refactored by refactorize.py to match gold standard structure.
"""

import sys
import json
import os
import subprocess

import time
import requests
import stat
from datetime import datetime


def safe_write_queue(queue_file, queue_data):
    """Safely write to potentially read-only queue file"""
    was_readonly = False
    if os.path.exists(queue_file):
        file_stat = os.stat(queue_file)
        if not (file_stat.st_mode & stat.S_IWUSR):
            was_readonly = True
            os.chmod(queue_file, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)  # 644

    with open(queue_file, 'w', encoding='utf-8') as f:
        json.dump(queue_data, f, indent=2)

    if was_readonly:
        os.chmod(queue_file, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)


def assign_task(params):
    """
    GPT assigns a task to Claude Code queue.

    Required:
    - task_id: unique identifier
    - description: what Claude should do

    Optional:
    - priority: high/medium/low (default: medium)
    - context: extra info for Claude (default: {})
    - create_output_doc: if true, Claude will create an outline doc (default: false)
    - batch_id: if provided, groups this task with others in same batch (default: generates unique ID)
    """
    task_id = params.get("task_id")
    description = params.get("description")
    priority = params.get("priority", "medium")
    create_output_doc = params.get("create_output_doc", False)
    batch_id = params.get("batch_id")  # Optional - for batch assignments

    # Generate batch_id if not provided
    if not batch_id:
        batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{task_id[:8]}"

    if not task_id:
        return {"status": "error", "message": "❌ Missing required field: task_id"}
    if not description:
        return {"status": "error", "message": "❌ Missing required field: description"}

    # Reset thread score to 100 at start of each task
    try:
        subprocess.run(
            ["python3", "execution_hub.py", "load_orchestrate_os"],
            capture_output=True,
            timeout=10,
            cwd=os.getcwd()
        )
    except Exception:
        pass  # Non-critical, continue

    # Load execution context (replaces orchestrate_profile.json)
    execution_context_file = os.path.join(os.getcwd(), "data/execution_context.json")
    execution_context = {}

    if os.path.exists(execution_context_file):
        try:
            with open(execution_context_file, 'r', encoding='utf-8') as f:
                execution_context = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load execution_context.json: {e}", file=sys.stderr)

    # Start with execution context as base
    context = params.get("context", {})
    if not context:
        context = {}

    # Inject execution_context into every task
    if execution_context:
        context["execution_context"] = execution_context
        context["context_note"] = "execution_context contains all routing rules, collection IDs, and tool policies. Use this instead of searching."

    # Always load working_memory.json (ephemeral, task-specific memory)
    working_memory_file = os.path.join(os.getcwd(), "data/working_memory.json")
    if os.path.exists(working_memory_file):
        try:
            with open(working_memory_file, 'r', encoding='utf-8') as f:
                working_memory = json.load(f)
            if working_memory:  # Only add if not empty
                context["working_memory"] = working_memory
        except Exception:
            pass

    context["create_output_doc"] = create_output_doc

    # If create_output_doc is true, add hint for Claude to use outline_editor
    if create_output_doc:
        context["hint"] = "Create an outline document for this task using execution_hub.py with outline_editor.create_doc"

    # AUTO-INJECT TOOL BUILD PROTOCOL if task involves building a tool
    tool_build_keywords = ["build tool", "create tool", "new tool", "implement tool", "write tool", "build.*tool"]
    description_lower = description.lower()

    if any(keyword.replace(".*", " ") in description_lower for keyword in tool_build_keywords):
        protocol_file = os.path.join(os.getcwd(), "data/tool_build_protocol.md")
        if os.path.exists(protocol_file):
            try:
                with open(protocol_file, 'r', encoding='utf-8') as f:
                    protocol_content = f.read()
                context["MANDATORY_PROTOCOL"] = {
                    "file": "data/tool_build_protocol.md",
                    "content": protocol_content,
                    "warning": "🚨 READ THIS BEFORE BUILDING TOOL 🚨 - Check existing credentials, test the tool, log completion. Skipping protocol = FAILED TASK."
                }
            except Exception as e:
                print(f"Warning: Could not load tool_build_protocol.md: {e}", file=sys.stderr)

    queue_file = "data/claude_task_queue.json"
    os.makedirs(os.path.dirname(queue_file), exist_ok=True)

    # Load queue
    if os.path.exists(queue_file):
        with open(queue_file, 'r', encoding='utf-8') as f:
            queue = json.load(f)
    else:
        queue = {"tasks": {}}

    # Add task with batch_id
    queue["tasks"][task_id] = {
        "status": "queued",
        "created_at": datetime.now().isoformat(),
        "assigned_by": "GPT",
        "priority": priority,
        "description": description,
        "context": context,
        "batch_id": batch_id  # Assigned at creation time
    }

    # Save queue (handle read-only protected file)
    safe_write_queue(queue_file, queue)

    # In-container mode: Queue processor handles execution
    # Just return success - queue processor will pick it up
    return {
        "status": "success",
        "message": f"✅ Task '{task_id}' assigned to Claude Code queue",
        "task_id": task_id,
        "batch_id": batch_id,
        "next_step": "Queue processor will execute this task automatically"
    }


def check_task_status(params):
    """
    Check status of a task.

    Required:
    - task_id: the task to check

    Returns status: queued, pending, done, error
    """
    task_id = params.get("task_id")

    if not task_id:
        return {"status": "error", "message": "❌ Missing required field: task_id"}

    # Check queue
    queue_file = "data/claude_task_queue.json"
    if os.path.exists(queue_file):
        with open(queue_file, 'r', encoding='utf-8') as f:
            queue = json.load(f)
            if task_id in queue.get("tasks", {}):
                task_data = queue["tasks"][task_id]
                return {
                    "status": "success",
                    "task_id": task_id,
                    "task_status": task_data["status"],
                    "created_at": task_data.get("created_at"),
                    "description": task_data.get("description")
                }

    # Check results
    results_file = "data/claude_task_results.json"
    if os.path.exists(results_file):
        try:
            with open(results_file, 'r', encoding='utf-8') as f:
                results = json.load(f)
            if task_id in results.get("results", {}):
                result_data = results["results"][task_id]
                return {
                    "status": "success",
                    "task_id": task_id,
                    "task_status": "done",
                    "completed_at": result_data.get("completed_at"),
                    "execution_time_seconds": result_data.get("execution_time_seconds"),
                    "output": result_data.get("output")
                }
        except Exception as e:
            return {"status": "error", "message": f"❌ Error reading results: {str(e)}"}

    return {
        "status": "error",
        "message": f"❌ Task '{task_id}' not found in queue or results"
    }


def get_task_result(params):
    """
    Get full result data from a completed task.

    Required:
    - task_id: the completed task

    Returns full completion report
    """
    task_id = params.get("task_id")

    if not task_id:
        return {"status": "error", "message": "❌ Missing required field: task_id"}

    results_file = "data/claude_task_results.json"

    if not os.path.exists(results_file):
        return {
            "status": "error",
            "message": f"❌ No results file found. Task '{task_id}' may not be complete yet."
        }

    try:
        with open(results_file, 'r', encoding='utf-8') as f:
            results = json.load(f)
    except Exception as e:
        return {"status": "error", "message": f"❌ Error reading results: {str(e)}"}

    if task_id not in results.get("results", {}):
        return {
            "status": "error",
            "message": f"❌ No result found for task '{task_id}'. Check if task is complete with check_task_status."
        }

    return {
        "status": "success",
        "task_id": task_id,
        "result": results["results"][task_id]
    }


def get_all_results(params):
    """
    Get all task results without needing individual task IDs.

    GPT calls this to see all completed tasks at once.

    No parameters needed.
    """
    results_file = "data/claude_task_results.json"

    if not os.path.exists(results_file):
        return {
            "status": "success",
            "message": "✅ No task results yet",
            "results": {},
            "task_count": 0
        }

    try:
        with open(results_file, 'r', encoding='utf-8') as f:
            results = json.load(f)
    except Exception as e:
        return {"status": "error", "message": f"❌ Error reading results: {str(e)}"}

    all_results = results.get("results", {})

    return {
        "status": "success",
        "message": f"Found {len(all_results)} completed task(s)",
        "results": all_results,
        "task_count": len(all_results)
    }


def ask_claude(params):
    """
    Quick Q&A - GPT asks Claude a simple question, Claude answers.

    No task queue, no logging. Just direct question/answer.
    Use this for quick lookups like "what did you use for X?" or "did that work?"

    Required:
    - question: the question to ask Claude

    Returns:
    - answer: Claude's response

    Note: This returns a placeholder. The actual answer comes from Claude
    reading this function call and responding in the session.
    """
    question = params.get("question")

    if not question:
        return {"status": "error", "message": "❌ Missing required field: question"}

    return {
        "status": "ready",
        "message": "📝 Question received - Claude will respond in current session",
        "question": question,
        "note": "Claude sees this and will answer directly without task queue"
    }


def cancel_task(params):
    """
    Cancel a queued or in_progress task.

    Required:
    - task_id: the task to cancel

    Returns success if task was cancelled.
    """
    task_id = params.get("task_id")

    if not task_id:
        return {"status": "error", "message": "❌ Missing required field: task_id"}

    queue_file = "data/claude_task_queue.json"

    if not os.path.exists(queue_file):
        return {"status": "error", "message": "❌ No task queue found"}

    try:
        with open(queue_file, 'r', encoding='utf-8') as f:
            queue = json.load(f)
    except Exception as e:
        return {"status": "error", "message": f"❌ Error reading queue: {str(e)}"}

    if task_id not in queue.get("tasks", {}):
        return {"status": "error", "message": f"❌ Task '{task_id}' not found in queue"}

    task = queue["tasks"][task_id]
    current_status = task.get("status")

    if current_status in ["done", "error"]:
        return {"status": "error", "message": f"❌ Cannot cancel task that is already {current_status}"}

    # Mark as cancelled
    queue["tasks"][task_id]["status"] = "cancelled"
    queue["tasks"][task_id]["cancelled_at"] = datetime.now().isoformat()

    try:
        with open(queue_file, 'w', encoding='utf-8') as f:
            json.dump(queue, f, indent=2)
    except Exception as e:
        return {"status": "error", "message": f"❌ Error writing queue: {str(e)}"}

    return {
        "status": "success",
        "message": f"✅ Task '{task_id}' cancelled",
        "task_id": task_id,
        "previous_status": current_status
    }


def update_task(params):
    """
    Update a queued task's description, priority, or context.

    Required:
    - task_id: the task to update

    Optional (at least one required):
    - description: new description
    - priority: new priority (high/medium/low)
    - context: new or updated context fields

    Can only update tasks with status 'queued'.
    """
    task_id = params.get("task_id")

    if not task_id:
        return {"status": "error", "message": "❌ Missing required field: task_id"}

    new_description = params.get("description")
    new_priority = params.get("priority")
    new_context = params.get("context")

    if not any([new_description, new_priority, new_context]):
        return {"status": "error", "message": "❌ Must provide at least one field to update (description, priority, or context)"}

    queue_file = "data/claude_task_queue.json"

    if not os.path.exists(queue_file):
        return {"status": "error", "message": "❌ No task queue found"}

    try:
        with open(queue_file, 'r', encoding='utf-8') as f:
            queue = json.load(f)
    except Exception as e:
        return {"status": "error", "message": f"❌ Error reading queue: {str(e)}"}

    if task_id not in queue.get("tasks", {}):
        return {"status": "error", "message": f"❌ Task '{task_id}' not found in queue"}

    task = queue["tasks"][task_id]

    if task.get("status") != "queued":
        return {"status": "error", "message": f"❌ Can only update tasks with status 'queued' (current: {task.get('status')})"}

    # Apply updates
    updated_fields = []

    if new_description:
        queue["tasks"][task_id]["description"] = new_description
        updated_fields.append("description")

    if new_priority:
        queue["tasks"][task_id]["priority"] = new_priority
        updated_fields.append("priority")

    if new_context:
        # Merge context instead of replacing
        current_context = queue["tasks"][task_id].get("context", {})
        current_context.update(new_context)
        queue["tasks"][task_id]["context"] = current_context
        updated_fields.append("context")

    queue["tasks"][task_id]["updated_at"] = datetime.now().isoformat()

    try:
        with open(queue_file, 'w', encoding='utf-8') as f:
            json.dump(queue, f, indent=2)
    except Exception as e:
        return {"status": "error", "message": f"❌ Error writing queue: {str(e)}"}

    return {
        "status": "success",
        "message": f"✅ Task '{task_id}' updated",
        "task_id": task_id,
        "updated_fields": updated_fields
    }


def process_queue(params):
    """
    Claude calls this to get all queued tasks.

    Returns list of tasks for Claude to process.
    AUTOMATICALLY marks all queued tasks as in_progress and sets started_at timestamp.
    Claude will then:
    1. Execute each task
    2. Call log_task_completion when done

    OPTIMIZATION: Only returns queued tasks. Completed tasks are invisible.
    """
    queue_file = "data/claude_task_queue.json"

    if not os.path.exists(queue_file):
        return {
            "status": "success",
            "message": "✅ No tasks in queue",
            "pending_tasks": [],
            "task_count": 0
        }

    try:
        with open(queue_file, 'r', encoding='utf-8') as f:
            queue = json.load(f)
    except Exception as e:
        return {"status": "error", "message": f"❌ Error reading queue: {str(e)}"}

    # Get queued tasks ONLY (filter out everything else)
    pending = []
    now = datetime.now().isoformat()
    tasks_marked = []

    for task_id, task_data in queue.get("tasks", {}).items():
        if task_data.get("status") == "queued":
            # AUTO-MARK as in_progress and set started_at timestamp
            queue["tasks"][task_id]["status"] = "in_progress"
            queue["tasks"][task_id]["started_at"] = now
            tasks_marked.append(task_id)

            pending.append({
                "task_id": task_id,
                "description": task_data["description"],
                "context": task_data.get("context", {}),
                "priority": task_data.get("priority", "medium"),
                "created_at": task_data.get("created_at"),
                "AFTER_COMPLETION_YOU_MUST": f"Call log_task_completion for task_id '{task_id}' via execution_hub.py - DO NOT SKIP THIS STEP"
            })

    if not pending:
        return {
            "status": "success",
            "message": "✅ No pending tasks",
            "pending_tasks": [],
            "task_count": 0
        }

    # Save updated queue with in_progress status and started_at timestamps
    try:
        safe_write_queue(queue_file, queue)
        print(f"⏱️  Auto-marked {len(tasks_marked)} task(s) as in_progress with started_at timestamp", file=sys.stderr)
    except Exception as e:
        print(f"Warning: Could not update task status: {e}", file=sys.stderr)

    return {
        "status": "success",
        "message": f"Found {len(pending)} pending task(s), auto-marked as in_progress",
        "pending_tasks": pending,
        "task_count": len(pending),
        "CRITICAL_REMINDER": "🚨 YOU MUST CALL log_task_completion FOR EACH TASK via execution_hub.py. If you complete a task without logging, the result is LOST. Logging is MANDATORY, not optional. 🚨"
    }


def mark_task_in_progress(params):
    """
    Mark a queued task as in_progress.

    Claude calls this when starting work on a task.

    Required:
    - task_id: the task to mark as in_progress
    """
    task_id = params.get("task_id")

    if not task_id:
        return {"status": "error", "message": "❌ Missing required field: task_id"}

    queue_file = "data/claude_task_queue.json"

    if not os.path.exists(queue_file):
        return {"status": "error", "message": "❌ No task queue found"}

    try:
        with open(queue_file, 'r', encoding='utf-8') as f:
            queue = json.load(f)
    except Exception as e:
        return {"status": "error", "message": f"❌ Error reading queue: {str(e)}"}

    if task_id not in queue.get("tasks", {}):
        return {"status": "error", "message": f"❌ Task '{task_id}' not found in queue"}

    task = queue["tasks"][task_id]
    current_status = task.get("status")

    # Allow marking in_progress if currently queued or already in_progress (idempotent)
    if current_status not in ["queued", "in_progress"]:
        return {
            "status": "error",
            "message": f"❌ Task '{task_id}' cannot be marked in_progress (current status: {current_status})"
        }

    queue["tasks"][task_id]["status"] = "in_progress"
    if "started_at" not in queue["tasks"][task_id]:
        queue["tasks"][task_id]["started_at"] = datetime.now().isoformat()

    try:
        with open(queue_file, 'w', encoding='utf-8') as f:
            json.dump(queue, f, indent=2)
    except Exception as e:
        return {"status": "error", "message": f"❌ Error writing queue: {str(e)}"}

    return {
        "status": "success",
        "message": f"✅ Task '{task_id}' marked as in_progress"
    }


def execute_queue(params):
    """
    Spawns a Claude Code session to process all queued tasks.

    Now captures stdout in real-time to extract token telemetry and writes to
    data/last_execution_telemetry.json for execution_hub to consume.

    Returns immediately after spawning the process. The background process will:
    - Process all queued tasks
    - Write results to claude_task_results.json when complete
    - Continue running even if parent process exits

    Claude Code has access to:
    - Bash commands
    - All Orchestrate tools via execution_hub.py
    - File operations (Read, Write, Edit)

    One session processes all tasks. No per-task spawning.
    """
    # CRITICAL: Check if we're already inside Claude Code
    if os.environ.get("CLAUDECODE"):
        return {
            "status": "error",
            "message": "❌ Cannot spawn nested Claude Code session. You're already inside Claude Code. Process tasks directly in the current session instead.",
            "hint": "Read tasks from data/claude_task_queue.json and process them here"
        }

    # LOCKFILE CHECK: Prevent multiple simultaneous execute_queue sessions
    lockfile = os.path.join(os.getcwd(), "data/execute_queue.lock")

    if os.path.exists(lockfile):
        # Check if process is actually still running
        try:
            with open(lockfile, 'r') as f:
                lock_data = json.load(f)
                pid = lock_data.get("pid")

            # Check if PID is still alive
            if pid:
                try:
                    os.kill(pid, 0)  # Signal 0 just checks if process exists
                    # Process is alive - return early
                    return {
                        "status": "already_running",
                        "message": f"⏳ Queue execution already in progress (PID {pid})",
                        "hint": "Wait for current batch to complete"
                    }
                except OSError:
                    # Process is dead but lockfile exists - clean up stale lockfile
                    print(f"⚠️  Removing stale lockfile (PID {pid} not found)", file=sys.stderr)
                    os.remove(lockfile)
        except Exception as e:
            print(f"Warning: Could not read lockfile: {e}", file=sys.stderr)
            # If we can't read/verify lockfile, play it safe and don't spawn

    # CREATE LOCKFILE IMMEDIATELY to prevent race conditions
    try:
        with open(lockfile, 'w') as f:
            json.dump({
                "created_at": datetime.now().isoformat(),
                "pid": os.getpid(),
                "note": "Checking queue..."
            }, f, indent=2)
        print(f"🔒 Created lockfile", file=sys.stderr)
    except Exception as e:
        print(f"Warning: Could not create lockfile: {e}", file=sys.stderr)
        # Continue anyway - don't block execution on lockfile failure

    result = process_queue(params)

    if result.get("task_count", 0) == 0:
        # No tasks - remove lockfile and return
        try:
            os.remove(lockfile)
        except:
            pass
        return result

    # Update lockfile with task count
    try:
        with open(lockfile, 'w') as f:
            json.dump({
                "created_at": datetime.now().isoformat(),
                "pid": os.getpid(),
                "task_count": result['task_count']
            }, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not update lockfile: {e}", file=sys.stderr)

    # Spawn Claude Code session to process queue
    try:
        # Inherit full environment to pass subscription auth
        env = os.environ.copy()

        # CRITICAL: Remove API key to force subscription auth (free) instead of API tokens (costs money)
        env.pop('ANTHROPIC_API_KEY', None)

        # CRITICAL: Remove CLAUDECODE so spawned process doesn't think it's nested
        env.pop('CLAUDECODE', None)

        # Minimal prompt - Claude Code auto-loads .claude/CLAUDE.md
        prompt = """Process all tasks in data/claude_task_queue.json.

═══════════════════════════════════════════════════════════
🚨 CRITICAL: LOGGING IS NOT OPTIONAL 🚨
You MUST call log_task_completion for EVERY task via execution_hub.py.
If you complete a task without logging it, the result is LOST FOREVER.
User will be pissed, tokens wasted, work vanished.
LOGGING IS MANDATORY. NO EXCEPTIONS.
═══════════════════════════════════════════════════════════

STOP WASTING TOKENS ON SEARCHES:
Before doing ANY Grep/Read/search operations, run the master diagnostic:
  python3 tools/orchestrate_diagnostic.py

This ONE command shows everything (broken engines, task failures, syntax errors, queue state, actionable fixes).

EXECUTION FLOW:
0. FIRST: python3 execution_hub.py execute_task --params '{"tool_name": "orchestrate", "action": "load_orchestrate_os", "params": {}}'
1. THEN: curl http://localhost:5001/get_supported_actions
2. Read queue: python3 execution_hub.py execute_task --params '{"tool_name": "claude_assistant", "action": "process_queue", "params": {}}'
   NOTE: process_queue AUTOMATICALLY marks all tasks as in_progress and sets started_at timestamp. DO NOT call mark_task_in_progress manually.

3. For each task:
   a. Execute task using execution_hub.py (REQUIRED for telemetry)
   b. Write telemetry BEFORE completion: echo '{"tokens_input": X, "tokens_output": Y, "tool": "...", "action": "..."}' > data/last_execution_telemetry.json
   c. Log completion: python3 execution_hub.py execute_task --params '{"tool_name": "claude_assistant", "action": "log_task_completion", "params": {"task_id": "<id>", "status": "done", "actions_taken": ["..."], "output": "..."}}'

   ⚠️  DO NOT SKIP STEP 3c - LOGGING IS MANDATORY FOR EVERY TASK ⚠️
   If you finish a task without calling log_task_completion, you FAILED.

4. AFTER ALL TASKS COMPLETE: rm data/execute_queue.lock

WORKFLOW ENFORCEMENT:
If task.context contains "workflow" key (e.g., "blog_prep_for_publication"), the workflow file at data/<workflow>.json MUST be followed EXACTLY.

For blog_prep_for_publication:
- Step 5 "apply_revisions" means ACTUALLY EDIT THE ARTICLE in Outline, not just make suggestions
- Step 6 "score_post_revision" means RE-SCORE THE REVISED VERSION, not the original
- DO NOT skip critical steps or half-ass workflows with "here are suggestions" bullshit

Workflow steps marked "critical: true" are MANDATORY. If you skip them or just make recommendations instead of executing, you FAILED the task.

CRITICAL JSON FILE PROTECTION:
NEVER use Write/Edit tools on: outline_queue.json, claude_task_queue.json, claude_task_results.json, automation_state.json, execution_log.json, outline_reference.json, youtube_published.json, youtube_publish_queue.json, podcast_index.json, working_memory.json

ONLY use json_manager tool. Direct Write/Edit corrupts JSON and causes race conditions.

Project context in .claude/CLAUDE.md (auto-loaded)."""

        # Create log file for stdout capture (for debugging)
        log_file_path = os.path.join(os.getcwd(), "data", "claude_execution.log")
        os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
        log_file = open(log_file_path, "w")

        # Use -p flag to pass prompt directly (no PTY needed)
        # Start new session so process continues even if parent exits
        process = subprocess.Popen([
            "claude",
            "-p", prompt,
            "--permission-mode", "acceptEdits",
            "--allowedTools", "Bash,Read,Write,Edit"
        ],
        env=env,
        cwd=os.getcwd(),
        stdout=log_file,  # Write to log file for debugging
        stderr=subprocess.STDOUT,  # Merge stderr into stdout
        start_new_session=True  # Detach from parent process
        )

        # Return immediately with task_started status
        return {
            "status": "task_started",
            "message": f"✅ Claude Code session started in background to process {result['task_count']} task(s)",
            "task_count": result['task_count'],
            "pid": process.pid,
            "note": "Process is running in background. Claude will write token telemetry to data/last_execution_telemetry.json after completion."
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"❌ Failed to spawn Claude Code session: {str(e)}"
        }


def log_task_completion(params):
    """
    Claude calls this when a task is complete.

    Required:
    - task_id: the task that was completed
    - status: "done" or "error"
    - actions_taken: list of what Claude did

    Optional:
    - output: any data produced
    - output_summary: human-readable summary
    - errors: if status is "error", what went wrong
    - execution_time_seconds: how long it took
    """
    task_id = params.get("task_id")
    status = params.get("status")
    actions_taken = params.get("actions_taken", [])
    output = params.get("output", {})
    output_summary = params.get("output_summary")
    errors = params.get("errors")
    execution_time = params.get("execution_time_seconds", 0)

    if not task_id:
        return {"status": "error", "message": "❌ Missing required field: task_id"}
    if not status:
        return {"status": "error", "message": "❌ Missing required field: status"}

    # REMOVE completed task from queue (todo list behavior - checked tasks disappear)
    task_description = None
    task_batch_id = None
    task_started_at = None
    queue_file = "data/claude_task_queue.json"
    if os.path.exists(queue_file):
        try:
            with open(queue_file, 'r', encoding='utf-8') as f:
                queue = json.load(f)

            if task_id in queue.get("tasks", {}):
                # Store description, batch_id, and started_at BEFORE deleting
                task_description = queue["tasks"][task_id].get("description", "")
                task_batch_id = queue["tasks"][task_id].get("batch_id")
                task_started_at = queue["tasks"][task_id].get("started_at")

                # REMOVE task from queue (completed tasks disappear from queue)
                del queue["tasks"][task_id]

                safe_write_queue(queue_file, queue)

                print(f"✅ Removed '{task_id}' from queue (completed)", file=sys.stderr)
        except Exception as e:
            # Non-critical, continue
            print(f"Warning: Could not update queue: {e}", file=sys.stderr)

    # Calculate execution_time if not provided and we have started_at
    if execution_time == 0 and task_started_at:
        try:
            # Remove timezone info if present (Python 3.7+ fromisoformat doesn't handle 'Z')
            started_str = task_started_at.replace('Z', '').replace('+00:00', '')
            started = datetime.fromisoformat(started_str)
            completed = datetime.now()
            execution_time = (completed - started).total_seconds()
            print(f"⏱️  Calculated execution time: {execution_time:.2f} seconds", file=sys.stderr)
        except Exception as e:
            print(f"Warning: Could not calculate execution time: {e}", file=sys.stderr)

    # Write result
    results_file = "data/claude_task_results.json"
    archive_dir = os.path.join(os.getcwd(), "data/task_archive")

    # Load existing results
    if os.path.exists(results_file):
        try:
            with open(results_file, 'r', encoding='utf-8') as f:
                results = json.load(f)
        except Exception as e:
            print(f"Warning: Could not read results file: {e}", file=sys.stderr)
            results = {"results": {}}
    else:
        results = {"results": {}}

    # Archive old results if count > 10 (keep last 10)
    if len(results.get("results", {})) > 10:
        try:
            os.makedirs(archive_dir, exist_ok=True)

            # Sort by completed_at timestamp
            sorted_results = sorted(
                results["results"].items(),
                key=lambda x: x[1].get("completed_at", ""),
                reverse=False  # Oldest first
            )

            # Archive all but the last 10
            to_archive = dict(sorted_results[:-10])
            to_keep = dict(sorted_results[-10:])

            if to_archive:
                # Append to archive file (NDJSON format for efficient appending)
                archive_file = os.path.join(archive_dir, f"results_{datetime.now().strftime('%Y-%m')}.jsonl")
                with open(archive_file, 'a', encoding='utf-8') as f:
                    for archived_task_id, result_data in to_archive.items():
                        f.write(json.dumps({"task_id": archived_task_id, **result_data}) + '\n')

                # Update results to keep only last 10
                results["results"] = to_keep
                print(f"📦 Archived {len(to_archive)} old results to {archive_file}", file=sys.stderr)
        except Exception as e:
            print(f"Warning: Could not archive old results: {e}", file=sys.stderr)

    # Generate output_summary if not provided
    if not output_summary:
        output_summary = "Task completed" if status == "done" else "Task failed"

    # Calculate batch position (task_batch_id already read above before deleting)
    is_first_task_in_batch = False
    batch_position = 0

    if task_batch_id:
        # Count how many tasks with this batch_id have already been completed
        completed_in_batch = 0
        for tid, result in results.get("results", {}).items():
            if result.get("batch_id") == task_batch_id:
                completed_in_batch += 1

        # First task in batch gets all input tokens, rest get 0
        is_first_task_in_batch = (completed_in_batch == 0)
        batch_position = completed_in_batch + 1

        print(f"📊 Batch {task_batch_id}: task {batch_position} (first: {is_first_task_in_batch})", file=sys.stderr)

    # Add result (append-only, no read-modify-write of existing entries)
    results["results"][task_id] = {
        "status": status,
        "description": task_description if task_description else output_summary,
        "completed_at": datetime.now().isoformat(),
        "execution_time_seconds": execution_time,
        "actions_taken": actions_taken,
        "output": output,
        "output_summary": output_summary,
        "errors": errors
    }

    # Add batch_id from task (assigned at creation time)
    if task_batch_id:
        results["results"][task_id]["batch_id"] = task_batch_id
        results["results"][task_id]["batch_position"] = batch_position

    # Log to stderr so we can track what's being logged without reading the file
    print(f"📝 Logged task '{task_id}' completion to results file", file=sys.stderr)

    # Save results with batch_id (first save)
    try:
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
    except Exception as e:
        return {"status": "error", "message": f"❌ Error writing results: {str(e)}"}

    # Merge token telemetry from last_execution_telemetry.json if available
    telemetry_file = os.path.join(os.getcwd(), "data", "last_execution_telemetry.json")
    telemetry_merged = False

    if os.path.exists(telemetry_file):
        try:
            with open(telemetry_file, 'r', encoding='utf-8') as f:
                telemetry_data = json.load(f)

            # BATCH TELEMETRY: Only first task in batch gets input tokens
            input_tokens = telemetry_data.get("tokens_input", 0)
            if task_batch_id and not is_first_task_in_batch:
                # Subsequent tasks: input tokens were already loaded, don't count again
                input_tokens = 0
                print(f"📊 Batch task {batch_position}: using shared input context (0 incremental tokens)", file=sys.stderr)

            # Add token data to result (using batch-adjusted input_tokens)
            output_tokens = telemetry_data.get("tokens_output", 0)
            if telemetry_data.get("tokens_input") or output_tokens:
                results["results"][task_id]["tokens"] = {
                    "input": input_tokens,  # Batch-adjusted (0 for subsequent tasks)
                    "output": output_tokens,
                    "total": input_tokens + output_tokens
                }
                # Use batch-adjusted token cost
                results["results"][task_id]["token_cost"] = input_tokens + output_tokens
                # Note: batch_id and batch_position already added earlier (line 817-819)

            # Update tool/action if captured
            if telemetry_data.get("tool"):
                results["results"][task_id]["tool"] = telemetry_data["tool"]
            if telemetry_data.get("action"):
                results["results"][task_id]["action"] = telemetry_data["action"]

            # Save updated results with telemetry
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2)

            # Also retroactively update execution_log.json with real token data
            execution_log_path = os.path.join(os.getcwd(), "data", "execution_log.json")
            if os.path.exists(execution_log_path):
                try:
                    with open(execution_log_path, 'r', encoding='utf-8') as f:
                        execution_log = json.load(f)

                    # Find the most recent claude_assistant.execute_queue entry
                    for entry in reversed(execution_log.get("executions", [])):
                        if entry.get("tool") == "claude_assistant" and entry.get("action") == "execute_queue":
                            # Update with real telemetry data
                            entry["token_cost"] = telemetry_data.get("tokens_input", 0) + telemetry_data.get("tokens_output", 0)
                            if telemetry_data.get("tool"):
                                entry["actual_tool"] = telemetry_data["tool"]
                            if telemetry_data.get("action"):
                                entry["actual_action"] = telemetry_data["action"]
                            entry["tokens"] = {
                                "input": telemetry_data.get("tokens_input", 0),
                                "output": telemetry_data.get("tokens_output", 0),
                                "total": telemetry_data.get("tokens_input", 0) + telemetry_data.get("tokens_output", 0)
                            }
                            break

                    # Save updated execution log
                    with open(execution_log_path, 'w', encoding='utf-8') as f:
                        json.dump(execution_log, f, indent=2)
                except Exception as e2:
                    print(f"Warning: Could not update execution_log.json: {e2}", file=sys.stderr)

            # Clean up telemetry file after merging
            os.remove(telemetry_file)
            telemetry_merged = True

        except Exception as e:
            # Non-critical - continue without telemetry
            print(f"Warning: Could not merge telemetry data: {e}", file=sys.stderr)
    else:
        # Auto-capture: Try to extract from claude_execution.log if telemetry file missing
        print(f"⚠️  No telemetry file found - attempting auto-capture from logs...", file=sys.stderr)

        try:
            from token_telemetry import extract_token_usage_from_log
            log_file_path = os.path.join(os.getcwd(), "data", "claude_execution.log")

            if os.path.exists(log_file_path):
                with open(log_file_path, 'r', encoding='utf-8') as f:
                    log_content = f.read()

                token_data = extract_token_usage_from_log(log_content)
                if token_data:
                    # Write to telemetry file so main merge logic can use it
                    auto_telemetry = {
                        "tokens_input": token_data.get("tokens_start", {}).get("total", 0),
                        "tokens_output": token_data.get("tokens_end", {}).get("total", 0) - token_data.get("tokens_start", {}).get("total", 0),
                        "tool": "auto_captured",
                        "action": "from_logs"
                    }

                    with open(telemetry_file, 'w', encoding='utf-8') as f:
                        json.dump(auto_telemetry, f, indent=2)

                    print(f"✅ Auto-captured tokens from logs: {auto_telemetry['tokens_input']} input, {auto_telemetry['tokens_output']} output", file=sys.stderr)

                    # Now retry the merge logic since we created the telemetry file
                    try:
                        with open(telemetry_file, 'r', encoding='utf-8') as f:
                            telemetry_data = json.load(f)

                        # Merge into results entry (FIX: use results["results"][task_id] not undefined 'entry')
                        results["results"][task_id]["token_cost"] = telemetry_data.get("tokens_input", 0) + telemetry_data.get("tokens_output", 0)
                        results["results"][task_id]["tokens"] = {
                            "input": telemetry_data.get("tokens_input", 0),
                            "output": telemetry_data.get("tokens_output", 0),
                            "total": telemetry_data.get("tokens_input", 0) + telemetry_data.get("tokens_output", 0)
                        }

                        # Save updated results after auto-capture merge
                        with open(results_file, 'w', encoding='utf-8') as f:
                            json.dump(results, f, indent=2)

                        os.remove(telemetry_file)
                        print(f"✅ Token telemetry merged successfully", file=sys.stderr)
                    except Exception as e2:
                        print(f"Warning: Auto-capture succeeded but merge failed: {e2}", file=sys.stderr)
                else:
                    print(f"⚠️  Could not extract token data from logs", file=sys.stderr)
            else:
                print(f"⚠️  No execution log found at {log_file_path}", file=sys.stderr)

        except Exception as e:
            print(f"⚠️  Auto-capture failed: {e}", file=sys.stderr)
            print(f"   Token usage will NOT be recorded for task '{task_id}'", file=sys.stderr)


    return {
        "status": "success",
        "message": f"✅ Task '{task_id}' completion logged with status: {status}",
        "output_summary": output_summary
    }


def batch_assign_tasks(params):
    """
    Assign multiple tasks at once.

    GPT calls this with a list of tasks to assign them all in one go.
    Each task is independently validated and dispatched.

    Required:
    - tasks: list of task dicts, each with task_id, description, priority (optional), context (optional)

    Returns:
    - success_count: how many tasks were successfully added
    - failed_count: how many failed
    - details: per-task results with errors if any
    - summary: human-readable summary

    Example:
    {
        "tasks": [
            {"task_id": "task_1", "description": "Do thing 1", "priority": "high"},
            {"task_id": "task_2", "description": "Do thing 2", "context": {"extra": "info"}}
        ]
    }
    """
    tasks = params.get("tasks")

    if not tasks:
        return {"status": "error", "message": "❌ Missing required field: tasks (must be a list)"}

    if not isinstance(tasks, list):
        return {"status": "error", "message": "❌ tasks must be a list of task dictionaries"}

    if len(tasks) == 0:
        return {"status": "error", "message": "❌ tasks list is empty"}

    results = []
    success_count = 0
    failed_count = 0

    for i, task in enumerate(tasks):
        task_id = task.get("task_id")

        # Validate task structure
        if not isinstance(task, dict):
            results.append({
                "index": i,
                "task_id": None,
                "status": "error",
                "message": "❌ Task must be a dictionary"
            })
            failed_count += 1
            continue

        if not task_id:
            results.append({
                "index": i,
                "task_id": None,
                "status": "error",
                "message": "❌ Task missing required field: task_id"
            })
            failed_count += 1
            continue

        # Use auto_execute=False to prevent spawning for each task
        task_params = task.copy()
        task_params["auto_execute"] = False

        # Call assign_task for each task
        try:
            result = assign_task(task_params)
            if result.get("status") == "success":
                success_count += 1
                results.append({
                    "index": i,
                    "task_id": task_id,
                    "status": "success",
                    "message": f"✅ Task {task_id} queued"
                })
            else:
                failed_count += 1
                results.append({
                    "index": i,
                    "task_id": task_id,
                    "status": "error",
                    "message": result.get("message", "Unknown error")
                })
        except Exception as e:
            failed_count += 1
            results.append({
                "index": i,
                "task_id": task_id,
                "status": "error",
                "message": f"❌ Exception: {str(e)}"
            })

    # Generate summary
    summary = f"Assigned {success_count}/{len(tasks)} tasks successfully"
    if failed_count > 0:
        summary += f" ({failed_count} failed)"

    return {
        "status": "success" if success_count > 0 else "error",
        "message": f"✅ {summary}" if success_count > 0 else f"❌ {summary}",
        "success_count": success_count,
        "failed_count": failed_count,
        "total_tasks": len(tasks),
        "details": results,
        "summary": summary
    }


def get_task_results(params):
    """
    Get recent task execution data with optional markdown table formatting.

    Follows jarvis.py pattern: offload rendering to script, not AI.

    Optional:
    - format: "table" for markdown table + session stats, "json" for raw data (default: json)
    - limit: number of recent tasks to show (default: 10)

    Returns:
    - If format="table": pre-formatted markdown with execution data and session stats
    - If format="json": raw results data for programmatic access
    """
    output_format = params.get("format", "json")
    limit = params.get("limit", 10)

    results_file = "data/claude_task_results.json"

    if not os.path.exists(results_file):
        if output_format == "table":
            return {
                "status": "success",
                "formatted_output": "## Recent Execution Data\n\nNo task results yet."
            }
        else:
            return {
                "status": "success",
                "results": {},
                "task_count": 0
            }

    try:
        with open(results_file, 'r', encoding='utf-8') as f:
            results = json.load(f)
    except Exception as e:
        return {"status": "error", "message": f"❌ Error reading results: {str(e)}"}

    all_results = results.get("results", {})

    if output_format == "json":
        # Return raw data
        return {
            "status": "success",
            "results": all_results,
            "task_count": len(all_results)
        }

    # Format as markdown table
    if not all_results:
        return {
            "status": "success",
            "formatted_output": "## Recent Execution Data\n\nNo completed tasks found."
        }

    # Sort by completion time (most recent first) and limit
    sorted_tasks = sorted(
        all_results.items(),
        key=lambda x: x[1].get("completed_at", ""),
        reverse=True
    )[:limit]

    # Build markdown table
    markdown_lines = ["## Recent Execution Data\n"]
    markdown_lines.append("| Task ID | Status | Execution Time | Human Equivalent | Speed Multiplier |")
    markdown_lines.append("|---------|--------|----------------|------------------|------------------|")

    total_time = 0
    success_count = 0
    total_human_time = 0

    for task_id, task_data in sorted_tasks:
        status = task_data.get("status", "unknown")
        exec_time = task_data.get("execution_time_seconds", 0)

        # Format execution time
        if exec_time >= 60:
            time_str = f"{int(exec_time // 60)}m {int(exec_time % 60)}s"
        else:
            time_str = f"{int(exec_time)}s"

        # Estimate human equivalent (conservative: 15x multiplier for most tasks)
        human_hours = exec_time * 15 / 3600
        if human_hours < 1:
            human_str = f"~{int(human_hours * 60)}min"
        else:
            human_str = f"~{human_hours:.1f}h"

        # Calculate speed multiplier
        speed_mult = "15x"

        # Track stats
        total_time += exec_time
        total_human_time += exec_time * 15
        if status == "done":
            success_count += 1

        # Add row
        markdown_lines.append(f"| {task_id[:30]} | {status} | {time_str} | {human_str} | {speed_mult} |")

    # Add session stats
    markdown_lines.append("\n**Session Stats:**")
    markdown_lines.append(f"- Tasks completed: {success_count}/{len(sorted_tasks)}")

    avg_time = total_time / len(sorted_tasks) if sorted_tasks else 0
    if avg_time >= 60:
        avg_str = f"{int(avg_time // 60)}m {int(avg_time % 60)}s"
    else:
        avg_str = f"{int(avg_time)}s"
    markdown_lines.append(f"- Average execution time: {avg_str}")

    success_rate = (success_count / len(sorted_tasks) * 100) if sorted_tasks else 0
    markdown_lines.append(f"- Success rate: {success_rate:.0f}%")

    # Total time saved
    time_saved_hours = (total_human_time - total_time) / 3600
    markdown_lines.append(f"- Total time saved: ~{time_saved_hours:.1f} hours")

    # Cost analysis
    markdown_lines.append("\n**Cost Analysis:**")
    session_cost = len(sorted_tasks) * 0.02
    api_cost_low = len(sorted_tasks) * 2
    api_cost_high = len(sorted_tasks) * 5
    savings_mult = api_cost_low / session_cost if session_cost > 0 else 0

    markdown_lines.append(f"- Session cost: ${session_cost:.2f}")
    markdown_lines.append(f"- API equivalent: ${api_cost_low:.2f}-${api_cost_high:.2f}")
    markdown_lines.append(f"- Savings: {savings_mult:.0f}x")

    formatted_output = "\n".join(markdown_lines)

    return {
        "status": "success",
        "formatted_output": formatted_output,
        "task_count": len(sorted_tasks)
    }


def get_recent_tasks(params):
    """
    Get the most recent N completed tasks, sorted by completion timestamp (descending).

    Purpose:
    - Returns only fully completed tasks (status = done)
    - Sorted by actual completion time (not queue order)
    - Enables accurate demo recap, auto-logging, and execution audits

    Optional:
    - limit: number of recent tasks to return (default: 10)

    Returns:
    - tasks: list of task dicts with task_id, status, completed_at, execution_time_seconds, output_summary
    - task_count: number of tasks returned
    """
    limit = params.get("limit", 10)

    results_file = "data/claude_task_results.json"

    if not os.path.exists(results_file):
        return {
            "status": "success",
            "message": "✅ No task results yet",
            "tasks": [],
            "task_count": 0
        }

    try:
        with open(results_file, 'r', encoding='utf-8') as f:
            results = json.load(f)
    except Exception as e:
        return {"status": "error", "message": f"❌ Error reading results: {str(e)}"}

    all_results = results.get("results", {})

    # Filter for completed tasks only (status = done)
    completed_tasks = {
        task_id: task_data
        for task_id, task_data in all_results.items()
        if task_data.get("status") == "done"
    }

    if not completed_tasks:
        return {
            "status": "success",
            "message": "✅ No completed tasks found",
            "tasks": [],
            "task_count": 0
        }

    # Sort by completion timestamp (most recent first)
    sorted_tasks = sorted(
        completed_tasks.items(),
        key=lambda x: x[1].get("completed_at", ""),
        reverse=True
    )[:limit]

    # Build output list
    task_list = []
    for task_id, task_data in sorted_tasks:
        task_list.append({
            "task_id": task_id,
            "status": task_data.get("status"),
            "completed_at": task_data.get("completed_at"),
            "execution_time_seconds": task_data.get("execution_time_seconds", 0),
            "output_summary": task_data.get("output_summary", "No summary"),
            "output": task_data.get("output", {})
        })

    return {
        "status": "success",
        "message": f"Found {len(task_list)} recent completed task(s)",
        "tasks": task_list,
        "task_count": len(task_list)
    }


def add_to_memory(params):
    """
    Adds an item to working memory (ephemeral, task-specific).

    Required:
    - key: unique identifier for the memory item
    - value: the data to store (can be string, dict, list, etc.)

    Optional:
    - type: category/type of memory (default: "note")
    """
    key = params.get("key")
    value = params.get("value")
    mem_type = params.get("type", "note")

    if not key:
        return {"status": "error", "message": "❌ Missing required field: key"}
    if value is None:
        return {"status": "error", "message": "❌ Missing required field: value"}

    working_memory_file = os.path.join(os.getcwd(), "data/working_memory.json")
    os.makedirs(os.path.dirname(working_memory_file), exist_ok=True)

    # Load existing memory
    if os.path.exists(working_memory_file):
        with open(working_memory_file, 'r', encoding='utf-8') as f:
            memory = json.load(f)
    else:
        memory = {}

    # Add timestamp if value is a dict
    if isinstance(value, dict):
        value["updated_at"] = datetime.now().isoformat()
        if "type" not in value:
            value["type"] = mem_type

    # Store the memory item
    memory[key] = value

    # Save memory
    with open(working_memory_file, 'w', encoding='utf-8') as f:
        json.dump(memory, f, indent=2)

    return {
        "status": "success",
        "message": f"✅ Added '{key}' to working memory",
        "memory_file": working_memory_file,
        "total_items": len(memory)
    }


def get_working_memory(params):
    """
    Returns current working memory contents.
    """
    working_memory_file = os.path.join(os.getcwd(), "data/working_memory.json")

    if not os.path.exists(working_memory_file):
        return {
            "status": "success",
            "memory": {},
            "item_count": 0,
            "message": "Working memory is empty"
        }

    with open(working_memory_file, 'r', encoding='utf-8') as f:
        memory = json.load(f)

    return {
        "status": "success",
        "memory": memory,
        "item_count": len(memory),
        "memory_file": working_memory_file
    }


def clear_working_memory(params):
    """
    Clears the working memory file to reset ephemeral session context.

    This should be called after task completion to ensure session-specific
    data doesn't carry over to future tasks.

    Optional:
    - preserve_keys: list of keys to preserve (default: [])

    Returns success status and what was cleared.
    """
    working_memory_file = os.path.join(os.getcwd(), "data/working_memory.json")
    preserve_keys = params.get("preserve_keys", [])

    if not os.path.exists(working_memory_file):
        return {
            "status": "success",
            "message": "✅ Working memory file doesn't exist (already clear)",
            "cleared": True
        }

    try:
        # Load current content
        with open(working_memory_file, 'r', encoding='utf-8') as f:
            current_memory = json.load(f)

        # Preserve specified keys if any
        preserved_data = {}
        if preserve_keys:
            for key in preserve_keys:
                if key in current_memory:
                    preserved_data[key] = current_memory[key]

        # Clear and write empty or preserved data
        cleared_count = len(current_memory) - len(preserved_data)

        with open(working_memory_file, 'w', encoding='utf-8') as f:
            json.dump(preserved_data, f, indent=2)

        return {
            "status": "success",
            "message": f"✅ Working memory cleared ({cleared_count} items removed, {len(preserved_data)} preserved)",
            "cleared": True,
            "cleared_count": cleared_count,
            "preserved_count": len(preserved_data)
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"❌ Failed to clear working memory: {str(e)}",
            "cleared": False
        }


def capture_token_telemetry(params):
    """
    Helper function to capture token usage telemetry and write to last_execution_telemetry.json.

    This should be called BEFORE log_task_completion to ensure token data is captured.

    Required:
    - tokens_input: input tokens from /usage command
    - tokens_output: output tokens from /usage command
    - task_id: current task ID

    Optional:
    - tool: primary tool used (default: "claude_assistant")
    - action: primary action taken (default: "execute_task")
    - execution_time_seconds: execution time in seconds (default: 0)
    - metadata: additional metadata dict (default: {})

    Returns success status and confirmation of data written.
    """
    tokens_input = params.get("tokens_input")
    tokens_output = params.get("tokens_output")
    task_id = params.get("task_id")

    if tokens_input is None or tokens_output is None:
        return {
            "status": "error",
            "message": "❌ Missing required fields: tokens_input and tokens_output"
        }

    if not task_id:
        return {
            "status": "error",
            "message": "❌ Missing required field: task_id"
        }

    tool = params.get("tool", "claude_assistant")
    action = params.get("action", "execute_task")
    execution_time = params.get("execution_time_seconds", 0)
    metadata = params.get("metadata", {})

    telemetry_file = os.path.join(os.getcwd(), "data", "last_execution_telemetry.json")

    try:
        telemetry_data = {
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
            "total_tokens": tokens_input + tokens_output,
            "tool": tool,
            "action": action,
            "task_id": task_id,
            "execution_time_seconds": execution_time,
            "timestamp": datetime.now().isoformat() + "Z"
        }

        # Merge any additional metadata
        if metadata:
            telemetry_data.update(metadata)

        with open(telemetry_file, 'w', encoding='utf-8') as f:
            json.dump(telemetry_data, f, indent=2)

        return {
            "status": "success",
            "message": f"✅ Token telemetry captured for task '{task_id}': {tokens_input} input + {tokens_output} output = {tokens_input + tokens_output} total",
            "telemetry_file": telemetry_file,
            "total_tokens": tokens_input + tokens_output
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"❌ Failed to write telemetry data: {str(e)}"
        }


def archive_thread_logs(params):
    """
    Archives thread logs older than specified retention period.

    Moves old entries from thread_log.json to thread_log_archive.json
    and optionally syncs recent logs to working_memory.json.

    Optional:
    - retention_days: number of days to keep (default: 30)
    - source_file: path to source thread log (default: data/thread_log.json)
    - archive_file: path to archive file (default: data/thread_log_archive.json)
    - sync_to_working_memory: whether to sync recent logs to working_memory.json (default: false)

    Returns:
    - Status, counts of archived vs retained logs
    """
    from datetime import datetime, timedelta

    retention_days = params.get("retention_days", 30)
    source_file = params.get("source_file", "data/thread_log.json")
    archive_file = params.get("archive_file", "data/thread_log_archive.json")
    sync_to_working_memory = params.get("sync_to_working_memory", False)

    source_path = os.path.join(os.getcwd(), source_file)
    archive_path = os.path.join(os.getcwd(), archive_file)
    working_memory_path = os.path.join(os.getcwd(), "data/working_memory.json")

    try:
        # Load source thread log
        if not os.path.exists(source_path):
            return {
                "status": "success",
                "message": f"✅ No thread log found at {source_file} (nothing to archive)",
                "archived_count": 0,
                "retained_count": 0
            }

        with open(source_path, 'r', encoding='utf-8') as f:
            thread_log = json.load(f)

        # Load existing archive or create new
        if os.path.exists(archive_path):
            with open(archive_path, 'r', encoding='utf-8') as f:
                archive = json.load(f)
            if "entries" not in archive:
                archive["entries"] = {}
        else:
            archive = {"entries": {}}

        # Calculate cutoff date
        cutoff_date = datetime.now() - timedelta(days=retention_days)

        # Separate old and recent entries
        entries = thread_log.get("entries", {})
        old_entries = {}
        recent_entries = {}

        for entry_key, entry_data in entries.items():
            timestamp_str = entry_data.get("timestamp", "")
            try:
                # Parse timestamp (format: 2025-09-26T11:58:22)
                entry_date = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))

                if entry_date < cutoff_date:
                    old_entries[entry_key] = entry_data
                else:
                    recent_entries[entry_key] = entry_data
            except (ValueError, AttributeError):
                # If timestamp parsing fails, keep in recent
                recent_entries[entry_key] = entry_data

        # Move old entries to archive
        if old_entries:
            archive["entries"].update(old_entries)

            with open(archive_path, 'w', encoding='utf-8') as f:
                json.dump(archive, f, indent=2)

        # Update source file with only recent entries
        thread_log["entries"] = recent_entries

        with open(source_path, 'w', encoding='utf-8') as f:
            json.dump(thread_log, f, indent=2)

        # Optionally sync to working_memory.json
        if sync_to_working_memory and recent_entries:
            if os.path.exists(working_memory_path):
                with open(working_memory_path, 'r', encoding='utf-8') as f:
                    working_memory = json.load(f)
            else:
                working_memory = {}

            working_memory["thread_logs"] = recent_entries

            with open(working_memory_path, 'w', encoding='utf-8') as f:
                json.dump(working_memory, f, indent=2)

        return {
            "status": "success",
            "message": f"✅ Thread log archival complete",
            "archived_count": len(old_entries),
            "retained_count": len(recent_entries),
            "retention_days": retention_days,
            "cutoff_date": cutoff_date.isoformat(),
            "archive_file": archive_file,
            "synced_to_working_memory": sync_to_working_memory
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"❌ Failed to archive thread logs: {str(e)}",
            "archived_count": 0,
            "retained_count": 0
        }


def infer_task_type(params):
    """
    Infers task type and returns matching module names based on keyword detection.

    This is a lightweight function that only does keyword matching without loading
    the actual module files. Used by get_task_context() internally.

    Required:
    - task_description: Task description to analyze

    Returns:
    - task_type: primary task type detected
    - modules: list of module file names to load
    - keywords_detected: keywords that triggered detection
    """
    task_description = params.get("task_description", "")

    if not task_description:
        return {
            "status": "error",
            "message": "❌ Missing required field: task_description"
        }

    task_lower = task_description.lower()
    modules_to_load = []
    detected_keywords = []
    primary_type = "general"

    # Email module detection
    email_keywords = ['email', 'inbox', 'nylas', 'message', 'reply', 'send email']
    if any(keyword in task_lower for keyword in email_keywords):
        modules_to_load.append('email_module.json')
        detected_keywords.extend([k for k in email_keywords if k in task_lower])
        primary_type = "email"

    # Outline module detection
    outline_keywords = ['outline', 'document', 'doc ', 'create doc', 'blog', 'article']
    if any(keyword in task_lower for keyword in outline_keywords):
        modules_to_load.append('outline_module.json')
        detected_keywords.extend([k for k in outline_keywords if k in task_lower])
        if primary_type == "general":
            primary_type = "outline"

    # Podcast module detection (check this BEFORE tool_building to avoid "transcript" false positives)
    podcast_keywords = ['podcast', 'episode', 'transcript', 'audio', 'midroll']
    if any(keyword in task_lower for keyword in podcast_keywords):
        modules_to_load.append('podcast_module.json')
        detected_keywords.extend([k for k in podcast_keywords if k in task_lower])
        if primary_type == "general":
            primary_type = "podcast"

    # Tool building module detection (more specific keywords to avoid false positives)
    # Exclude if podcast transcript already matched
    tool_keywords = ['build tool', 'build function', 'new tool', 'implement tool', 'create tool', 'script.py', 'install tool', 'function', 'implement']
    if 'podcast_module.json' not in modules_to_load:
        if any(keyword in task_lower for keyword in tool_keywords):
            modules_to_load.append('tool_building_module.json')
            detected_keywords.extend([k for k in tool_keywords if k in task_lower])
            if primary_type == "general":
                primary_type = "tool_building"

    # Fallback to full profile if no modules detected
    fallback = len(modules_to_load) == 0

    return {
        "status": "success",
        "task_type": primary_type,
        "modules": modules_to_load,
        "keywords_detected": list(set(detected_keywords)),  # Remove duplicates
        "fallback_to_full": fallback,
        "message": f"✅ Detected task type: {primary_type} ({len(modules_to_load)} module(s))"
    }


def get_task_context(params):
    """
    Phase 2: Module Loader
    Combines core profile + task-specific modules for selective loading.

    Required:
    - task_description: Task description to analyze for module selection

    Returns:
    - Combined context with core profile + relevant modules
    - Logs module selection decisions
    """
    task_description = params.get("task_description", "")

    if not task_description:
        return {
            "status": "error",
            "message": "❌ Missing required field: task_description"
        }

    try:
        # 1. Load core profile (3K tokens)
        core_profile_file = os.path.join(os.getcwd(), ".claude/orchestrate_profile.json")
        if not os.path.exists(core_profile_file):
            return {
                "status": "error",
                "message": f"❌ Core profile not found at {core_profile_file}"
            }

        with open(core_profile_file, 'r', encoding='utf-8') as f:
            core_profile = json.load(f)

        # 2. Detect task type using infer_task_type()
        inference = infer_task_type({"task_description": task_description})
        if inference.get("status") == "error":
            return inference

        modules_to_load = inference.get("modules", [])

        # 3. Load matching modules
        loaded_modules = []
        modules_dir = os.path.join(os.getcwd(), ".claude/modules")

        for module_file in modules_to_load:
            module_path = os.path.join(modules_dir, module_file)
            if os.path.exists(module_path):
                with open(module_path, 'r', encoding='utf-8') as f:
                    module_data = json.load(f)
                    loaded_modules.append(module_data)

        # 4. Merge JSON structures
        combined_context = {
            "core_profile": core_profile,
            "specialized_modules": loaded_modules,
            "module_selection": {
                "task_description": task_description,
                "task_type": inference.get("task_type", "general"),
                "detected_keywords": inference.get("keywords_detected", []),
                "loaded_modules": [m.get("module", "unknown") for m in loaded_modules],
                "module_count": len(loaded_modules),
                "fallback_to_full": inference.get("fallback_to_full", False)
            }
        }

        # 5. Return combined context with logging
        return {
            "status": "success",
            "message": f"✅ Loaded core profile + {len(loaded_modules)} specialized module(s)",
            "context": combined_context,
            "logging": {
                "core_profile_loaded": True,
                "task_type": inference.get("task_type", "general"),
                "modules_loaded": [m.get("module", "unknown") for m in loaded_modules],
                "module_count": len(loaded_modules),
                "fallback_to_full": inference.get("fallback_to_full", False)
            }
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"❌ Failed to load task context: {str(e)}"
        }


def main():
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    if args.action == 'add_to_memory':
        result = add_to_memory(params)
    elif args.action == 'archive_thread_logs':
        result = archive_thread_logs(params)
    elif args.action == 'ask_claude':
        result = ask_claude(params)
    elif args.action == 'assign_task':
        result = assign_task(params)
    elif args.action == 'batch_assign_tasks':
        result = batch_assign_tasks(params)
    elif args.action == 'cancel_task':
        result = cancel_task(params)
    elif args.action == 'capture_token_telemetry':
        result = capture_token_telemetry(params)
    elif args.action == 'check_task_status':
        result = check_task_status(params)
    elif args.action == 'clear_working_memory':
        result = clear_working_memory(params)
    elif args.action == 'execute_queue':
        result = execute_queue(params)
    elif args.action == 'get_all_results':
        result = get_all_results(params)
    elif args.action == 'get_recent_tasks':
        result = get_recent_tasks(params)
    elif args.action == 'get_task_context':
        result = get_task_context(params)
    elif args.action == 'get_task_result':
        result = get_task_result(params)
    elif args.action == 'get_task_results':
        result = get_task_results(params)
    elif args.action == 'get_working_memory':
        result = get_working_memory(params)
    elif args.action == 'infer_task_type':
        result = infer_task_type(params)
    elif args.action == 'log_task_completion':
        result = log_task_completion(params)
    elif args.action == 'mark_task_in_progress':
        result = mark_task_in_progress(params)
    elif args.action == 'process_queue':
        result = process_queue(params)
    elif args.action == 'safe_write_queue':
        result = safe_write_queue(**params)
    elif args.action == 'update_task':
        result = update_task(params)
    else:
        result = {'status': 'error', 'message': f'Unknown action {args.action}'}

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()