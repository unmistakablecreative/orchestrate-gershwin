#!/usr/bin/env python3
"""
Execution Hub - Clean Sequential Execution
No locks, no retries, no defensive bullshit. Just execute.
"""

import os
import json
import subprocess
import argparse
import logging
import time
import sys
from datetime import datetime
from pathlib import Path
from tools.response_sanitizer import sanitize_response

NDJSON_REGISTRY_FILE = "system_settings.ndjson"
EXECUTION_LOG = "data/execution_log.ndjson"
THREAD_STATE_FILE = "data/thread_state.json"
ERROR_HANDLERS_FILE = "data/error_handlers.json"
MAX_TOKEN_BUDGET = 100000
DEFAULT_TIMEOUT = 200

# Error handlers cache
_error_handlers_cache = None
_error_handlers_mtime = 0

# Self-healing param tracking: persisted to disk for subprocess survival
# Format: {"tool": str, "action": str, "params": dict, "timestamp": float}
LAST_FAILED_CALL_FILE = "data/last_failed_call.json"

# Action aliases - maps common mistakes to correct action names
# Format: (tool_name, wrong_action) -> correct_action
ACTION_ALIASES = {
    ("claude_assistant", "add_task"): "assign_task",
    ("claude_assistant", "queue_task"): "assign_task",
    ("claude_assistant", "create_task"): "assign_task",
    ("claude_assistant", "new_task"): "assign_task",
    ("claude_assistant", "get_tasks"): "get_staged_tasks",
    ("claude_assistant", "list_tasks"): "get_staged_tasks",
    ("claude_assistant", "view_tasks"): "get_staged_tasks",
    ("claude_assistant", "get_results"): "get_task_results",
    ("claude_assistant", "results"): "get_task_results",
    ("claude_assistant", "task_status"): "check_task_status",
    ("claude_assistant", "status"): "check_task_status",
    ("terminal_tool", "read_file"): "read_file_text",
    ("terminal_tool", "read"): "read_file_text",
    ("terminal_tool", "grep"): "grep_content",
    ("terminal_tool", "search"): "grep_content",
    ("terminal_tool", "find"): "find_file",
    ("terminal_tool", "run"): "run_terminal_command",
    ("terminal_tool", "exec"): "run_terminal_command",
    ("terminal_tool", "shell"): "run_terminal_command",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


# ============================================================================
# SIMPLE JSON HELPERS
# ============================================================================

def read_json(filepath, default=None):
    """Read JSON file, return default if missing/corrupt"""
    if not os.path.exists(filepath):
        return default if default is not None else {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return default if default is not None else {}


def write_json(filepath, data):
    """Write JSON file"""
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


def get_action_schema(tool_name, action):
    """Look up action schema from system_settings.ndjson"""
    if not os.path.exists(NDJSON_REGISTRY_FILE):
        return None
    try:
        with open(NDJSON_REGISTRY_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if entry.get("tool") == tool_name and entry.get("action") == action:
                    schema = {}
                    if entry.get("params"):
                        schema["required"] = entry["params"]
                    if entry.get("optional_params"):
                        schema["optional"] = entry["optional_params"]
                    if entry.get("example"):
                        schema["example"] = entry["example"]
                    return schema if schema else None
    except:
        pass
    return None


def inject_schema_on_error(result, tool_name, action):
    """If result is a 'Missing required' error, inject the schema hint"""
    if not isinstance(result, dict):
        return result
    if result.get("status") != "error":
        return result
    msg = result.get("message", "")
    if "Missing required" not in msg and "missing required" not in msg.lower():
        return result

    schema = get_action_schema(tool_name, action)
    if schema:
        result["expected_params"] = schema
    return result


def load_error_handlers():
    """Load error_handlers.json with mtime-based caching"""
    global _error_handlers_cache, _error_handlers_mtime

    if not os.path.exists(ERROR_HANDLERS_FILE):
        return {}

    try:
        current_mtime = os.path.getmtime(ERROR_HANDLERS_FILE)
        if _error_handlers_cache is not None and current_mtime == _error_handlers_mtime:
            return _error_handlers_cache

        with open(ERROR_HANDLERS_FILE, 'r', encoding='utf-8') as f:
            _error_handlers_cache = json.load(f)
        _error_handlers_mtime = current_mtime
        return _error_handlers_cache
    except Exception as e:
        logging.warning(f"Failed to load error_handlers.json: {e}")
        return {}


def pre_call_intercept(tool_name, action, params):
    """
    Pre-call interception for tool redirects, param corrections, and auto-fixes.
    Returns (should_continue, modified_params_or_error_result)
    - (True, params) = continue with execution using potentially modified params
    - (False, result) = block execution and return this result
    """
    handlers = load_error_handlers()
    if not handlers:
        return True, params

    # 1. Tool redirect check
    redirect_key = f"redirect__{tool_name}"
    if redirect_key in handlers:
        handler = handlers[redirect_key]
        return False, {
            "status": "error",
            "message": handler.get("message", f"Tool '{tool_name}' is not available. Use '{handler.get('correct_tool')}' instead."),
            "correct_tool": handler.get("correct_tool"),
            "intercepted_by": "pre_call_redirect"
        }

    # 2. Param correction
    if isinstance(params, dict):
        for param_key, param_value in list(params.items()):
            correction_key = f"param__{tool_name}__{action}__{param_key}"
            if correction_key in handlers:
                handler = handlers[correction_key]
                correct_param = handler.get("correct_param")
                if correct_param:
                    # Rename the param
                    params[correct_param] = params.pop(param_key)
                    logging.info(f"Auto-corrected param: {param_key} -> {correct_param}")

    # 3. Auto-fix patterns
    if isinstance(params, dict):
        # Double-nested params: {params: {params: {actual}}}
        if "params" in params and isinstance(params["params"], dict):
            inner = params["params"]
            if "params" in inner and isinstance(inner["params"], dict):
                # Double nested - unwrap twice
                params = inner["params"]
                logging.info("Auto-fixed double-nested params")
            else:
                # Single nested - unwrap once
                params = inner
                logging.info("Auto-fixed nested params")

    # 4. Schema check for required params
    schema_key = f"schema__{tool_name}__{action}"
    if schema_key in handlers:
        handler = handlers[schema_key]
        required = handler.get("required_params", "")
        if required:
            required_list = [p.strip() for p in required.split(",") if p.strip()]
            missing = [p for p in required_list if p not in params]
            if missing:
                return False, {
                    "status": "error",
                    "message": handler.get("message", f"Missing required params: {missing}"),
                    "missing_params": missing,
                    "schema": handler,
                    "intercepted_by": "pre_call_schema"
                }

    return True, params


def record_failed_call(tool_name, action, params):
    """Record a failed call for potential self-healing autocorrect. Persisted to disk."""
    failed_call = {
        "tool": tool_name,
        "action": action,
        "params": params.copy() if isinstance(params, dict) else {},
        "timestamp": time.time()
    }
    try:
        write_json(LAST_FAILED_CALL_FILE, failed_call)
    except Exception as e:
        logging.warning(f"Failed to persist failed call: {e}")


def clear_failed_call():
    """Remove the persisted failed call file."""
    try:
        if os.path.exists(LAST_FAILED_CALL_FILE):
            os.remove(LAST_FAILED_CALL_FILE)
    except Exception as e:
        logging.warning(f"Failed to clear failed call file: {e}")


def attempt_param_autocorrect(tool_name, action, params, result, was_error=False):
    """
    If previous call was a failed call to the same tool+action within 60 seconds,
    and exactly one param key changed (same value, different key name),
    auto-append a param correction entry to error_handlers.json.

    Args:
        was_error: True if the current call was an error (including traceback detection)
    """
    # Only process successful calls (no traceback, no explicit error)
    if was_error:
        return
    if not isinstance(result, dict) or result.get("status") == "error":
        return

    # Load persisted failed call from disk
    last_failed_call = read_json(LAST_FAILED_CALL_FILE, default=None)
    if last_failed_call is None:
        return

    # Must be same tool+action
    if last_failed_call.get("tool") != tool_name or last_failed_call.get("action") != action:
        clear_failed_call()
        return

    # Must be within 60 seconds
    elapsed = time.time() - last_failed_call.get("timestamp", 0)
    if elapsed > 60:
        clear_failed_call()
        return

    failed_params = last_failed_call.get("params", {})
    success_params = params if isinstance(params, dict) else {}

    # Find keys that differ
    failed_keys = set(failed_params.keys())
    success_keys = set(success_params.keys())

    # Keys only in failed call (wrong param names)
    wrong_keys = failed_keys - success_keys
    # Keys only in successful call (correct param names)
    correct_keys = success_keys - failed_keys

    # Must have exactly one key changed
    if len(wrong_keys) != 1 or len(correct_keys) != 1:
        clear_failed_call()
        return

    wrong_param = list(wrong_keys)[0]
    correct_param = list(correct_keys)[0]

    # Verify the values are the same (it's truly a rename, not different params)
    if failed_params.get(wrong_param) != success_params.get(correct_param):
        clear_failed_call()
        return

    # Check if this correction already exists
    handlers = load_error_handlers()
    correction_key = f"param__{tool_name}__{action}__{wrong_param}"

    if correction_key in handlers:
        clear_failed_call()
        return

    # Build the correction entry
    correction_entry = {
        "type": "param_correction",
        "tool": tool_name,
        "action": action,
        "wrong_param": wrong_param,
        "correct_param": correct_param,
        "message": f"The param '{wrong_param}' does not exist for {tool_name}.{action}. Use '{correct_param}' instead."
    }

    # Append to error_handlers.json
    try:
        handlers[correction_key] = correction_entry
        write_json(ERROR_HANDLERS_FILE, handlers)

        # Invalidate cache so next load picks up the new entry
        global _error_handlers_cache, _error_handlers_mtime
        _error_handlers_cache = None
        _error_handlers_mtime = 0

        logging.info(f"Self-healing: auto-added param correction {wrong_param} -> {correct_param} for {tool_name}.{action}")
    except Exception as e:
        logging.warning(f"Failed to write param autocorrect: {e}")

    # Clear the failed call tracking
    clear_failed_call()


def post_call_enrich(result, tool_name, action):
    """
    Post-call error enrichment. If result is error, check for matching patterns
    in error_handlers.json and add helpful hints.
    """
    if not isinstance(result, dict):
        return result
    if result.get("status") != "error":
        return result

    handlers = load_error_handlers()
    if not handlers:
        return result

    error_msg = result.get("message", "").lower()

    # Check param corrections for hints
    for key, handler in handlers.items():
        if handler.get("type") == "param_correction":
            if handler.get("tool") == tool_name and handler.get("action") == action:
                wrong_param = handler.get("wrong_param", "")
                if wrong_param and wrong_param.lower() in error_msg:
                    result["hint"] = handler.get("message")
                    result["correction"] = {
                        "wrong_param": wrong_param,
                        "correct_param": handler.get("correct_param")
                    }
                    return result

    # Check schema hints
    schema_key = f"schema__{tool_name}__{action}"
    if schema_key in handlers:
        handler = handlers[schema_key]
        if "required" in error_msg or "missing" in error_msg:
            result["schema_hint"] = handler.get("message")

    return result


# ============================================================================
# THREAD STATE (minimal)
# ============================================================================

def read_thread_state():
    state = read_json(THREAD_STATE_FILE, default={
        "score": 100,
        "tokens_used": 0,
        "execution_count": 0,
        "thread_started_at": time.strftime("%Y-%m-%dT%H:%M:%S")
    })
    # Auto-reset if thread_started_at is >24 hours old
    try:
        started_at = state.get("thread_started_at", "")
        if started_at:
            started = datetime.fromisoformat(started_at.replace('Z', ''))
            age_hours = (datetime.now() - started).total_seconds() / 3600
            if age_hours > 24:
                logging.info(f"Thread state stale ({age_hours:.1f}h old), resetting")
                state = reset_thread_state()
    except Exception:
        pass
    return state


def update_state(score_change=0, token_cost=0):
    state = read_thread_state()
    state["score"] = max(0, min(150, state.get("score", 100) + score_change))
    state["tokens_used"] = state.get("tokens_used", 0) + token_cost
    state["execution_count"] = state.get("execution_count", 0) + 1
    write_json(THREAD_STATE_FILE, state)
    return state


def reset_thread_state():
    state = {
        "score": 100,
        "tokens_used": 0,
        "execution_count": 0,
        "thread_started_at": time.strftime("%Y-%m-%dT%H:%M:%S")
    }
    write_json(THREAD_STATE_FILE, state)
    return state


def attach_telemetry(response, state):
    if not isinstance(response, dict):
        response = {"result": response}
    response["thread_score"] = state.get("score", 100)
    response["tokens_used"] = state.get("tokens_used", 0)
    response["tokens_remaining"] = MAX_TOKEN_BUDGET - state.get("tokens_used", 0)
    response["token_budget"] = MAX_TOKEN_BUDGET
    return response


# ============================================================================
# LOG ROTATION
# ============================================================================

def rotate_logs():
    """Rotate debug logs that grow unbounded. Called periodically."""
    import shutil

    logs_to_rotate = [
        ("data/hook_debug.log", 500 * 1024),  # 500KB max
        ("data/claude_execution.log", 500 * 1024),  # 500KB max
    ]

    archive_dir = Path("data/log_archive")
    archive_dir.mkdir(parents=True, exist_ok=True)

    for log_path, max_size in logs_to_rotate:
        log_file = Path(log_path)
        if log_file.exists():
            try:
                size = log_file.stat().st_size
                if size > max_size:
                    # Archive with timestamp
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    archive_name = f"{log_file.stem}_{timestamp}{log_file.suffix}"
                    archive_path = archive_dir / archive_name
                    shutil.move(str(log_file), str(archive_path))
                    logging.info(f"Rotated {log_path} ({size/1024:.1f}KB) to {archive_path}")

                    # Keep only last 5 archives per log type
                    pattern = f"{log_file.stem}_*{log_file.suffix}"
                    archives = sorted(archive_dir.glob(pattern), reverse=True)
                    for old_archive in archives[5:]:
                        old_archive.unlink()
                        logging.info(f"Deleted old archive: {old_archive}")
            except Exception as e:
                logging.warning(f"Failed to rotate {log_path}: {e}")


# ============================================================================
# EXECUTION LOGGING
# ============================================================================

def log_execution(tool, action, params, status, result, duration_ms=None):
    """NDJSON append-only logging - one JSON per line"""
    try:
        os.makedirs("data", exist_ok=True)

        # Rotate logs periodically (every 10th execution)
        state = read_json(THREAD_STATE_FILE, default={})
        if state.get("execution_count", 0) % 10 == 0:
            rotate_logs()

        # NDJSON append - one entry per line, no read-modify-write
        entry = {
            "tool": tool,
            "action": action,
            "params": params,
            "status": status,
            "source": "claude_code",
            "output": result,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
        }
        if duration_ms is not None:
            entry["duration_ms"] = duration_ms

        # Append to NDJSON file
        with open(EXECUTION_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + '\n')

    except Exception as e:
        logging.warning(f"Failed to log execution: {e}")


# ============================================================================
# REGISTRY
# ============================================================================

def load_registry():
    if not os.path.exists(NDJSON_REGISTRY_FILE):
        return {}

    tools = {}
    with open(NDJSON_REGISTRY_FILE, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                tool = entry["tool"]
                action = entry["action"]

                if tool not in tools:
                    tools[tool] = {"path": None, "actions": {}, "locked": False}

                if action == "__tool__":
                    tools[tool]["path"] = entry["script_path"]
                    tools[tool]["locked"] = entry.get("locked", False)
                else:
                    tools[tool]["actions"][action] = {
                        "params": entry.get("params", []),
                        "timeout_seconds": entry.get("timeout_seconds", DEFAULT_TIMEOUT)
                    }
            except:
                pass
    return tools


# ============================================================================
# CORE EXECUTION
# ============================================================================

def execute_tool(tool_name, action, params):
    """Execute tool via subprocess. Simple."""
    registry = load_registry()
    state = read_thread_state()

    # PRE-CALL INTERCEPTION
    should_continue, intercept_result = pre_call_intercept(tool_name, action, params)
    if not should_continue:
        state = update_state(-5)
        log_execution(tool_name, action, params, "intercepted", intercept_result)
        return sanitize_response(attach_telemetry(intercept_result, state))
    params = intercept_result  # May have been modified by auto-fix

    # Validate tool exists
    if tool_name not in registry:
        state = update_state(-10)
        result = {"status": "error", "message": f"Tool '{tool_name}' not found"}
        log_execution(tool_name, action, params, "error", result)
        return sanitize_response(attach_telemetry(result, state))

    tool_info = registry[tool_name]
    script_path = tool_info.get("path")

    if not script_path or not os.path.isfile(script_path):
        state = update_state(-10)
        result = {"status": "error", "message": f"Script not found: {script_path}"}
        log_execution(tool_name, action, params, "error", result)
        return sanitize_response(attach_telemetry(result, state))

    # Resolve action aliases
    alias_key = (tool_name, action)
    if alias_key in ACTION_ALIASES:
        action = ACTION_ALIASES[alias_key]

    if action not in tool_info["actions"]:
        state = update_state(-10)
        result = {"status": "error", "message": f"Action '{action}' not found", "available": list(tool_info["actions"].keys())}
        log_execution(tool_name, action, params, "error", result)
        return sanitize_response(attach_telemetry(result, state))

    # Get timeout
    timeout = tool_info["actions"][action].get("timeout_seconds", DEFAULT_TIMEOUT)

    # Special: execute_queue runs async
    if tool_name == "claude_assistant" and action == "execute_queue":
        reset_thread_state()
        start_time = time.time()
        try:
            process = subprocess.Popen(
                [sys.executable, script_path, action, "--params", json.dumps(params)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            duration_ms = round((time.time() - start_time) * 1000)
            result = {"status": "started", "message": "Queue execution started", "pid": process.pid}
            log_execution(tool_name, action, params, "started", result, duration_ms)
            return sanitize_response(attach_telemetry(result, read_thread_state()))
        except Exception as e:
            duration_ms = round((time.time() - start_time) * 1000)
            result = {"status": "error", "message": str(e)}
            log_execution(tool_name, action, params, "error", result, duration_ms)
            return sanitize_response(attach_telemetry(result, read_thread_state()))

    # Execute subprocess
    start_time = time.time()
    try:
        cmd = [sys.executable, script_path, action, "--params", json.dumps(params)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

        duration_ms = round((time.time() - start_time) * 1000)

        output = proc.stdout.strip()
        stderr_output = proc.stderr.strip() if proc.stderr else ""

        try:
            parsed = json.loads(output)
        except:
            parsed = {"raw_output": output, "stderr": stderr_output}

        # Inject schema hint on "Missing required" errors
        parsed = inject_schema_on_error(parsed, tool_name, action)

        # POST-CALL ERROR ENRICHMENT
        parsed = post_call_enrich(parsed, tool_name, action)

        # Determine status: check explicit error OR traceback in stderr
        has_traceback = "Traceback" in stderr_output
        explicit_error = parsed.get("status") == "error"
        status = "error" if (explicit_error or has_traceback) else "success"

        # If traceback detected but no explicit error status, add context
        if has_traceback and not explicit_error:
            parsed["_traceback_detected"] = True
            parsed["stderr"] = stderr_output

        state = update_state(-10 if status == "error" else +5)
        log_execution(tool_name, action, params, status, parsed, duration_ms)

        # Self-healing: record failed calls, attempt autocorrect on success
        if status == "error":
            record_failed_call(tool_name, action, params)
        else:
            attempt_param_autocorrect(tool_name, action, params, parsed, was_error=False)

        return sanitize_response(attach_telemetry(parsed, state))

    except subprocess.TimeoutExpired:
        duration_ms = round((time.time() - start_time) * 1000)
        state = update_state(-20)
        result = {"status": "error", "message": f"Timeout after {timeout}s"}
        log_execution(tool_name, action, params, "timeout", result, duration_ms)
        return sanitize_response(attach_telemetry(result, state))

    except Exception as e:
        duration_ms = round((time.time() - start_time) * 1000)
        state = update_state(-20)
        result = {"status": "error", "message": str(e)}
        log_execution(tool_name, action, params, "error", result, duration_ms)
        return sanitize_response(attach_telemetry(result, state))


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action")
    parser.add_argument("--params", type=str)
    args = parser.parse_args()

    if args.action == "load_orchestrate_os":
        state = reset_thread_state()
        result = {"status": "ready", "message": "OrchestrateOS loaded"}
        print(json.dumps(attach_telemetry(result, state), indent=4))
        return

    if args.action == "execute_task":
        try:
            p = json.loads(args.params or "{}")
            tool = p.get("tool_name")
            act = p.get("action")
            prms = p.get("params", {})

            if not tool or not act:
                raise ValueError("Missing tool_name or action")

            result = execute_tool(tool, act, prms)
            print(json.dumps(result, indent=4))

        except Exception as e:
            result = {"status": "error", "message": str(e)}
            print(json.dumps(attach_telemetry(result, read_thread_state()), indent=4))
    else:
        result = {"status": "error", "message": "Invalid action"}
        print(json.dumps(attach_telemetry(result, read_thread_state()), indent=4))


if __name__ == "__main__":
    main()
