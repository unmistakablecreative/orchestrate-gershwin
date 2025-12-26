#!/usr/bin/env python3
"""
Json Manager

Auto-refactored by refactorize.py to match gold standard structure.
"""

import sys
import json
import os
import argparse


def insert_json_entry_from_template(params):
    filename = os.path.basename(params['filename'])
    entry_key = params['entry_key']
    template_name = params['template_name']
    data_dir = os.path.join(os.getcwd(), 'data')
    template_path = os.path.join(data_dir, template_name)
    filepath = os.path.join(data_dir, filename)
    if not os.path.exists(template_path):
        return {'status': 'error', 'message':
            f"❌ Template '{template_name}' not found."}
    if not os.path.exists(filepath):
        return {'status': 'error', 'message': '❌ File not found.'}
    with open(template_path, 'r', encoding='utf-8') as f:
        template_data = json.load(f)
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    data.setdefault('entries', {})
    data['entries'][str(entry_key)] = template_data
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    return {'status': 'success', 'message':
        f"✅ Inserted entry '{entry_key}' from template."}


def create_json_file_from_template(params):
    template_name = params['template_name']
    new_filename = os.path.basename(params['new_filename'])
    data_dir = os.path.join(os.getcwd(), 'data')
    template_path = os.path.join(data_dir, template_name)
    new_file_path = os.path.join(data_dir, new_filename)
    if not os.path.exists(template_path):
        return {'status': 'error', 'message':
            f"❌ Template '{template_name}' not found."}
    with open(template_path, 'r', encoding='utf-8') as f:
        template_data = json.load(f)
    with open(new_file_path, 'w', encoding='utf-8') as f:
        json.dump(template_data, f, indent=4)
    return {'status': 'success', 'message':
        f"✅ Created file '{new_filename}' from template."}


def batch_add_field_to_json_entries(params):
    filename = os.path.basename(params['filename'])
    entry_keys = params['entry_keys']
    field_name = params['field_name']
    field_value = params['field_value']
    filepath = os.path.join(os.getcwd(), 'data', filename)
    if not os.path.exists(filepath):
        return {'status': 'error', 'message': '❌ File not found.'}
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    updated = 0
    for key in entry_keys:
        if key in data.get('entries', {}):
            data['entries'][key][field_name] = field_value
            updated += 1
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    return {'status': 'success', 'message':
        f"✅ Field '{field_name}' added to {updated} entries."}


def add_field_to_json_entry(params):
    filename = os.path.basename(params['filename'])
    entry_key = params['entry_key']
    field_name = params['field_name']
    field_value = params['field_value']
    filepath = os.path.join(os.getcwd(), 'data', filename)
    if not os.path.exists(filepath):
        return {'status': 'error', 'message': '❌ File not found.'}
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if entry_key in data.get('entries', {}):
        data['entries'][entry_key][field_name] = field_value
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        return {'status': 'success', 'message':
            f"✅ Field '{field_name}' added to entry '{entry_key}'."}
    return {'status': 'error', 'message': '❌ Entry not found.'}


def search_json_entries(params):
    import os, json
    filename = os.path.basename(params['filename'])
    keyword = params.get('search_value', '').lower()
    filepath = os.path.join(os.getcwd(), 'data', filename)
    if not os.path.exists(filepath):
        return {'status': 'error', 'message': f'❌ File not found: {filename}'}
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    entries = data.get('entries', {})
    results = {}
    for entry_key, entry_value in entries.items():
        entry_blob = json.dumps(entry_value).lower()
        if keyword in entry_blob:
            results[entry_key] = entry_value
    return {'status': 'success', 'results': results}


def list_json_entries(params):
    filename = os.path.basename(params['filename'])
    filepath = os.path.join(os.getcwd(), 'data', filename)
    if not os.path.exists(filepath):
        return {'status': 'error', 'message': '❌ File not found.'}
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return {'status': 'success', 'entries': data.get('entries', {})}


def batch_delete_json_entries(params):
    filename = os.path.basename(params['filename'])
    entry_keys = params['entry_keys']
    filepath = os.path.join(os.getcwd(), 'data', filename)
    if not os.path.exists(filepath):
        return {'status': 'error', 'message': '❌ File not found.'}
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    deleted_count = 0
    for key in entry_keys:
        if key in data.get('entries', {}):
            del data['entries'][key]
            deleted_count += 1
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    return {'status': 'success', 'message':
        f'✅ Deleted {deleted_count} entries.'}


def delete_json_entry(params):
    filename = os.path.basename(params['filename'])
    entry_key = params['entry_key']
    filepath = os.path.join(os.getcwd(), 'data', filename)
    if not os.path.exists(filepath):
        return {'status': 'error', 'message': '❌ File not found.'}
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if entry_key in data.get('entries', {}):
        del data['entries'][entry_key]
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        return {'status': 'success', 'message':
            f"✅ Entry '{entry_key}' deleted."}
    return {'status': 'error', 'message': '❌ Entry not found.'}


def batch_update_json_entries(params):
    filename = os.path.basename(params['filename'])
    updates = params['updates']
    filepath = os.path.join(os.getcwd(), 'data', filename)
    if not os.path.exists(filepath):
        return {'status': 'error', 'message': '❌ File not found.'}
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    updated_count = 0
    for entry_key, new_data in updates.items():
        if entry_key in data.get('entries', {}):
            data['entries'][entry_key].update(new_data)
            updated_count += 1
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    return {'status': 'success', 'message':
        f'✅ Updated {updated_count} entries.'}


def update_json_entry(params):
    filename = os.path.basename(params['filename'])
    entry_key = params['entry_key']
    new_data = params['new_data']
    filepath = os.path.join(os.getcwd(), 'data', filename)
    if not os.path.exists(filepath):
        return {'status': 'error', 'message': '❌ File not found.'}
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if entry_key in data.get('entries', {}):
        data['entries'][entry_key].update(new_data)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        return {'status': 'success', 'message':
            f"✅ Entry '{entry_key}' updated."}
    return {'status': 'error', 'message': '❌ Entry not found.'}


def read_json_entry(params):
    filename = os.path.basename(params['filename'])
    entry_key = params['entry_key']
    filepath = os.path.join(os.getcwd(), 'data', filename)
    if not os.path.exists(filepath):
        return {'status': 'error', 'message': '❌ File not found.'}
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    entry = data.get('entries', {}).get(entry_key)
    if entry is None:
        return {'status': 'error', 'message':
            f"❌ Entry '{entry_key}' not found."}
    return {'status': 'success', 'entry': entry}


def add_json_entry(params):
    filename = os.path.basename(params['filename'])
    entry_key = params['entry_key']
    entry_data = params['entry_data']
    filepath = os.path.join(os.getcwd(), 'data', filename)
    if not os.path.exists(filepath):
        return {'status': 'error', 'message': '❌ File not found.'}
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    data.setdefault('entries', {})
    data['entries'][str(entry_key)] = entry_data
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    return {'status': 'success', 'message': f"✅ Entry '{entry_key}' added."}


def read_json_file(params):
    filename = os.path.basename(params['filename'])
    filepath = os.path.join(os.getcwd(), 'data', filename)
    if not os.path.exists(filepath):
        return {'status': 'error', 'message': '❌ File not found.'}
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return {'status': 'success', 'entries': data.get('entries', {})}


def create_json_file(params):
    filename = os.path.basename(params['filename'])
    filepath = os.path.join(os.getcwd(), 'data', filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump({'entries': {}}, f, indent=4)
    return {'status': 'success', 'message': '✅ File initialized.'}


def batch_add_json_entries(params):
    """Add multiple entries with individual data for each entry"""
    filename = os.path.basename(params['filename'])
    entries = params['entries']  # List of entry objects with entry_key + fields
    filepath = os.path.join(os.getcwd(), 'data', filename)

    if not os.path.exists(filepath):
        return {"status": "error", "message": "❌ File not found."}

    if not isinstance(entries, list):
        return {"status": "error", "message": "❌ 'entries' must be a list of entry objects."}

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    data.setdefault('entries', {})
    added_count = 0
    skipped_count = 0

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        entry_key = entry.get('entry_key')
        if not entry_key:
            continue

        # Skip if entry already exists
        if entry_key in data['entries']:
            skipped_count += 1
            continue

        # Extract entry data (everything except entry_key)
        entry_data = {k: v for k, v in entry.items() if k != 'entry_key'}

        if entry_data:  # Only add if there's actual data
            data['entries'][str(entry_key)] = entry_data
            added_count += 1

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

    message = f"✅ Added {added_count} entries"
    if skipped_count > 0:
        message += f", skipped {skipped_count} existing entries"

    return {"status": "success", "message": message}


def main():
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    if args.action == 'add_field_to_json_entry':
        result = add_field_to_json_entry(params)
    elif args.action == 'add_json_entry':
        result = add_json_entry(params)
    elif args.action == 'batch_add_field_to_json_entries':
        result = batch_add_field_to_json_entries(params)
    elif args.action == 'batch_delete_json_entries':
        result = batch_delete_json_entries(params)
    elif args.action == 'batch_update_json_entries':
        result = batch_update_json_entries(params)
    elif args.action == 'create_json_file':
        result = create_json_file(params)
    elif args.action == 'create_json_file_from_template':
        result = create_json_file_from_template(params)
    elif args.action == 'delete_json_entry':
        result = delete_json_entry(params)
    elif args.action == 'insert_json_entry_from_template':
        result = insert_json_entry_from_template(params)
    elif args.action == 'list_json_entries':
        result = list_json_entries(params)
    elif args.action == 'read_json_entry':
        result = read_json_entry(params)
    elif args.action == 'read_json_file':
        result = read_json_file(params)
    elif args.action == 'search_json_entries':
        result = search_json_entries(params)
    elif args.action == 'update_json_entry':
        result = update_json_entry(params)
    elif args.action == 'batch_add_json_entries':
        result = batch_add_json_entries(params)
    else:
        result = {'status': 'error', 'message': f'Unknown action {args.action}'}

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()