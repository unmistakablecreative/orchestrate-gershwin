#!/usr/bin/env python3
"""
Claude Assistant - Fixed Version with Parallel Execution
Based on minimal core version with proper agent filtering and prison guard limits
"""

import sys
import json
import os
import subprocess
import time
import requests
import stat
import re
import uuid
from datetime import datetime, timedelta


# =============================================================================
# PRISON GUARD: Hard limits on parallel agents
# =============================================================================
MAX_PARALLEL_AGENTS = 3  # NEVER allow more than this

def count_running_agents():
    """Count currently running Claude Code agent processes."""
    lockfile = os.path.join(os.getcwd(), "data/execute_queue.lock")
    
    if not os.path.exists(lockfile):
        return 0
    
    try:
        with open(lockfile, 'r') as f:
            lock_data = json.load(f)
        
        pids = lock_data.get("pids", [])
        if not pids and lock_data.get("pid"):
            pids = [lock_data["pid"]]
        
        running = 0
        for pid in pids:
            try:
                os.kill(pid, 0)
                running += 1
            except OSError:
                pass
        
        return running
    except:
        return 0

def enforce_agent_limit():
    """Returns False if we're at max agents, True if we can spawn more."""
    running = count_running_agents()
    if running >= MAX_PARALLEL_AGENTS:
        return False
    return True


def safe_write_queue(queue_file, queue_data):
    """Safely write to potentially read-only queue file"""
    was_readonly = False
    if os.path.exists(queue_file):
        file_stat = os.stat(queue_file)
        if not (file_stat.st_mode & stat.S_IWUSR):
            was_readonly = True
            os.chmod(queue_file, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)

    with open(queue_file, 'w', encoding='utf-8') as f:
        json.dump(queue_data, f, indent=2)

    if was_readonly:
        os.chmod(queue_file, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)


def assign_task(params):
    """
    GPT assigns a task to Claude Code queue.

    Required:
    - description: what Claude should do

    Optional:
    - task_id: unique identifier (auto-generated if not provided)
    - priority: high/medium/low (default: medium)
    - context: extra info for Claude (default: {})
    - create_output_doc: if true, Claude will create an outline doc (default: false)
    - batch_id: if provided, groups this task with others in same batch
    - agent_id: for parallel execution, which agent should handle this task
    """
    task_id = params.get("task_id")
    description = params.get("description")
    priority = params.get("priority", "medium")
    create_output_doc = params.get("create_output_doc", False)
    batch_id = params.get("batch_id")
    agent_id = params.get("agent_id")

    # Auto-generate task_id if not provided
    if not task_id:
        task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    if not description:
        return {"status": "error", "message": "❌ Missing required field: description"}

    # Generate batch_id if not provided
    if not batch_id:
        batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{task_id[:8]}"

    # Reset thread score to 100 at start of each task
    try:
        subprocess.run(
            ["python3", "execution_hub.py", "load_orchestrate_os"],
            capture_output=True,
            timeout=10,
            cwd=os.getcwd()
        )
    except Exception:
        pass

    context = params.get("context", {})
    if not context:
        context = {}

    context["create_output_doc"] = create_output_doc

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
                    "warning": "🚨 READ THIS BEFORE BUILDING TOOL 🚨"
                }
            except Exception as e:
                print(f"Warning: Could not load tool_build_protocol.md: {e}", file=sys.stderr)

    # AUTO-INJECT TRIGGER STEPS if task contains @trigger pattern
    trigger_match = re.search(r'@([\w_-]+)', description)
    if trigger_match:
        trigger_name = f"@{trigger_match.group(1)}"
        triggers_file = os.path.join(os.getcwd(), "data/task_context_triggers.json")
        if os.path.exists(triggers_file):
            try:
                with open(triggers_file, 'r', encoding='utf-8') as f:
                    triggers_data = json.load(f)

                trigger_config = triggers_data.get("triggers", {}).get(trigger_name)
                if trigger_config:
                    context_file = trigger_config.get("context_file")
                    if context_file:
                        context_path = os.path.join(os.getcwd(), context_file)
                        if os.path.exists(context_path):
                            context["trigger_context_file"] = context_file

                    inject_steps = trigger_config.get("inject_steps", "")
                    if inject_steps:
                        # Handle both string (new format) and array (legacy)
                        steps_text = inject_steps if isinstance(inject_steps, str) else "\n".join(inject_steps)
                        description = f"{description}\n\n--- INJECTED STEPS FROM {trigger_name} ---\n{steps_text}"

                    template_doc_id = trigger_config.get("template_doc_id")
                    if template_doc_id:
                        context["template_doc_id"] = template_doc_id

                    routing = trigger_config.get("routing")
                    if routing:
                        context["routing"] = routing

            except Exception as e:
                print(f"Warning: Could not load triggers: {e}", file=sys.stderr)

    # AUTO-INJECT SKILL CONTENT if task matches skill triggers
    skills_dir = os.path.expanduser("~/.claude/skills")
    if os.path.exists(skills_dir):
        try:
            skill_names = os.listdir(skills_dir)
            matched_skill = None

            # PRIORITY 1: Check if skill folder name is literally in description
            # This prevents alphabetical trigger matching from picking wrong skill
            for skill_name in skill_names:
                if skill_name.lower() in description_lower:
                    skill_md = os.path.join(skills_dir, skill_name, "SKILL.md")
                    if os.path.exists(skill_md):
                        matched_skill = skill_name
                        break

            # PRIORITY 2: Fall back to trigger matching if no explicit match
            if not matched_skill:
                for skill_name in skill_names:
                    skill_md = os.path.join(skills_dir, skill_name, "SKILL.md")
                    if os.path.exists(skill_md):
                        with open(skill_md, 'r', encoding='utf-8') as f:
                            skill_content = f.read()
                        import re as regex
                        triggers_match = regex.search(r'Triggers? on (.+?)\.', skill_content, regex.IGNORECASE)
                        if triggers_match:
                            triggers_str = triggers_match.group(1)
                            triggers = [t.strip().lower() for t in triggers_str.split(',')]
                            if any(trigger in description_lower for trigger in triggers):
                                matched_skill = skill_name
                                break

            # Inject the matched skill
            if matched_skill:
                skill_md = os.path.join(skills_dir, matched_skill, "SKILL.md")
                with open(skill_md, 'r', encoding='utf-8') as f:
                    skill_content = f.read()
                description = f"{description}\n\n--- SKILL: {matched_skill} ---\n{skill_content}\n\nFOLLOW THE SKILL INSTRUCTIONS ABOVE. DO NOT DEVIATE."
        except Exception as e:
            print(f"Warning: Could not load skills: {e}", file=sys.stderr)

    queue_file = os.path.join(os.getcwd(), "data/claude_task_queue.json")
    os.makedirs(os.path.dirname(queue_file), exist_ok=True)

    if os.path.exists(queue_file):
        with open(queue_file, 'r', encoding='utf-8') as f:
            queue = json.load(f)
    else:
        queue = {"tasks": {}}

    now = datetime.now().isoformat()
    task_entry = {
        "status": "queued",
        "created_at": now,
        "started_at": now,
        "assigned_by": "GPT",
        "priority": priority,
        "description": description,
        "context": context,
        "batch_id": batch_id
    }
    if agent_id:
        task_entry["agent_id"] = agent_id
    queue["tasks"][task_id] = task_entry

    safe_write_queue(queue_file, queue)

    auto_execute = params.get("auto_execute", True)

    if auto_execute and not os.environ.get("CLAUDECODE"):
        execute_result = execute_queue({})
        return {
            "status": "success",
            "message": f"✅ Task '{task_id}' assigned and execution started",
            "task_id": task_id,
            "batch_id": batch_id,
            "agent_id": agent_id,
            "execution": execute_result
        }

    return {
        "status": "success",
        "message": f"✅ Task '{task_id}' assigned to Claude Code queue",
        "task_id": task_id,
        "batch_id": batch_id,
        "agent_id": agent_id,
        "next_step": "Call execute_queue to trigger processing" if not auto_execute else "Task will be processed in current session"
    }


def assign_demo_task(params):
    """Assigns a task with guaranteed 'demo_' prefix for demo recordings."""
    task_id = params.get("task_id")

    if not task_id:
        return {"status": "error", "message": "❌ Missing required field: task_id"}

    if not task_id.startswith("demo_"):
        task_id = f"demo_{task_id}"

    modified_params = params.copy()
    modified_params["task_id"] = task_id

    result = assign_task(modified_params)

    if result.get("status") == "success":
        result["message"] = f"✅ Demo task '{task_id}' assigned and will execute autonomously"

    return result


def check_task_status(params):
    """Check status of a task."""
    task_id = params.get("task_id")

    if not task_id:
        return {"status": "error", "message": "❌ Missing required field: task_id"}

    queue_file = os.path.join(os.getcwd(), "data/claude_task_queue.json")
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
                    "description": task_data.get("description"),
                    "agent_id": task_data.get("agent_id")
                }

    results_file = os.path.join(os.getcwd(), "data/claude_task_results.json")
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
    """Get full result data from a completed task."""
    task_id = params.get("task_id")

    if not task_id:
        return {"status": "error", "message": "❌ Missing required field: task_id"}

    results_file = os.path.join(os.getcwd(), "data/claude_task_results.json")

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
            "message": f"❌ No result found for task '{task_id}'."
        }

    return {
        "status": "success",
        "task_id": task_id,
        "result": results["results"][task_id]
    }


def get_all_results(params):
    """Get all task results without needing individual task IDs."""
    results_file = os.path.join(os.getcwd(), "data/claude_task_results.json")

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
    """Quick Q&A - GPT asks Claude a simple question, Claude answers."""
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
    """Cancel a queued or in_progress task."""
    task_id = params.get("task_id")

    if not task_id:
        return {"status": "error", "message": "❌ Missing required field: task_id"}

    queue_file = os.path.join(os.getcwd(), "data/claude_task_queue.json")

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
    """Update a queued task's description, priority, or context."""
    task_id = params.get("task_id")

    if not task_id:
        return {"status": "error", "message": "❌ Missing required field: task_id"}

    new_description = params.get("description")
    new_priority = params.get("priority")
    new_context = params.get("context")
    new_agent_id = params.get("agent_id")

    if not any([new_description, new_priority, new_context, new_agent_id]):
        return {"status": "error", "message": "❌ Must provide at least one field to update"}

    queue_file = os.path.join(os.getcwd(), "data/claude_task_queue.json")

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
        return {"status": "error", "message": f"❌ Can only update tasks with status 'queued'"}

    updated_fields = []

    if new_description:
        queue["tasks"][task_id]["description"] = new_description
        updated_fields.append("description")

    if new_priority:
        queue["tasks"][task_id]["priority"] = new_priority
        updated_fields.append("priority")

    if new_context:
        current_context = queue["tasks"][task_id].get("context", {})
        current_context.update(new_context)
        queue["tasks"][task_id]["context"] = current_context
        updated_fields.append("context")

    if new_agent_id:
        queue["tasks"][task_id]["agent_id"] = new_agent_id
        updated_fields.append("agent_id")

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
    
    NOW WITH AGENT FILTERING - if agent_id provided, only returns tasks for that agent.
    
    Parameters:
    - agent_id: If provided, ONLY return tasks assigned to this agent
    """
    agent_id = params.get("agent_id")  # KEY: Agent filter
    
    queue_file = os.path.join(os.getcwd(), "data/claude_task_queue.json")

    if not os.path.exists(queue_file):
        return {
            "status": "success",
            "message": "✅ No tasks in queue",
            "pending_tasks": [],
            "task_count": 0,
            "agent_id": agent_id
        }

    try:
        with open(queue_file, 'r', encoding='utf-8') as f:
            queue = json.load(f)
    except Exception as e:
        return {"status": "error", "message": f"❌ Error reading queue: {str(e)}"}

    pending = []
    now = datetime.now().isoformat()
    tasks_marked = []

    for task_id, task_data in queue.get("tasks", {}).items():
        if task_data.get("status") != "queued":
            continue
        
        # === AGENT FILTERING ===
        # If agent_id specified, ONLY get tasks for this agent
        if agent_id:
            task_agent = task_data.get("agent_id")
            if task_agent != agent_id:
                continue  # Skip - not assigned to this agent

        # Mark as in_progress
        queue["tasks"][task_id]["status"] = "in_progress"
        queue["tasks"][task_id]["started_at"] = now
        tasks_marked.append(task_id)

        pending.append({
            "task_id": task_id,
            "description": task_data["description"],
            "context": task_data.get("context", {}),
            "priority": task_data.get("priority", "medium"),
            "created_at": task_data.get("created_at"),
            "agent_id": task_data.get("agent_id"),
            "AFTER_COMPLETION_YOU_MUST": f"Call log_task_completion for task_id '{task_id}'"
        })

    if not pending:
        msg = "✅ No pending tasks"
        if agent_id:
            msg = f"✅ No pending tasks for {agent_id}"
        return {
            "status": "success",
            "message": msg,
            "pending_tasks": [],
            "task_count": 0,
            "agent_id": agent_id
        }

    # Save updated queue
    try:
        safe_write_queue(queue_file, queue)
        print(f"⏱️ Auto-marked {len(tasks_marked)} task(s) as in_progress", file=sys.stderr)
    except Exception as e:
        print(f"Warning: Could not update task status: {e}", file=sys.stderr)

    return {
        "status": "success",
        "message": f"Found {len(pending)} pending task(s)" + (f" for {agent_id}" if agent_id else ""),
        "pending_tasks": pending,
        "task_count": len(pending),
        "agent_id": agent_id,
        "CRITICAL_REMINDER": "🚨 YOU MUST CALL log_task_completion FOR EACH TASK 🚨"
    }


def mark_task_in_progress(params):
    """
    Mark a queued task as in_progress.

    IMPORTANT: This sets 'processing_started_at' which is used for ACTUAL execution time calculation.
    In parallel execution, 'started_at' gets set when all tasks are pulled from queue simultaneously,
    but 'processing_started_at' records when Claude ACTUALLY starts working on this specific task.
    """
    task_id = params.get("task_id")

    if not task_id:
        return {"status": "error", "message": "❌ Missing required field: task_id"}

    queue_file = os.path.join(os.getcwd(), "data/claude_task_queue.json")

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

    if current_status not in ["queued", "in_progress"]:
        return {
            "status": "error",
            "message": f"❌ Task '{task_id}' cannot be marked in_progress (current: {current_status})"
        }

    now = datetime.now().isoformat()
    queue["tasks"][task_id]["status"] = "in_progress"

    # started_at = when task entered queue processing
    if "started_at" not in queue["tasks"][task_id]:
        queue["tasks"][task_id]["started_at"] = now

    # processing_started_at = when Claude ACTUALLY starts working on this task
    # This is the key timestamp for accurate execution time in parallel runs
    queue["tasks"][task_id]["processing_started_at"] = now
    started_at = queue["tasks"][task_id]["started_at"]

    try:
        with open(queue_file, 'w', encoding='utf-8') as f:
            json.dump(queue, f, indent=2)
    except Exception as e:
        return {"status": "error", "message": f"❌ Error writing queue: {str(e)}"}

    # Write stub to results file
    results_file = os.path.join(os.getcwd(), "data/claude_task_results.json")
    try:
        if os.path.exists(results_file):
            with open(results_file, 'r', encoding='utf-8') as f:
                results = json.load(f)
        else:
            results = {"results": {}}

        if task_id not in results.get("results", {}):
            results["results"][task_id] = {
                "status": "in_progress",
                "started_at": started_at,
                "processing_started_at": now,
                "description": queue["tasks"][task_id].get("description", ""),
                "batch_id": queue["tasks"][task_id].get("batch_id")
            }
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not write started_at stub: {e}", file=sys.stderr)

    return {
        "status": "success",
        "message": f"✅ Task '{task_id}' marked as in_progress",
        "processing_started_at": now
    }


def execute_queue(params):
    """
    Spawns Claude Code session(s) to process queued tasks.
    
    MODES:
    1. Sequential (default): One agent processes all tasks
    2. Single agent: agent_id param filters to specific agent's tasks
    3. Parallel: parallel param spawns multiple agents
    
    PRISON GUARD: Hard limit of 3 agents max, enforced here.
    """
    # CRITICAL: Check if already inside Claude Code
    if os.environ.get("CLAUDECODE"):
        return {
            "status": "error",
            "message": "❌ Cannot spawn nested Claude Code session. Process tasks directly.",
            "hint": "Read tasks from data/claude_task_queue.json and process them here"
        }

    agent_id = params.get("agent_id")
    parallel = params.get("parallel", 1)
    
    # PRISON GUARD: Enforce max agents
    parallel = min(max(parallel, 1), MAX_PARALLEL_AGENTS)
    
    # Check current running agents
    if not enforce_agent_limit():
        running = count_running_agents()
        return {
            "status": "blocked",
            "message": f"❌ Prison guard: {running} agents already running (max {MAX_PARALLEL_AGENTS})",
            "hint": "Wait for current agents to complete or kill them with kill_agents()"
        }

    # LOCKFILE CHECK
    lockfile = os.path.join(os.getcwd(), "data/execute_queue.lock")

    if os.path.exists(lockfile):
        should_remove = False
        try:
            with open(lockfile, 'r') as f:
                lock_data = json.load(f)
                pid = lock_data.get("pid")
                pids = lock_data.get("pids", [])
                created_at = lock_data.get("created_at")

            # Check timestamp - auto-remove locks older than 30 minutes
            if created_at:
                try:
                    lock_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    age_minutes = (datetime.now() - lock_time.replace(tzinfo=None)).total_seconds() / 60
                    if age_minutes > 30:
                        print(f"⚠️ Removing stale lockfile ({age_minutes:.1f} min old)", file=sys.stderr)
                        should_remove = True
                except:
                    pass

            # Check if any PIDs still alive
            if not should_remove:
                all_pids = pids if pids else ([pid] if pid else [])
                any_alive = False
                for p in all_pids:
                    try:
                        os.kill(p, 0)
                        any_alive = True
                        break
                    except OSError:
                        pass
                
                if any_alive:
                    return {
                        "status": "already_running",
                        "message": f"⏳ Queue execution already in progress",
                        "hint": "Wait for current batch to complete"
                    }
                else:
                    should_remove = True

            if should_remove:
                os.remove(lockfile)

        except Exception as e:
            print(f"Warning: Could not read lockfile: {e}", file=sys.stderr)
            try:
                os.remove(lockfile)
            except:
                pass

    # CHECK for queued tasks
    queue_file = os.path.join(os.getcwd(), "data/claude_task_queue.json")
    if not os.path.exists(queue_file):
        return {
            "status": "success",
            "message": "✅ No tasks in queue",
            "task_count": 0
        }

    try:
        with open(queue_file, 'r', encoding='utf-8') as f:
            queue = json.load(f)
    except Exception as e:
        return {"status": "error", "message": f"❌ Error reading queue: {str(e)}"}

    # Count queued tasks
    task_count = sum(1 for task_data in queue.get("tasks", {}).values()
                     if task_data.get("status") == "queued")

    if task_count == 0:
        return {
            "status": "success",
            "message": "✅ No pending tasks",
            "task_count": 0
        }

    # Setup environment
    base_env = os.environ.copy()
    base_env.pop('ANTHROPIC_API_KEY', None)
    base_env.pop('CLAUDECODE', None)  # CRITICAL: Remove so spawned process doesn't think it's nested

    spawned = []
    pids = []

    # PARALLEL MODE
    if parallel > 1:
        # Group tasks by agent_id to count per agent
        agent_tasks = {}
        for task_id, task_data in queue.get("tasks", {}).items():
            if task_data.get("status") == "queued":
                aid = task_data.get("agent_id", "agent_1")
                if aid not in agent_tasks:
                    agent_tasks[aid] = []
                agent_tasks[aid].append(task_id)

        # Limit to max agents
        agent_ids = sorted(agent_tasks.keys())[:MAX_PARALLEL_AGENTS]

        for aid in agent_ids:
            task_list = agent_tasks.get(aid, [])
            if not task_list:
                continue

            # Each agent uses MAIN queue file but filters by agent_id
            prompt = f"""You are {aid}. Process ONLY your assigned tasks.

⚠️ CRITICAL: You are {aid}. Only process tasks assigned to you.

1. Get YOUR tasks only:
   python3 execution_hub.py execute_task --params '{{"tool_name": "claude_assistant", "action": "process_queue", "params": {{"agent_id": "{aid}"}}}}'

2. For each task returned, execute it
3. Log completion for each task via execution_hub.py
4. Exit when done

Project context in .claude/CLAUDE.md"""

            try:
                log_file = open(os.path.join(os.getcwd(), f"data/claude_execution_{aid}.log"), "w")
                process = subprocess.Popen(
                    ["claude", "-p", prompt, "--permission-mode", "acceptEdits", "--allowedTools", "Bash,Read,Write,Edit"],
                    env=base_env, cwd=os.getcwd(), stdout=log_file, stderr=subprocess.STDOUT, start_new_session=True
                )
                spawned.append({"agent_id": aid, "pid": process.pid, "tasks": len(task_list)})
                pids.append(process.pid)
                print(f"🚀 Spawned {aid} with PID {process.pid} for {len(task_list)} tasks", file=sys.stderr)
            except Exception as e:
                print(f"❌ Failed to spawn {aid}: {e}", file=sys.stderr)

    # SINGLE AGENT MODE (with optional agent_id filter)
    else:
        if agent_id:
            prompt = f"""You are {agent_id}. Process ONLY tasks assigned to {agent_id}.

Call process_queue with agent_id="{agent_id}" to get YOUR tasks:
python3 execution_hub.py execute_task --params '{{"tool_name": "claude_assistant", "action": "process_queue", "params": {{"agent_id": "{agent_id}"}}}}'

1. Get YOUR tasks only
2. Execute each task
3. Log completion for each
4. rm data/execute_queue.lock when done

Project context in .claude/CLAUDE.md"""
        else:
            prompt = """Process all tasks in data/claude_task_queue.json.

🚨 LOGGING IS MANDATORY - call log_task_completion for EVERY task 🚨

1. python3 execution_hub.py execute_task --params '{"tool_name": "claude_assistant", "action": "process_queue", "params": {}}'
2. For each task, execute it
3. Log completion for each task
4. rm data/execute_queue.lock when done

Project context in .claude/CLAUDE.md"""

        try:
            log_file = open(os.path.join(os.getcwd(), "data/claude_execution.log"), "w")
            process = subprocess.Popen(
                ["claude", "-p", prompt, "--permission-mode", "acceptEdits", "--allowedTools", "Bash,Read,Write,Edit"],
                env=base_env, cwd=os.getcwd(), stdout=log_file, stderr=subprocess.STDOUT, start_new_session=True
            )
            spawned.append({"pid": process.pid, "tasks": task_count, "agent_id": agent_id})
            pids.append(process.pid)
        except Exception as e:
            return {"status": "error", "message": f"❌ Failed to spawn Claude Code: {str(e)}"}

    # CREATE LOCKFILE
    try:
        with open(lockfile, 'w') as f:
            json.dump({
                "created_at": datetime.now().isoformat(),
                "pid": pids[0] if len(pids) == 1 else None,
                "pids": pids,
                "task_count": task_count,
                "parallel": parallel,
                "agents": [s.get("agent_id") for s in spawned if s.get("agent_id")]
            }, f, indent=2)
        print(f"🔒 Created lockfile for {task_count} task(s)", file=sys.stderr)
    except Exception as e:
        print(f"Warning: Could not create lockfile: {e}", file=sys.stderr)

    return {
        "status": "task_started",
        "message": f"✅ {len(spawned)} agent(s) started to process {task_count} task(s)",
        "task_count": task_count,
        "parallel": parallel,
        "agents": spawned
    }


def kill_agents(params):
    """Kill all running parallel agents and clean up lockfile."""
    lockfile = os.path.join(os.getcwd(), "data/execute_queue.lock")
    
    killed = []
    failed = []
    
    if os.path.exists(lockfile):
        try:
            with open(lockfile, 'r') as f:
                lock_data = json.load(f)
            
            pids = lock_data.get("pids", [])
            if not pids and lock_data.get("pid"):
                pids = [lock_data["pid"]]
            
            for pid in pids:
                try:
                    os.kill(pid, 9)  # SIGKILL
                    killed.append(pid)
                except OSError:
                    failed.append(pid)
            
            os.remove(lockfile)
            
        except Exception as e:
            return {"status": "error", "message": f"❌ Error: {e}"}
    
    # Also try to kill any claude processes
    try:
        subprocess.run(["pkill", "-f", "claude.*-p"], capture_output=True, timeout=5)
    except:
        pass
    
    return {
        "status": "success",
        "message": f"✅ Killed {len(killed)} agent(s)",
        "killed_pids": killed,
        "already_dead": failed
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

    # Normalize status: accept "completed", "complete", "done" as success
    status_lower = status.lower().strip()
    if status_lower in ["completed", "complete", "done"]:
        status = "done"
    else:
        # Anything else is treated as an error
        status = "error"

    # REMOVE completed task from queue
    task_description = None
    task_batch_id = None
    task_started_at = None
    task_created_at = None
    task_processing_started_at = None  # Actual work start time (key for parallel execution)
    queue_file = os.path.join(os.getcwd(), "data/claude_task_queue.json")

    if os.path.exists(queue_file):
        try:
            with open(queue_file, 'r', encoding='utf-8') as f:
                queue = json.load(f)

            if task_id in queue.get("tasks", {}):
                task_description = queue["tasks"][task_id].get("description", "")
                task_batch_id = queue["tasks"][task_id].get("batch_id")
                task_started_at = queue["tasks"][task_id].get("started_at")
                task_created_at = queue["tasks"][task_id].get("created_at")
                task_processing_started_at = queue["tasks"][task_id].get("processing_started_at")

                del queue["tasks"][task_id]
                safe_write_queue(queue_file, queue)
                print(f"✅ Removed '{task_id}' from queue (completed)", file=sys.stderr)
        except Exception as e:
            print(f"Warning: Could not update queue: {e}", file=sys.stderr)

    # Try to get timestamps from results stub if not in queue
    if execution_time == 0 and not task_processing_started_at:
        results_file = os.path.join(os.getcwd(), "data/claude_task_results.json")
        if os.path.exists(results_file):
            try:
                with open(results_file, 'r', encoding='utf-8') as f:
                    existing_results = json.load(f)
                if task_id in existing_results.get("results", {}):
                    stub = existing_results["results"][task_id]
                    # Prefer processing_started_at (actual work time) over started_at (queue time)
                    task_processing_started_at = stub.get("processing_started_at")
                    if not task_started_at:
                        task_started_at = stub.get("started_at")
                    if not task_description:
                        task_description = stub.get("description")
                    if not task_batch_id:
                        task_batch_id = stub.get("batch_id")
            except:
                pass

    # Calculate execution_time if not provided
    # PRIORITY: processing_started_at > started_at > created_at
    # This ensures parallel tasks report ACTUAL work time, not queue wait time
    if execution_time == 0:
        timestamp = task_processing_started_at or task_started_at or task_created_at
        if timestamp:
            try:
                started_str = timestamp.replace('Z', '').replace('+00:00', '')
                started = datetime.fromisoformat(started_str)
                completed = datetime.now()
                execution_time = (completed - started).total_seconds()
                time_source = "processing_started_at" if task_processing_started_at else ("started_at" if task_started_at else "created_at")
                print(f"⏱️ Calculated execution time: {execution_time:.2f}s (from {time_source})", file=sys.stderr)
            except Exception as e:
                print(f"Warning: Could not calculate execution time: {e}", file=sys.stderr)

    # Write result
    results_file = os.path.join(os.getcwd(), "data/claude_task_results.json")
    archive_dir = os.path.join(os.getcwd(), "data/task_archive")

    if os.path.exists(results_file):
        try:
            with open(results_file, 'r', encoding='utf-8') as f:
                results = json.load(f)
        except:
            results = {"results": {}}
    else:
        results = {"results": {}}

    # Archive old results if count > 10
    if len(results.get("results", {})) > 10:
        try:
            os.makedirs(archive_dir, exist_ok=True)

            sorted_results = sorted(
                results["results"].items(),
                key=lambda x: x[1].get("completed_at", ""),
                reverse=False
            )

            to_archive = dict(sorted_results[:-10])
            to_keep = dict(sorted_results[-10:])

            if to_archive:
                archive_file = os.path.join(archive_dir, "tasks.jsonl")
                with open(archive_file, 'a', encoding='utf-8') as f:
                    for archived_task_id, result_data in to_archive.items():
                        # Convert to simplified tagged format
                        desc = result_data.get('description', '')
                        summary = desc.replace('\n', ' ')[:100].strip()
                        if len(desc) > 100:
                            summary += '...'

                        # Extract and map tags
                        tags = result_data.get('project_tags', [])
                        tag_map = {'war-plan': 'orchestrate-blitzkrieg', 'blog': 'blogs'}
                        mapped_tags = [f'#{tag_map.get(t, t)}' for t in tags]

                        # Infer category
                        desc_lower = desc.lower()
                        if 'blog' in desc_lower or 'chronicle' in desc_lower:
                            category = 'content'
                        elif 'email' in desc_lower or 'inbox' in desc_lower:
                            category = 'email'
                        elif 'outline' in result_data.get('tool', '').lower():
                            category = 'docs'
                        elif 'automation' in desc_lower:
                            category = 'automation'
                        elif 'test' in archived_task_id.lower():
                            category = 'testing'
                        else:
                            category = 'general'

                        archived_entry = {
                            'task_id': archived_task_id,
                            'summary': summary,
                            'completed': result_data.get('completed_at', 'unknown'),
                            'tag': ' '.join(mapped_tags),
                            'category': category
                        }
                        f.write(json.dumps(archived_entry) + '\n')

                results["results"] = to_keep
                print(f"📦 Archived {len(to_archive)} old results", file=sys.stderr)
        except Exception as e:
            print(f"Warning: Could not archive old results: {e}", file=sys.stderr)

    if not output_summary:
        output_summary = "Task completed" if status == "done" else "Task failed"

    # Calculate batch position
    is_first_task_in_batch = False
    batch_position = 0

    if task_batch_id:
        completed_in_batch = 0
        for tid, result in results.get("results", {}).items():
            if result.get("batch_id") == task_batch_id:
                completed_in_batch += 1

        is_first_task_in_batch = (completed_in_batch == 0)
        batch_position = completed_in_batch + 1

    # Extract project tags from task description using regex
    project_tags = []
    if task_description:
        project_tags = re.findall(r'#([\w-]+)', task_description)

    # Add result
    results["results"][task_id] = {
        "status": status,
        "description": task_description if task_description else output_summary,
        "completed_at": datetime.now().isoformat(),
        "execution_time_seconds": round(execution_time, 2),
        "actions_taken": actions_taken,
        "output": output,
        "output_summary": output_summary,
        "errors": errors,
        "project_tags": project_tags
    }

    # Include processing_started_at for transparency on parallel execution timing
    if task_processing_started_at:
        results["results"][task_id]["processing_started_at"] = task_processing_started_at
    if task_started_at:
        results["results"][task_id]["started_at"] = task_started_at

    if task_batch_id:
        results["results"][task_id]["batch_id"] = task_batch_id
        results["results"][task_id]["batch_position"] = batch_position

    print(f"📝 Logged task '{task_id}' completion to results file", file=sys.stderr)

    try:
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
    except Exception as e:
        return {"status": "error", "message": f"❌ Error writing results: {str(e)}"}

    # FORM-TO-OUTPUT PATTERN: Write output to semantic_memory/results/{request_id}.json
    # This enables HTML forms to poll for results directly
    if task_description and "REQUEST_ID:" in task_description:
        try:
            # Extract request_id from task description
            request_id_match = re.search(r'REQUEST_ID:\s*(\S+)', task_description)
            if request_id_match:
                request_id = request_id_match.group(1).strip()
                results_dir = os.path.join(os.getcwd(), "semantic_memory", "results")
                os.makedirs(results_dir, exist_ok=True)
                result_file_path = os.path.join(results_dir, f"{request_id}.json")

                # Write the output in format HTML expects
                result_data = {
                    "status": "complete",
                    "type": task_id,
                    "output": output if isinstance(output, str) else output_summary or str(output)
                }

                with open(result_file_path, 'w', encoding='utf-8') as f:
                    json.dump(result_data, f, indent=2)

                print(f"📄 Wrote form-to-output result to {result_file_path}", file=sys.stderr)
        except Exception as e:
            print(f"Warning: Could not write form-to-output result: {e}", file=sys.stderr)

    # Merge token telemetry if available
    telemetry_file = os.path.join(os.getcwd(), "data", "last_execution_telemetry.json")

    if os.path.exists(telemetry_file):
        try:
            with open(telemetry_file, 'r', encoding='utf-8') as f:
                telemetry_data = json.load(f)

            raw_input_tokens = telemetry_data.get("tokens_raw_input", 0)
            output_tokens = telemetry_data.get("tokens_output", 0)
            cache_read_tokens = telemetry_data.get("tokens_cache_read", 0)
            actual_cost = raw_input_tokens + output_tokens

            if raw_input_tokens or output_tokens:
                results["results"][task_id]["tokens"] = {
                    "input": raw_input_tokens,
                    "output": output_tokens,
                    "total": actual_cost,
                    "cache_read": cache_read_tokens
                }
                results["results"][task_id]["token_cost"] = actual_cost

            if telemetry_data.get("tool"):
                results["results"][task_id]["tool"] = telemetry_data["tool"]
            if telemetry_data.get("action"):
                results["results"][task_id]["action"] = telemetry_data["action"]

            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2)

            os.remove(telemetry_file)

        except Exception as e:
            print(f"Warning: Could not merge telemetry data: {e}", file=sys.stderr)

    return {
        "status": "success",
        "message": f"✅ Task '{task_id}' completion logged with status: {status}",
        "output_summary": output_summary
    }


def batch_assign_tasks(params):
    """
    Assign multiple tasks at once with optional parallel execution.

    Required:
    - tasks: list of task dicts

    Optional:
    - parallel: number of agents (1-3, default 1)
    """
    tasks = params.get("tasks")
    parallel = min(max(params.get("parallel", 1), 1), MAX_PARALLEL_AGENTS)

    if not tasks:
        return {"status": "error", "message": "❌ Missing required field: tasks"}

    if not isinstance(tasks, list):
        return {"status": "error", "message": "❌ tasks must be a list"}

    if len(tasks) == 0:
        return {"status": "error", "message": "❌ tasks list is empty"}

    results = []
    success_count = 0
    failed_count = 0

    for i, task in enumerate(tasks):
        task_id = task.get("task_id")

        if not isinstance(task, dict):
            results.append({"index": i, "task_id": None, "status": "error", "message": "❌ Task must be a dict"})
            failed_count += 1
            continue

        if not task_id:
            results.append({"index": i, "task_id": None, "status": "error", "message": "❌ Missing task_id"})
            failed_count += 1
            continue

        task_params = task.copy()
        task_params["auto_execute"] = False

        # Assign agent_id for parallel execution
        if parallel > 1:
            agent_num = (i % parallel) + 1
            task_params["agent_id"] = f"agent_{agent_num}"

        try:
            result = assign_task(task_params)
            if result.get("status") == "success":
                success_count += 1
                agent_label = f" ({task_params.get('agent_id')})" if parallel > 1 else ""
                results.append({
                    "index": i,
                    "task_id": task_id,
                    "status": "success",
                    "message": f"✅ Task {task_id} queued{agent_label}"
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

    summary = f"Assigned {success_count}/{len(tasks)} tasks"
    if failed_count > 0:
        summary += f" ({failed_count} failed)"

    # Auto-execute after batch assignment
    execution = None
    if success_count > 0 and not os.environ.get("CLAUDECODE"):
        execution = execute_queue({"parallel": parallel})

    return {
        "status": "success" if success_count > 0 else "error",
        "message": f"✅ {summary}" if success_count > 0 else f"❌ {summary}",
        "success_count": success_count,
        "failed_count": failed_count,
        "total_tasks": len(tasks),
        "details": results,
        "parallel": parallel,
        "execution": execution
    }


def get_recent_tasks(params):
    """Get the most recent N completed tasks."""
    limit = params.get("limit", 10)

    results_file = os.path.join(os.getcwd(), "data/claude_task_results.json")

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

    sorted_tasks = sorted(
        completed_tasks.items(),
        key=lambda x: x[1].get("completed_at", ""),
        reverse=True
    )[:limit]

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


def parse_tasks_from_doc(params):
    """Parse tasks from markdown document text."""
    doc_text = params.get("doc_text", "")

    if not doc_text:
        return {"status": "error", "message": "❌ Missing required field: doc_text"}

    tasks = []
    lines = doc_text.split('\n')
    current_task = None
    current_lines = []

    for line in lines:
        is_header = line.startswith('#')
        is_bullet = line.startswith('- ') and not line.startswith('  ')

        if is_header or is_bullet:
            if current_task:
                tasks.append({
                    "description": '\n'.join(current_lines).strip(),
                    "raw_header": current_task
                })

            current_task = line.lstrip('#- ').strip()
            current_lines = [current_task]
        elif current_task and line.strip():
            current_lines.append(line)

    if current_task:
        tasks.append({
            "description": '\n'.join(current_lines).strip(),
            "raw_header": current_task
        })

    return {
        "status": "success",
        "message": f"✅ Parsed {len(tasks)} task(s) from document",
        "tasks": tasks,
        "task_count": len(tasks)
    }


def self_assign_from_doc(params):
    """
    One-command task import from Outline doc.

    Required:
    - doc_id: Outline document ID to fetch tasks from

    Optional:
    - test_mode: if true, writes to claude_test_task_queue.json (default: false)
    - parallel: number of agents for parallel execution (1-3, default: 3)
    """
    doc_id = params.get("doc_id", "8398b552-a586-4c11-9821-cc85844e9156")
    test_mode = params.get("test_mode", False)
    parallel = min(max(params.get("parallel", 3), 1), MAX_PARALLEL_AGENTS)

    # Fetch document from Outline
    try:
        result = subprocess.run(
            ["python3", "execution_hub.py", "execute_task", "--params",
             json.dumps({"tool_name": "outline_editor", "action": "get_doc", "params": {"doc_id": doc_id}})],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=os.getcwd()
        )

        if result.returncode != 0:
            return {"status": "error", "message": f"❌ Failed to fetch doc: {result.stderr}"}

        doc_response = json.loads(result.stdout)
        if doc_response.get("status") == "error":
            return {"status": "error", "message": doc_response.get("message", "Failed to fetch doc")}

        doc_text = doc_response.get("data", {}).get("text", "")
        if not doc_text:
            return {"status": "error", "message": "❌ Document has no text content"}

    except Exception as e:
        return {"status": "error", "message": f"❌ Error fetching document: {str(e)}"}

    # Parse tasks from document
    parse_result = parse_tasks_from_doc({"doc_text": doc_text})
    if parse_result.get("status") == "error":
        return parse_result

    parsed_tasks = parse_result.get("tasks", [])
    if not parsed_tasks:
        return {"status": "success", "message": "✅ No tasks found in document", "tasks_added": 0}

    # Generate task list
    tasks_to_assign = []
    task_ids = []

    for task in parsed_tasks:
        description = task.get("description", "")
        raw_header = task.get("raw_header", "")

        clean_header = re.sub(r'^\d+\.\s*', '', raw_header)
        task_id = re.sub(r'[^a-z0-9]+', '_', clean_header.lower()).strip('_')
        task_id = task_id[:50]

        tasks_to_assign.append({
            "task_id": task_id,
            "description": description,
            "context": {"source_doc": doc_id}
        })
        task_ids.append(task_id)

    # Use batch_assign_tasks
    batch_result = batch_assign_tasks({"tasks": tasks_to_assign, "parallel": parallel})

    return {
        "status": "success",
        "message": f"✅ Imported {batch_result.get('success_count', 0)} task(s) from document",
        "tasks_added": batch_result.get("success_count", 0),
        "task_ids": task_ids,
        "source_doc": doc_id,
        "test_mode": test_mode,
        "parallel": parallel
    }


def get_task_results(params):
    """Get recent task execution data with optional markdown table formatting."""
    output_format = params.get("format", "json")
    limit = params.get("limit", 10)

    results_file = os.path.join(os.getcwd(), "data/claude_task_results.json")

    if not os.path.exists(results_file):
        if output_format == "table":
            return {"status": "success", "formatted_output": "## Recent Execution Data\n\nNo task results yet."}
        else:
            return {"status": "success", "results": {}, "task_count": 0}

    try:
        with open(results_file, 'r', encoding='utf-8') as f:
            results = json.load(f)
    except Exception as e:
        return {"status": "error", "message": f"❌ Error reading results: {str(e)}"}

    all_results = results.get("results", {})

    if output_format == "json":
        return {"status": "success", "results": all_results, "task_count": len(all_results)}

    # Format as markdown table
    if not all_results:
        return {"status": "success", "formatted_output": "## Recent Execution Data\n\nNo completed tasks found."}

    sorted_tasks = sorted(
        all_results.items(),
        key=lambda x: x[1].get("completed_at", ""),
        reverse=True
    )[:limit]

    markdown_lines = ["## Recent Execution Data\n"]
    markdown_lines.append("| Task ID | Status | Execution Time |")
    markdown_lines.append("|---------|--------|----------------|")

    for task_id, task_data in sorted_tasks:
        status = task_data.get("status", "unknown")
        exec_time = task_data.get("execution_time_seconds", 0)

        if exec_time >= 60:
            time_str = f"{int(exec_time // 60)}m {int(exec_time % 60)}s"
        else:
            time_str = f"{int(exec_time)}s"

        markdown_lines.append(f"| {task_id[:30]} | {status} | {time_str} |")

    return {
        "status": "success",
        "formatted_output": "\n".join(markdown_lines),
        "task_count": len(sorted_tasks)
    }


def add_to_memory(params):
    """Adds an item to working memory."""
    key = params.get("key")
    value = params.get("value")
    mem_type = params.get("type", "note")

    if not key:
        return {"status": "error", "message": "❌ Missing required field: key"}
    if value is None:
        return {"status": "error", "message": "❌ Missing required field: value"}

    working_memory_file = os.path.join(os.getcwd(), "data/working_memory.json")
    os.makedirs(os.path.dirname(working_memory_file), exist_ok=True)

    if os.path.exists(working_memory_file):
        with open(working_memory_file, 'r', encoding='utf-8') as f:
            memory = json.load(f)
    else:
        memory = {}

    if isinstance(value, dict):
        value["updated_at"] = datetime.now().isoformat()
        if "type" not in value:
            value["type"] = mem_type

    memory[key] = value

    with open(working_memory_file, 'w', encoding='utf-8') as f:
        json.dump(memory, f, indent=2)

    return {
        "status": "success",
        "message": f"✅ Added '{key}' to working memory",
        "total_items": len(memory)
    }


def get_working_memory(params):
    """Returns current working memory contents."""
    working_memory_file = os.path.join(os.getcwd(), "data/working_memory.json")

    if not os.path.exists(working_memory_file):
        return {"status": "success", "memory": {}, "item_count": 0, "message": "Working memory is empty"}

    with open(working_memory_file, 'r', encoding='utf-8') as f:
        memory = json.load(f)

    return {"status": "success", "memory": memory, "item_count": len(memory)}


def clear_working_memory(params):
    """Clears the working memory file."""
    working_memory_file = os.path.join(os.getcwd(), "data/working_memory.json")
    preserve_keys = params.get("preserve_keys", [])

    if not os.path.exists(working_memory_file):
        return {"status": "success", "message": "✅ Working memory already clear", "cleared": True}

    try:
        with open(working_memory_file, 'r', encoding='utf-8') as f:
            current_memory = json.load(f)

        preserved_data = {}
        if preserve_keys:
            for key in preserve_keys:
                if key in current_memory:
                    preserved_data[key] = current_memory[key]

        cleared_count = len(current_memory) - len(preserved_data)

        with open(working_memory_file, 'w', encoding='utf-8') as f:
            json.dump(preserved_data, f, indent=2)

        return {
            "status": "success",
            "message": f"✅ Working memory cleared ({cleared_count} items removed)",
            "cleared": True,
            "cleared_count": cleared_count
        }

    except Exception as e:
        return {"status": "error", "message": f"❌ Failed to clear: {str(e)}", "cleared": False}


def capture_token_telemetry(params):
    """Helper function to capture token usage telemetry."""
    tokens_input = params.get("tokens_input")
    tokens_output = params.get("tokens_output")
    task_id = params.get("task_id")

    if tokens_input is None or tokens_output is None:
        return {"status": "error", "message": "❌ Missing tokens_input and tokens_output"}

    if not task_id:
        return {"status": "error", "message": "❌ Missing task_id"}

    telemetry_file = os.path.join(os.getcwd(), "data", "last_execution_telemetry.json")

    try:
        telemetry_data = {
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
            "total_tokens": tokens_input + tokens_output,
            "tool": params.get("tool", "claude_assistant"),
            "action": params.get("action", "execute_task"),
            "task_id": task_id,
            "timestamp": datetime.now().isoformat() + "Z"
        }

        with open(telemetry_file, 'w', encoding='utf-8') as f:
            json.dump(telemetry_data, f, indent=2)

        return {
            "status": "success",
            "message": f"✅ Token telemetry captured: {tokens_input + tokens_output} total",
            "total_tokens": tokens_input + tokens_output
        }

    except Exception as e:
        return {"status": "error", "message": f"❌ Failed to write telemetry: {str(e)}"}


def infer_task_type(params):
    """Infers task type based on keyword detection."""
    task_description = params.get("task_description", "")

    if not task_description:
        return {"status": "error", "message": "❌ Missing task_description"}

    task_lower = task_description.lower()
    modules_to_load = []
    detected_keywords = []
    primary_type = "general"

    email_keywords = ['email', 'inbox', 'nylas', 'message', 'reply', 'send email']
    if any(keyword in task_lower for keyword in email_keywords):
        modules_to_load.append('email_module.json')
        detected_keywords.extend([k for k in email_keywords if k in task_lower])
        primary_type = "email"

    outline_keywords = ['outline', 'document', 'doc ', 'create doc', 'blog', 'article']
    if any(keyword in task_lower for keyword in outline_keywords):
        modules_to_load.append('outline_module.json')
        detected_keywords.extend([k for k in outline_keywords if k in task_lower])
        if primary_type == "general":
            primary_type = "outline"

    podcast_keywords = ['podcast', 'episode', 'transcript', 'audio', 'midroll']
    if any(keyword in task_lower for keyword in podcast_keywords):
        modules_to_load.append('podcast_module.json')
        detected_keywords.extend([k for k in podcast_keywords if k in task_lower])
        if primary_type == "general":
            primary_type = "podcast"

    tool_keywords = ['build tool', 'build function', 'new tool', 'implement tool', 'create tool']
    if 'podcast_module.json' not in modules_to_load:
        if any(keyword in task_lower for keyword in tool_keywords):
            modules_to_load.append('tool_building_module.json')
            detected_keywords.extend([k for k in tool_keywords if k in task_lower])
            if primary_type == "general":
                primary_type = "tool_building"

    return {
        "status": "success",
        "task_type": primary_type,
        "modules": modules_to_load,
        "keywords_detected": list(set(detected_keywords)),
        "fallback_to_full": len(modules_to_load) == 0
    }


def get_task_context(params):
    """Combines core profile + task-specific modules for selective loading."""
    task_description = params.get("task_description", "")

    if not task_description:
        return {"status": "error", "message": "❌ Missing task_description"}

    try:
        core_profile_file = os.path.join(os.getcwd(), ".claude/orchestrate_profile.json")
        if not os.path.exists(core_profile_file):
            return {"status": "error", "message": f"❌ Core profile not found"}

        with open(core_profile_file, 'r', encoding='utf-8') as f:
            core_profile = json.load(f)

        inference = infer_task_type({"task_description": task_description})
        if inference.get("status") == "error":
            return inference

        modules_to_load = inference.get("modules", [])
        loaded_modules = []
        modules_dir = os.path.join(os.getcwd(), ".claude/modules")

        for module_file in modules_to_load:
            module_path = os.path.join(modules_dir, module_file)
            if os.path.exists(module_path):
                with open(module_path, 'r', encoding='utf-8') as f:
                    loaded_modules.append(json.load(f))

        return {
            "status": "success",
            "message": f"✅ Loaded core profile + {len(loaded_modules)} module(s)",
            "context": {
                "core_profile": core_profile,
                "specialized_modules": loaded_modules,
                "task_type": inference.get("task_type", "general")
            }
        }

    except Exception as e:
        return {"status": "error", "message": f"❌ Failed to load task context: {str(e)}"}


def archive_thread_logs(params):
    """Archives thread logs older than specified retention period."""
    retention_days = params.get("retention_days", 30)
    source_file = params.get("source_file", "data/thread_log.json")
    archive_file = params.get("archive_file", "data/thread_log_archive.json")

    source_path = os.path.join(os.getcwd(), source_file)
    archive_path = os.path.join(os.getcwd(), archive_file)

    try:
        if not os.path.exists(source_path):
            return {"status": "success", "message": "✅ No thread log found", "archived_count": 0, "retained_count": 0}

        with open(source_path, 'r', encoding='utf-8') as f:
            thread_log = json.load(f)

        if os.path.exists(archive_path):
            with open(archive_path, 'r', encoding='utf-8') as f:
                archive = json.load(f)
            if "entries" not in archive:
                archive["entries"] = {}
        else:
            archive = {"entries": {}}

        cutoff_date = datetime.now() - timedelta(days=retention_days)
        entries = thread_log.get("entries", {})
        old_entries = {}
        recent_entries = {}

        for entry_key, entry_data in entries.items():
            timestamp_str = entry_data.get("timestamp", "")
            try:
                entry_date = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                if entry_date < cutoff_date:
                    old_entries[entry_key] = entry_data
                else:
                    recent_entries[entry_key] = entry_data
            except:
                recent_entries[entry_key] = entry_data

        if old_entries:
            archive["entries"].update(old_entries)
            with open(archive_path, 'w', encoding='utf-8') as f:
                json.dump(archive, f, indent=2)

        thread_log["entries"] = recent_entries
        with open(source_path, 'w', encoding='utf-8') as f:
            json.dump(thread_log, f, indent=2)

        return {
            "status": "success",
            "message": "✅ Thread log archival complete",
            "archived_count": len(old_entries),
            "retained_count": len(recent_entries)
        }

    except Exception as e:
        return {"status": "error", "message": f"❌ Failed to archive: {str(e)}"}


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()

    params = json.loads(args.params) if args.params else {}

    actions = {
        'assign_task': assign_task,
        'assign_demo_task': assign_demo_task,
        'batch_assign_tasks': batch_assign_tasks,
        'check_task_status': check_task_status,
        'get_task_result': get_task_result,
        'get_task_results': get_task_results,
        'get_recent_tasks': get_recent_tasks,
        'get_all_results': get_all_results,
        'ask_claude': ask_claude,
        'cancel_task': cancel_task,
        'update_task': update_task,
        'process_queue': process_queue,
        'execute_queue': execute_queue,
        'mark_task_in_progress': mark_task_in_progress,
        'log_task_completion': log_task_completion,
        'kill_agents': kill_agents,
        'capture_token_telemetry': capture_token_telemetry,
        'add_to_memory': add_to_memory,
        'get_working_memory': get_working_memory,
        'clear_working_memory': clear_working_memory,
        'archive_thread_logs': archive_thread_logs,
        'infer_task_type': infer_task_type,
        'get_task_context': get_task_context,
        'parse_tasks_from_doc': parse_tasks_from_doc,
        'self_assign_from_doc': self_assign_from_doc
    }

    if args.action in actions:
        result = actions[args.action](params)
    else:
        result = {
            'status': 'error',
            'message': f'Unknown action: {args.action}',
            'available_actions': list(actions.keys())
        }

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()