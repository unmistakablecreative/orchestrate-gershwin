import json
import os
from difflib import get_close_matches

SUPPORTED_ACTIONS_PATH = "supported_actions.json"
SESSION_STATE_PATH = "session_state.json"

AUTO_PARAM_MAP = {
    "query": "filename",
    "file_name": "filename",
    "doc": "filename",
    "name": "filename"
}

VALIDATION_MODE = "correct"  # Options: 'strict', 'correct', 'warn'

def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

supported_actions = load_json(SUPPORTED_ACTIONS_PATH)
session = load_json(SESSION_STATE_PATH)

class ContractViolation(Exception):
    pass

def validate_action(tool_name, action_name, params):
    # Skip param validation for tools not in registry (AI-only actions)
    if tool_name not in supported_actions:
        return params

    tool_actions = supported_actions.get(tool_name, {})
    expected_params = tool_actions.get(action_name, {}).get("params", [])

    corrected_params = {}
    warnings = []

    for key, value in params.items():
        corrected_key = AUTO_PARAM_MAP.get(key, key)

        # Auto-correct and log
        if key != corrected_key:
            print(f"⚠️ Autocorrected param '{key}' to '{corrected_key}'")

        if expected_params and corrected_key not in expected_params:
            close = get_close_matches(corrected_key, expected_params, n=1)
            if VALIDATION_MODE == "strict":
                raise ContractViolation(f"🚫 Invalid param '{key}' → Did you mean '{close[0]}'?")
            elif VALIDATION_MODE == "warn":
                warnings.append(f"⚠️ Param '{key}' not expected. Using '{corrected_key}'")

        corrected_params[corrected_key] = value

    # Special fail-safe: make sure filename is present even if query slipped through
    if "filename" not in corrected_params and "query" in params:
        corrected_params["filename"] = params["query"]
        print("⚠️ Enforced fallback: Injected 'filename' from 'query'")

    filename = corrected_params.get("filename", "")
    base_filename = os.path.basename(filename)

    # === Root directory write protection ===
    abs_path = os.path.abspath(filename)
    if tool_name in ["json_manager", "vs_code_tool"] and action_name in DESTRUCTIVE_ACTIONS:
        if os.path.dirname(abs_path) == os.path.abspath("."):
            raise ContractViolation(
                f"🚫 Writing to root directory is not allowed: '{filename}'"
            )


    # === VS Code block for json mode ===
    if session.get("mode") == "json" and tool_name == "vs_code_tool":
        if filename.endswith(".json"):
            raise ContractViolation("🚫 You're in JSON mode. VS Code cannot write to JSON memory files.")

    # === Protected file logic ===
    LOCKED_FILES = [
        "srini_notes.json", "files.json", "recall.json",
        "thread_memory.json", "system_notes.json", "roadmap.json",
        "content_calendar.json", "arin_render_protocol.json", "execution_logic.json"
    ]

    DESTRUCTIVE_ACTIONS = [
        "create_file", "write_file", "replace_in_file", "delete_file"
    ]

    if base_filename in LOCKED_FILES and action_name in DESTRUCTIVE_ACTIONS:
        raise ContractViolation(
            f"🚨 Action '{action_name}' is not allowed on protected file '{base_filename}'. "
            "Field-level operations only. This file cannot be overwritten."
        )

    if warnings:
        print("\n".join(warnings))

    return corrected_params
