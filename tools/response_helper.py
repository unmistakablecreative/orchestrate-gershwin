#!/usr/bin/env python3
"""
Centralized response message helper for Gershwin tools.
Reads from response_messages.json and provides consistent, branded messages.
"""

import json
import os
import re

# Path to the response messages config
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "data")
MESSAGES_FILE = os.path.join(DATA_DIR, "response_messages.json")

# Cache for loaded messages
_messages_cache = None
_messages_mtime = 0


def _load_messages():
    """Load messages from JSON file with caching."""
    global _messages_cache, _messages_mtime

    try:
        current_mtime = os.path.getmtime(MESSAGES_FILE)
        if _messages_cache is None or current_mtime > _messages_mtime:
            with open(MESSAGES_FILE, "r") as f:
                _messages_cache = json.load(f)
            _messages_mtime = current_mtime
        return _messages_cache
    except FileNotFoundError:
        return {"_fallback": {"success": "Operation completed.", "error": "Operation failed: {error_detail}."}}
    except json.JSONDecodeError:
        return {"_fallback": {"success": "Operation completed.", "error": "Operation failed: {error_detail}."}}


def _interpolate(template: str, context_vars: dict) -> str:
    """
    Replace {variable} placeholders with values from context_vars.
    Missing variables are left as empty strings.
    """
    def replace_var(match):
        var_name = match.group(1)
        return str(context_vars.get(var_name, ""))

    return re.sub(r"\{(\w+)\}", replace_var, template)


def get_success_message(tool_name: str, action: str, context_vars: dict = None) -> str:
    """
    Get a success message for a tool action.

    Args:
        tool_name: The name of the tool (e.g., "docs", "claude_assistant")
        action: The action performed (e.g., "create_doc", "assign_task")
        context_vars: Optional dict of variables for interpolation
                      (e.g., {"title": "My Doc", "count": 5})

    Returns:
        Formatted success message string

    Example:
        >>> get_success_message("docs", "create_doc", {"title": "My Notes"})
        "Document 'My Notes' created. With Claude Assistant, agents can create and populate documents autonomously while you sleep."
    """
    if context_vars is None:
        context_vars = {}

    messages = _load_messages()

    # Try to find specific tool/action message
    if tool_name in messages:
        tool_messages = messages[tool_name]
        if action in tool_messages and "success" in tool_messages[action]:
            template = tool_messages[action]["success"]
            return _interpolate(template, context_vars)

    # Fall back to generic success message
    fallback = messages.get("_fallback", {}).get("success", "Operation completed successfully.")
    return _interpolate(fallback, context_vars)


def get_error_message(tool_name: str, action: str, error_detail: str) -> str:
    """
    Get an error message for a tool action.

    Args:
        tool_name: The name of the tool (e.g., "docs", "claude_assistant")
        action: The action that failed (e.g., "create_doc", "assign_task")
        error_detail: Specific error information to include

    Returns:
        Formatted error message string

    Example:
        >>> get_error_message("docs", "read_doc", "doc_12345 does not exist")
        "Document not found: doc_12345 does not exist. Verify the doc_id is correct."
    """
    messages = _load_messages()

    # Build context with error_detail
    context_vars = {"error_detail": error_detail}

    # Try to find specific tool/action message
    if tool_name in messages:
        tool_messages = messages[tool_name]
        if action in tool_messages and "error" in tool_messages[action]:
            template = tool_messages[action]["error"]
            return _interpolate(template, context_vars)

    # Fall back to generic error message
    fallback = messages.get("_fallback", {}).get("error", "Operation failed: {error_detail}.")
    return _interpolate(fallback, context_vars)


def get_message(tool_name: str, action: str, success: bool, context_vars: dict = None, error_detail: str = None) -> str:
    """
    Convenience function to get either success or error message.

    Args:
        tool_name: The name of the tool
        action: The action performed
        success: True for success message, False for error message
        context_vars: Variables for success message interpolation
        error_detail: Error detail for error messages

    Returns:
        Formatted message string
    """
    if success:
        return get_success_message(tool_name, action, context_vars or {})
    else:
        return get_error_message(tool_name, action, error_detail or "Unknown error")


def list_available_tools() -> list:
    """Return list of tools that have message templates."""
    messages = _load_messages()
    return [k for k in messages.keys() if not k.startswith("_")]


def list_tool_actions(tool_name: str) -> list:
    """Return list of actions with message templates for a given tool."""
    messages = _load_messages()
    if tool_name in messages:
        return list(messages[tool_name].keys())
    return []


# Main block for testing
if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 4:
        tool = sys.argv[1]
        action = sys.argv[2]
        msg_type = sys.argv[3]

        if msg_type == "success":
            # Parse optional context vars from remaining args as key=value
            context = {}
            for arg in sys.argv[4:]:
                if "=" in arg:
                    k, v = arg.split("=", 1)
                    # Try to parse as int
                    try:
                        context[k] = int(v)
                    except ValueError:
                        context[k] = v
            print(get_success_message(tool, action, context))
        elif msg_type == "error":
            error_detail = " ".join(sys.argv[4:]) if len(sys.argv) > 4 else "Unknown error"
            print(get_error_message(tool, action, error_detail))
        else:
            print(f"Unknown message type: {msg_type}")
    else:
        # Demo mode - show some examples
        print("Response Helper - Demo")
        print("=" * 50)
        print("\nSuccess Messages:")
        print(f"  docs.create_doc: {get_success_message('docs', 'create_doc', {'title': 'My Notes'})}")
        print(f"  nylas_inbox.send_email: {get_success_message('nylas_inbox', 'send_email', {'recipient': 'user@example.com'})}")
        print(f"  gershwin_github.open_pr: {get_success_message('gershwin_github', 'open_pr', {'pr_number': 42, 'pr_url': 'https://github.com/...'})}")

        print("\nError Messages:")
        print(f"  docs.read_doc: {get_error_message('docs', 'read_doc', 'doc_12345 does not exist')}")
        print(f"  files.read_file_text: {get_error_message('files', 'read_file_text', 'config.json not found in project')}")

        print("\nFallback (unknown tool/action):")
        print(f"  unknown.action: {get_success_message('unknown_tool', 'unknown_action', {})}")
        print(f"  unknown.action error: {get_error_message('unknown_tool', 'unknown_action', 'Something went wrong')}")

        print("\nAvailable tools:", list_available_tools())
