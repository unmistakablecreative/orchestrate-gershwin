#!/usr/bin/env python3
"""
Claude Assistant - Fixed Version with Proper Agent Assignment and File Locking
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
import fcntl
from datetime import datetime, timedelta


# === 7-QUEUE PARALLEL EXECUTION SYSTEM ===
NUM_QUEUES = 7

def get_queue_file_for_task(task_id):
    """Hash task_id to determine which queue file to use (1, 2, or 3)"""
    queue_num = (hash(task_id) % NUM_QUEUES) + 1
    return os.path.join(os.getcwd(), f"data/claude_task_q{queue_num}.json")

def get_all_queue_files():
    """Return list of all queue file paths"""
    return [os.path.join(os.getcwd(), f"data/claude_task_q{i}.json") for i in range(1, NUM_QUEUES + 1)]


def safe_read_queue_with_lock(queue_file):
    """Read queue file with exclusive lock to prevent race conditions"""
    if not os.path.exists(queue_file):
        return {"tasks": {}}
    
    with open(queue_file, 'r+', encoding='utf-8') as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            queue = json.load(f)
        except:
            queue = {"tasks": {}}
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    
    return queue


def safe_write_queue_with_lock(queue_file, queue_data):
    """Write queue file with exclusive lock"""
    os.makedirs(os.path.dirname(queue_file), exist_ok=True)
    
    mode = 'r+' if os.path.exists(queue_file) else 'w+'
    with open(queue_file, mode, encoding='utf-8') as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        f.seek(0)
        f.truncate()
        json.dump(queue_data, f, indent=2)
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


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


def validate_task_format(description):
    """
    Validate task description follows OrchestrateOS format.
    Returns (is_valid, warnings) tuple.
    Warnings are informational, not blocking.
    """
    warnings = []

    if "@" in description and "`@" not in description:
        warnings.append("Trigger found but not wrapped in backticks - consider `@trigger` format")

    if "Expected output:" not in description and "expected output:" not in description:
        if len(description) > 100:
            warnings.append("Consider adding 'Expected output:' line for clarity")

    fluff_patterns = ["please ", "could you ", "would you ", "if you could"]
    for pattern in fluff_patterns:
        if pattern in description.lower():
            warnings.append(f"Contains '{pattern}' - tasks should be direct commands")
            break

    return True, warnings


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

    if not task_id:
        task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    if not description:
        return {"status": "error", "message": "❌ Missing required field: description"}

    _, format_warnings = validate_task_format(description)

    if not batch_id:
        batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{task_id[:8]}"

    context = params.get("context", {})
    if not context:
        context = {}

    context["create_output_doc"] = create_output_doc

    if create_output_doc:
        context["hint"] = "Create a document for this task using execution_hub.py with doc_editor.create_doc"

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

    skills_dir = os.path.expanduser("~/.claude/skills")
    if os.path.exists(skills_dir):
        try:
            skill_names = os.listdir(skills_dir)
            matched_skill = None

            for skill_name in skill_names:
                if skill_name.lower() in description_lower:
                    skill_md = os.path.join(skills_dir, skill_name, "SKILL.md")
                    if os.path.exists(skill_md):
                        matched_skill = skill_name
                        break

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

            if matched_skill:
                skill_md = os.path.join(skills_dir, matched_skill, "SKILL.md")
                with open(skill_md, 'r', encoding='utf-8') as f:
                    skill_content = f.read()
                description = f"{description}\n\n--- SKILL: {matched_skill} ---\n{skill_content}\n\nFOLLOW THE SKILL INSTRUCTIONS ABOVE. DO NOT DEVIATE."
        except Exception as e:
            print(f"Warning: Could not load skills: {e}", file=sys.stderr)

    # === CASCADE TYPE HANDLING ===
    # If cascade_type is provided, spawn subtasks instead of queuing the parent task
    cascade_type = params.get("cascade_type")
    if cascade_type:
        cascade_file = os.path.join(os.getcwd(), "data/cascade_configs.json")
        if not os.path.exists(cascade_file):
            return {"status": "error", "message": f"❌ Cascade config file not found: {cascade_file}"}

        try:
            with open(cascade_file, 'r', encoding='utf-8') as f:
                cascade_configs = json.load(f)
        except Exception as e:
            return {"status": "error", "message": f"❌ Error reading cascade config: {str(e)}"}

        cascade_config = cascade_configs.get(cascade_type)
        if not cascade_config:
            return {"status": "error", "message": f"❌ Unknown cascade_type: {cascade_type}. Available: {list(cascade_configs.keys())}"}

        # Extract doc_id and campaign_id from params/context
        doc_id = params.get("doc_id") or context.get("doc_id", "")
        campaign_id = params.get("campaign_id") or context.get("campaign_id", "")

        if not doc_id or not campaign_id:
            return {"status": "error", "message": "❌ cascade_type requires doc_id and campaign_id in params or context"}

        subtasks = cascade_config.get("subtasks", [])
        if not subtasks:
            return {"status": "error", "message": f"❌ No subtasks defined for cascade_type: {cascade_type}"}

        spawned_task_ids = []
        cascade_batch_id = f"cascade_{cascade_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

        # For blog_cascade: spawn score+images first, delay 45s, then spawn revise
        # This ensures scoring completes and writes blog_revisions.json before revise starts
        first_batch = []  # score, images (parallel)
        delayed_batch = []  # revise (after 45s delay)

        for subtask in subtasks:
            subtask_id_name = subtask.get("id", "")
            if subtask_id_name == "revise":
                delayed_batch.append(subtask)
            else:
                first_batch.append(subtask)

        # Queue first batch (score + images)
        for i, subtask in enumerate(first_batch):
            subtask_desc = subtask.get("description", "")
            subtask_desc = subtask_desc.replace("{doc_id}", doc_id)
            subtask_desc = subtask_desc.replace("{campaign_id}", campaign_id)

            subtask_id = f"{cascade_batch_id}_{subtask.get('id', str(i))}"
            subtask_priority = subtask.get("priority", "high")

            subtask_result = assign_task({
                "task_id": subtask_id,
                "description": subtask_desc,
                "priority": subtask_priority,
                "context": {"doc_id": doc_id, "campaign_id": campaign_id, "cascade_batch": cascade_batch_id},
                "batch_id": cascade_batch_id,
                "agent_id": f"agent_{(i % 3) + 1}",
                "auto_execute": False
            })

            if subtask_result.get("status") == "success":
                spawned_task_ids.append(subtask_id)
            else:
                print(f"Warning: Failed to queue subtask {subtask_id}: {subtask_result}", file=sys.stderr)

        # Queue delayed batch (revise) - these tasks also go to queue but we spawn them later
        delayed_task_ids = []
        for i, subtask in enumerate(delayed_batch):
            subtask_desc = subtask.get("description", "")
            subtask_desc = subtask_desc.replace("{doc_id}", doc_id)
            subtask_desc = subtask_desc.replace("{campaign_id}", campaign_id)

            subtask_id = f"{cascade_batch_id}_{subtask.get('id', str(i + len(first_batch)))}"
            subtask_priority = subtask.get("priority", "high")

            subtask_result = assign_task({
                "task_id": subtask_id,
                "description": subtask_desc,
                "priority": subtask_priority,
                "context": {"doc_id": doc_id, "campaign_id": campaign_id, "cascade_batch": cascade_batch_id},
                "batch_id": cascade_batch_id,
                "agent_id": "agent_3",
                "auto_execute": False
            })

            if subtask_result.get("status") == "success":
                spawned_task_ids.append(subtask_id)
                delayed_task_ids.append(subtask_id)
            else:
                print(f"Warning: Failed to queue subtask {subtask_id}: {subtask_result}", file=sys.stderr)

        # Spawn first batch (score + images) immediately
        if first_batch and not os.environ.get("CLAUDECODE"):
            clean_env = os.environ.copy()
            clean_env.pop('CLAUDECODE', None)
            clean_env.pop('CLAUDE_CODE_ENTRYPOINT', None)
            hub_path = os.path.join(os.path.dirname(__file__), '..', 'execution_hub.py')
            params_json = json.dumps({
                "tool_name": "claude_assistant",
                "action": "execute_queue",
                "params": {"parallel": 2}  # 2 agents for score + images
            })
            subprocess.Popen(
                ['bash', '-c', f'sleep 1.5 && python3 "{hub_path}" execute_task --params \'{params_json}\''],
                env=clean_env,
                cwd=os.path.dirname(os.path.dirname(__file__)),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )

        # Spawn delayed batch (revise) after 45 second delay
        if delayed_batch and not os.environ.get("CLAUDECODE"):
            clean_env = os.environ.copy()
            clean_env.pop('CLAUDECODE', None)
            clean_env.pop('CLAUDE_CODE_ENTRYPOINT', None)
            hub_path = os.path.join(os.path.dirname(__file__), '..', 'execution_hub.py')
            params_json = json.dumps({
                "tool_name": "claude_assistant",
                "action": "execute_queue",
                "params": {"parallel": 1}  # 1 agent for revise
            })
            # 45 second delay ensures score task has finished writing blog_revisions.json
            subprocess.Popen(
                ['bash', '-c', f'sleep 45 && python3 "{hub_path}" execute_task --params \'{params_json}\''],
                env=clean_env,
                cwd=os.path.dirname(os.path.dirname(__file__)),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )

        # Return without queuing parent task
        return {
            "status": "success",
            "message": f"✅ Cascade '{cascade_type}' triggered with {len(spawned_task_ids)} subtasks",
            "cascade_type": cascade_type,
            "cascade_batch_id": cascade_batch_id,
            "doc_id": doc_id,
            "campaign_id": campaign_id,
            "spawned_task_ids": spawned_task_ids,
            "execution": {"triggered": True, "parallel": 3}
        }

    # Use hash-based queue selection for parallel execution
    queue_file = get_queue_file_for_task(task_id)
    os.makedirs(os.path.dirname(queue_file), exist_ok=True)

    queue = safe_read_queue_with_lock(queue_file)

    now = datetime.now().isoformat()
    auto_execute = params.get("auto_execute", True)
    initial_status = "queued" if not auto_execute else "in_progress"
    task_entry = {
        "status": initial_status,
        "created_at": now,
        "started_at": now if auto_execute else None,
        "processing_started_at": now if auto_execute else None,
        "assigned_by": "GPT",
        "priority": priority,
        "description": description,
        "context": context,
        "batch_id": batch_id
    }
    if agent_id:
        task_entry["agent_id"] = agent_id
    queue["tasks"][task_id] = task_entry

    safe_write_queue_with_lock(queue_file, queue)

    # Write in_progress stub to results file only when auto-executing (single task spawn)
    # For batch tasks, the agent writes the stub when it actually starts processing
    if auto_execute:
        results_file = os.path.join(os.getcwd(), "data/claude_task_results.json")
        try:
            if os.path.exists(results_file):
                with open(results_file, "r", encoding="utf-8") as f:
                    results = json.load(f)
            else:
                results = {"results": {}}

            if task_id not in results.get("results", {}):
                stub = {
                    "status": "in_progress",
                    "started_at": now,
                    "processing_started_at": now,
                    "description": description,
                    "batch_id": batch_id
                }
                results["results"][task_id] = stub
                with open(results_file, "w", encoding="utf-8") as f:
                    json.dump(results, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not write in_progress stub: {e}", file=sys.stderr)

    execution = None
    if auto_execute:
        # Spawn Claude directly to process this specific task
        import shlex
        clean_env = os.environ.copy()
        clean_env.pop('ANTHROPIC_API_KEY', None)
        clean_env.pop('CLAUDECODE', None)
        clean_env.pop('CLAUDE_CODE_ENTRYPOINT', None)
        clean_env.pop('CLAUDE_CODE_SSE_PORT', None)
        clean_env['PATH'] = '/opt/homebrew/bin:/usr/local/bin:' + clean_env.get('PATH', '')
        
        prompt = f"""Process this single task:

Task ID: {task_id}
Description: {description}

1. Mark in progress:
   python3 execution_hub.py execute_task --params '{{"tool_name": "claude_assistant", "action": "mark_task_in_progress", "params": {{"task_id": "{task_id}"}}}}'

2. Execute the task as described

3. Log completion:
   python3 execution_hub.py execute_task --params '{{"tool_name": "claude_assistant", "action": "log_task_completion", "params": {{"task_id": "{task_id}", "status": "done", "actions_taken": "REPLACE_THIS_WITH_ACTUAL_LIST_OF_ACTIONS_YOU_TOOK"}}}}'

IMPORTANT: Replace the actions_taken placeholder above with a JSON array of strings describing what you actually did. Example: ["read file X", "modified function Y", "created doc Z"]. Do NOT pass '...' as actions_taken.

Project context in .claude/CLAUDE.md"""

        try:
            log_file = open(os.path.join(os.getcwd(), f"data/claude_execution_{task_id}.log"), "w")
            process = subprocess.Popen(
                ["/opt/homebrew/bin/claude", "--add-dir", os.getcwd(), "-p", prompt,
                 "--permission-mode", "acceptEdits", "--no-session-persistence",
                 "--allowedTools", "Bash,Read,Write,Edit"],
                env=clean_env,
                cwd=os.getcwd(),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True
            )
            execution = {"triggered": True, "spawned": "direct", "pid": process.pid}
        except Exception as spawn_error:
            print(f"Warning: Failed to spawn Claude: {spawn_error}", file=sys.stderr)
            execution = {"triggered": False, "error": str(spawn_error)}

        # === FALLBACK: if spawn failed or process died immediately ===
        if not execution or not execution.get("pid") or execution.get("triggered") == False:
            print(f"NO PID returned, fallback triggering for {task_id}", file=sys.stderr)
            try:
                # Mark task as fallback in queue (don't delete - board needs to see it)
                queue = safe_read_queue_with_lock(queue_file)
                if task_id in queue.get("tasks", {}):
                    queue["tasks"][task_id]["spawned_via"] = "fallback"
                    queue["tasks"][task_id]["status"] = "in_progress"
                    safe_write_queue_with_lock(queue_file, queue)
                # Spawn via fallback
                fallback_prompt = f"""Process this single task:

Task ID: {task_id}
Description: {description}

1. Mark in progress:
   python3 execution_hub.py execute_task --params '{{"tool_name": "claude_assistant_fallback", "action": "mark_task_in_progress", "params": {{"task_id": "{task_id}"}}}}'

2. Execute the task as described

3. Log completion:
   python3 execution_hub.py execute_task --params '{{"tool_name": "claude_assistant_fallback", "action": "log_task_completion", "params": {{"task_id": "{task_id}", "status": "done", "actions_taken": "REPLACE_THIS_WITH_ACTUAL_LIST_OF_ACTIONS_YOU_TOOK"}}}}'\n\nIMPORTANT: Replace the actions_taken placeholder above with a JSON array of strings describing what you actually did. Example: ["read file X", "modified function Y", "created doc Z"]. Do NOT pass '...' as actions_taken.\n\nProject context in .claude/CLAUDE.md"""
                import shlex as _shlex
                fallback_cmd = f"/opt/homebrew/bin/claude --add-dir '{os.getcwd()}' -p {_shlex.quote(fallback_prompt)} --permission-mode acceptEdits --no-session-persistence --allowedTools 'Bash,Read,Write,Edit'"
                fallback_log = open(os.path.join(os.getcwd(), f"data/claude_fallback_{task_id}.log"), "w")
                fallback_process = subprocess.Popen(
                    ["/bin/zsh", "-l", "-c", fallback_cmd],
                    env=clean_env,
                    cwd=os.getcwd(),
                    stdout=fallback_log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True
                )
                execution = {"triggered": True, "spawned": "fallback", "pid": fallback_process.pid, "fallback": True}
            except Exception as fallback_error:
                print(f"Fallback also failed: {fallback_error}", file=sys.stderr)
                execution = {"triggered": False, "error": str(spawn_error), "fallback_error": str(fallback_error)}


    result = {
        "status": "success",
        "message": f"✅ Task '{task_id}' assigned and execution triggered" if execution else f"✅ Task '{task_id}' assigned to Claude Code queue",
        "task_id": task_id,
        "batch_id": batch_id,
        "agent_id": agent_id,
        "execution": execution,
        "next_step": None if execution else "Call execute_queue to trigger processing"
    }

    if format_warnings:
        result["format_warnings"] = format_warnings

    return result


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

    # Search all queue files
    for queue_file in get_all_queue_files():
        if os.path.exists(queue_file):
            queue = safe_read_queue_with_lock(queue_file)
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
    """Quick Q&A - Spawn Claude session to answer a question via stdin pipe."""
    question = params.get("question")
    wait = params.get("wait", True)  # Wait for response by default
    working_dir = params.get("cwd", "/tmp")  # Default to /tmp, but can override for context

    if not question:
        return {"status": "error", "message": "❌ Missing required field: question"}

    # Same env setup as execute_queue - remove ALL Claude detection vars
    base_env = os.environ.copy()
    base_env.pop('ANTHROPIC_API_KEY', None)
    base_env.pop('CLAUDECODE', None)
    base_env.pop('CLAUDE_CODE_ENTRYPOINT', None)
    base_env.pop('CLAUDE_CODE_SSE_PORT', None)
    base_env.pop('CLAUDE_CODE_SUBAGENT_MODEL', None)
    base_env['PATH'] = '/opt/homebrew/bin:/usr/local/bin:' + base_env.get('PATH', '')

    try:
        # Pipe question through stdin instead of command line argument
        claude_cmd = ["/opt/homebrew/bin/claude", "--print"]

        if wait:
            # Synchronous - wait for response, pipe question via stdin
            # Use working_dir (default /tmp, or pass cwd for project context)
            result = subprocess.run(
                claude_cmd,
                input=question,
                env=base_env, cwd=working_dir, capture_output=True, text=True, timeout=120
            )
            return {
                "status": "success" if result.returncode == 0 else "error",
                "response": result.stdout.strip(),
                "stderr": result.stderr.strip() if result.stderr else None,
                "returncode": result.returncode
            }
        else:
            # Async - fire and forget with stdin
            log_file = open(os.path.join(os.getcwd(), "data/claude_ask.log"), "w")
            process = subprocess.Popen(
                claude_cmd,
                stdin=subprocess.PIPE,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=base_env, cwd=os.getcwd(), text=True, start_new_session=True
            )
            process.stdin.write(question)
            process.stdin.close()
            return {
                "status": "success",
                "message": f"🚀 Claude spawned with PID {process.pid}",
                "pid": process.pid,
                "log": "data/claude_ask.log"
            }
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "⏱️ Claude timed out after 120s"}
    except Exception as e:
        return {"status": "error", "message": f"❌ Failed to spawn Claude: {str(e)}"}


def cancel_task(params):
    """Cancel a queued or in_progress task. Use remove=true to delete entirely."""
    task_id = params.get("task_id")
    remove = params.get("remove", False)

    if not task_id:
        return {"status": "error", "message": "❌ Missing required field: task_id"}

    # Search all queue files for the task
    queue_file = None
    queue = None
    for qf in get_all_queue_files():
        if os.path.exists(qf):
            try:
                q = safe_read_queue_with_lock(qf)
                if task_id in q.get("tasks", {}):
                    queue_file = qf
                    queue = q
                    break
            except:
                continue

    if not queue_file or not queue:
        return {"status": "error", "message": f"❌ Task '{task_id}' not found in any queue"}

    task = queue["tasks"][task_id]
    current_status = task.get("status")

    if remove:
        # Completely remove the task from queue
        del queue["tasks"][task_id]
        action = "removed"
    else:
        if current_status in ["done", "error"]:
            return {"status": "error", "message": f"❌ Cannot cancel task that is already {current_status}"}
        queue["tasks"][task_id]["status"] = "cancelled"
        queue["tasks"][task_id]["cancelled_at"] = datetime.now().isoformat()
        action = "cancelled"

    try:
        safe_write_queue_with_lock(queue_file, queue)
    except Exception as e:
        return {"status": "error", "message": f"❌ Error writing queue: {str(e)}"}

    return {
        "status": "success",
        "message": f"✅ Task '{task_id}' {action}",
        "task_id": task_id,
        "previous_status": current_status
    }


def clear_queue(params):
    """Remove all tasks from all queues."""
    total_count = 0
    all_task_ids = []

    for queue_file in get_all_queue_files():
        if not os.path.exists(queue_file):
            continue

        try:
            queue = safe_read_queue_with_lock(queue_file)
            task_count = len(queue.get("tasks", {}))
            task_ids = list(queue.get("tasks", {}).keys())
            
            total_count += task_count
            all_task_ids.extend(task_ids)
            
            queue["tasks"] = {}
            safe_write_queue_with_lock(queue_file, queue)
        except Exception as e:
            print(f"Warning: Could not clear {queue_file}: {e}", file=sys.stderr)

    return {
        "status": "success",
        "message": f"✅ Cleared {total_count} tasks from all queues",
        "removed_count": total_count,
        "removed_tasks": all_task_ids
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

    # Search all queue files for the task
    queue_file = None
    queue = None
    for qf in get_all_queue_files():
        if os.path.exists(qf):
            try:
                q = safe_read_queue_with_lock(qf)
                if task_id in q.get("tasks", {}):
                    queue_file = qf
                    queue = q
                    break
            except:
                continue

    if not queue_file or not queue:
        return {"status": "error", "message": f"❌ Task '{task_id}' not found in any queue"}

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
        safe_write_queue_with_lock(queue_file, queue)
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
    Claude calls this to get all queued tasks from all queue files.

    NOW WITH AGENT FILTERING - if agent_id provided, only returns tasks for that agent.

    Parameters:
    - agent_id: If provided, ONLY return tasks assigned to this agent
    - peek: If True, return ALL tasks (queued + in_progress) WITHOUT marking them.
            Used by dashboard for polling without side effects.
    """
    agent_id = params.get("agent_id")
    peek = params.get("peek", False)

    pending = []
    now = datetime.now().isoformat()
    tasks_marked = []
    queues_updated = []  # Track which queues need to be written back

    # Read from all queue files
    for queue_file in get_all_queue_files():
        if not os.path.exists(queue_file):
            continue

        try:
            queue = safe_read_queue_with_lock(queue_file)
        except Exception as e:
            print(f"Warning: Could not read {queue_file}: {e}", file=sys.stderr)
            continue

        queue_modified = False
        for task_id, task_data in queue.get("tasks", {}).items():
            task_status = task_data.get("status", "queued")

            # In peek mode, return queued AND in_progress tasks
            if peek:
                if task_status not in ["queued", "in_progress"]:
                    continue
            else:
                if task_status != "queued":
                    continue

            if agent_id:
                task_agent = task_data.get("agent_id")
                if task_agent != agent_id:
                    continue

            # Only modify queue if NOT in peek mode
            if not peek:
                queue["tasks"][task_id]["status"] = "in_progress"
                queue["tasks"][task_id]["started_at"] = now
                tasks_marked.append(task_id)
                queue_modified = True

            task_entry = {
                "task_id": task_id,
                "description": task_data["description"],
                "status": task_status if peek else "in_progress",
                "context": task_data.get("context", {}),
                "priority": task_data.get("priority", "medium"),
                "created_at": task_data.get("created_at"),
                "agent_id": task_data.get("agent_id"),
                "card_title": task_data.get("card_title"),
                "processing_started_at": task_data.get("processing_started_at")
            }
            if not peek:
                task_entry["AFTER_COMPLETION_YOU_MUST"] = f"Call log_task_completion for task_id '{task_id}'"
            pending.append(task_entry)

        # Write back if modified
        if queue_modified:
            try:
                safe_write_queue_with_lock(queue_file, queue)
                queues_updated.append(queue_file)
            except Exception as e:
                print(f"Warning: Could not update {queue_file}: {e}", file=sys.stderr)

    if not pending:
        msg = "✅ No active tasks" if peek else "✅ No pending tasks"
        if agent_id:
            msg = f"✅ No {'active' if peek else 'pending'} tasks for {agent_id}"
        return {
            "status": "success",
            "message": msg,
            "pending_tasks": [],
            "task_count": 0,
            "agent_id": agent_id,
            "peek": peek
        }

    if not peek:
        print(f"⏱️ Auto-marked {len(tasks_marked)} task(s) as in_progress across {len(queues_updated)} queue(s)", file=sys.stderr)

    result = {
        "status": "success",
        "message": f"Found {len(pending)} {'active' if peek else 'pending'} task(s)" + (f" for {agent_id}" if agent_id else ""),
        "pending_tasks": pending,
        "task_count": len(pending),
        "agent_id": agent_id,
        "peek": peek
    }
    if not peek:
        result["CRITICAL_REMINDER"] = "🚨 YOU MUST CALL log_task_completion FOR EACH TASK 🚨"
    return result


def mark_task_in_progress(params):
    """
    Mark a queued task as in_progress.

    IMPORTANT: This sets 'processing_started_at' which is used for ACTUAL execution time calculation.
    In parallel execution, 'started_at' gets set when all tasks are pulled from queue simultaneously,
    but 'processing_started_at' records when Claude ACTUALLY starts working on this specific task.

    Optional:
    - card_title: Short distinctive name for the task (max 40 chars) for dashboard display
    """
    task_id = params.get("task_id")
    card_title = params.get("card_title")  # Optional: agent-generated short title for dashboard

    if not task_id:
        return {"status": "error", "message": "❌ Missing required field: task_id"}

    # Search all queue files for the task
    queue_file = None
    queue = None
    for qf in get_all_queue_files():
        if os.path.exists(qf):
            try:
                q = safe_read_queue_with_lock(qf)
                if task_id in q.get("tasks", {}):
                    queue_file = qf
                    queue = q
                    break
            except:
                continue

    if not queue_file or not queue:
        return {"status": "error", "message": f"❌ Task '{task_id}' not found in any queue"}

    task = queue["tasks"][task_id]
    current_status = task.get("status")

    if current_status not in ["queued", "in_progress"]:
        return {
            "status": "error",
            "message": f"❌ Task '{task_id}' cannot be marked in_progress (current: {current_status})"
        }

    now = datetime.now().isoformat()
    queue["tasks"][task_id]["status"] = "in_progress"

    if "started_at" not in queue["tasks"][task_id]:
        queue["tasks"][task_id]["started_at"] = now

    queue["tasks"][task_id]["processing_started_at"] = now
    if card_title:
        queue["tasks"][task_id]["card_title"] = card_title[:40]  # Cap at 40 chars
    started_at = queue["tasks"][task_id]["started_at"]

    try:
        safe_write_queue_with_lock(queue_file, queue)
    except Exception as e:
        return {"status": "error", "message": f"❌ Error writing queue: {str(e)}"}

    results_file = os.path.join(os.getcwd(), "data/claude_task_results.json")
    try:
        if os.path.exists(results_file):
            with open(results_file, 'r', encoding='utf-8') as f:
                results = json.load(f)
        else:
            results = {"results": {}}

        if task_id not in results.get("results", {}):
            stub = {
                "status": "in_progress",
                "started_at": started_at,
                "processing_started_at": now,
                "description": queue["tasks"][task_id].get("description", ""),
                "batch_id": queue["tasks"][task_id].get("batch_id")
            }
            if card_title:
                stub["card_title"] = card_title[:40]
            results["results"][task_id] = stub
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not write started_at stub: {e}", file=sys.stderr)

    result = {
        "status": "success",
        "message": f"✅ Task '{task_id}' marked as in_progress",
        "processing_started_at": now
    }
    if card_title:
        result["card_title"] = card_title[:40]
    return result


def execute_queue(params):
    """
    Spawns Claude Code session(s) to process queued tasks.
    
    No hard limits on parallel agents - task count drives spawning.
    """
    if os.environ.get("CLAUDECODE"):
        return {
            "status": "error",
            "message": "❌ Cannot spawn nested Claude Code session. Process tasks directly.",
            "hint": "Read tasks from data/claude_task_queue.json and process them here"
        }

    agent_id = params.get("agent_id")
    parallel = params.get("parallel", 3)
    
    # No lockfile needed - agents claim tasks directly via claimed_by field
    # Count tasks across all queue files
    task_count = 0
    all_queued_tasks = {}  # task_id -> task_data
    for queue_file in get_all_queue_files():
        if not os.path.exists(queue_file):
            continue
        try:
            queue = safe_read_queue_with_lock(queue_file)
            for task_id, task_data in queue.get("tasks", {}).items():
                if task_data.get("status") == "queued":
                    task_count += 1
                    all_queued_tasks[task_id] = task_data
        except Exception as e:
            print(f"Warning: Could not read {queue_file}: {e}", file=sys.stderr)

    if task_count == 0:
        return {
            "status": "success",
            "message": "✅ No pending tasks",
            "task_count": 0
        }

    base_env = os.environ.copy()
    base_env.pop('ANTHROPIC_API_KEY', None)
    base_env.pop('CLAUDECODE', None)
    base_env.pop('CLAUDE_CODE_ENTRYPOINT', None)
    base_env.pop('CLAUDE_CODE_SSE_PORT', None)
    base_env.pop('CLAUDE_CODE_SUBAGENT_MODEL', None)
    base_env['PATH'] = '/opt/homebrew/bin:/usr/local/bin:' + base_env.get('PATH', '')

    spawned = []
    pids = []

    if parallel > 1:
        # Distribute tasks evenly across agents (round-robin)
        # Don't rely on pre-set agent_id - most tasks don't have it
        queued_task_ids = list(all_queued_tasks.keys())
        agent_tasks = {}

        for i, task_id in enumerate(queued_task_ids):
            agent_num = (i % parallel) + 1
            aid = f"agent_{agent_num}"
            if aid not in agent_tasks:
                agent_tasks[aid] = []
            agent_tasks[aid].append(task_id)

        agent_ids = sorted(agent_tasks.keys())[:parallel]

        for aid in agent_ids:
            task_list = agent_tasks.get(aid, [])
            if not task_list:
                continue

            prompt = f"""You are {aid}. Process ONLY your assigned tasks.

⚠️ CRITICAL: You are {aid}. Only process tasks assigned to you.

1. Get YOUR tasks:
   python3 execution_hub.py execute_task --params '{{"tool_name": "claude_assistant", "action": "process_queue", "params": {{"agent_id": "{aid}"}}}}'

2. For EACH task:
   a. Generate a card_title (max 40 chars) - a short distinctive name like "SaaSpocalypse journalist blast" or "Post-scarcity execution blog". NO generic prefixes like "Build" or "Create".
   b. Call mark_task_in_progress with task_id AND card_title:
      python3 execution_hub.py execute_task --params '{{"tool_name": "claude_assistant", "action": "mark_task_in_progress", "params": {{"task_id": "...", "card_title": "..."}}}}'
   c. Execute the task
   d. Generate a card_stat (max 15 chars) - the key outcome like "24 sent", "6 sections", "deployed"
   e. Call log_task_completion with task_id, status, actions_taken, card_title, AND card_stat

3. Exit when done

Project context in .claude/CLAUDE.md"""

            try:
                import shlex
                claude_cmd = f"/opt/homebrew/bin/claude --add-dir '{os.getcwd()}' -p {shlex.quote(prompt)} --permission-mode acceptEdits --no-session-persistence --allowedTools 'Bash,Read,Write,Edit'"
                log_file = open(os.path.join(os.getcwd(), f"data/claude_execution_{aid}.log"), "w")
                process = subprocess.Popen(
                    ["/bin/zsh", "-l", "-c", claude_cmd],
                    env=base_env, cwd=os.getcwd(), stdout=log_file, stderr=subprocess.STDOUT, start_new_session=True
                )
                spawned.append({"agent_id": aid, "pid": process.pid, "tasks": len(task_list)})
                pids.append(process.pid)
                print(f"🚀 Spawned {aid} with PID {process.pid} for {len(task_list)} tasks", file=sys.stderr)
            except Exception as e:
                print(f"❌ Failed to spawn {aid}: {e}", file=sys.stderr)

    else:
        if agent_id:
            prompt = f"""You are {agent_id}. Process ONLY tasks assigned to {agent_id}.

1. Get YOUR tasks:
   python3 execution_hub.py execute_task --params '{{"tool_name": "claude_assistant", "action": "process_queue", "params": {{"agent_id": "{agent_id}"}}}}'

2. For EACH task:
   a. Generate a card_title (max 40 chars) - short distinctive name like "SaaSpocalypse journalist blast". NO generic prefixes.
   b. Call mark_task_in_progress with task_id AND card_title
   c. Execute the task
   d. Generate a card_stat (max 15 chars) - key outcome like "24 sent", "6 sections", "deployed"
   e. Call log_task_completion with task_id, status, actions_taken, card_title, AND card_stat

3. rm data/execute_queue.lock when done

Project context in .claude/CLAUDE.md"""
        else:
            prompt = """Process all tasks in the queue.

🚨 LOGGING IS MANDATORY - call log_task_completion for EVERY task 🚨

1. Get tasks:
   python3 execution_hub.py execute_task --params '{"tool_name": "claude_assistant", "action": "process_queue", "params": {}}'

2. For EACH task:
   a. Generate a card_title (max 40 chars) - short distinctive name like "SaaSpocalypse journalist blast". NO generic prefixes.
   b. Call mark_task_in_progress with task_id AND card_title
   c. Execute the task
   d. Generate a card_stat (max 15 chars) - key outcome like "24 sent", "6 sections", "deployed"
   e. Call log_task_completion with task_id, status, actions_taken, card_title, AND card_stat

3. rm data/execute_queue.lock when done

Project context in .claude/CLAUDE.md"""

        try:
            import shlex
            claude_cmd = f"/opt/homebrew/bin/claude --add-dir '{os.getcwd()}' -p {shlex.quote(prompt)} --permission-mode acceptEdits --no-session-persistence --allowedTools 'Bash,Read,Write,Edit'"
            log_file = open(os.path.join(os.getcwd(), "data/claude_execution.log"), "w")
            process = subprocess.Popen(
                ["/bin/zsh", "-l", "-c", claude_cmd],
                env=base_env, cwd=os.getcwd(), stdout=log_file, stderr=subprocess.STDOUT, start_new_session=True
            )
            spawned.append({"pid": process.pid, "tasks": task_count, "agent_id": agent_id})
            pids.append(process.pid)
        except Exception as e:
            return {"status": "error", "message": f"❌ Failed to spawn Claude Code: {str(e)}"}

    # No lockfile - agents claim tasks directly
    return {
        "status": "task_started",
        "message": f"✅ {len(spawned)} agent(s) started to process {task_count} task(s)",
        "task_count": task_count,
        "parallel": parallel,
        "agents": spawned
    }


def kill_agents(params):
    """Kill all running parallel agents."""
    killed = 0

    # Kill any claude processes running with -p flag (task agents)
    try:
        result = subprocess.run(["pkill", "-f", "claude.*-p"], capture_output=True, timeout=5)
        if result.returncode == 0:
            killed += 1
    except:
        pass

    # Clean up any stale lockfile if it exists (legacy cleanup)
    lockfile = os.path.join(os.getcwd(), "data/execute_queue.lock")
    if os.path.exists(lockfile):
        try:
            os.remove(lockfile)
        except:
            pass

    return {
        "status": "success",
        "message": f"✅ Killed agents and cleaned up"
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
    - card_title: Short distinctive name (max 40 chars) for dashboard display
    - card_stat: Key outcome metric (max 15 chars) like "24 sent", "6 sections", "deployed"
    """
    task_id = params.get("task_id")
    status = params.get("status")
    actions_taken = params.get("actions_taken", [])
    output = params.get("output", {})
    output_summary = params.get("output_summary")
    errors = params.get("errors")
    execution_time = params.get("execution_time_seconds", 0)
    card_title = params.get("card_title")  # Optional: agent-generated short title
    card_stat = params.get("card_stat")    # Optional: agent-generated outcome metric

    if not task_id:
        return {"status": "error", "message": "❌ Missing required field: task_id"}
    if not status:
        return {"status": "error", "message": "❌ Missing required field: status"}

    status_lower = status.lower().strip()
    if status_lower in ["completed", "complete", "done"]:
        status = "done"
    else:
        status = "error"

    task_description = None
    task_batch_id = None
    task_started_at = None
    task_created_at = None
    task_processing_started_at = None

    # Search all queue files for the task
    for queue_file in get_all_queue_files():
        if not os.path.exists(queue_file):
            continue
        try:
            queue = safe_read_queue_with_lock(queue_file)

            if task_id in queue.get("tasks", {}):
                task_description = queue["tasks"][task_id].get("description", "")
                task_batch_id = queue["tasks"][task_id].get("batch_id")
                task_started_at = queue["tasks"][task_id].get("started_at")
                task_created_at = queue["tasks"][task_id].get("created_at")
                task_processing_started_at = queue["tasks"][task_id].get("processing_started_at")

                del queue["tasks"][task_id]
                safe_write_queue_with_lock(queue_file, queue)
                print(f"✅ Removed '{task_id}' from queue (completed)", file=sys.stderr)
                break  # Found and removed, no need to check other queues
        except Exception as e:
            print(f"Warning: Could not update {queue_file}: {e}", file=sys.stderr)

    if execution_time == 0 and not task_processing_started_at:
        results_file = os.path.join(os.getcwd(), "data/claude_task_results.json")
        if os.path.exists(results_file):
            try:
                with open(results_file, 'r', encoding='utf-8') as f:
                    existing_results = json.load(f)
                if task_id in existing_results.get("results", {}):
                    stub = existing_results["results"][task_id]
                    task_processing_started_at = stub.get("processing_started_at")
                    if not task_started_at:
                        task_started_at = stub.get("started_at")
                    if not task_description:
                        task_description = stub.get("description")
                    if not task_batch_id:
                        task_batch_id = stub.get("batch_id")
                    # Preserve card_title from stub if agent didn't provide one
                    if not card_title and stub.get("card_title"):
                        card_title = stub.get("card_title")
            except:
                pass

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

                # Load existing task_ids to prevent duplicates
                existing_task_ids = set()
                if os.path.exists(archive_file):
                    try:
                        with open(archive_file, 'r', encoding='utf-8') as f:
                            for line in f:
                                try:
                                    entry = json.loads(line.strip())
                                    existing_task_ids.add(entry.get('task_id'))
                                except:
                                    pass
                    except:
                        pass

                with open(archive_file, 'a', encoding='utf-8') as f:
                    for archived_task_id, result_data in to_archive.items():
                        # Skip if already archived
                        if archived_task_id in existing_task_ids:
                            continue

                        # Skip stubs that never completed — actions_taken will be empty
                        if result_data.get('status') == 'in_progress':
                            continue

                        desc = result_data.get('description', '')
                        summary = desc.replace('\n', ' ')[:200].strip()
                        if len(desc) > 200:
                            summary += '...'

                        # Extract doc references: [Name](/doc/UUID)
                        doc_refs = re.findall(r'\[([^\]]+)\]\(/doc/([a-f0-9-]+)\)', desc)
                        doc_refs_dict = {name: doc_id for name, doc_id in doc_refs}

                        # Load project tags mapping and add linked docs
                        project_tags_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'project_tags.json')
                        if os.path.exists(project_tags_file):
                            try:
                                with open(project_tags_file, 'r') as ptf:
                                    project_tags_map = json.load(ptf)
                                for tag in result_data.get('project_tags', []):
                                    if tag in project_tags_map:
                                        for doc_key, doc_id in project_tags_map[tag].items():
                                            doc_refs_dict[f"[project:{doc_key}]"] = doc_id
                            except:
                                pass

                        tags = result_data.get('project_tags', [])
                        tag_map = {'war-plan': 'orchestrate-blitzkrieg', 'blog': 'blogs'}
                        mapped_tags = [f'#{tag_map.get(t, t)}' for t in tags]
                        # Dedupe tags
                        mapped_tags = list(dict.fromkeys(mapped_tags))

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

                        completed_at = result_data.get('completed_at')
                        if not completed_at or completed_at == 'unknown':
                            completed_at = datetime.now().isoformat()

                        archived_entry = {
                            'task_id': archived_task_id,
                            'summary': summary,
                            'completed': completed_at,
                            'tag': ' '.join(mapped_tags),
                            'category': category,
                            'doc_refs': doc_refs_dict,
                            'actions_taken': result_data.get('actions_taken', [])
                        }
                        f.write(json.dumps(archived_entry) + '\n')

                results["results"] = to_keep
                print(f"📦 Archived {len(to_archive)} old results", file=sys.stderr)
        except Exception as e:
            print(f"Warning: Could not archive old results: {e}", file=sys.stderr)

    if not output_summary:
        output_summary = "Task completed" if status == "done" else "Task failed"

    is_first_task_in_batch = False
    batch_position = 0

    if task_batch_id:
        completed_in_batch = 0
        for tid, result in results.get("results", {}).items():
            if result.get("batch_id") == task_batch_id:
                completed_in_batch += 1

        is_first_task_in_batch = (completed_in_batch == 0)
        batch_position = completed_in_batch + 1

    project_tags = []
    if task_description:
        project_tags = re.findall(r'#([\w-]+)', task_description)

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

    # Add card_title and card_stat for dashboard display
    if card_title:
        results["results"][task_id]["card_title"] = card_title[:40]
    if card_stat:
        results["results"][task_id]["card_stat"] = card_stat[:15]

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

    if task_description and "REQUEST_ID:" in task_description:
        try:
            request_id_match = re.search(r'REQUEST_ID:\s*(\S+)', task_description)
            if request_id_match:
                request_id = request_id_match.group(1).strip()
                results_dir = os.path.join(os.getcwd(), "semantic_memory", "results")
                os.makedirs(results_dir, exist_ok=True)
                result_file_path = os.path.join(results_dir, f"{request_id}.json")

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
    - parallel: number of agents (default 3)
    """
    tasks = params.get("tasks")
    parallel = params.get("parallel", 3)

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

        # task_id is optional - assign_task will auto-generate if not provided

        task_params = task.copy()
        task_params["auto_execute"] = False

        if parallel > 1 and not task_params.get("agent_id"):
            agent_num = (i % parallel) + 1
            task_params["agent_id"] = f"agent_{agent_num}"

        try:
            result = assign_task(task_params)
            # Get task_id from result (assign_task auto-generates if not provided)
            actual_task_id = result.get("task_id") or task_id
            if result.get("status") == "success":
                success_count += 1
                agent_label = f" ({task_params.get('agent_id')})" if parallel > 1 else ""
                results.append({
                    "index": i,
                    "task_id": actual_task_id,
                    "status": "success",
                    "message": f"✅ Task {actual_task_id} queued{agent_label}"
                })
            else:
                failed_count += 1
                results.append({
                    "index": i,
                    "task_id": actual_task_id,
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

    execution = None
    if success_count > 0:
        # Spawn execute_queue in subprocess with clean env (no CLAUDECODE)
        # This triggers agent spawn immediately instead of waiting for engine
        import json as _json
        clean_env = os.environ.copy()
        clean_env.pop('CLAUDECODE', None)
        clean_env.pop('CLAUDE_CODE_ENTRYPOINT', None)
        eq_log = open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'execute_queue_spawn.log'), 'w')
        eq_process = subprocess.Popen(
            ['python3', os.path.join(os.path.dirname(__file__), '..', 'execution_hub.py'),
             'execute_task', '--params', _json.dumps({
                 "tool_name": "claude_assistant",
                 "action": "execute_queue",
                 "params": {"parallel": parallel}
             })],
            env=clean_env,
            cwd=os.path.dirname(os.path.dirname(__file__)),
            stdout=eq_log,
            stderr=subprocess.STDOUT,
            start_new_session=True
        )
        execution = {"triggered": True, "parallel": parallel, "eq_pid": eq_process.pid}

        # === FALLBACK: if no PID returned, retry via fallback ===
        if not eq_process.pid:
            print(f"NO PID returned from batch spawn, fallback triggering", file=sys.stderr)
            try:
                fallback_process = subprocess.Popen(
                    ['python3', os.path.join(os.path.dirname(__file__), '..', 'execution_hub.py'),
                     'execute_task', '--params', _json.dumps({
                         "tool_name": "claude_assistant_fallback",
                         "action": "execute_queue",
                         "params": {"parallel": parallel}
                     })],
                    env=clean_env,
                    cwd=os.path.dirname(os.path.dirname(__file__)),
                    stdout=eq_log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True
                )
                execution = {"triggered": True, "parallel": parallel, "eq_pid": fallback_process.pid, "fallback": True}
            except Exception as fallback_error:
                print(f"Batch fallback also failed: {fallback_error}", file=sys.stderr)

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


def assign_mockup_batch(params):
    """
    Fan out a mockup description into N parallel variations.

    Required:
    - description: the mockup task description

    Optional:
    - base_name: explicit filename base (e.g., 'built_by_claude' -> built_by_claude_v1.html)
                 If not provided, derives from description keywords.
    - variations: number of variations to create (default: 4)
    - parallel: number of agents (default: 3)
    - styles: array of style directions (e.g., ["minimalist sparse", "dense galaxy", "neon cyberpunk"])
              If provided, each variation gets its own style appended to description.
              If fewer styles than variations, cycles through them.
              If not provided, auto-generates distinct style directions.

    Each variation gets:
    - Unique version suffix (v1, v2, ... vN)
    - Unique output filename baked into description (e.g., semantic_memory/mockups/built_by_claude_v1.html)
    - Unique style direction to ensure visual variety
    """
    description = params.get("description")
    variations = params.get("variations", 4)
    parallel = params.get("parallel", 3)
    base_name = params.get("base_name")
    styles = params.get("styles")

    if not description:
        return {"status": "error", "message": "❌ Missing required field: description"}

    if not isinstance(variations, int) or variations < 1:
        return {"status": "error", "message": "❌ variations must be a positive integer"}

    if variations > 50:
        return {"status": "error", "message": "❌ variations capped at 50 to avoid queue flooding"}

    # Auto-generate styles if not provided
    default_styles = [
        "minimalist with sparse cards, lots of negative space, clean lines",
        "dense galaxy layout with hundreds of tiny interactive elements",
        "neon cyberpunk aesthetic with glowing edges and dark backgrounds",
        "organic flowing curves with soft gradients and natural colors",
        "brutalist raw concrete aesthetic with sharp edges and bold typography",
        "glassmorphism with frosted layers and depth effects",
        "retro 80s synthwave with grid lines and sunset gradients",
        "newspaper editorial style with columns and serif typography",
        "geometric bauhaus with primary colors and strong shapes",
        "hand-drawn sketch aesthetic with wobbly lines and paper texture"
    ]

    if styles and isinstance(styles, list) and len(styles) > 0:
        style_list = styles
    else:
        style_list = default_styles

    # Use explicit base_name if provided, otherwise derive from description
    if not base_name:
        desc_lower = description.lower()
        stopwords = ['a', 'an', 'the', 'for', 'to', 'of', 'and', 'with', 'that', 'this', 'create', 'make', 'build', 'design']
        words = re.sub(r'[^\w\s]', '', desc_lower).split()
        keywords = [w for w in words if w not in stopwords and len(w) > 2][:3]
        base_name = '_'.join(keywords) if keywords else 'mockup'

    # Sanitize base_name (remove spaces, special chars)
    base_name = re.sub(r'[^\w]', '_', base_name.lower()).strip('_')
    base_name = re.sub(r'_+', '_', base_name)  # collapse multiple underscores

    # Build task list
    tasks = []
    for i in range(1, variations + 1):
        version_suffix = f"v{i}"
        output_filename = f"semantic_memory/mockups/{base_name}_{version_suffix}.html"

        # Cycle through styles if fewer styles than variations
        style_index = (i - 1) % len(style_list)
        style_direction = style_list[style_index]

        # Bake unique filename AND style directly into task description
        versioned_description = f"""{description}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VERSION: {version_suffix} (variation {i} of {variations})
OUTPUT FILE: {output_filename}
STYLE DIRECTION: {style_direction}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🚨 CRITICAL: You MUST save your mockup to exactly this path:
   {output_filename}

🎨 STYLE: Your design MUST follow this aesthetic direction:
   {style_direction}

This filename is unique to your task. Other agents have different filenames.
Your style direction is DIFFERENT from other variations - embrace it fully."""

        tasks.append({
            "description": versioned_description,
            "context": {
                "version": version_suffix,
                "variation_number": i,
                "total_variations": variations,
                "output_file": output_filename,
                "create_output_doc": False
            },
            "priority": "medium"
        })

    # Use batch_assign_tasks to queue them
    result = batch_assign_tasks({
        "tasks": tasks,
        "parallel": parallel
    })

    return {
        "status": result.get("status"),
        "message": f"🎨 Spawned {variations} mockup variations across {parallel} agents",
        "base_name": base_name,
        "variations": variations,
        "output_pattern": f"semantic_memory/mockups/{base_name}_v*.html",
        "batch_result": result
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
    """Parse tasks from markdown document text. Only # headers start new tasks."""
    doc_text = params.get("doc_text", "")

    if not doc_text:
        return {"status": "error", "message": "❌ Missing required field: doc_text"}

    tasks = []
    lines = doc_text.split('\n')
    current_task = None
    current_lines = []

    for line in lines:
        # Only headers start new tasks, bullets are part of task description
        is_header = line.startswith('#')

        if is_header:
            if current_task:
                tasks.append({
                    "description": '\n'.join(current_lines).strip(),
                    "raw_header": current_task
                })

            current_task = line.lstrip('# ').strip()
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
    
    FIXED: Now assigns agent_ids BEFORE spawning to prevent race conditions.

    Required:
    - doc_id: Outline document ID to fetch tasks from

    Optional:
    - test_mode: if true, writes to claude_test_task_queue.json (default: false)
    - parallel: number of agents for parallel execution (default: 3)
    """
    doc_id = params.get("doc_id", "51b72c69-0e28-4d20-bfbc-6b0854ec2f25")  # Claude Tasks in outline_editor
    test_mode = params.get("test_mode", False)
    parallel = params.get("parallel", 3)

    try:
        # Set up environment for psycopg2 to find libpq
        env = os.environ.copy()
        env.pop('PYTHONPATH', None)
        env['PATH'] = '/Users/srinivas/venv/bin:/opt/homebrew/bin:' + env.get('PATH', '')
        env['DYLD_LIBRARY_PATH'] = '/opt/homebrew/lib:' + env.get('DYLD_LIBRARY_PATH', '')

        result = subprocess.run(
            ["/Users/srinivas/venv/bin/python3", "execution_hub.py", "execute_task", "--params",
             json.dumps({"tool_name": "outline_editor", "action": "get_doc", "params": {"doc_id": doc_id}})],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=os.getcwd(),
            env=env
        )

        if result.returncode != 0:
            return {"status": "error", "message": f"❌ Failed to fetch doc: {result.stderr}"}

        doc_response = json.loads(result.stdout)
        if doc_response.get("status") == "error":
            return {"status": "error", "message": doc_response.get("message", "Failed to fetch doc")}

        doc_text = doc_response.get("data", {}).get("text", "")
        if not doc_text:
            return {"status": "error", "message": f"❌ Document has no text content. stdout: {result.stdout[:300]} stderr: {result.stderr[:300]}"}

    except Exception as e:
        return {"status": "error", "message": f"❌ Error fetching document: {str(e)}"}

    parse_result = parse_tasks_from_doc({"doc_text": doc_text})
    if parse_result.get("status") == "error":
        return parse_result

    parsed_tasks = parse_result.get("tasks", [])
    if not parsed_tasks:
        return {"status": "success", "message": "✅ No tasks found in document", "tasks_added": 0}

    tasks_to_assign = []
    task_ids = []

    for i, task in enumerate(parsed_tasks):
        description = task.get("description", "")
        raw_header = task.get("raw_header", "")

        clean_header = re.sub(r'^\d+\.\s*', '', raw_header)
        task_id = re.sub(r'[^a-z0-9]+', '_', clean_header.lower()).strip('_')
        task_id = task_id[:50]

        agent_num = (i % parallel) + 1
        agent_id = f"agent_{agent_num}"

        tasks_to_assign.append({
            "task_id": task_id,
            "description": description,
            "context": {"source_doc": doc_id},
            "agent_id": agent_id
        })
        task_ids.append(task_id)

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


# === STAGING FUNCTIONS FOR DASHBOARD ===

STAGED_TASKS_FILE = os.path.join(os.getcwd(), "data/staged_tasks.json")


def stage_task(params):
    """
    Stage a task for later execution. Used by Claude in conversation to queue tasks
    that appear in the dashboard staging stack without triggering execution.

    Required:
    - description: The task description

    Optional:
    - preset: Task preset type (custom, email, website, report, tool, blog)
    """
    description = params.get("description")
    preset = params.get("preset", "custom")

    if not description:
        return {"status": "error", "message": "❌ Missing required field: description"}

    # Read existing staged tasks
    staged = []
    if os.path.exists(STAGED_TASKS_FILE):
        try:
            with open(STAGED_TASKS_FILE, 'r', encoding='utf-8') as f:
                staged = json.load(f)
        except:
            staged = []

    # Add new task
    staged.append({
        "description": description,
        "preset": preset,
        "staged_at": datetime.now().isoformat()
    })

    # Write back
    try:
        with open(STAGED_TASKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(staged, f, indent=2)
    except Exception as e:
        return {"status": "error", "message": f"❌ Failed to stage task: {str(e)}"}

    return {
        "status": "success",
        "message": f"✅ Task staged ({len(staged)} total)",
        "staged_count": len(staged)
    }


def get_staged_tasks(params):
    """
    Get all staged tasks from the staging file.
    Used by dashboard to display the staging stack.
    """
    if not os.path.exists(STAGED_TASKS_FILE):
        return {
            "status": "success",
            "staged_tasks": [],
            "count": 0
        }

    try:
        with open(STAGED_TASKS_FILE, 'r', encoding='utf-8') as f:
            staged = json.load(f)
    except:
        staged = []

    return {
        "status": "success",
        "staged_tasks": staged,
        "count": len(staged)
    }


def clear_staged_tasks(params):
    """
    Clear all staged tasks. Called by dashboard after Execute All
    moves staged tasks to the queue.
    """
    try:
        with open(STAGED_TASKS_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f)
    except Exception as e:
        return {"status": "error", "message": f"❌ Failed to clear staged tasks: {str(e)}"}

    return {
        "status": "success",
        "message": "✅ Staged tasks cleared"
    }


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
        'assign_mockup_batch': assign_mockup_batch,
        'batch_assign_tasks': batch_assign_tasks,
        'check_task_status': check_task_status,
        'get_task_result': get_task_result,
        'get_task_results': get_task_results,
        'get_recent_tasks': get_recent_tasks,
        'get_all_results': get_all_results,
        'ask_claude': ask_claude,
        'cancel_task': cancel_task,
        'clear_queue': clear_queue,
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
        'self_assign_from_doc': self_assign_from_doc,
        'stage_task': stage_task,
        'get_staged_tasks': get_staged_tasks,
        'clear_staged_tasks': clear_staged_tasks
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