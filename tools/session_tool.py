#!/usr/bin/env python3
"""
Session Tool

Auto-refactored by refactorize.py to match gold standard structure.
"""

import os
import json
import sys
import argparse


SESSION_PATH = "session_state.json"


def set_mode(mode):
    with open(SESSION_PATH, "r") as f:
        session = json.load(f)
    session["mode"] = mode
    with open(SESSION_PATH, "w") as f:
        json.dump(session, f, indent=4)
    return {"status": "success", "message": f"✅ Mode set to '{mode}'."}


def main():
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    if args.action == 'set_mode':
        result = set_mode(**params)
    else:
        result = {'status': 'error', 'message': f'Unknown action {args.action}'}

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()