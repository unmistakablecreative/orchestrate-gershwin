#!/usr/bin/env python3
"""
Account Tool - Consolidated credits, referrals, and tool unlocking

Merged from: check_credits.py, refer_user.py, unlock_tool.py

Actions:
  - check: Return credits balance and unlock status
  - refer: Submit referral emails and earn credits
  - unlock: Unlock a tool with credits
"""

import os
import sys
import json
import argparse
import uuid
import subprocess
import webbrowser
from datetime import datetime

import requests

from response_helper import get_success_message, get_error_message


# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUNTIME_DIR = os.path.dirname(BASE_DIR)
STATE_DIR = os.path.expanduser("~/Library/Application Support/OrchestrateOS")
IDENTITY_PATH = os.path.join(STATE_DIR, "system_identity.json")
SECONDBRAIN_PATH = os.path.join(RUNTIME_DIR, "data", "secondbrain.json")
APP_STORE_PATH = os.path.join(RUNTIME_DIR, "data", "orchestrate_app_store.json")
UNLOCK_STATUS_PATH = os.path.join(RUNTIME_DIR, "data", "unlock_status.json")
SYSTEM_REGISTRY = os.path.join(RUNTIME_DIR, "system_settings.ndjson")
UNLOCK_MESSAGES_PATH = os.path.join(RUNTIME_DIR, "data", "unlock_messages.json")

# JSONBin config
JSONBIN_KEY = "$2a$10$MoavwaWsCucy2FkU/5ycV.lBTPWoUq4uKHhCi9Y47DOHWyHFL3o2C"
LEDGER_BIN = "6955618fd0ea881f404c2cdd"
REFERRALS_BIN = "694a185eae596e708fab9028"
HEADERS = {"X-Master-Key": JSONBIN_KEY, "Content-Type": "application/json"}


# =============================================================================
# SHARED HELPERS
# =============================================================================

def get_user_id():
    """Get user's unique ID from system identity"""
    try:
        if not os.path.exists(IDENTITY_PATH):
            return None
        with open(IDENTITY_PATH, 'r') as f:
            return json.load(f).get("user_id")
    except Exception:
        return None


def get_referrer_name():
    """Get referrer name from secondbrain.json user_profile"""
    try:
        if os.path.exists(SECONDBRAIN_PATH):
            with open(SECONDBRAIN_PATH, 'r') as f:
                secondbrain = json.load(f)
                entries = secondbrain.get("entries", {})
                user_profile = entries.get("user_profile", {})
                return user_profile.get("full_name", "Unknown Referrer")
        return "Unknown Referrer"
    except Exception:
        return "Unknown Referrer"


def fetch_ledger():
    """Fetch the full install ledger from JSONBin"""
    try:
        res = requests.get(f"https://api.jsonbin.io/v3/b/{LEDGER_BIN}/latest", headers=HEADERS, timeout=30)
        res.raise_for_status()
        return res.json().get("record", {"filename": "install_ledger.json", "installs": {}})
    except Exception as e:
        return {"error": f"Failed to fetch ledger: {e}"}


def save_ledger(ledger):
    """Save updated ledger to JSONBin"""
    try:
        res = requests.put(f"https://api.jsonbin.io/v3/b/{LEDGER_BIN}", headers=HEADERS, json=ledger, timeout=30)
        if res.ok:
            return {"status": "success"}
        return {"error": f"Failed to save ledger: {res.text}"}
    except Exception as e:
        return {"error": f"Failed to save ledger: {e}"}


def load_app_store():
    """Load app store configuration"""
    try:
        with open(APP_STORE_PATH, 'r') as f:
            return json.load(f).get("entries", {})
    except Exception:
        return {}


def load_registry():
    """Load system_settings.ndjson"""
    try:
        with open(SYSTEM_REGISTRY, 'r') as f:
            return [json.loads(line.strip()) for line in f if line.strip()]
    except Exception:
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


def load_unlock_messages():
    """Load unlock messages config"""
    try:
        with open(UNLOCK_MESSAGES_PATH, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


# =============================================================================
# ACTION: add_user (Admin)
# =============================================================================

def action_add_user(params):
    """
    Add a new user to the install ledger.

    Params:
      - user_id: Unique identifier for the user (optional, auto-generated if not provided)
      - name: User's display name (optional)
      - credits: Initial credits to grant (default: 0)

    Returns: user_id, initial_credits
    """
    user_id = params.get("user_id") or f"user-{str(uuid.uuid4())[:8]}"
    name = params.get("name", "Test User")
    initial_credits = params.get("credits", 0)

    ledger = fetch_ledger()
    if "error" in ledger:
        return {"status": "error", "message": ledger["error"]}

    if "installs" not in ledger:
        ledger["installs"] = {}

    if user_id in ledger["installs"]:
        return {
            "status": "error",
            "message": f"User '{user_id}' already exists in ledger"
        }

    ledger["installs"][user_id] = {
        "name": name,
        "referral_count": 0,
        "referral_credits": initial_credits,
        "tools_unlocked": [],
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    ledger["filename"] = "install_ledger.json"

    save_result = save_ledger(ledger)
    if "error" in save_result:
        return {"status": "error", "message": save_result["error"]}

    return {
        "status": "success",
        "message": f"User '{user_id}' added to install ledger",
        "user_id": user_id,
        "name": name,
        "initial_credits": initial_credits
    }


# =============================================================================
# ACTION: list_users (Admin)
# =============================================================================

def action_list_users(params):
    """
    List all users in the install ledger.

    Returns: list of users with their credits and unlocked tools
    """
    ledger = fetch_ledger()
    if "error" in ledger:
        return {"status": "error", "message": ledger["error"]}

    installs = ledger.get("installs", {})
    users = []

    for user_id, data in installs.items():
        users.append({
            "user_id": user_id,
            "name": data.get("name", "Unknown"),
            "credits": data.get("referral_credits", 0),
            "referral_count": data.get("referral_count", 0),
            "tools_unlocked": data.get("tools_unlocked", []),
            "timestamp": data.get("timestamp")
        })

    return {
        "status": "success",
        "message": f"Found {len(users)} users in ledger",
        "users": users,
        "total_users": len(users)
    }


# =============================================================================
# ACTION: grant_credits (Admin)
# =============================================================================

def action_grant_credits(params):
    """
    Grant credits to a user (admin function for testing).

    Params:
      - user_id: User to grant credits to
      - amount: Number of credits to grant

    Returns: new credit balance
    """
    user_id = params.get("user_id")
    amount = params.get("amount", 0)

    if not user_id:
        return {"status": "error", "message": "Missing user_id parameter"}

    if not isinstance(amount, int) or amount < 0:
        return {"status": "error", "message": "Amount must be a positive integer"}

    ledger = fetch_ledger()
    if "error" in ledger:
        return {"status": "error", "message": ledger["error"]}

    if "installs" not in ledger:
        ledger["installs"] = {}

    if user_id not in ledger["installs"]:
        return {
            "status": "error",
            "message": f"User '{user_id}' not found in ledger"
        }

    ledger["installs"][user_id]["referral_credits"] = \
        ledger["installs"][user_id].get("referral_credits", 0) + amount
    ledger["filename"] = "install_ledger.json"

    save_result = save_ledger(ledger)
    if "error" in save_result:
        return {"status": "error", "message": save_result["error"]}

    new_balance = ledger["installs"][user_id]["referral_credits"]

    return {
        "status": "success",
        "message": f"Granted {amount} credits to '{user_id}'",
        "user_id": user_id,
        "credits_granted": amount,
        "new_balance": new_balance
    }


# =============================================================================
# ACTION: delete_user (Admin)
# =============================================================================

def action_delete_user(params):
    """
    Delete a user from the install ledger.

    Params:
      - user_id: User to delete

    Returns: confirmation of deletion
    """
    user_id = params.get("user_id")

    if not user_id:
        return {"status": "error", "message": "Missing user_id parameter"}

    ledger = fetch_ledger()
    if "error" in ledger:
        return {"status": "error", "message": ledger["error"]}

    if "installs" not in ledger or user_id not in ledger.get("installs", {}):
        return {
            "status": "error",
            "message": f"User '{user_id}' not found in ledger"
        }

    del ledger["installs"][user_id]
    ledger["filename"] = "install_ledger.json"

    save_result = save_ledger(ledger)
    if "error" in save_result:
        return {"status": "error", "message": save_result["error"]}

    return {
        "status": "success",
        "message": f"User '{user_id}' deleted from ledger",
        "user_id": user_id
    }


# =============================================================================
# ACTION: check
# =============================================================================

def action_check(params):
    """
    Return credits balance and unlock status.

    Returns: user_id, credits, tools_unlocked, referral_count
    """
    user_id = get_user_id()
    if not user_id:
        return {
            "status": "error",
            "message": "system_identity.json not found or invalid."
        }

    ledger = fetch_ledger()
    if "error" in ledger:
        return {"status": "error", "message": ledger["error"]}

    user = ledger.get("installs", {}).get(user_id)
    if not user:
        return {
            "status": "error",
            "message": get_error_message("account", "check", f"User '{user_id}' not found in install ledger")
        }

    credits = user.get("referral_credits", 0)
    return {
        "status": "success",
        "message": get_success_message("account", "check", {"credits": credits}),
        "user_id": user_id,
        "credits": credits,
        "referral_count": user.get("referral_count", 0),
        "tools_unlocked": user.get("tools_unlocked", []),
        "timestamp": user.get("timestamp")
    }


# =============================================================================
# ACTION: refer
# =============================================================================

def action_refer(params):
    """
    Submit referral emails and earn credits.

    Params:
      - name: Referee's name
      - email: Referee's email

    Returns: referral_id, credits_awarded (3 per referral)
    """
    name = params.get("name")
    email = params.get("email")

    if not name or not email:
        return {"status": "error", "message": get_error_message("account", "refer", "Missing name or email")}

    user_id = get_user_id()
    if not user_id:
        return {"status": "error", "message": get_error_message("account", "refer", "No user_id found in system_identity.json")}

    referrer_name = get_referrer_name()
    referral_id = f"ref-{str(uuid.uuid4())[:8]}"

    # Add to referrals bin
    try:
        resp = requests.get(f"https://api.jsonbin.io/v3/b/{REFERRALS_BIN}", headers=HEADERS, timeout=30)
        referrals = resp.json().get("record", {"filename": "referrals.json", "entries": {}}) if resp.ok else {"filename": "referrals.json", "entries": {}}
    except Exception:
        referrals = {"filename": "referrals.json", "entries": {}}

    if not isinstance(referrals.get("entries"), dict):
        referrals["entries"] = {}

    referrals["entries"][referral_id] = {
        "referrer_id": user_id,
        "referrer_name": referrer_name,
        "referee_name": name,
        "referee_email": email,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "credits_awarded": 3,
        "email_sent": False
    }
    referrals["filename"] = "referrals.json"

    resp = requests.put(f"https://api.jsonbin.io/v3/b/{REFERRALS_BIN}", headers=HEADERS, json=referrals, timeout=30)
    if not resp.ok:
        return {"status": "error", "message": f"Failed to update referrals bin: {resp.text}"}

    # Update ledger with credits
    ledger = fetch_ledger()
    if "error" in ledger:
        return {"status": "error", "message": ledger["error"]}

    if "installs" not in ledger:
        ledger["installs"] = {}

    if user_id not in ledger["installs"]:
        ledger["installs"][user_id] = {
            "referral_count": 0,
            "referral_credits": 0,
            "tools_unlocked": [],
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

    ledger["installs"][user_id]["referral_credits"] = ledger["installs"][user_id].get("referral_credits", 0) + 3
    ledger["installs"][user_id]["referral_count"] = ledger["installs"][user_id].get("referral_count", 0) + 1
    ledger["filename"] = "install_ledger.json"

    save_result = save_ledger(ledger)
    if "error" in save_result:
        return {"status": "error", "message": save_result["error"]}

    return {
        "status": "success",
        "message": get_success_message("account", "refer", {"email": email}),
        "referral_id": referral_id,
        "referrer_id": user_id,
        "credits_awarded": 3
    }


# =============================================================================
# ACTION: unlock
# =============================================================================

def find_tool_location(tool_name):
    """
    Determine where tool exists:
    - 'preinstalled': exists in system_settings.ndjson
    - 'marketplace': exists in orchestrate_app_store.json
    - 'not_found': doesn't exist anywhere
    """
    registry = load_registry()
    for entry in registry:
        if entry.get("tool") == tool_name and entry.get("action") == "__tool__":
            return "preinstalled", entry.get("referral_unlock_cost", 0)

    app_store = load_app_store()
    if tool_name in app_store:
        return "marketplace", app_store[tool_name].get("referral_unlock_cost", 0)

    return "not_found", 0


def register_tool_actions(tool_name):
    """Register tool actions in system_settings.ndjson"""
    try:
        tool_script = os.path.join(BASE_DIR, f"{tool_name}.py")

        if not os.path.exists(tool_script):
            return {"error": f"Tool script not found: {tool_script}"}

        sys.path.insert(0, BASE_DIR)
        from system_settings import add_tool

        result = add_tool({
            "tool_name": tool_name,
            "script_path": tool_script,
            "locked": False,
            "referral_unlock_cost": 0
        })
        return result

    except Exception as e:
        return {"error": f"Failed to register actions: {e}"}


def unlock_preinstalled_tool(tool_name, cost, user_id, ledger):
    """Unlock a pre-installed tool"""
    unlock_messages = load_unlock_messages()
    user_data = ledger.get("installs", {}).get(user_id, {})
    unlocked_tools = user_data.get("tools_unlocked", [])

    if tool_name in unlocked_tools:
        tool_message = unlock_messages.get(tool_name, {})

        if tool_name == "claude_assistant" and tool_message.get("auto_browser_auth"):
            auth_url = tool_message.get("auth_url", "https://claude.ai/oauth/authorize")
            try:
                webbrowser.open(auth_url)
                browser_opened = True
            except Exception:
                browser_opened = False

            response = {
                "status": "already_unlocked",
                "message": f"✅ {tool_name} is already unlocked",
                "auth_required": True,
                "browser_opened": browser_opened,
                "auth_url": auth_url
            }
            if tool_message.get("credential_setup"):
                response["credential_setup"] = tool_message["credential_setup"]
            if tool_message.get("guided_activation"):
                response["guided_activation"] = tool_message["guided_activation"]
            return response

        message = tool_message.get("message", f"✅ {tool_name} is already unlocked")
        return {"status": "already_unlocked", "message": message}

    current_credits = user_data.get("referral_credits", 0)
    if current_credits < cost:
        return {
            "status": "error",
            "message": f"Insufficient credits. Need {cost}, have {current_credits}",
            "credits_needed": cost - current_credits
        }

    # Deduct credits and unlock
    ledger["installs"][user_id]["referral_credits"] -= cost
    if "tools_unlocked" not in ledger["installs"][user_id]:
        ledger["installs"][user_id]["tools_unlocked"] = []
    ledger["installs"][user_id]["tools_unlocked"].append(tool_name)

    save_result = save_ledger(ledger)
    if "error" in save_result:
        return {"status": "error", "message": save_result["error"]}

    # Update local registry
    registry = load_registry()
    for entry in registry:
        if entry.get("tool") == tool_name and entry.get("action") == "__tool__":
            entry["locked"] = False
            entry["unlocked"] = True
            break
    save_registry(registry)

    update_unlock_status(tool_name)

    tool_message = unlock_messages.get(tool_name, {})
    credits_remaining = ledger["installs"][user_id]["referral_credits"]
    message = tool_message.get("message", get_success_message("account", "unlock", {"tool_name": tool_name, "credits_remaining": credits_remaining}))

    response = {
        "status": "success",
        "tool": tool_name,
        "type": "preinstalled",
        "credits_remaining": credits_remaining,
        "message": message
    }

    if tool_message.get("requires_credentials"):
        response["requires_credentials"] = True
        if tool_message.get("credential_setup"):
            response["credential_setup"] = tool_message["credential_setup"]
        if tool_message.get("credential_setup_url"):
            response["credential_setup_url"] = tool_message["credential_setup_url"]
        if tool_message.get("credential_key"):
            response["credential_key"] = tool_message["credential_key"]

    if tool_message.get("auto_browser_auth"):
        auth_url = tool_message.get("auth_url", "https://claude.ai/oauth/authorize")
        try:
            webbrowser.open(auth_url)
            response["browser_opened"] = True
        except Exception:
            response["browser_opened"] = False
        response["auth_url"] = auth_url
        if tool_message.get("credential_setup"):
            response["credential_setup"] = tool_message["credential_setup"]

    if tool_message.get("guided_activation"):
        response["guided_activation"] = tool_message["guided_activation"]

    return response


def unlock_marketplace_tool(tool_name, cost, user_id, ledger):
    """Unlock a marketplace tool"""
    app_store = load_app_store()
    tool_config = app_store.get(tool_name, {})
    unlock_messages = load_unlock_messages()

    user_data = ledger.get("installs", {}).get(user_id, {})
    unlocked_tools = user_data.get("tools_unlocked", [])

    if tool_name in unlocked_tools:
        return {
            "status": "already_unlocked",
            "message": f"✅ {tool_config.get('label', tool_name)} is already unlocked"
        }

    current_credits = user_data.get("referral_credits", 0)
    if current_credits < cost:
        return {
            "status": "error",
            "message": f"Insufficient credits. Need {cost}, have {current_credits}",
            "credits_needed": cost - current_credits
        }

    # Deduct credits and unlock
    ledger["installs"][user_id]["referral_credits"] -= cost
    if "tools_unlocked" not in ledger["installs"][user_id]:
        ledger["installs"][user_id]["tools_unlocked"] = []
    ledger["installs"][user_id]["tools_unlocked"].append(tool_name)

    save_result = save_ledger(ledger)
    if "error" in save_result:
        return {"status": "error", "message": save_result["error"]}

    # Register tool actions
    register_result = register_tool_actions(tool_name)
    if "error" in register_result:
        return {
            "status": "error",
            "message": "Tool unlocked but action registration failed",
            "details": register_result["error"]
        }

    update_unlock_status(tool_name)

    tool_message = unlock_messages.get(tool_name, {})
    credits_remaining = ledger["installs"][user_id]["referral_credits"]

    if tool_message.get("auto_browser_auth"):
        auth_url = tool_message.get("auth_url", "https://claude.ai/oauth/authorize")
        try:
            webbrowser.open(auth_url)
            browser_opened = True
        except Exception:
            browser_opened = False

        response = {
            "status": "success",
            "tool": tool_name,
            "type": "marketplace",
            "label": tool_config.get("label", tool_name),
            "credits_remaining": credits_remaining,
            "message": tool_message.get("message", f"✅ {tool_config.get('label', tool_name)} unlocked!"),
            "browser_opened": browser_opened,
            "auth_url": auth_url
        }
        if tool_message.get("credential_setup"):
            response["credential_setup"] = tool_message["credential_setup"]
        if tool_message.get("guided_activation"):
            response["guided_activation"] = tool_message["guided_activation"]
        if "post_unlock_nudge" in tool_config:
            response["nudge"] = tool_config["post_unlock_nudge"]
        return response

    if "setup_script" in tool_config and not tool_message.get("auto_browser_auth"):
        setup_script = tool_config["setup_script"]
        script_path = os.path.join(RUNTIME_DIR, setup_script)

        script_launched = False
        if os.path.exists(script_path):
            try:
                subprocess.Popen(
                    ["/bin/bash", script_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
                script_launched = True
            except Exception:
                script_launched = False

        return {
            "status": "success",
            "tool": tool_name,
            "type": "marketplace",
            "label": tool_config.get("label", tool_name),
            "credits_remaining": credits_remaining,
            "script_launched": script_launched,
            "unlock_message": f"✅ {tool_config.get('label', tool_name)} unlocked! ({credits_remaining} credits remaining)\n\n" +
                ('🌐 Authentication launched — check your browser to sign in with your Claude Pro/Team account.' if script_launched else f'🔧 Authentication Required — run this in Terminal:\n\nbash {script_path}\n\nThis opens your browser for Claude Code OAuth.'),
            "post_unlock_nudge": tool_config.get("post_unlock_nudge", "")
        }

    response = {
        "status": "success",
        "tool": tool_name,
        "type": "marketplace",
        "label": tool_config.get("label", tool_name),
        "credits_remaining": credits_remaining,
        "unlock_message": tool_config.get("unlock_message", f"✅ {tool_config.get('label', tool_name)} unlocked!")
    }

    if "post_unlock_nudge" in tool_config:
        response["nudge"] = tool_config["post_unlock_nudge"]

    if tool_message.get("requires_credentials"):
        response["requires_credentials"] = True
        if tool_message.get("credential_setup"):
            response["credential_setup"] = tool_message["credential_setup"]
        if tool_message.get("credential_setup_url"):
            response["credential_setup_url"] = tool_message["credential_setup_url"]
        if tool_message.get("credential_key"):
            response["credential_key"] = tool_message["credential_key"]

    if tool_message.get("guided_activation"):
        response["guided_activation"] = tool_message["guided_activation"]

    return response


def action_unlock(params):
    """
    Unlock a tool with credits.

    Params:
      - tool_name: Name of the tool to unlock

    Returns: unlock status, credits remaining
    """
    tool_name = params.get("tool_name")
    if not tool_name:
        return {"status": "error", "message": get_error_message("account", "unlock", "Missing tool_name parameter")}

    user_id = get_user_id()
    if not user_id:
        return {"status": "error", "message": get_error_message("account", "unlock", "No user_id found in system_identity.json")}

    location, cost = find_tool_location(tool_name)

    if location == "not_found":
        return {
            "status": "error",
            "message": f"Tool '{tool_name}' not found in pre-installed tools or marketplace"
        }

    ledger = fetch_ledger()
    if "error" in ledger:
        return {"status": "error", "message": ledger["error"]}

    # Ensure user exists in ledger
    if "installs" not in ledger:
        ledger["installs"] = {}
    if user_id not in ledger["installs"]:
        ledger["installs"][user_id] = {
            "referral_count": 0,
            "referral_credits": 0,
            "tools_unlocked": [],
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

    if location == "preinstalled":
        return unlock_preinstalled_tool(tool_name, cost, user_id, ledger)
    else:
        return unlock_marketplace_tool(tool_name, cost, user_id, ledger)


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    if args.action == 'check':
        result = action_check(params)
    elif args.action == 'refer':
        result = action_refer(params)
    elif args.action == 'unlock':
        result = action_unlock(params)
    elif args.action == 'add_user':
        result = action_add_user(params)
    elif args.action == 'list_users':
        result = action_list_users(params)
    elif args.action == 'grant_credits':
        result = action_grant_credits(params)
    elif args.action == 'delete_user':
        result = action_delete_user(params)
    else:
        result = {'status': 'error', 'message': f'Unknown action: {args.action}'}

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
