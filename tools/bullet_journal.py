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
import requests
from datetime import datetime

# Add parent dir for json_manager import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from json_manager import safe_write_json

DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'bullet_journal.json')
CREDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'credentials.json')

# Only 4 verb-based collections allowed
VALID_COLLECTIONS = ['SHIP', 'HANDLE', 'PUBLISH', 'IDEAS']


def _generate_summary(content):
    """
    Generate a one-sentence summary for machine consumption.

    Uses Claude API if available, otherwise extracts first meaningful sentence.
    NEVER truncates content - that's lazy and useless for search/indexing.
    """
    # Try to get API key from multiple sources
    api_key = None

    # Check environment variable first
    api_key = os.environ.get('ANTHROPIC_API_KEY')

    # Check credentials file
    if not api_key:
        try:
            with open(CREDS_FILE, 'r') as f:
                creds = json.load(f)
            api_key = creds.get('anthropic_api_key')
        except:
            pass

    # If we have an API key, use Claude to generate a real summary
    if api_key:
        try:
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "claude-3-5-haiku-20241022",
                    "max_tokens": 100,
                    "messages": [{
                        "role": "user",
                        "content": f"Summarize this in ONE short sentence (max 15 words) for machine indexing. No quotes, no preamble, just the summary:\n\n{content}"
                    }]
                },
                timeout=10
            )
            if response.status_code == 200:
                return response.json()['content'][0]['text'].strip()
        except:
            pass

    # Fallback: extract first meaningful sentence (NOT truncation)
    # This is still useful - a sentence is better than a substring
    return _extract_first_sentence(content)


def _extract_first_sentence(content):
    """
    Extract first complete sentence from content.
    If content is short enough, return as-is.
    Never truncate mid-word or mid-thought.
    """
    # If content is already short, return it
    if len(content) <= 100:
        return content

    # Try to find first sentence ending
    # Look for period, question mark, or exclamation followed by space or end
    import re

    # First, try to find a natural sentence break
    sentence_match = re.search(r'^(.+?[.!?])(?:\s|$)', content)
    if sentence_match and len(sentence_match.group(1)) <= 150:
        return sentence_match.group(1)

    # If no sentence break found, look for a dash or colon break (common in notes)
    dash_match = re.search(r'^(.+?)(?:\s*[-—–]\s*|\s*:\s*)', content)
    if dash_match and 30 <= len(dash_match.group(1)) <= 100:
        return dash_match.group(1)

    # Last resort: find a logical break point (end of phrase before a comma or connector)
    # but still ensure we're not truncating mid-word
    words = content.split()
    if len(words) <= 15:
        return content

    # Take first ~15 words that form a complete thought
    partial = ' '.join(words[:15])

    # If it ends with a preposition or article, include one more word
    if partial.endswith((' a', ' an', ' the', ' to', ' of', ' in', ' on', ' for', ' with', ' and', ' or', ' but')):
        if len(words) > 15:
            partial = ' '.join(words[:16])

    return partial


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
    - collection: BUILD | LAUNCH | PUBLISH | HANDLE | THINK (default: HANDLE)
    """
    entry_type = params.get('type')
    content = params.get('content')
    collection = params.get('collection', 'HANDLE').upper()

    # Validate collection
    if collection not in VALID_COLLECTIONS:
        return {"status": "error", "message": f"Invalid collection '{collection}'. Must be one of: {', '.join(VALID_COLLECTIONS)}"}

    if not entry_type or entry_type not in ['note', 'task', 'event']:
        return {"status": "error", "message": "type required: note, task, or event"}

    if not content:
        return {"status": "error", "message": "content required"}

    entry_key = generate_entry_key()

    # Generate summary for machine consumption
    summary = _generate_summary(content)

    entry = {
        "type": entry_type,
        "content": content,
        "summary": summary,
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
    """List the 4 valid verb-based collections."""
    return {
        "status": "success",
        "collections": VALID_COLLECTIONS,
        "descriptions": {
            "SHIP": "code, bugs, tools, features, infrastructure, launches, customers, demos",
            "HANDLE": "inbox, meetings, daily ops, personal",
            "PUBLISH": "blogs, videos, podcasts, newsletters, social posts",
            "IDEAS": "permanent notes, insights, reading list, ideas, architecture"
        }
    }


def backfill_summaries(params):
    """
    Backfill summaries for all entries that don't have one.
    Reads all entries, generates summary for each missing one, writes back.
    """
    data = load_journal()
    entries = data.get("entries", {})

    updated_count = 0
    skipped_count = 0

    for key, entry in entries.items():
        if entry.get("summary"):
            skipped_count += 1
            continue

        content = entry.get("content", "")
        if content:
            summary = _generate_summary(content)
            data["entries"][key]["summary"] = summary
            updated_count += 1

    if updated_count > 0:
        save_journal(data)

    return {
        "status": "success",
        "message": f"Backfilled {updated_count} entries, skipped {skipped_count} with existing summaries",
        "updated": updated_count,
        "skipped": skipped_count
    }


def batch_update_status(params):
    """
    Update status on multiple entries in one call.

    Required:
    - entry_keys: Array of entry keys to update
    - status: New status to apply to all (done, migrated, scheduled, cancelled, irrelevant)
    """
    entry_keys = params.get("entry_keys", [])
    new_status = params.get("status")

    if not entry_keys:
        return {"status": "error", "message": "entry_keys required (array)"}

    if not isinstance(entry_keys, list):
        return {"status": "error", "message": "entry_keys must be an array"}

    if not new_status:
        return {"status": "error", "message": "status required"}

    data = load_journal()
    entries = data.get("entries", {})

    updated = []
    not_found = []
    now = datetime.now().isoformat()

    for key in entry_keys:
        if key in entries:
            entries[key]["status"] = new_status
            entries[key]["updated_at"] = now
            updated.append(key)
        else:
            not_found.append(key)

    if updated:
        save_journal(data)

    return {
        "status": "success",
        "message": f"Updated {len(updated)} entries to {new_status}",
        "updated": updated,
        "not_found": not_found
    }


def batch_add_entries(params):
    """
    Add multiple bullet journal entries at once.

    Required:
    - entries: Array of entry objects, each with:
        - type: note | task | event
        - content: The entry text
        - collection (optional): BUILD | LAUNCH | PUBLISH | HANDLE | THINK (default: HANDLE)
        - summary (optional): Pre-generated summary (skips API call if provided)
    """
    entries_input = params.get("entries", [])

    if not entries_input:
        return {"status": "error", "message": "entries required (array)"}

    if not isinstance(entries_input, list):
        return {"status": "error", "message": "entries must be an array"}

    data = load_journal()
    added = []
    errors = []

    for i, entry_input in enumerate(entries_input):
        entry_type = entry_input.get("type")
        content = entry_input.get("content")
        collection = entry_input.get("collection", "HANDLE").upper()
        summary = entry_input.get("summary")

        # Validate
        if collection not in VALID_COLLECTIONS:
            errors.append({"index": i, "error": f"Invalid collection '{collection}'"})
            continue

        if not entry_type or entry_type not in ["note", "task", "event"]:
            errors.append({"index": i, "error": "type required: note, task, or event"})
            continue

        if not content:
            errors.append({"index": i, "error": "content required"})
            continue

        # Generate unique key with microsecond to avoid collisions
        import time
        time.sleep(0.001)  # Ensure unique timestamps
        entry_key = generate_entry_key()

        # Use provided summary or generate one
        if not summary:
            summary = _generate_summary(content)

        entry = {
            "type": entry_type,
            "content": content,
            "summary": summary,
            "collection": collection,
            "status": "raw",
            "timestamp": datetime.now().isoformat()
        }

        data["entries"][entry_key] = entry
        added.append({"entry_key": entry_key, "type": entry_type, "collection": collection})

    if added:
        save_journal(data)

    return {
        "status": "success",
        "message": f"Added {len(added)} entries",
        "added": added,
        "errors": errors
    }


def batch_delete_entries(params):
    """
    Delete multiple entries in one call.

    Required:
    - entry_keys: Array of entry keys to delete
    """
    entry_keys = params.get("entry_keys", [])

    if not entry_keys:
        return {"status": "error", "message": "entry_keys required (array)"}

    if not isinstance(entry_keys, list):
        return {"status": "error", "message": "entry_keys must be an array"}

    data = load_journal()
    entries = data.get("entries", {})

    deleted = []
    not_found = []

    for key in entry_keys:
        if key in entries:
            del entries[key]
            deleted.append(key)
        else:
            not_found.append(key)

    if deleted:
        save_journal(data)

    return {
        "status": "success",
        "message": f"Deleted {len(deleted)} entries",
        "deleted": deleted,
        "not_found": not_found
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
        'get_collections': get_collections,
        'backfill_summaries': backfill_summaries,
        'batch_update_status': batch_update_status,
        'batch_add_entries': batch_add_entries,
        'batch_delete_entries': batch_delete_entries
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
