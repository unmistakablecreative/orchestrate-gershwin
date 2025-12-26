#!/usr/bin/env python3
"""
System Settings

Auto-refactored by refactorize.py to match gold standard structure.
"""

import os
import sys
import json
import subprocess

import importlib.util
import inspect
import shutil


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SYSTEM_REGISTRY = os.path.join(os.path.dirname(BASE_DIR), "system_settings.ndjson")
TOOLS_DIR = BASE_DIR
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")


def load_credential(key):
    """Load a credential from credentials.json"""
    try:
        if not os.path.exists(CREDENTIALS_FILE):
            return None
        with open(CREDENTIALS_FILE, 'r') as f:
            creds = json.load(f)
        return creds.get(key)
    except Exception:
        return None


def save_credential(key, value):
    """Save a credential to credentials.json"""
    try:
        creds = {}
        if os.path.exists(CREDENTIALS_FILE):
            with open(CREDENTIALS_FILE, 'r') as f:
                creds = json.load(f)

        creds[key] = value

        with open(CREDENTIALS_FILE, 'w') as f:
            json.dump(creds, f, indent=2)

        return {"status": "success"}
    except Exception as e:
        return {"error": f"Failed to save credential: {e}"}


def set_credential(params):
    """
    Set a credential for a tool by parsing the script to auto-detect required keys

    Required:
    - tool_name: name of tool (e.g., "outline_editor")
    - value: credential value

    Example:
    {"tool_name": "outline_editor", "value": "sk-outline-abc123"}

    The function looks up the script_path from the registry, parses it to find
    load_credential() calls, and extracts the actual key names.
    """
    import re

    value = params.get("value")
    tool_name = params.get("tool_name")

    if not value:
        return {"status": "error", "message": "❌ Missing 'value' in params"}
    if not tool_name:
        return {"status": "error", "message": "❌ Missing 'tool_name' in params"}

    # Look up script_path from registry
    registry = load_registry()
    script_path = None
    for entry in registry:
        if entry.get("tool") == tool_name and entry.get("action") == "__tool__":
            script_path = entry.get("script_path")
            break

    if not script_path:
        return {"status": "error", "message": f"❌ Tool '{tool_name}' not found in registry"}

    # Handle both absolute and relative paths
    if not os.path.isabs(script_path):
        script_path = os.path.join(os.path.dirname(SYSTEM_REGISTRY), script_path)

    if not os.path.exists(script_path):
        return {"status": "error", "message": f"❌ Script not found: {script_path}"}

    expected_keys = set()

    try:
        with open(script_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Targeted pattern matching - catch credential access patterns
        patterns = [
            # load_credential("key") or load_credential('key')
            r'load_credential\([\'"]([a-zA-Z0-9_]{3,40})[\'"]\)',

            # creds.get("key") or creds.get('key')
            r'creds\.get\([\'"]([a-zA-Z0-9_]{3,40})[\'"]\)',

            # creds["key"] or creds['key']
            r'creds\[[\'"]([a-zA-Z0-9_]{3,40})[\'"]\]',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                if match and len(match) >= 5:
                    # Filter out overly generic single-word keys
                    if match.lower() not in ['api_key', 'token', 'secret', 'access_token', 'key', 'value', 'creds', 'credential']:
                        # If it has an underscore OR ends with common suffixes, it's valid
                        if '_' in match or any(match.lower().endswith(suffix) for suffix in ['_api_key', '_token', '_secret', '_key', 'api_key', 'token', 'secret']):
                            expected_keys.add(match)

    except Exception as e:
        return {"status": "error", "message": f"❌ Failed to parse script: {str(e)}"}

    if not expected_keys:
        return {
            "status": "error",
            "message": "❌ No credential keys found in script. Supported patterns: load_credential(), creds.get(), creds[]"
        }

    # Inject into credentials.json
    creds_path = CREDENTIALS_FILE

    creds = {}
    if os.path.exists(creds_path):
        try:
            with open(creds_path, "r") as f:
                creds = json.load(f)
        except:
            creds = {}

    # Set all found keys to the same value
    for key in expected_keys:
        creds[key] = value

    with open(creds_path, "w") as f:
        json.dump(creds, f, indent=2)

    return {
        "status": "success",
        "keys_set": list(expected_keys),
        "credentials_file": creds_path,
        "message": f"✅ Credential injected into: {', '.join(expected_keys)}"
    }


def load_registry():
    """Load system_settings.ndjson as list of entries"""
    try:
        with open(SYSTEM_REGISTRY, 'r') as f:
            return [json.loads(line.strip()) for line in f if line.strip()]
    except Exception as e:
        return []


def save_registry(entries):
    """Save registry entries back to system_settings.ndjson"""
    try:
        with open(SYSTEM_REGISTRY, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + '\n')
        return {"status": "success"}
    except Exception as e:
        return {"error": f"Failed to save registry: {e}"}


def extract_actions_from_script(tool_script_path):
    """
    Extract actions from tool script

    Supports both:
    1. Legacy ACTIONS dict (for backward compatibility)
    2. Refactored main() if/elif router (gold standard)
    """
    import ast
    import re

    try:
        # Try loading module first for ACTIONS dict (backward compatibility)
        spec = importlib.util.spec_from_file_location("tool_module", tool_script_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Check for legacy ACTIONS dict
        if hasattr(module, 'ACTIONS'):
            actions_dict = module.ACTIONS
            actions = []

            for action_name, action_func in actions_dict.items():
                sig = inspect.signature(action_func)
                params = []

                for param_name, param in sig.parameters.items():
                    param_info = {
                        "name": param_name,
                        "required": param.default == inspect.Parameter.empty
                    }

                    if param.annotation != inspect.Parameter.empty:
                        param_info["type"] = param.annotation.__name__

                    params.append(param_info)

                description = action_func.__doc__ or f"Execute {action_name}"
                description = description.strip().split('\n')[0]

                actions.append({
                    "action": action_name,
                    "description": description,
                    "parameters": params
                })

            return {"status": "success", "actions": actions}

        # No ACTIONS dict - parse main() function for refactored tools
        with open(tool_script_path, 'r') as f:
            content = f.read()

        tree = ast.parse(content)

        # Find main() function
        main_func = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'main':
                main_func = node
                break

        if not main_func:
            return {"error": "No ACTIONS dict or main() function found"}

        # Extract action names from if/elif chain
        actions = []
        action_pattern = re.compile(r"args\.action\s*==\s*['\"]([a-zA-Z0-9_]+)['\"]")

        for node in ast.walk(main_func):
            if isinstance(node, ast.Compare):
                # Convert node back to source to check pattern
                try:
                    line = ast.get_source_segment(content, node)
                    match = action_pattern.search(line)
                    if match:
                        action_name = match.group(1)

                        # Try to find function with this name in module
                        if hasattr(module, action_name):
                            action_func = getattr(module, action_name)
                            sig = inspect.signature(action_func)
                            params = []

                            for param_name, param in sig.parameters.items():
                                param_info = {
                                    "name": param_name,
                                    "required": param.default == inspect.Parameter.empty
                                }

                                if param.annotation != inspect.Parameter.empty:
                                    param_info["type"] = param.annotation.__name__

                                params.append(param_info)

                            description = action_func.__doc__ or f"Execute {action_name}"
                            description = description.strip().split('\n')[0]

                            actions.append({
                                "action": action_name,
                                "description": description,
                                "parameters": params
                            })
                except:
                    pass

        if not actions:
            return {"error": "No actions extracted from main() function"}

        return {"status": "success", "actions": actions}

    except Exception as e:
        return {"error": f"Failed to extract actions: {e}"}


def add_tool(params):
    """
    Register a tool and all its actions
    
    Required:
    - tool_name: name of tool
    - script_path: path to tool script (optional, auto-detects from tools/{tool_name}.py)
    
    Optional:
    - locked: whether tool starts locked (default: False)
    - referral_unlock_cost: cost to unlock (default: 0)
    """
    tool_name = params.get("tool_name")
    script_path = params.get("script_path")
    locked = params.get("locked", False)  # Default to unlocked
    cost = params.get("referral_unlock_cost", 0)

    if not tool_name:
        return {"status": "error", "message": "Missing required field: tool_name"}

    # Auto-detect script path
    if not script_path:
        script_path = os.path.join(TOOLS_DIR, f"{tool_name}.py")

    if not os.path.exists(script_path):
        return {"error": f"Tool script not found: {script_path}"}

    # Extract actions
    extract_result = extract_actions_from_script(script_path)
    if "error" in extract_result:
        return extract_result

    actions = extract_result["actions"]

    # Load registry
    registry = load_registry()

    # Remove existing entries for this tool
    registry = [entry for entry in registry if entry.get("tool") != tool_name]

    # Add tool header with proper lock status
    registry.append({
        "tool": tool_name,
        "action": "__tool__",
        "script_path": script_path,
        "description": f"{tool_name} tool",
        "locked": locked,
        "unlocked": not locked,  # Inverse of locked
        "referral_unlock_cost": cost
    })

    # Add actions
    for action in actions:
        entry = {
            "tool": tool_name,
            "action": action["action"],
            "script_path": script_path,
            "description": action["description"]
        }
        
        if action["parameters"]:
            entry["parameters"] = action["parameters"]
        
        registry.append(entry)

    # Save
    save_result = save_registry(registry)
    if "error" in save_result:
        return save_result

    return {
        "status": "success",
        "tool": tool_name,
        "actions_registered": len(actions)
    }


def remove_tool(params):
    """
    Remove a tool from registry
    
    Required:
    - tool_name: name of tool to remove
    """
    tool_name = params.get("tool_name")

    if not tool_name:
        return {"status": "error", "message": "Missing required field: tool_name"}

    registry = load_registry()

    original_count = len(registry)
    registry = [entry for entry in registry if entry.get("tool") != tool_name]
    removed_count = original_count - len(registry)

    if removed_count == 0:
        return {"status": "error", "message": f"Tool '{tool_name}' not found"}

    save_result = save_registry(registry)
    if "error" in save_result:
        return save_result

    return {
        "status": "success",
        "message": f"Removed {removed_count} entries for '{tool_name}'"
    }


def add_action(params):
    """
    Add a single action to a tool
    
    Required:
    - tool_name: name of tool
    - action_name: name of action
    - description: action description
    
    Optional:
    - parameters: list of parameter dicts
    """
    tool_name = params.get("tool_name")
    action_name = params.get("action_name")
    description = params.get("description", f"Execute {action_name}")
    parameters = params.get("parameters", [])

    if not tool_name or not action_name:
        return {"status": "error", "message": "Missing required fields: tool_name, action_name"}

    registry = load_registry()

    entry = {
        "tool": tool_name,
        "action": action_name,
        "description": description
    }
    
    if parameters:
        entry["parameters"] = parameters

    registry.append(entry)

    save_result = save_registry(registry)
    if "error" in save_result:
        return save_result

    return {
        "status": "success",
        "message": f"Action '{action_name}' added to '{tool_name}'"
    }


def remove_action(params):
    """
    Remove a specific action from a tool
    
    Required:
    - tool_name: name of tool
    - action_name: name of action to remove
    """
    tool_name = params.get("tool_name")
    action_name = params.get("action_name")

    if not tool_name or not action_name:
        return {"status": "error", "message": "Missing required fields: tool_name, action_name"}

    registry = load_registry()

    original_count = len(registry)
    registry = [entry for entry in registry 
                if not (entry.get("tool") == tool_name and entry.get("action") == action_name)]
    removed_count = original_count - len(registry)

    if removed_count == 0:
        return {"status": "error", "message": f"Action '{action_name}' not found in '{tool_name}'"}

    save_result = save_registry(registry)
    if "error" in save_result:
        return save_result

    return {
        "status": "success",
        "message": f"Removed action '{action_name}' from '{tool_name}'"
    }


def list_tools(params):
    """List all registered tools"""
    registry = load_registry()

    tools = {}
    for entry in registry:
        if entry.get("action") == "__tool__":
            tool_name = entry.get("tool")
            tools[tool_name] = {
                "name": tool_name,
                "unlocked": entry.get("unlocked", False),
                "description": entry.get("description", "")
            }

    return {
        "status": "success",
        "tools": list(tools.values())
    }


def list_supported_actions(params):
    """List all actions in the system"""
    registry = load_registry()

    actions = []
    for entry in registry:
        if entry.get("action") != "__tool__":
            actions.append({
                "tool": entry.get("tool"),
                "action": entry.get("action"),
                "description": entry.get("description", ""),
                "params": entry.get("parameters", [])
            })

    return {
        "status": "success",
        "actions": actions
    }


def add_memory_file(params):
    """
    Add a file to memory tracking
    
    Required:
    - path: file path to track
    """
    path = params.get("path")

    if not path:
        return {"status": "error", "message": "Missing required field: path"}

    memory_config = os.path.join(BASE_DIR, "data", "memory_files.json")

    memory_files = []
    if os.path.exists(memory_config):
        with open(memory_config, 'r') as f:
            memory_files = json.load(f)

    if path not in memory_files:
        memory_files.append(path)

    os.makedirs(os.path.dirname(memory_config), exist_ok=True)
    with open(memory_config, 'w') as f:
        json.dump(memory_files, f, indent=2)

    return {
        "status": "success",
        "message": f"Added '{path}' to memory tracking"
    }


def remove_memory_file(params):
    """
    Remove a file from memory tracking
    
    Required:
    - path: file path to remove
    """
    path = params.get("path")

    if not path:
        return {"status": "error", "message": "Missing required field: path"}

    memory_config = os.path.join(BASE_DIR, "data", "memory_files.json")

    if not os.path.exists(memory_config):
        return {"status": "error", "message": "No memory files configured"}

    with open(memory_config, 'r') as f:
        memory_files = json.load(f)

    if path not in memory_files:
        return {"status": "error", "message": f"Path '{path}' not in memory tracking"}

    memory_files.remove(path)

    with open(memory_config, 'w') as f:
        json.dump(memory_files, f, indent=2)

    return {
        "status": "success",
        "message": f"Removed '{path}' from memory tracking"
    }


def list_memory_files(params):
    """List all memory tracked files"""
    memory_config = os.path.join(BASE_DIR, "data", "memory_files.json")

    if not os.path.exists(memory_config):
        return {"status": "success", "memory_files": []}

    with open(memory_config, 'r') as f:
        memory_files = json.load(f)

    return {"status": "success", "memory_files": memory_files}


def build_working_memory(params):
    """Build working memory from tracked files"""
    memory_config = os.path.join(BASE_DIR, "data", "memory_files.json")

    if not os.path.exists(memory_config):
        return {
            "status": "success",
            "message": "No memory files configured",
            "working_memory": {}
        }

    with open(memory_config, 'r') as f:
        memory_files = json.load(f)

    working_memory = {}

    for file_path in memory_files:
        full_path = os.path.join(BASE_DIR, file_path)
        if os.path.exists(full_path):
            try:
                with open(full_path, 'r') as f:
                    data = json.load(f)
                    working_memory[file_path] = data
            except Exception:
                pass

    # Save to working_memory.json
    output_path = os.path.join(BASE_DIR, "data", "working_memory.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(working_memory, f, indent=2)

    return {
        "status": "success",
        "message": "Working memory built",
        "files_loaded": len(working_memory)
    }


def refresh_runtime(params):
    """
    Pull latest updates from repo while preserving user data
    
    Protected:
    - data/ directory (credentials, queues, user data)
    - container_state/ (system identity, referrals)
    - User's unlock status
    
    Updated:
    - Tool scripts
    - orchestrate_app_store.json
    - System messages
    """
    try:
        # Save user state
        referral_path = os.path.join(BASE_DIR, "container_state", "referrals.json")
        unlocked_tools = set()
        user_credits = 0

        if os.path.exists(referral_path):
            with open(referral_path, 'r') as f:
                referral_data = json.load(f)
                unlocked_tools = set(referral_data.get("tools_unlocked", []))
                user_credits = referral_data.get("referral_credits", 0)

        # Git pull
        result = subprocess.run(
            ["git", "-C", BASE_DIR, "pull"],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            return {"error": "Git pull failed", "details": result.stderr}

        # Restore unlock status
        registry = load_registry()
        for entry in registry:
            tool_name = entry.get("tool")
            if entry.get("action") == "__tool__" and tool_name in unlocked_tools:
                entry["unlocked"] = True

        save_registry(registry)

        return {
            "status": "success",
            "message": "Runtime refreshed",
            "tools_preserved": list(unlocked_tools),
            "credits_preserved": user_credits
        }

    except subprocess.TimeoutExpired:
        return {"error": "Git pull timed out"}
    except Exception as e:
        return {"error": f"Runtime refresh failed: {e}"}


def main():
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    if args.action == 'add_action':
        result = add_action(params)
    elif args.action == 'add_memory_file':
        result = add_memory_file(params)
    elif args.action == 'add_tool':
        result = add_tool(params)
    elif args.action == 'build_working_memory':
        result = build_working_memory(params)
    elif args.action == 'extract_actions_from_script':
        result = extract_actions_from_script(**params)
    elif args.action == 'list_memory_files':
        result = list_memory_files(params)
    elif args.action == 'list_supported_actions':
        result = list_supported_actions(params)
    elif args.action == 'list_tools':
        result = list_tools(params)
    elif args.action == 'load_credential':
        result = load_credential(**params)
    elif args.action == 'load_registry':
        result = load_registry()
    elif args.action == 'refresh_runtime':
        result = refresh_runtime(params)
    elif args.action == 'remove_action':
        result = remove_action(params)
    elif args.action == 'remove_memory_file':
        result = remove_memory_file(params)
    elif args.action == 'remove_tool':
        result = remove_tool(params)
    elif args.action == 'save_credential':
        result = save_credential(**params)
    elif args.action == 'save_registry':
        result = save_registry(**params)
    elif args.action == 'set_credential':
        result = set_credential(params)
    else:
        result = {'status': 'error', 'message': f'Unknown action {args.action}'}

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()