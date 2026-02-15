#!/usr/bin/env python3
"""
Bullet Journal Tool - Thin wrapper around json_manager for rapid capture.

Entry types:
- note (bullet): Quick thoughts, observations
- task (dash): Action items
- event (circle): Calendar entries, things that happened

All entries go to data/bullet_journal.json.
"""

import sys
import os
import json
import argparse
from datetime import datetime

# Add parent dir for json_manager import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from json_manager import safe_write_json

DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'bullet_journal.json')


def load_journal():
    """Load journal data or create empty structure."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"entries": {}}


def save_journal(data):
    """Save journal data with safe write."""
    safe_write_json(DATA_FILE, data)


def generate_entry_key():
    """Generate entry key: bj_YYYYMMDD_HHMMSS"""
    return f"bj_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def add_entry(params):
    """
    Add a new bullet journal entry.

    Required:
    - type: note | task | event
    - content: The entry text

    Optional:
    - collection: Group/category (default: general)
    """
    entry_type = params.get('type')
    content = params.get('content')
    collection = params.get('collection', 'general')

    if not entry_type or entry_type not in ['note', 'task', 'event']:
        return {"status": "error", "message": "type required: note, task, or event"}

    if not content:
        return {"status": "error", "message": "content required"}

    entry_key = generate_entry_key()

    entry = {
        "type": entry_type,
        "content": content,
        "collection": collection,
        "status": "raw",
        "timestamp": datetime.now().isoformat()
    }

    data = load_journal()
    data["entries"][entry_key] = entry
    save_journal(data)

    symbols = {"note": "•", "task": "-", "event": "○"}

    return {
        "status": "success",
        "message": f"{symbols[entry_type]} Entry added",
        "entry_key": entry_key,
        "entry": entry
    }


def list_entries(params):
    """
    List journal entries with optional filters.

    Optional:
    - type: Filter by note | task | event
    - collection: Filter by collection
    - status: Filter by status (raw, done, migrated, etc.)
    - limit: Max entries to return (default: 50)
    """
    filter_type = params.get('type')
    filter_collection = params.get('collection')
    filter_status = params.get('status')
    limit = int(params.get('limit', 50))

    data = load_journal()
    entries = data.get("entries", {})

    # Apply filters
    filtered = {}
    for key, entry in entries.items():
        if filter_type and entry.get('type') != filter_type:
            continue
        if filter_collection and entry.get('collection') != filter_collection:
            continue
        if filter_status and entry.get('status') != filter_status:
            continue
        filtered[key] = entry

    # Sort by timestamp (newest first)
    sorted_entries = dict(sorted(
        filtered.items(),
        key=lambda x: x[1].get('timestamp', ''),
        reverse=True
    )[:limit])

    return {
        "status": "success",
        "count": len(sorted_entries),
        "entries": sorted_entries
    }


def update_status(params):
    """
    Update entry status.

    Required:
    - entry_key: The entry to update
    - status: New status (done, migrated, scheduled, cancelled, irrelevant)
    """
    entry_key = params.get('entry_key')
    new_status = params.get('status')

    if not entry_key:
        return {"status": "error", "message": "entry_key required"}

    if not new_status:
        return {"status": "error", "message": "status required"}

    data = load_journal()

    if entry_key not in data.get("entries", {}):
        return {"status": "error", "message": f"Entry {entry_key} not found"}

    data["entries"][entry_key]["status"] = new_status
    data["entries"][entry_key]["updated_at"] = datetime.now().isoformat()
    save_journal(data)

    return {
        "status": "success",
        "message": f"Entry {entry_key} marked as {new_status}",
        "entry": data["entries"][entry_key]
    }


def delete_entry(params):
    """
    Delete an entry.

    Required:
    - entry_key: The entry to delete
    """
    entry_key = params.get('entry_key')

    if not entry_key:
        return {"status": "error", "message": "entry_key required"}

    data = load_journal()

    if entry_key not in data.get("entries", {}):
        return {"status": "error", "message": f"Entry {entry_key} not found"}

    deleted_entry = data["entries"].pop(entry_key)
    save_journal(data)

    return {
        "status": "success",
        "message": f"Entry {entry_key} deleted",
        "deleted_entry": deleted_entry
    }


def get_collections(params):
    """List all unique collections in the journal."""
    data = load_journal()
    collections = set()

    for entry in data.get("entries", {}).values():
        collections.add(entry.get("collection", "general"))

    return {
        "status": "success",
        "collections": sorted(list(collections))
    }


def main():
    parser = argparse.ArgumentParser(description="Bullet Journal Tool")
    parser.add_argument('action', help='Action to perform')
    parser.add_argument('--params', type=str, default='{}', help='JSON params')
    args = parser.parse_args()

    try:
        params = json.loads(args.params) if args.params else {}
    except json.JSONDecodeError as e:
        print(json.dumps({"status": "error", "message": f"Invalid JSON: {e}"}, indent=2))
        return

    actions = {
        'add_entry': add_entry,
        'list_entries': list_entries,
        'update_status': update_status,
        'delete_entry': delete_entry,
        'get_collections': get_collections
    }

    if args.action not in actions:
        print(json.dumps({
            "status": "error",
            "message": f"Unknown action: {args.action}",
            "available_actions": list(actions.keys())
        }, indent=2))
        return

    result = actions[args.action](params)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
