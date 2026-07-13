#!/usr/bin/env python3
"""
Account Tool - Consolidated credits, referrals, and tool unlocking

TURSO LIBSQL VERSION
This version uses Turso cloud database for accounts.


Actions:
  - check: Return credits balance and unlock status
  - refer: Submit referral emails and earn credits
  - unlock: Unlock a tool with credits
  - add_user: Create a new user account (for testing)
  - list_users: List all users in the database (for testing)
  - add_credits: Add credits to a user (for testing)
"""

import os
import sys
import json
import argparse
import uuid
import subprocess
from datetime import datetime

# Simple response helpers for local testing
def get_success_message(message, data=None):
    """Return success response dict"""
    result = {"status": "success", "message": message}
    if data:
        result["data"] = data
    return result


def get_error_message(message):
    """Return error response dict"""
    return {"status": "error", "message": message}


# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUNTIME_DIR = os.path.dirname(BASE_DIR)
IDENTITY_PATH = os.path.join(RUNTIME_DIR, "data", "system_identity.json")
SECONDBRAIN_PATH = os.path.join(RUNTIME_DIR, "data", "secondbrain.json")
SYSTEM_REGISTRY = os.path.join(RUNTIME_DIR, "system_settings.ndjson")
UNLOCK_MESSAGES_PATH = os.path.join(RUNTIME_DIR, "data", "unlock_messages.json")

# SQLite DB path (local testing)
ACCOUNTS_DB_PATH = os.path.join(RUNTIME_DIR, "data", "accounts.db")


# =============================================================================
# DATABASE INITIALIZATION
# =============================================================================

def init_db():
    """Initialize the accounts database with required tables"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            email TEXT,
            credits INTEGER DEFAULT 3,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_active TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS unlocked_tools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            tool_id TEXT NOT NULL,
            unlocked_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, tool_id),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id TEXT NOT NULL,
            referee_email TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            credits_awarded INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            converted_at TEXT,
            FOREIGN KEY (referrer_id) REFERENCES users(user_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS credit_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            amount INTEGER NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)

    conn.commit()
    conn.sync()
    conn.close()


def get_db_connection():
    """Get a Turso database connection"""
    creds_path = os.path.join(BASE_DIR, "credentials.json")
    with open(creds_path, "r") as f:
        creds = json.load(f)

    turso_url = creds.get("turso_url")
    turso_token = creds.get("turso_token")

    if not turso_url or not turso_token:
        raise Exception("Turso credentials not found in credentials.json")

    conn = libsql.connect("/tmp/gershwin_accounts.db", sync_url=turso_url, auth_token=turso_token)
    conn.sync()
    return conn


# =============================================================================
# SHARED HELPERS
# =============================================================================

def get_user_id():
    """Get user unique ID from system identity"""
    try:
        if not os.path.exists(IDENTITY_PATH):
            return None
        with open(IDENTITY_PATH, 'r') as f:
            return json.load(f).get("user_id")
    except Exception:
        return None


def _get_turso_config():
    """Hardcoded Turso HTTP API config"""
    turso_url = "https://orchestrateos-accounts-unmistakableceo.aws-us-west-2.turso.io/v2/pipeline"
    turso_token = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3ODM4NzczMTQsImlkIjoiMDE5ZjU3NWYtNjUwMS03MTljLWJhMmYtZjYxOWExOGU0YTMwIiwia2lkIjoiTElEcXI5MVJ3OENKcmdqRjVYWWRxOWhMc3lIbWU5eHJWRkxsLUN6SnZ6USIsInJpZCI6ImM1YTYyZmM2LWI2ZWItNDM5NC05NTliLTU0ODJmNjVhODE0YSJ9.MVqnnK5M6N-gB6J4_VWVYlLuG1-XhJnlAEk6uXxk9HEXybWHGyJqznhX2nYL00I4NsOy7d-oVZyNGd2oECflAw"
    return turso_url, turso_token


def _turso_exec(turso_url, turso_token, requests_list):
    """Execute a Turso HTTP API pipeline request"""
    import urllib.request
    payload = json.dumps({"requests": requests_list}).encode()
    req = urllib.request.Request(turso_url, data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {turso_token}"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def get_or_create_user(user_id, email=None):
    """Get existing user or create new one via Turso HTTP API"""
    import urllib.request

    turso_url, turso_token = _get_turso_config()

    check_result = _turso_exec(turso_url, turso_token, [
        {"type": "execute", "stmt": {"sql": "SELECT user_id, email, credits, created_at FROM users WHERE user_id = ?", "args": [{"type": "text", "value": user_id}]}},
        {"type": "close"}
    ])

    try:
        rows = check_result["results"][0]["response"]["result"]["rows"]
        if rows:
            row = rows[0]
            return {
                "user_id": row[0]["value"],
                "email": row[1].get("value") if row[1].get("type") != "null" else None,
                "credits": int(row[2]["value"]),
                "created_at": row[3].get("value"),
            }
    except (KeyError, IndexError):
        pass

    email_arg = {"type": "text", "value": email} if email else {"type": "null"}
    _turso_exec(turso_url, turso_token, [
        {"type": "execute", "stmt": {"sql": "INSERT INTO users (user_id, email, credits) VALUES (?, ?, 3)", "args": [{"type": "text", "value": user_id}, email_arg]}},
        {"type": "execute", "stmt": {"sql": "INSERT INTO credit_transactions (user_id, amount, reason) VALUES (?, 3, 'initial_signup')", "args": [{"type": "text", "value": user_id}]}},
        {"type": "close"}
    ])

    result = _turso_exec(turso_url, turso_token, [
        {"type": "execute", "stmt": {"sql": "SELECT user_id, email, credits, created_at FROM users WHERE user_id = ?", "args": [{"type": "text", "value": user_id}]}},
        {"type": "close"}
    ])

    try:
        row = result["results"][0]["response"]["result"]["rows"][0]
        return {
            "user_id": row[0]["value"],
            "email": row[1].get("value") if row[1].get("type") != "null" else None,
            "credits": int(row[2]["value"]),
            "created_at": row[3]["value"],
            "last_active": None
        }
    except (KeyError, IndexError):
        return {"user_id": user_id, "email": email, "credits": 3, "created_at": None, "last_active": None}


def get_user_credits(user_id):
    """Get current credits for a user via Turso HTTP API"""
    import urllib.request

    turso_url, turso_token = _get_turso_config()

    result = _turso_exec(turso_url, turso_token, [
        {"type": "execute", "stmt": {"sql": "SELECT credits FROM users WHERE user_id = ?", "args": [{"type": "text", "value": user_id}]}},
        {"type": "close"}
    ])

    try:
        rows = result["results"][0]["response"]["result"]["rows"]
        if rows:
            return int(rows[0][0]["value"])
    except (KeyError, IndexError):
        pass
    return 0


def get_unlocked_tools(user_id):
    """Get list of unlocked tool IDs for a user via Turso HTTP API"""
    import urllib.request

    turso_url, turso_token = _get_turso_config()

    result = _turso_exec(turso_url, turso_token, [
        {"type": "execute", "stmt": {"sql": "SELECT tool_id FROM unlocked_tools WHERE user_id = ?", "args": [{"type": "text", "value": user_id}]}},
        {"type": "close"}
    ])

    try:
        rows = result["results"][0]["response"]["result"]["rows"]
        return [row[0]["value"] for row in rows]
    except (KeyError, IndexError):
        return []


def add_credits_to_user(user_id, amount, reason):
    """Add credits to a user account via Turso HTTP API"""
    import urllib.request

    turso_url, turso_token = _get_turso_config()

    result = _turso_exec(turso_url, turso_token, [
        {"type": "execute", "stmt": {"sql": "UPDATE users SET credits = credits + ? WHERE user_id = ?", "args": [{"type": "integer", "value": str(amount)}, {"type": "text", "value": user_id}]}},
        {"type": "execute", "stmt": {"sql": "INSERT INTO credit_transactions (user_id, amount, reason) VALUES (?, ?, ?)", "args": [{"type": "text", "value": user_id}, {"type": "integer", "value": str(amount)}, {"type": "text", "value": reason}]}},
        {"type": "execute", "stmt": {"sql": "SELECT credits FROM users WHERE user_id = ?", "args": [{"type": "text", "value": user_id}]}},
        {"type": "close"}
    ])

    try:
        new_balance = result["results"][2]["response"]["result"]["rows"][0][0]["value"]
        return int(new_balance)
    except (KeyError, IndexError):
        return None


def deduct_credits_from_user(user_id, amount, reason):
    """Deduct credits from a user account via Turso HTTP API"""
    import urllib.request

    turso_url, turso_token = _get_turso_config()

    check_result = _turso_exec(turso_url, turso_token, [
        {"type": "execute", "stmt": {"sql": "SELECT credits FROM users WHERE user_id = ?", "args": [{"type": "text", "value": user_id}]}},
        {"type": "close"}
    ])

    try:
        rows = check_result["results"][0]["response"]["result"]["rows"]
        if not rows:
            return None
        current = int(rows[0][0]["value"])
        if current < amount:
            return None
    except (KeyError, IndexError):
        return None

    result = _turso_exec(turso_url, turso_token, [
        {"type": "execute", "stmt": {"sql": "UPDATE users SET credits = credits - ? WHERE user_id = ?", "args": [{"type": "integer", "value": str(amount)}, {"type": "text", "value": user_id}]}},
        {"type": "execute", "stmt": {"sql": "INSERT INTO credit_transactions (user_id, amount, reason) VALUES (?, ?, ?)", "args": [{"type": "text", "value": user_id}, {"type": "integer", "value": str(-amount)}, {"type": "text", "value": reason}]}},
        {"type": "execute", "stmt": {"sql": "SELECT credits FROM users WHERE user_id = ?", "args": [{"type": "text", "value": user_id}]}},
        {"type": "close"}
    ])

    try:
        new_balance = result["results"][2]["response"]["result"]["rows"][0][0]["value"]
        return int(new_balance)
    except (KeyError, IndexError):
        return None


# =============================================================================
# ACTIONS
# =============================================================================

def action_check(params):
    """Check credits balance and unlock status"""
    user_id = params.get("user_id") or get_user_id()

    if not user_id:
        return get_error_message("No user ID found. Run system setup first.")

    user = get_or_create_user(user_id)
    user['credits'] = get_user_credits(user_id)
    unlocked = get_unlocked_tools(user_id)

    tools_data = []
    if os.path.exists(SYSTEM_REGISTRY):
        with open(SYSTEM_REGISTRY, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("action") == "__tool__" and entry.get("locked") is not None:
                        tool_id = entry.get("tool")
                        tools_data.append({
                            "id": tool_id,
                            "name": entry.get("description", tool_id).split(" - ")[0] if entry.get("description") else tool_id,
                            "cost": entry.get("referral_unlock_cost", 1),
                            "unlocked": tool_id in unlocked or not entry.get("locked", False)
                        })
                except json.JSONDecodeError:
                    continue

    return get_success_message(
        f"Credits: {user['credits']} | Unlocked: {len(unlocked)} tools",
        data={
            "user_id": user_id,
            "credits": user['credits'],
            "unlocked_tools": unlocked,
            "tools": tools_data
        }
    )


def action_refer(params):
    """Submit referral emails via Turso HTTP API"""
    import urllib.request

    user_id = params.get("user_id") or get_user_id()
    emails = params.get("emails", [])

    if not user_id:
        return get_error_message("No user ID found. Run system setup first.")

    if not emails:
        return get_error_message("No emails provided for referral.")

    if isinstance(emails, str):
        emails = [e.strip() for e in emails.split(",")]

    get_or_create_user(user_id)

    turso_url, turso_token = _get_turso_config()

    submitted = []
    already_referred = []

    for email in emails:
        email = email.strip().lower()
        if not email:
            continue

        check_result = _turso_exec(turso_url, turso_token, [
            {"type": "execute", "stmt": {"sql": "SELECT id FROM referrals WHERE referrer_id = ? AND referee_email = ?", "args": [{"type": "text", "value": user_id}, {"type": "text", "value": email}]}},
            {"type": "close"}
        ])

        try:
            rows = check_result["results"][0]["response"]["result"]["rows"]
            if rows:
                already_referred.append(email)
                continue
        except (KeyError, IndexError):
            pass

        _turso_exec(turso_url, turso_token, [
            {"type": "execute", "stmt": {"sql": "INSERT INTO referrals (referrer_id, referee_email, status) VALUES (?, ?, 'pending')", "args": [{"type": "text", "value": user_id}, {"type": "text", "value": email}]}},
            {"type": "close"}
        ])
        submitted.append(email)

    if submitted:
        new_balance = add_credits_to_user(user_id, len(submitted), f"referrals:{','.join(submitted)}")
        msg = f"Submitted {len(submitted)} referral(s). +{len(submitted)} credits. Balance: {new_balance}"
    else:
        msg = "No new referrals submitted."

    if already_referred:
        msg += f" ({len(already_referred)} already referred)"

    return get_success_message(msg, data={
        "submitted": submitted,
        "already_referred": already_referred,
        "credits": get_user_credits(user_id)
    })


def update_system_settings_lock(tool_id, locked=False):
    """Update the locked flag for a tool in system_settings.ndjson"""
    if not os.path.exists(SYSTEM_REGISTRY):
        return False

    try:
        lines = []
        updated = False
        with open(SYSTEM_REGISTRY, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("tool") == tool_id and entry.get("action") == "__tool__":
                        entry["locked"] = locked
                        entry["unlocked"] = not locked
                        updated = True
                    lines.append(json.dumps(entry))
                except json.JSONDecodeError:
                    lines.append(line)

        if updated:
            with open(SYSTEM_REGISTRY, 'w') as f:
                for line in lines:
                    f.write(line + '\n')

        return updated
    except Exception:
        return False


def action_unlock(params):
    """Unlock a tool using credits"""
    import urllib.request

    user_id = params.get("user_id") or get_user_id()
    tool_id = params.get("tool_id")

    if not user_id:
        return get_error_message("No user ID found. Run system setup first.")

    if not tool_id:
        return get_error_message("No tool_id specified.")

    tool_cost = 1
    tool_name = tool_id
    tool_locked = False

    if os.path.exists(SYSTEM_REGISTRY):
        with open(SYSTEM_REGISTRY, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("tool") == tool_id and entry.get("action") == "__tool__":
                        tool_cost = entry.get("referral_unlock_cost", 1)
                        tool_name = entry.get("description", tool_id).split(" - ")[0] if entry.get("description") else tool_id
                        tool_locked = entry.get("locked", False)
                        break
                except json.JSONDecodeError:
                    continue

    if not tool_locked:
        unlocked = get_unlocked_tools(user_id)
        if tool_id in unlocked:
            return get_error_message(f"{tool_name} is already unlocked.")

    user = get_or_create_user(user_id)
    if user['credits'] < tool_cost:
        return get_error_message(
            f"Insufficient credits. Need {tool_cost}, have {user['credits']}."
        )

    new_balance = deduct_credits_from_user(user_id, tool_cost, f"unlock:{tool_id}")

    if new_balance is None:
        return get_error_message("Failed to deduct credits.")

    if tool_id == "claude_assistant":
        try:
            claude_bin = os.path.expanduser("~/.local/bin/claude")
            if os.path.exists(claude_bin):
                subprocess.Popen([claude_bin, "login"])
        except Exception:
            pass

    turso_url, turso_token = _get_turso_config()
    try:
        _turso_exec(turso_url, turso_token, [
            {"type": "execute", "stmt": {"sql": "INSERT INTO unlocked_tools (user_id, tool_id) VALUES (?, ?)", "args": [{"type": "text", "value": user_id}, {"type": "text", "value": tool_id}]}},
            {"type": "close"}
        ])
    except Exception:
        pass

    settings_updated = update_system_settings_lock(tool_id, locked=False)

    return get_success_message(
        f"Unlocked {tool_name}! -{tool_cost} credit(s). Balance: {new_balance}",
        data={
            "tool_id": tool_id,
            "tool_name": tool_name,
            "cost": tool_cost,
            "credits_remaining": new_balance,
            "system_settings_updated": settings_updated
        }
    )


def action_add_user(params):
    """Create a new user account (for testing)"""
    user_id = params.get("user_id") or str(uuid.uuid4())[:8]
    email = params.get("email")
    initial_credits = params.get("credits", 3)

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if cursor.fetchone():
        conn.close()
        return get_error_message(f"User {user_id} already exists.")

    cursor.execute(
        "INSERT INTO users (user_id, email, credits) VALUES (?, ?, ?)",
        (user_id, email, initial_credits)
    )
    cursor.execute(
        "INSERT INTO credit_transactions (user_id, amount, reason) VALUES (?, ?, 'initial_signup')",
        (user_id, initial_credits)
    )
    conn.commit()
    conn.sync()
    conn.close()

    return get_success_message(
        f"Created user {user_id} with {initial_credits} credits",
        data={"user_id": user_id, "email": email, "credits": initial_credits}
    )


def action_list_users(params):
    """List all users in the database (for testing)"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT u.user_id, u.email, u.credits, u.created_at,
               COUNT(ut.tool_id) as unlocked_count
        FROM users u
        LEFT JOIN unlocked_tools ut ON u.user_id = ut.user_id
        GROUP BY u.user_id
        ORDER BY u.created_at DESC
    """)

    users = []
    for row in cursor.fetchall():
        users.append({
            "user_id": row[0],
            "email": row[1],
            "credits": row[2],
            "created_at": row[3],
            "unlocked_count": row[4]
        })

    conn.close()

    return get_success_message(
        f"Found {len(users)} user(s)",
        data={"users": users}
    )


def action_add_credits(params):
    """Add credits to a user (for testing)"""
    user_id = params.get("user_id")
    amount = params.get("amount", 1)
    reason = params.get("reason", "manual_add")

    if not user_id:
        return get_error_message("user_id required")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        conn.close()
        return get_error_message(f"User {user_id} not found")
    conn.close()

    new_balance = add_credits_to_user(user_id, amount, reason)

    return get_success_message(
        f"Added {amount} credits to {user_id}. New balance: {new_balance}",
        data={"user_id": user_id, "credits_added": amount, "new_balance": new_balance}
    )


def action_get_transactions(params):
    """Get credit transaction history for a user"""
    user_id = params.get("user_id") or get_user_id()
    limit = params.get("limit", 20)

    if not user_id:
        return get_error_message("No user ID found.")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """SELECT * FROM credit_transactions
           WHERE user_id = ?
           ORDER BY created_at DESC
           LIMIT ?""",
        (user_id, limit)
    )

    columns = ['id', 'user_id', 'amount', 'reason', 'created_at']
    transactions = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()

    return get_success_message(
        f"Found {len(transactions)} transaction(s)",
        data={"transactions": transactions}
    )


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action")
    parser.add_argument("--params", default="{}")
    args = parser.parse_args()

    params = json.loads(args.params)
    action = args.action

    if action == "check":
        result = action_check(params)
    elif action == "refer":
        result = action_refer(params)
    elif action == "unlock":
        result = action_unlock(params)
    elif action == "add_user":
        result = action_add_user(params)
    elif action == "list_users":
        result = action_list_users(params)
    elif action == "add_credits":
        result = action_add_credits(params)
    elif action == "get_transactions":
        result = action_get_transactions(params)
    else:
        result = get_error_message(f"Unknown action: {action}")

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
