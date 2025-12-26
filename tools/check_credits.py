#!/usr/bin/env python3
"""
Check Credits

Auto-refactored by refactorize.py to match gold standard structure.
"""

import sys
import json
import os

import requests


IDENTITY_PATH = "/container_state/system_identity.json"
BIN_ID = "68292fcf8561e97a50162139"
API_KEY = "$2a$10$MoavwaWsCucy2FkU/5ycV.lBTPWoUq4uKHhCi9Y47DOHWyHFL3o2C"
HEADERS = {"X-Master-Key": API_KEY, "Content-Type": "application/json"}


def load_system_id():
    if not os.path.exists(IDENTITY_PATH):
        return None
    with open(IDENTITY_PATH, "r") as f:
        return json.load(f).get("user_id")


def check_credits():
    user_id = load_system_id()
    if not user_id:
        return {
            "status": "error",
            "message": "system_identity.json not found or invalid."
        }

    try:
        res = requests.get(f"https://api.jsonbin.io/v3/b/{BIN_ID}/latest", headers=HEADERS)
        res.raise_for_status()
        ledger = res.json()["record"]
    except Exception as e:
        return {
            "status": "error",
            "message": "Failed to fetch install ledger.",
            "details": str(e)
        }

    user = ledger["installs"].get(user_id)
    if not user:
        return {
            "status": "error",
            "message": f"User '{user_id}' not found in install ledger."
        }

    return {
        "status": "success",
        "user_id": user_id,
        "credits": user.get("referral_credits", 0),
        "tools_unlocked": user.get("tools_unlocked", []),
        "timestamp": user.get("timestamp")
    }


def main():
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    if args.action == 'check_credits':
        result = check_credits()
    elif args.action == 'load_system_id':
        result = load_system_id()
    else:
        result = {'status': 'error', 'message': f'Unknown action {args.action}'}

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()