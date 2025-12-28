#!/usr/bin/env python3
"""
Refer User - JSONBin-only referral system
"""

import os
import sys
import json
import argparse
import uuid
from datetime import datetime

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUNTIME_DIR = os.path.dirname(BASE_DIR)
SECONDBRAIN_PATH = os.path.join(RUNTIME_DIR, "data", "secondbrain.json")
STATE_DIR = os.path.expanduser("~/Library/Application Support/OrchestrateOS")
CREDENTIALS_PATH = os.path.join(STATE_DIR, "system_identity.json")
JSONBIN_MASTER_KEY = "$2a$10$MoavwaWsCucy2FkU/5ycV.lBTPWoUq4uKHhCi9Y47DOHWyHFL3o2C"
REFERRALS_BIN = "694a185eae596e708fab9028"
# TEST LEDGER - Switch to production (68292fcf8561e97a50162139) before release
LEDGER_BIN = "694f0af6ae596e708fb2bd68"


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


def refer_user(params):
    name = params.get("name")
    email = params.get("email")

    if not name or not email:
        return {"status": "error", "message": "Missing name or email"}

    # Get referrer_id from system identity
    if not os.path.exists(CREDENTIALS_PATH):
        return {"status": "error", "message": f"Credentials file not found: {CREDENTIALS_PATH}"}

    with open(CREDENTIALS_PATH, 'r') as f:
        identity = json.load(f)

    referrer_id = identity.get("user_id")
    # Get referrer name from secondbrain.json (set during onboarding)
    referrer_name = get_referrer_name()

    if not referrer_id:
        return {"status": "error", "message": "No user_id found in system_identity.json"}

    referral_id = f"ref-{str(uuid.uuid4())[:8]}"
    headers = {"X-Master-Key": JSONBIN_MASTER_KEY, "Content-Type": "application/json"}

    # Add entry to referrals bin (entries is a dict, not a list)
    resp = requests.get(f"https://api.jsonbin.io/v3/b/{REFERRALS_BIN}", headers=headers, timeout=30)
    referrals = resp.json().get("record", {"filename": "referrals.json", "entries": {}}) if resp.ok else {"filename": "referrals.json", "entries": {}}

    # Ensure entries is a dict
    if not isinstance(referrals.get("entries"), dict):
        referrals["entries"] = {}

    # Add new referral entry keyed by referral_id
    referrals["entries"][referral_id] = {
        "referrer_id": referrer_id,
        "referrer_name": referrer_name,
        "referee_name": name,
        "referee_email": email,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "credits_awarded": 3,
        "email_sent": False
    }
    referrals["filename"] = "referrals.json"

    resp = requests.put(f"https://api.jsonbin.io/v3/b/{REFERRALS_BIN}", headers=headers, json=referrals, timeout=30)
    if not resp.ok:
        return {"status": "error", "message": f"Failed to update referrals bin: {resp.text}"}

    # Update ledger with credits (uses 'installs' key, not 'users')
    resp = requests.get(f"https://api.jsonbin.io/v3/b/{LEDGER_BIN}", headers=headers, timeout=30)
    ledger = resp.json().get("record", {"filename": "install_ledger.json", "installs": {}}) if resp.ok else {"filename": "install_ledger.json", "installs": {}}

    # Ensure installs dict exists
    if "installs" not in ledger:
        ledger["installs"] = {}

    # Create user entry if not exists
    if referrer_id not in ledger["installs"]:
        ledger["installs"][referrer_id] = {
            "referral_count": 0,
            "referral_credits": 0,
            "tools_unlocked": [],
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

    # Update credits and count
    ledger["installs"][referrer_id]["referral_credits"] = ledger["installs"][referrer_id].get("referral_credits", 0) + 3
    ledger["installs"][referrer_id]["referral_count"] = ledger["installs"][referrer_id].get("referral_count", 0) + 1
    ledger["filename"] = "install_ledger.json"

    resp = requests.put(f"https://api.jsonbin.io/v3/b/{LEDGER_BIN}", headers=headers, json=ledger, timeout=30)
    if not resp.ok:
        return {"status": "error", "message": f"Failed to update ledger bin: {resp.text}"}

    return {
        "status": "success",
        "message": f"Referral created for {name} ({email})",
        "referral_id": referral_id,
        "referrer_id": referrer_id,
        "credits_awarded": 3
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    if args.action == 'refer_user':
        result = refer_user(params)
    else:
        result = {'status': 'error', 'message': f'Unknown action {args.action}'}

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
