#!/usr/bin/env python3
"""
Account Tool - Consolidated credits, referrals, and tool unlocking

LOCAL SQLITE VERSION FOR TESTING
This version uses accounts.db locally instead of JSONBin.
Once tested, will migrate to Turso.

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
import sqlite3
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
    conn = sqlite3.connect(ACCOUNTS_DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Users table - main account info
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            email TEXT,
            credits INTEGER DEFAULT 3,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_active TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Unlocked tools table - tracks which tools each user has unlocked
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

    # Referrals table - tracks referral submissions
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

    # Credit transactions table - audit log for credit changes
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
    conn.close()


def get_db_connection():
    """Get a database connection with row factory"""
    init_db()  # Ensure tables exist
    conn = sqlite3.connect(ACCOUNTS_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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


def get_or_create_user(user_id, email=None):
    """Get existing user or create new one"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        cursor.execute(
            "INSERT INTO users (user_id, email, credits) VALUES (?, ?, 3)",
            (user_id, email)
        )
        conn.commit()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()

        # Log initial credits
        cursor.execute(
            "INSERT INTO credit_transactions (user_id, amount, reason) VALUES (?, 3, 'initial_signup')",
            (user_id,)
        )
        conn.commit()

    conn.close()
    return dict(user)


def get_user_credits(user_id):
    """Get current credits for a user"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT credits FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row['credits'] if row else 0


def get_unlocked_tools(user_id):
    """Get list of unlocked tool IDs for a user"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT tool_id FROM unlocked_tools WHERE user_id = ?", (user_id,))
    tools = [row['tool_id'] for row in cursor.fetchall()]
    conn.close()
    return tools


def add_credits_to_user(user_id, amount, reason):
    """Add credits to a user account"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE users SET credits = credits + ? WHERE user_id = ?",
        (amount, user_id)
    )
    cursor.execute(
        "INSERT INTO credit_transactions (user_id, amount, reason) VALUES (?, ?, ?)",
        (user_id, amount, reason)
    )

    conn.commit()
    cursor.execute("SELECT credits FROM users WHERE user_id = ?", (user_id,))
    new_balance = cursor.fetchone()['credits']
    conn.close()

    return new_balance


def deduct_credits_from_user(user_id, amount, reason):
    """Deduct credits from a user account"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT credits FROM users WHERE user_id = ?", (user_id,))
    current = cursor.fetchone()

    if not current or current['credits'] < amount:
        conn.close()
        return None  # Insufficient credits

    cursor.execute(
        "UPDATE users SET credits = credits - ? WHERE user_id = ?",
        (amount, user_id)
    )
    cursor.execute(
        "INSERT INTO credit_transactions (user_id, amount, reason) VALUES (?, ?, ?)",
        (user_id, -amount, reason)
    )

    conn.commit()
    cursor.execute("SELECT credits FROM users WHERE user_id = ?", (user_id,))
    new_balance = cursor.fetchone()['credits']
    conn.close()

    return new_balance


# =============================================================================
# ACTIONS
# =============================================================================

def action_check(params):
    """Check credits balance and unlock status"""
    user_id = params.get("user_id") or get_user_id()

    if not user_id:
        return get_error_message("No user ID found. Run system setup first.")

    user = get_or_create_user(user_id)
    unlocked = get_unlocked_tools(user_id)

    # Load tools from system_settings.ndjson
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
    """Submit referral emails"""
    user_id = params.get("user_id") or get_user_id()
    emails = params.get("emails", [])

    if not user_id:
        return get_error_message("No user ID found. Run system setup first.")

    if not emails:
        return get_error_message("No emails provided for referral.")

    if isinstance(emails, str):
        emails = [e.strip() for e in emails.split(",")]

    # Ensure user exists
    get_or_create_user(user_id)

    conn = get_db_connection()
    cursor = conn.cursor()

    submitted = []
    already_referred = []

    for email in emails:
        email = email.strip().lower()
        if not email:
            continue

        # Check if already referred
        cursor.execute(
            "SELECT id FROM referrals WHERE referrer_id = ? AND referee_email = ?",
            (user_id, email)
        )
        if cursor.fetchone():
            already_referred.append(email)
            continue

        # Add new referral
        cursor.execute(
            "INSERT INTO referrals (referrer_id, referee_email, status) VALUES (?, ?, 'pending')",
            (user_id, email)
        )
        submitted.append(email)

    conn.commit()
    conn.close()

    # Award credits for new referrals (1 credit per referral in test mode)
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
                    # Match tool by name and check if it's a __tool__ entry
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
    user_id = params.get("user_id") or get_user_id()
    tool_id = params.get("tool_id")

    if not user_id:
        return get_error_message("No user ID found. Run system setup first.")

    if not tool_id:
        return get_error_message("No tool_id specified.")

    # Get tool cost from system_settings.ndjson (referral_unlock_cost)
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

    # Check if already unlocked in system_settings
    if not tool_locked:
        # Also check the database
        unlocked = get_unlocked_tools(user_id)
        if tool_id in unlocked:
            return get_error_message(f"{tool_name} is already unlocked.")

    # Check credits
    user = get_or_create_user(user_id)
    if user['credits'] < tool_cost:
        return get_error_message(
            f"Insufficient credits. Need {tool_cost}, have {user['credits']}."
        )

    # Deduct credits and unlock
    new_balance = deduct_credits_from_user(user_id, tool_cost, f"unlock:{tool_id}")

    if new_balance is None:
        return get_error_message("Failed to deduct credits.")

    # Add to unlocked tools in database
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO unlocked_tools (user_id, tool_id) VALUES (?, ?)",
            (user_id, tool_id)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass  # Already unlocked in DB
    conn.close()

    # Update system_settings.ndjson - set locked: false
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

    # Check if user exists
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if cursor.fetchone():
        conn.close()
        return get_error_message(f"User {user_id} already exists.")

    # Create user
    cursor.execute(
        "INSERT INTO users (user_id, email, credits) VALUES (?, ?, ?)",
        (user_id, email, initial_credits)
    )
    cursor.execute(
        "INSERT INTO credit_transactions (user_id, amount, reason) VALUES (?, ?, 'initial_signup')",
        (user_id, initial_credits)
    )
    conn.commit()
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
            "user_id": row['user_id'],
            "email": row['email'],
            "credits": row['credits'],
            "created_at": row['created_at'],
            "unlocked_count": row['unlocked_count']
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

    # Ensure user exists
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

    transactions = [dict(row) for row in cursor.fetchall()]
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
