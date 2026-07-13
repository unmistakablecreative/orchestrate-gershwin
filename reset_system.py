#!/usr/bin/env python3
"""Reset Gershwin to clean slate for testing unlock flow."""
import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
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
    import urllib.request

    # Reset via Turso HTTP API directly - SET to 50, wipe unlocked_tools
    try:
        creds_path = os.path.join(BASE_DIR, "tools", "credentials.json")
        with open(creds_path) as f:
            creds = json.load(f)
        turso_url = creds["turso_url"].replace("libsql://", "https://") + "/v2/pipeline"
        turso_token = creds["turso_token"]

        payload = json.dumps({"requests": [
            {"type": "execute", "stmt": {"sql": "UPDATE users SET credits = 50 WHERE user_id = ?", "args": [{"type": "text", "value": user_id}]}},
            {"type": "execute", "stmt": {"sql": "DELETE FROM unlocked_tools WHERE user_id = ?", "args": [{"type": "text", "value": user_id}]}},
            {"type": "close"}
        ]}).encode()

        req = urllib.request.Request(turso_url, data=payload, headers={"Content-Type": "application/json", "Authorization": f"Bearer {turso_token}"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
        print(f"[OK] Turso reset - user '{user_id}' set to 50 credits, unlocked_tools cleared")
    except Exception as e:
        print(f"[WARN] Turso reset failed: {e}")

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
