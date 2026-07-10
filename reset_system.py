#!/usr/bin/env python3
"""Reset Gershwin to clean slate for testing unlock flow."""
import os
import json
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
ACCOUNTS_DB = os.path.join(DATA_DIR, "accounts.db")
SYSTEM_IDENTITY = os.path.join(DATA_DIR, "system_identity.json")
SETTINGS = os.path.join(BASE_DIR, "system_settings.ndjson")

PREMIUM_TOOLS = ["claude_assistant", "github_tool_universal", "buffer_engine", "ideogram_tool", "readwise_tool"]

def reset_user_state():
    with open(SYSTEM_IDENTITY, "r") as f:
        identity = json.load(f)
    identity["first_run_complete"] = False
    with open(SYSTEM_IDENTITY, "w") as f:
        json.dump(identity, f, indent=4)
    print("[OK] system_identity.json reset - first_run_complete: false")

def get_system_user():
    with open(SYSTEM_IDENTITY, "r") as f:
        identity = json.load(f)
    return identity.get("user_id")

def reset_accounts_db():
    user_id = get_system_user()
    conn = sqlite3.connect(ACCOUNTS_DB)

    # Clear all unlocked tools
    conn.execute("DELETE FROM unlocked_tools")

    # Reset credits for system user to 50
    conn.execute("UPDATE users SET credits = 50 WHERE user_id = ?", (user_id,))

    # If system user doesn't exist, create them
    cursor = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        conn.execute("INSERT INTO users (user_id, email, credits, created_at, updated_at) VALUES (?, ?, 50, datetime('now'), datetime('now'))", (user_id, "test@orchestrateos.io"))

    conn.commit()

    # Verify
    cursor = conn.execute("SELECT credits FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    credits = row[0] if row else "NOT FOUND"

    cursor = conn.execute("SELECT COUNT(*) FROM unlocked_tools")
    unlocked_count = cursor.fetchone()[0]

    conn.close()
    print(f"[OK] accounts.db reset - user '{user_id}' has {credits} credits, {unlocked_count} unlocked tools")

def reset_system_settings():
    lines = []
    modified = 0
    with open(SETTINGS, "r") as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("action") == "__tool__" and entry.get("tool") in PREMIUM_TOOLS:
                entry["locked"] = True
                entry.pop("unlocked", None)
                modified += 1
            lines.append(json.dumps(entry))

    with open(SETTINGS, "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"[OK] system_settings.ndjson reset - {modified} tools locked: {', '.join(PREMIUM_TOOLS)}")

if __name__ == "__main__":
    print("=" * 50)
    print("GERSHWIN RESET SYSTEM")
    print("=" * 50)
    reset_user_state()
    reset_accounts_db()
    reset_system_settings()
    print("=" * 50)
    print("DONE. Refresh browser to see first_run.html")
    print("=" * 50)
