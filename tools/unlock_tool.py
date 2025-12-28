#!/usr/bin/env python3
"""
Unlock Tool

Auto-refactored by refactorize.py to match gold standard structure.
"""

import os
import sys
import json
import subprocess

import requests
from datetime import datetime


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUNTIME_DIR = os.path.dirname(BASE_DIR)
APP_STORE_PATH = os.path.join(RUNTIME_DIR, "data", "orchestrate_app_store.json")
UNLOCK_STATUS_PATH = os.path.join(RUNTIME_DIR, "data", "unlock_status.json")
STATE_DIR = os.path.expanduser("~/Library/Application Support/OrchestrateOS")
REFERRAL_PATH = os.path.join(STATE_DIR, "referrals.json")
IDENTITY_PATH = os.path.join(STATE_DIR, "system_identity.json")
SYSTEM_REGISTRY = os.path.join(RUNTIME_DIR, "system_settings.ndjson")
JSONBIN_ID = "694f0af6ae596e708fb2bd68"
JSONBIN_KEY = "$2a$10$MoavwaWsCucy2FkU/5ycV.lBTPWoUq4uKHhCi9Y47DOHWyHFL3o2C"


def update_unlock_status(tool_name):
    """Update unlock_status.json with newly unlocked tool"""
    try:
        unlock_status = {"tools_unlocked": []}
        if os.path.exists(UNLOCK_STATUS_PATH):
            with open(UNLOCK_STATUS_PATH, 'r') as f:
                unlock_status = json.load(f)

        if "tools_unlocked" not in unlock_status:
            unlock_status["tools_unlocked"] = []

        if tool_name not in unlock_status["tools_unlocked"]:
            unlock_status["tools_unlocked"].append(tool_name)

            with open(UNLOCK_STATUS_PATH, 'w') as f:
                json.dump(unlock_status, f, indent=2)

        return {"status": "success"}
    except Exception as e:
        return {"error": f"Failed to update unlock_status.json: {e}"}


def load_app_store():
    """Load app store configuration"""
    try:
        with open(APP_STORE_PATH, 'r') as f:
            data = json.load(f)
            return data.get("entries", {})
    except Exception as e:
        return {}


def load_registry():
    """Load system_settings.ndjson"""
    try:
        with open(SYSTEM_REGISTRY, 'r') as f:
            return [json.loads(line.strip()) for line in f if line.strip()]
    except Exception as e:
        return []


def save_registry(entries):
    """Save system_settings.ndjson"""
    try:
        with open(SYSTEM_REGISTRY, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + '\n')
        return {"status": "success"}
    except Exception as e:
        return {"error": f"Failed to save registry: {e}"}


def load_local_ledger():
    """Load user's local referral ledger"""
    try:
        with open(REFERRAL_PATH, 'r') as f:
            return json.load(f)
    except Exception as e:
        return {"error": f"Failed to load local ledger: {e}"}


def save_local_ledger(ledger):
    """Save updated local ledger"""
    try:
        with open(REFERRAL_PATH, 'w') as f:
            json.dump(ledger, f, indent=2)
        return {"status": "success"}
    except Exception as e:
        return {"error": f"Failed to save local ledger: {e}"}


def get_user_id():
    """Get user's unique ID from system identity"""
    try:
        with open(IDENTITY_PATH, 'r') as f:
            identity = json.load(f)
            return identity.get("user_id")
    except Exception as e:
        return None


def sync_from_jsonbin():
    """Sync credits FROM JSONBin to local ledger"""
    try:
        user_id = get_user_id()
        if not user_id:
            return {"error": "No user ID found"}

        response = requests.get(
            f"https://api.jsonbin.io/v3/b/{JSONBIN_ID}/latest",
            headers={"X-Master-Key": JSONBIN_KEY}
        )

        if response.status_code != 200:
            return {"error": "Failed to fetch JSONBin ledger"}

        full_ledger = response.json().get("record", {})
        installs = full_ledger.get("installs", {})

        if user_id in installs:
            # Update local ledger with JSONBin data
            save_local_ledger(installs[user_id])
            return {"status": "success"}
        else:
            return {"error": f"User {user_id} not found in JSONBin"}

    except Exception as e:
        return {"error": f"JSONBin sync error: {e}"}


def sync_to_jsonbin(user_id, ledger):
    """Sync local ledger to JSONBin cloud"""
    try:
        response = requests.get(
            f"https://api.jsonbin.io/v3/b/{JSONBIN_ID}/latest",
            headers={"X-Master-Key": JSONBIN_KEY}
        )

        if response.status_code != 200:
            return {"error": "Failed to fetch JSONBin ledger"}

        full_ledger = response.json().get("record", {})
        installs = full_ledger.get("installs", {})

        installs[user_id] = ledger

        updated = {
            "filename": "install_ledger.json",
            "installs": installs
        }

        response = requests.put(
            f"https://api.jsonbin.io/v3/b/{JSONBIN_ID}",
            headers={
                "Content-Type": "application/json",
                "X-Master-Key": JSONBIN_KEY
            },
            json=updated
        )

        if response.status_code == 200:
            return {"status": "success"}
        else:
            return {"error": f"JSONBin sync failed: {response.status_code}"}

    except Exception as e:
        return {"error": f"JSONBin sync error: {e}"}


def register_tool_actions(tool_name):
    """Register tool actions in system_settings.ndjson"""
    try:
        tool_script = os.path.join(BASE_DIR, f"{tool_name}.py")

        if not os.path.exists(tool_script):
            return {"error": f"Tool script not found: {tool_script}"}

        sys.path.insert(0, BASE_DIR)
        from system_settings import add_tool

        # Tool is being unlocked, so register as unlocked with no cost
        result = add_tool({
            "tool_name": tool_name, 
            "script_path": tool_script,
            "locked": False,  # Just unlocked
            "referral_unlock_cost": 0  # Already paid
        })
        return result

    except Exception as e:
        return {"error": f"Failed to register actions: {e}"}


def run_setup_script(script_path):
    """Execute the setup script via standalone helper"""
    try:
        from setup_script_runner import run_setup_script as execute_setup
        return execute_setup(script_path)
    except Exception as e:
        return {
            "status": "error",
            "message": f"❌ Failed to run setup: {str(e)}"
        }


def find_tool_location(tool_name):
    """
    Determine where tool exists:
    - 'preinstalled': exists in system_settings.ndjson
    - 'marketplace': exists in orchestrate_app_store.json
    - 'not_found': doesn't exist anywhere
    """
    # Check registry for pre-installed tool
    registry = load_registry()
    for entry in registry:
        if entry.get("tool") == tool_name and entry.get("action") == "__tool__":
            return "preinstalled", entry.get("referral_unlock_cost", 0)

    # Check app store for marketplace tool
    app_store = load_app_store()
    if tool_name in app_store:
        return "marketplace", app_store[tool_name].get("referral_unlock_cost", 0)

    return "not_found", 0


def unlock_preinstalled_tool(tool_name, cost):
    """Unlock a pre-installed tool (mark as unlocked in registry)"""
    # Load unlock messages
    unlock_messages_path = os.path.join(RUNTIME_DIR, "data", "unlock_messages.json")
    try:
        with open(unlock_messages_path, "r") as f:
            unlock_messages = json.load(f)
    except FileNotFoundError:
        unlock_messages = {}

    # Sync from JSONBin first
    sync_from_jsonbin()

    # Load ledger
    ledger = load_local_ledger()
    if "error" in ledger:
        return ledger

    # Check if already unlocked
    unlocked_tools = ledger.get("tools_unlocked", [])
    if tool_name in unlocked_tools:
        # Special handling for claude_assistant - return auth instructions
        if tool_name == "claude_assistant":
            return {
                "status": "already_unlocked",
                "message": "✅ claude_assistant is already unlocked",
                "auth_required": True,
                "auth_instructions": "🔐 AUTHENTICATION REQUIRED:\n\nRun this command in the container to authenticate:\n\n/home/orchestrate/.local/bin/claude auth login\n\nThis will provide a URL to complete OAuth authentication.\nAfter authentication, Claude Code can execute autonomous tasks."
            }

        # Return message from unlock_messages.json if available
        tool_message = unlock_messages.get(tool_name, {})
        message = tool_message.get("message", f"✅ {tool_name} is already unlocked")
        return {
            "status": "already_unlocked",
            "message": message
        }

    # Check credits
    current_credits = ledger.get("referral_credits", 0)
    if current_credits < cost:
        return {
            "error": f"Insufficient credits. Need {cost}, have {current_credits}",
            "credits_needed": cost - current_credits
        }

    # Deduct credits
    ledger["referral_credits"] -= cost
    ledger["tools_unlocked"].append(tool_name)

    # Save local ledger
    save_result = save_local_ledger(ledger)
    if "error" in save_result:
        return save_result

    # Sync to JSONBin
    user_id = get_user_id()
    if user_id:
        sync_result = sync_to_jsonbin(user_id, ledger)
        if "error" in sync_result:
            print(f"⚠️  Warning: JSONBin sync failed: {sync_result['error']}", file=sys.stderr)

    # Mark as unlocked in registry
    registry = load_registry()
    for entry in registry:
        if entry.get("tool") == tool_name and entry.get("action") == "__tool__":
            entry["locked"] = False
            entry["unlocked"] = True
            break

    save_registry(registry)

    # Update unlock_status.json for dashboard rendering
    update_unlock_status(tool_name)

    # Get unlock message from unlock_messages.json
    tool_message = unlock_messages.get(tool_name, {})
    if tool_message:
        message = tool_message.get("message", f"✅ {tool_name} unlocked! {ledger['referral_credits']} credits remaining.")
    else:
        message = f"✅ {tool_name} unlocked! {ledger['referral_credits']} credits remaining."

    return {
        "status": "success",
        "tool": tool_name,
        "type": "preinstalled",
        "credits_remaining": ledger["referral_credits"],
        "message": message
    }


def unlock_marketplace_tool(tool_name, cost):
    """Unlock a marketplace tool (register + add to registry)"""
    # Sync from JSONBin first
    sync_from_jsonbin()

    app_store = load_app_store()
    tool_config = app_store.get(tool_name, {})

    # Load ledger
    ledger = load_local_ledger()
    if "error" in ledger:
        return ledger

    # Check if already unlocked
    unlocked_tools = ledger.get("tools_unlocked", [])
    if tool_name in unlocked_tools:
        return {
            "status": "already_unlocked",
            "message": f"✅ {tool_config.get('label', tool_name)} is already unlocked"
        }

    # Check credits
    current_credits = ledger.get("referral_credits", 0)
    if current_credits < cost:
        return {
            "error": f"Insufficient credits. Need {cost}, have {current_credits}",
            "credits_needed": cost - current_credits
        }

    # Deduct credits
    ledger["referral_credits"] -= cost
    ledger["tools_unlocked"].append(tool_name)

    # Save local ledger
    save_result = save_local_ledger(ledger)
    if "error" in save_result:
        return save_result

    # Sync to JSONBin
    user_id = get_user_id()
    if user_id:
        sync_result = sync_to_jsonbin(user_id, ledger)
        if "error" in sync_result:
            print(f"⚠️  Warning: JSONBin sync failed: {sync_result['error']}", file=sys.stderr)

    # Register tool actions
    register_result = register_tool_actions(tool_name)
    if "error" in register_result:
        return {
            "error": "Tool unlocked but action registration failed",
            "details": register_result["error"]
        }

    # Update unlock_status.json for dashboard rendering
    update_unlock_status(tool_name)

    # Handle setup script if specified
    if "setup_script" in tool_config:
        setup_script = tool_config["setup_script"]

        return {
            "status": "success",
            "tool": tool_name,
            "type": "marketplace",
            "label": tool_config.get("label", tool_name),
            "credits_remaining": ledger["referral_credits"],
            "unlock_message": f"✅ {tool_config.get('label', tool_name)} unlocked! ({ledger['referral_credits']} credits remaining)\n\n🔧 Authentication Required - Copy/paste this into Terminal:\n\nbash ~/Documents/Orchestrate/{setup_script}\n\nThis opens your browser for Claude Code OAuth (takes 30 seconds).",
            "post_unlock_nudge": tool_config.get("post_unlock_nudge", "")
        }

    # No setup required - standard unlock
    response = {
        "status": "success",
        "tool": tool_name,
        "type": "marketplace",
        "label": tool_config.get("label", tool_name),
        "credits_remaining": ledger["referral_credits"],
        "unlock_message": tool_config.get("unlock_message", f"✅ {tool_config.get('label', tool_name)} unlocked!")
    }

    if "post_unlock_nudge" in tool_config:
        response["nudge"] = tool_config["post_unlock_nudge"]

    return response


def unlock_tool(tool_name):
    """
    Unified unlock function - intelligently routes to correct unlock flow

    Flow:
    1. Check if tool exists in system_settings.ndjson (pre-installed)
       → If yes: unlock_preinstalled_tool()
    2. Check if tool exists in orchestrate_app_store.json (marketplace)
       → If yes: unlock_marketplace_tool()
    3. If neither: return error
    """

    # Find where tool exists
    location, cost = find_tool_location(tool_name)

    if location == "not_found":
        return {
            "error": f"Tool '{tool_name}' not found in pre-installed tools or marketplace"
        }

    # Route to appropriate unlock function
    if location == "preinstalled":
        return unlock_preinstalled_tool(tool_name, cost)
    else:  # marketplace
        return unlock_marketplace_tool(tool_name, cost)


def list_marketplace_tools():
    """List all available marketplace tools with lock status"""
    app_store = load_app_store()
    ledger = load_local_ledger()

    if "error" in ledger:
        return ledger

    unlocked = set(ledger.get("tools_unlocked", []))
    credits = ledger.get("referral_credits", 0)

    tools = []
    for tool_name, config in app_store.items():
        tools.append({
            "name": tool_name,
            "label": config.get("label", tool_name),
            "description": config.get("description", ""),
            "cost": config.get("referral_unlock_cost", 0),
            "priority": config.get("priority", 999),
            "locked": tool_name not in unlocked,
            "requires_subscription": config.get("requires_subscription", False),
            "subscription_type": config.get("subscription_type", None),
            "requires_credentials": config.get("requires_credentials", False)
        })

    tools.sort(key=lambda x: x["priority"])

    return {
        "status": "success",
        "credits_available": credits,
        "tools": tools
    }


def get_credits_balance():
    """Get current credit balance"""
    ledger = load_local_ledger()
    if "error" in ledger:
        return ledger

    return {
        "status": "success",
        "credits": ledger.get("referral_credits", 0),
        "referral_count": ledger.get("referral_count", 0),
        "tools_unlocked": ledger.get("tools_unlocked", [])
    }


def main():
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    if args.action == 'find_tool_location':
        result = find_tool_location(**params)
    elif args.action == 'get_credits_balance':
        result = get_credits_balance()
    elif args.action == 'get_user_id':
        result = get_user_id()
    elif args.action == 'list_marketplace_tools':
        result = list_marketplace_tools()
    elif args.action == 'load_app_store':
        result = load_app_store()
    elif args.action == 'load_local_ledger':
        result = load_local_ledger()
    elif args.action == 'load_registry':
        result = load_registry()
    elif args.action == 'register_tool_actions':
        result = register_tool_actions(**params)
    elif args.action == 'run_setup_script':
        result = run_setup_script(**params)
    elif args.action == 'save_local_ledger':
        result = save_local_ledger(**params)
    elif args.action == 'save_registry':
        result = save_registry(**params)
    elif args.action == 'sync_from_jsonbin':
        result = sync_from_jsonbin()
    elif args.action == 'sync_to_jsonbin':
        result = sync_to_jsonbin(**params)
    elif args.action == 'unlock_marketplace_tool':
        result = unlock_marketplace_tool(**params)
    elif args.action == 'unlock_preinstalled_tool':
        result = unlock_preinstalled_tool(**params)
    elif args.action == 'unlock_tool':
        result = unlock_tool(**params)
    else:
        result = {'status': 'error', 'message': f'Unknown action {args.action}'}

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
