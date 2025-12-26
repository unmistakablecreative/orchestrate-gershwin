#!/usr/bin/env python3
"""
Mem Tool

Auto-refactored by refactorize.py to match gold standard structure.
"""

import sys
import os
import json
import argparse

import requests


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CREDENTIALS_PATH = os.path.join(BASE_DIR, "tools", "credentials.json")
API_BASE = "https://api.mem.ai/v2"


def load_credential(key):
    try:
        with open(CREDENTIALS_PATH, "r") as f:
            return json.load(f).get(key)
    except Exception:
        return None


mem_api_key = load_credential("mem_api_key")

HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {mem_api_key}"
}


def handle_response(res):
    try:
        res.raise_for_status()
        return res.json()
    except requests.exceptions.HTTPError:
        return {"status": "error", "message": res.text}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def create_note(params):
    payload = {
        "content": params.get("content")
    }
    return handle_response(requests.post(f"{API_BASE}/notes", headers=HEADERS, json=payload))


def read_note(params):
    note_id = params.get("note_id")
    return handle_response(requests.get(f"{API_BASE}/notes/{note_id}", headers=HEADERS))


def delete_note(params):
    note_id = params.get("note_id")
    return handle_response(requests.delete(f"{API_BASE}/notes/{note_id}", headers=HEADERS))


def mem_it(params):
    payload = {
        "input": params.get("input")
    }
    if params.get("instructions"):
        payload["instructions"] = params.get("instructions")
    return handle_response(requests.post(f"{API_BASE}/mem-it", headers=HEADERS, json=payload))


def create_collection(params):
    payload = {
        "title": params.get("title")
    }
    if params.get("description"):
        payload["description"] = params.get("description")
    return handle_response(requests.post(f"{API_BASE}/collections", headers=HEADERS, json=payload))


def delete_collection(params):
    cid = params.get("collection_id")
    return handle_response(requests.delete(f"{API_BASE}/collections/{cid}", headers=HEADERS))


def ping(_):
    return handle_response(requests.get(f"{API_BASE}/notes/bogus-id", headers=HEADERS))


def main():
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    if args.action == 'create_collection':
        result = create_collection(params)
    elif args.action == 'create_note':
        result = create_note(params)
    elif args.action == 'delete_collection':
        result = delete_collection(params)
    elif args.action == 'delete_note':
        result = delete_note(params)
    elif args.action == 'handle_response':
        result = handle_response(**params)
    elif args.action == 'mem_it':
        result = mem_it(params)
    elif args.action == 'ping':
        result = ping(**params)
    elif args.action == 'read_note':
        result = read_note(params)
    else:
        result = {'status': 'error', 'message': f'Unknown action {args.action}'}

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()