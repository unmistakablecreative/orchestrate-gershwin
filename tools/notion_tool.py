#!/usr/bin/env python3
"""
Notion Tool

Auto-refactored by refactorize.py to match gold standard structure.
"""

import sys
import os
import json

import requests


NOTION_VERSION = "2022-02-22"
CREDENTIALS_FILE = "credentials.json"


def get_headers():
    path = os.path.join(os.path.dirname(__file__), CREDENTIALS_FILE)
    with open(path, "r") as f:
        creds = json.load(f)
    token = creds.get("NOTION_API_KEY")
    if not token:
        return {"status": "error", "message": "❌ NOTION_API_KEY missing in credentials.json"}
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION
    }


def create_page(params):
    title = params.get("title")
    database_id = params.get("database_id")
    parent_page_id = params.get("parent_page_id")

    if database_id:
        body = {
            "parent": { "database_id": database_id },
            "properties": {
                "Name": {
                    "title": [ { "text": { "content": title } } ]
                }
            }
        }
    elif parent_page_id:
        body = {
            "parent": { "type": "page_id", "page_id": parent_page_id },
            "properties": {
                "title": [ { "type": "text", "text": { "content": title } } ]
            }
        }
    else:
        return {"status": "error", "message": "❌ Must provide either database_id or parent_page_id"}

    res = requests.post("https://api.notion.com/v1/pages", headers=get_headers(), json=body)
    res.raise_for_status()
    return res.json()


def create_database(params):
    parent_page_id = params.get("parent_page_id")
    title = params.get("title")
    properties = params.get("properties")

    if not parent_page_id or not title or not properties:
        return {"status": "error", "message": "❌ create_database requires 'parent_page_id', 'title', and 'properties'"}

    body = {
        "parent": { "type": "page_id", "page_id": parent_page_id },
        "title": [ { "type": "text", "text": { "content": title } } ],
        "properties": properties
    }

    res = requests.post("https://api.notion.com/v1/databases", headers=get_headers(), json=body)
    res.raise_for_status()
    return res.json()


def update_page(params):
    page_id = params.get("page_id")
    properties = params.get("properties")

    if not page_id or not properties:
        return {"status": "error", "message": "❌ update_page requires 'page_id' and 'properties'"}

    res = requests.patch(f"https://api.notion.com/v1/pages/{page_id}", headers=get_headers(), json={"properties": properties})
    res.raise_for_status()
    return res.json()


def append_block_children(params):
    block_id = params.get("block_id")
    children = params.get("children")

    if not block_id or not children:
        return {"status": "error", "message": "❌ append_block_children requires 'block_id' and 'children'"}

    res = requests.patch(f"https://api.notion.com/v1/blocks/{block_id}/children", headers=get_headers(), json={"children": children})
    res.raise_for_status()
    return res.json()


def search(params):
    res = requests.post("https://api.notion.com/v1/search", headers=get_headers(), json=params)
    res.raise_for_status()
    return res.json()


def main():
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    if args.action == 'append_block_children':
        result = append_block_children(params)
    elif args.action == 'create_database':
        result = create_database(params)
    elif args.action == 'create_page':
        result = create_page(params)
    elif args.action == 'get_headers':
        result = get_headers()
    elif args.action == 'search':
        result = search(params)
    elif args.action == 'update_page':
        result = update_page(params)
    else:
        result = {'status': 'error', 'message': f'Unknown action {args.action}'}

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()