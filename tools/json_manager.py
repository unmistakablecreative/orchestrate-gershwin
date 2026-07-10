import sys
import json
import os
import argparse
import stat
import fcntl
try:
    from response_helper import get_success_message, get_error_message
except ImportError:
    from tools.response_helper import get_success_message, get_error_message
# Full docstrings and function descriptions: data/orchestrate_docstrings.json

PROTECTED_FILES = [
    'outline_queue.json',
    'claude_task_queue.json',
    'claude_task_results.json',
    'automation_state.json',
    'execution_log.json',
    'youtube_published.json',
    'youtube_publish_queue.json',
    'working_memory.json'
]

def safe_write_json(filepath, data):
    filename = os.path.basename(filepath)
    is_protected = filename in PROTECTED_FILES
    was_readonly = False

    lock_path = filepath + '.lock'

    try:
        lock_file = open(lock_path, 'w')
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

        try:
            if is_protected and os.path.exists(filepath):
                file_stat = os.stat(filepath)
                if not (file_stat.st_mode & stat.S_IWUSR):
                    was_readonly = True
                    os.chmod(filepath, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)

            if is_protected and was_readonly:
                os.chmod(filepath, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()

    except PermissionError as e:
        raise PermissionError(
            f"\n\n{'='*60}\n"
            f"❌ FUCK NO: You tried to directly edit protected JSON file: {filename}\n\n"
            f"This file is READ-ONLY to prevent corruption and race conditions.\n\n"
            f"YOU'RE CAUSING THE SAME PROBLEMS OVER AND OVER.\n\n"
            f"USE json_manager tool via execution_hub:\n"
            f"  python3 execution_hub.py execute_task --params '{{\n"
            f"    \"tool_name\": \"json_manager\",\n"
            f"    \"action\": \"add_json_entry\",  # or update_json_entry\n"
            f"    \"params\": {{\"filename\": \"{filename}\", \"entry_key\": \"...\", ...}}\n"
            f"  }}'\n\n"
            f"STOP using Write/Edit tools on JSON files.\n"
            f"That's what's breaking outline_queue.json with duplicate entries.\n"
            f"{'='*60}\n\n"
            f"Original error: {e}"
        )

def flatten_params(params):
    flattened = {}

    UNWRAP_KEYS = {'entry_data', 'data', 'fields', 'content', 'updates', 'new_data'}

    for key, value in params.items():
        if isinstance(value, dict) and key in UNWRAP_KEYS:
            flattened.update(value)
        elif isinstance(value, dict):
            for nested_key, nested_value in value.items():
                flat_key = f"{key}_{nested_key}" if key != 'entry_data' else nested_key
                flattened[flat_key] = nested_value
        else:
            flattened[key] = value

    return flattened

def validate_flat_params(params):
    for key, value in params.items():
        if isinstance(value, dict):
            raise ValueError(f"Parameter '{key}' contains nested data - all params must be flat")
        if isinstance(value, list):
            continue
    return True

def get_entries(data):
    if isinstance(data, dict) and 'entries' in data and isinstance(data['entries'], dict):
        return data['entries'], True
    return data, False

def set_entries(data, entries, was_wrapped):
    if was_wrapped:
        data['entries'] = entries
        return data
    return entries

def parse_filter_key(key):
    OPERATORS = ['__gte', '__gt', '__lte', '__lt', '__contains', '__startswith', '__endswith', '__in']
    for op in OPERATORS:
        if key.endswith(op):
            return key[:-len(op)], op[2:]
    return key, None

def compare_value(field_val, filter_val, operator):
    if operator is None:
        return str(field_val).lower() == str(filter_val).lower()

    if operator == 'gte':
        try:
            return float(field_val) >= float(filter_val)
        except (ValueError, TypeError):
            return str(field_val) >= str(filter_val)

    if operator == 'gt':
        try:
            return float(field_val) > float(filter_val)
        except (ValueError, TypeError):
            return str(field_val) > str(filter_val)

    if operator == 'lte':
        try:
            return float(field_val) <= float(filter_val)
        except (ValueError, TypeError):
            return str(field_val) <= str(filter_val)

    if operator == 'lt':
        try:
            return float(field_val) < float(filter_val)
        except (ValueError, TypeError):
            return str(field_val) < str(filter_val)

    if operator == 'contains':
        return str(filter_val).lower() in str(field_val).lower()

    if operator == 'startswith':
        return str(field_val).lower().startswith(str(filter_val).lower())

    if operator == 'endswith':
        return str(field_val).lower().endswith(str(filter_val).lower())

    if operator == 'in':
        if isinstance(filter_val, str):
            allowed = [v.strip().lower() for v in filter_val.split(',')]
        else:
            allowed = [str(v).lower() for v in filter_val]
        return str(field_val).lower() in allowed

    return False

def render_as_table(results, columns=None):
    if not results:
        return "No results found."

    if columns is None:
        sample = list(results.values())[:3] if isinstance(results, dict) else results[:3]
        all_keys = set().union(*[entry.keys() for entry in sample if isinstance(entry, dict)])
        if isinstance(results, dict):
            columns = ['entry_key'] + list(all_keys)
        else:
            columns = list(all_keys)

    header = "| " + " | ".join(columns) + " |"
    separator = "|" + "|".join(["---" for _ in columns]) + "|"

    rows = []
    if isinstance(results, dict):
        for entry_key, entry_value in results.items():
            if isinstance(entry_value, dict):
                row_data = {'entry_key': entry_key}
                row_data.update(entry_value)
                row = "| " + " | ".join([str(row_data.get(col, "")) for col in columns]) + " |"
                rows.append(row)
    else:
        for entry in results:
            if isinstance(entry, dict):
                row = "| " + " | ".join([str(entry.get(col, "")) for col in columns]) + " |"
                rows.append(row)

    return "\n".join([header, separator] + rows)

def render_as_markdown(results):
    if not results:
        return "No results found."

    output = []
    entries = results.values() if isinstance(results, dict) else results

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        title = entry.get("title", "Untitled")
        status = entry.get("status", "")
        priority = entry.get("priority", "")

        item = f"**{title}**"
        if status:
            item += f" `{status}`"
        if priority:
            item += f" ⚡{priority}"

        output.append(f"- {item}")

        if desc := entry.get("description"):
            output.append(f"  {desc[:100]}...")

    return "\n".join(output)

def render_as_summary(results):
    if not results:
        return "No results found."

    entries = list(results.values() if isinstance(results, dict) else results)
    total = len(entries)

    status_counts = {}
    for entry in entries:
        if isinstance(entry, dict):
            status = entry.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1

    type_counts = {}
    for entry in entries:
        if isinstance(entry, dict):
            entry_type = entry.get("type", "unknown")
            type_counts[entry_type] = type_counts.get(entry_type, 0) + 1

    summary = [f"**Total:** {total} entries\n"]

    if status_counts:
        summary.append("**By Status:**")
        for status, count in sorted(status_counts.items()):
            summary.append(f"- {status}: {count}")

    if type_counts:
        summary.append("\n**By Type:**")
        for type_name, count in sorted(type_counts.items()):
            summary.append(f"- {type_name}: {count}")

    return "\n".join(summary)

def insert_json_entry_from_template(params):
    params = flatten_params(params)
    validate_flat_params(params)

    filename = os.path.basename(params['filename'])
    entry_key = params['entry_key']
    template_name = params['template_name']
    data_dir = os.path.join(os.getcwd(), 'data')
    template_path = os.path.join(data_dir, template_name)
    filepath = os.path.join(data_dir, filename)

    if not os.path.exists(template_path):
        return {'status': 'error', 'message': get_error_message('json_manager', 'read_json_file', f"Template '{template_name}' not found")}
    if not os.path.exists(filepath):
        return {'status': 'error', 'message': get_error_message('json_manager', 'read_json_file', 'File not found')}

    with open(template_path, 'r', encoding='utf-8') as f:
        template_data = json.load(f)
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    entries, was_wrapped = get_entries(data)
    entries[str(entry_key)] = template_data
    data = set_entries(data, entries, was_wrapped)

    safe_write_json(filepath, data)

    return {'status': 'success', 'message': get_success_message('json_manager', 'add_json_entry', {'filename': filename})}

def create_json_file_from_template(params):
    params = flatten_params(params)
    validate_flat_params(params)

    template_name = params['template_name']
    new_filename = os.path.basename(params['new_filename'])
    data_dir = os.path.join(os.getcwd(), 'data')
    template_path = os.path.join(data_dir, template_name)
    new_file_path = os.path.join(data_dir, new_filename)

    if not os.path.exists(template_path):
        return {'status': 'error', 'message': get_error_message('json_manager', 'create_json_file', f"Template '{template_name}' not found")}

    with open(template_path, 'r', encoding='utf-8') as f:
        template_data = json.load(f)

    with open(new_file_path, 'w', encoding='utf-8') as f:
        json.dump(template_data, f, indent=4)

    return {'status': 'success', 'message': get_success_message('json_manager', 'create_json_file', {'filename': new_filename})}

def batch_add_field_to_json_entries(params):
    params = flatten_params(params)
    validate_flat_params(params)

    filename = os.path.basename(params['filename'])
    entry_keys = params['entry_keys']
    field_name = params['field_name']
    field_value = params['field_value']
    filepath = os.path.join(os.getcwd(), 'data', filename)

    if not os.path.exists(filepath):
        return {'status': 'error', 'message': get_error_message('json_manager', 'add_field_to_json_entry', 'File not found')}

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    entries, was_wrapped = get_entries(data)
    updated = 0
    for key in entry_keys:
        if key in entries:
            entries[key][field_name] = field_value
            updated += 1

    data = set_entries(data, entries, was_wrapped)
    safe_write_json(filepath, data)

    return {'status': 'success', 'message': get_success_message('json_manager', 'add_field_to_json_entry', {})}

def add_field_to_json_entry(params):
    params = flatten_params(params)
    validate_flat_params(params)

    filename = os.path.basename(params['filename'])
    entry_key = params['entry_key']
    field_name = params['field_name']
    field_value = params['field_value']
    filepath = os.path.join(os.getcwd(), 'data', filename)

    if not os.path.exists(filepath):
        return {'status': 'error', 'message': get_error_message('json_manager', 'add_field_to_json_entry', 'File not found')}

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    entries, was_wrapped = get_entries(data)
    if entry_key in entries:
        entries[entry_key][field_name] = field_value
        data = set_entries(data, entries, was_wrapped)
        safe_write_json(filepath, data)
        return {'status': 'success', 'message': get_success_message('json_manager', 'add_field_to_json_entry', {})}

    return {'status': 'error', 'message': get_error_message('json_manager', 'add_field_to_json_entry', 'Entry not found')}

def search_json_entries(params):
    params = flatten_params(params)
    validate_flat_params(params)

    filename = os.path.basename(params['filename'])
    case_insensitive = params.get('case_insensitive', True)
    max_results = params.get('max_results', 50)
    offset = params.get('offset', 0)
    fields_to_return = params.get('fields_to_return', [])
    if isinstance(fields_to_return, str):
        fields_to_return = [f.strip() for f in fields_to_return.split(',')]
    format_type = params.get('format', 'json')

    search_value = params.get('search_value', '').lower()
    control_keys = {'filename', 'search_value', 'case_insensitive', 'fields_to_return', 'max_results', 'format', 'offset'}
    field_filters = {k: v for k, v in params.items() if k not in control_keys}

    filepath = os.path.join(os.getcwd(), 'data', filename)
    if not os.path.exists(filepath):
        return {'status': 'error', 'message': get_error_message('json_manager', 'search_json_entries', f'File not found: {filename}')}

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    entries, _ = get_entries(data)
    all_matches = {}

    for entry_key, entry_value in entries.items():
        if not isinstance(entry_value, dict):
            continue

        match = True

        for filter_key, filter_val in field_filters.items():
            field_name, operator = parse_filter_key(filter_key)
            field_val = entry_value.get(field_name)

            if field_val is None:
                match = False
                break

            if not compare_value(field_val, filter_val, operator):
                match = False
                break

        if not field_filters and search_value:
            blob = json.dumps(entry_value).lower()
            if search_value not in blob:
                match = False

        if match:
            all_matches[entry_key] = entry_value

    match_items = list(all_matches.items())
    total_matches = len(match_items)
    paginated_items = match_items[offset:offset + max_results]
    results = {}

    for entry_key, entry_value in paginated_items:
        if fields_to_return:
            filtered = {k: entry_value.get(k) for k in fields_to_return}
            results[entry_key] = filtered
        else:
            results[entry_key] = entry_value

    if format_type == "table":
        output = render_as_table(results)
        return {'status': 'success', 'output': output, 'format': 'table', 'match_count': len(results), 'total_matches': total_matches}
    elif format_type == "markdown":
        output = render_as_markdown(results)
        return {'status': 'success', 'output': output, 'format': 'markdown', 'match_count': len(results), 'total_matches': total_matches}
    elif format_type == "summary":
        output = render_as_summary(results)
        return {'status': 'success', 'output': output, 'format': 'summary', 'match_count': len(results), 'total_matches': total_matches}
    else:
        return {'status': 'success', 'results': results, 'match_count': len(results), 'total_matches': total_matches, 'offset': offset}

def list_json_entries(params):
    params = flatten_params(params)
    validate_flat_params(params)

    filename = os.path.basename(params['filename'])
    max_results = params.get('max_results', 50)
    offset = params.get('offset', 0)
    filepath = os.path.join(os.getcwd(), 'data', filename)

    if not os.path.exists(filepath):
        return {'status': 'error', 'message': get_error_message('json_manager', 'list_json_entries', 'File not found')}

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    entries, _ = get_entries(data)
    total_entries = len(entries)

    entry_items = list(entries.items())
    paginated_items = entry_items[offset:offset + max_results]
    paginated_entries = dict(paginated_items)

    if total_entries > offset + max_results:
        return {
            'status': 'success',
            'entries': paginated_entries,
            'entry_count': len(paginated_entries),
            'total_entries': total_entries,
            'offset': offset,
            'has_more': True,
            'next_offset': offset + max_results
        }

    return {'status': 'success', 'entries': paginated_entries, 'entry_count': len(paginated_entries), 'total_entries': total_entries, 'offset': offset, 'has_more': False}

def _cleanup_automation_state(filepath, entry_keys):
    automation_state_path = os.path.join(os.getcwd(), 'data', 'automation_state.json')
    if not os.path.exists(automation_state_path):
        return
    
    try:
        with open(automation_state_path, 'r', encoding='utf-8') as f:
            state = json.load(f)
        
        if filepath not in state:
            return
        
        entry_statuses = state[filepath].get('entry_statuses', {})
        modified = False
        for key in entry_keys:
            if key in entry_statuses:
                del entry_statuses[key]
                modified = True
        
        if modified:
            safe_write_json(automation_state_path, state)
    except (json.JSONDecodeError, IOError):
        pass

def batch_delete_json_entries(params):
    params = flatten_params(params)
    validate_flat_params(params)

    filename = os.path.basename(params['filename'])
    entry_keys = params['entry_keys']
    filepath = os.path.join(os.getcwd(), 'data', filename)

    if not os.path.exists(filepath):
        return {'status': 'error', 'message': get_error_message('json_manager', 'batch_delete_json_entries', 'File not found')}

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    entries, was_wrapped = get_entries(data)
    deleted_count = 0
    for key in entry_keys:
        if key in entries:
            del entries[key]
            deleted_count += 1

    data = set_entries(data, entries, was_wrapped)
    safe_write_json(filepath, data)

    _cleanup_automation_state(filepath, entry_keys)

    return {'status': 'success', 'message': get_success_message('json_manager', 'batch_delete_json_entries', {'count': deleted_count})}

def delete_json_entry(params):
    params = flatten_params(params)
    validate_flat_params(params)

    filename = os.path.basename(params['filename'])
    entry_key = params['entry_key']
    filepath = os.path.join(os.getcwd(), 'data', filename)

    if not os.path.exists(filepath):
        return {'status': 'error', 'message': get_error_message('json_manager', 'delete_json_entry', 'File not found')}

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    entries, was_wrapped = get_entries(data)
    if entry_key in entries:
        del entries[entry_key]
        data = set_entries(data, entries, was_wrapped)
        safe_write_json(filepath, data)
        _cleanup_automation_state(filepath, [entry_key])
        return {'status': 'success', 'message': get_success_message('json_manager', 'delete_json_entry', {'filename': filename})}

    return {'status': 'error', 'message': get_error_message('json_manager', 'delete_json_entry', 'Entry not found')}

def batch_update_json_entries(params):
    params = flatten_params(params)

    filename = os.path.basename(params['filename'])
    updates = params['updates']
    filepath = os.path.join(os.getcwd(), 'data', filename)

    if not os.path.exists(filepath):
        return {'status': 'error', 'message': get_error_message('json_manager', 'batch_update_json_entries', 'File not found')}

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    entries, was_wrapped = get_entries(data)
    updated_count = 0
    for update in updates:
        entry_key = update.get('entry_key')
        if not entry_key:
            continue

        if entry_key in entries:
            update_fields = {k: v for k, v in update.items() if k != 'entry_key'}
            entries[entry_key].update(update_fields)
            updated_count += 1

    data = set_entries(data, entries, was_wrapped)
    safe_write_json(filepath, data)

    return {'status': 'success', 'message': get_success_message('json_manager', 'batch_update_json_entries', {'count': updated_count})}

def update_json_entry(params):
    params = flatten_params(params)

    filename = os.path.basename(params['filename'])
    entry_key = params['entry_key']
    filepath = os.path.join(os.getcwd(), 'data', filename)

    if not os.path.exists(filepath):
        return {'status': 'error', 'message': get_error_message('json_manager', 'update_json_entry', 'File not found')}

    update_fields = {k: v for k, v in params.items() if k not in ['filename', 'entry_key']}

    if not update_fields:
        return {'status': 'error', 'message': get_error_message('json_manager', 'update_json_entry', 'No update fields provided')}

    lock_path = filepath + '.lock'
    lock_file = open(lock_path, 'w')
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        entries, was_wrapped = get_entries(data)

        if entry_key not in entries:
            return {'status': 'error', 'message': get_error_message('json_manager', 'update_json_entry', 'Entry not found')}

        if isinstance(entries[entry_key], str):
            if 'value' in update_fields:
                entries[entry_key] = update_fields['value']
            else:
                return {'status': 'error', 'message': get_error_message('json_manager', 'update_json_entry', f"Entry '{entry_key}' is a string. Use 'value' param to replace it")}
        else:
            entries[entry_key].update(update_fields)
        data = set_entries(data, entries, was_wrapped)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)

    finally:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()

    return {'status': 'success', 'message': get_success_message('json_manager', 'update_json_entry', {'filename': filename})}

def read_json_entry(params):
    params = flatten_params(params)
    validate_flat_params(params)

    filename = os.path.basename(params['filename'])
    entry_key = params['entry_key']
    filepath = os.path.join(os.getcwd(), 'data', filename)

    if not os.path.exists(filepath):
        return {'status': 'error', 'message': get_error_message('json_manager', 'read_json_entry', 'File not found')}

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    entries, _ = get_entries(data)
    entry = entries.get(entry_key)
    if entry is None:
        return {'status': 'error', 'message': get_error_message('json_manager', 'read_json_entry', f"Entry '{entry_key}' not found")}

    return {'status': 'success', 'message': get_success_message('json_manager', 'read_json_entry', {}), 'entry': entry}

def add_json_entry(params):
    params = flatten_params(params)

    filename = os.path.basename(params['filename'])
    entry_key = params['entry_key']
    filepath = os.path.join(os.getcwd(), 'data', filename)

    if not os.path.exists(filepath):
        return {'status': 'error', 'message': get_error_message('json_manager', 'add_json_entry', 'File not found')}

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    entries, was_wrapped = get_entries(data)
    entry_data = {k: v for k, v in params.items() if k not in ['filename', 'entry_key']}

    if not entry_data:
        return {'status': 'error', 'message': get_error_message('json_manager', 'add_json_entry', 'No entry data provided')}

    entries[str(entry_key)] = entry_data
    data = set_entries(data, entries, was_wrapped)
    safe_write_json(filepath, data)

    return {'status': 'success', 'message': get_success_message('json_manager', 'add_json_entry', {'filename': filename})}

def upsert_json_entry(params):
    params = flatten_params(params)

    filename = os.path.basename(params['filename'])
    entry_key = str(params['entry_key'])
    filepath = os.path.join(os.getcwd(), 'data', filename)

    if not os.path.exists(filepath):
        return {'status': 'error', 'message': get_error_message('json_manager', 'upsert_json_entry', 'File not found')}

    entry_data = {k: v for k, v in params.items() if k not in ['filename', 'entry_key']}

    if not entry_data:
        return {'status': 'error', 'message': get_error_message('json_manager', 'upsert_json_entry', 'No entry data provided')}

    lock_path = filepath + '.lock'
    lock_file = open(lock_path, 'w')
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        entries, was_wrapped = get_entries(data)

        if entry_key in entries:
            entries[entry_key].update(entry_data)
            action = 'updated'
        else:
            entries[entry_key] = entry_data
            action = 'created'

        data = set_entries(data, entries, was_wrapped)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)

    finally:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()

    return {'status': 'success', 'message': get_success_message('json_manager', 'upsert_json_entry', {'filename': filename}), 'action': action}

def read_json_file(params):
    params = flatten_params(params)
    validate_flat_params(params)

    filename = os.path.basename(params['filename'])
    filepath = os.path.join(os.getcwd(), 'data', filename)

    if not os.path.exists(filepath):
        return {'status': 'error', 'message': get_error_message('json_manager', 'read_json_file', 'File not found')}

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    entries, _ = get_entries(data)
    return {'status': 'success', 'message': get_success_message('json_manager', 'read_json_file', {'count': len(entries)}), 'entries': entries}

def create_json_file(params):
    params = flatten_params(params)
    validate_flat_params(params)

    filename = os.path.basename(params['filename'])
    filepath = os.path.join(os.getcwd(), 'data', filename)

    safe_write_json(filepath, {'entries': {}})

    return {'status': 'success', 'message': get_success_message('json_manager', 'create_json_file', {'filename': filename})}

def log_thread_event(params):
    import time
    params = flatten_params(params)

    filename = "thread_log.json"
    key = params.get("entry_key")
    context_goal = params.get("context_goal")
    recovery_signals = params.get("recovery_signals")
    next_steps = params.get("next_steps")
    status = params.get("status")

    if not all([key, context_goal, recovery_signals, next_steps, status]):
        return {"status": "error", "message": "Missing required fields: entry_key, context_goal, recovery_signals, next_steps, status"}

    if not isinstance(recovery_signals, list) or not isinstance(next_steps, list):
        return {"status": "error", "message": "recovery_signals and next_steps must be lists."}

    return add_json_entry({
        "filename": filename,
        "entry_key": key,
        "context_goal": context_goal,
        "recovery_signals": recovery_signals,
        "next_steps": next_steps,
        "status": status,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "author": "Jarvis 3.0"
    })

def batch_add_json_entries(params):
    params = flatten_params(params)

    filename = os.path.basename(params['filename'])
    entries_list = params['entries']
    filepath = os.path.join(os.getcwd(), 'data', filename)

    if not os.path.exists(filepath):
        return {"status": "error", "message": get_error_message('json_manager', 'batch_add_json_entries', 'File not found')}

    if not isinstance(entries_list, list):
        return {"status": "error", "message": get_error_message('json_manager', 'batch_add_json_entries', "'entries' must be a list of entry objects")}

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    entries, was_wrapped = get_entries(data)
    added_count = 0
    skipped_count = 0

    for entry in entries_list:
        if not isinstance(entry, dict):
            continue

        entry_key = entry.get('entry_key')
        if not entry_key:
            continue

        if entry_key in entries:
            skipped_count += 1
            continue

        entry_data = {k: v for k, v in entry.items() if k != 'entry_key'}

        if entry_data:
            entries[str(entry_key)] = entry_data
            added_count += 1

    data = set_entries(data, entries, was_wrapped)
    safe_write_json(filepath, data)

    return {"status": "success", "message": get_success_message('json_manager', 'batch_add_json_entries', {'count': added_count, 'filename': filename})}

def log_task_entry(params):
    params = flatten_params(params)

    filename = "orchestrate_brain.json"
    entry_key = str(params.get("entry_key"))

    required_fields = ["title", "description", "related_area"]
    missing = [field for field in required_fields if field not in params]

    if not entry_key:
        return {"status": "error", "message": get_error_message('json_manager', 'add_json_entry', 'Missing entry_key')}
    if missing:
        return {"status": "error", "message": get_error_message('json_manager', 'add_json_entry', f"Missing required fields: {', '.join(missing)}")}

    entry = {
        "type": "task",
        "title": params["title"],
        "description": params["description"],
        "priority": params.get("priority", "TBD"),
        "related_area": params["related_area"],
        "status": params.get("status", "todo"),
        "due": params.get("due", "TBD"),
        "estimated_time_min": params.get("estimated_time_min", 30)
    }

    filepath = os.path.join(os.getcwd(), 'data', filename)
    try:
        with open(filepath, "r", encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {"entries": {}}

    if "entries" not in data:
        data["entries"] = {}

    data["entries"][entry_key] = entry

    with open(filepath, "w", encoding='utf-8') as f:
        json.dump(data, f, indent=2)

    return {"status": "success", "message": get_success_message('json_manager', 'add_json_entry', {'filename': filename})}

def log_resource_entry(params):
    params = flatten_params(params)

    filename = "orchestrate_brain.json"
    entry_key = str(params.get("entry_key"))

    required_fields = ["title", "description"]
    missing = [field for field in required_fields if field not in params]

    if not entry_key:
        return {"status": "error", "message": get_error_message('json_manager', 'add_json_entry', 'Missing entry_key')}
    if missing:
        return {"status": "error", "message": get_error_message('json_manager', 'add_json_entry', f"Missing required fields: {', '.join(missing)}")}

    entry = {
        "type": "resource",
        "title": params["title"],
        "description": params["description"]
    }

    filepath = os.path.join(os.getcwd(), 'data', filename)
    try:
        with open(filepath, "r", encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {"entries": {}}

    data.setdefault("entries", {})
    data["entries"][entry_key] = entry

    with open(filepath, "w", encoding='utf-8') as f:
        json.dump(data, f, indent=2)

    return {"status": "success", "message": get_success_message('json_manager', 'add_json_entry', {'filename': filename})}

def log_project_entry(params):
    params = flatten_params(params)

    filename = "orchestrate_brain.json"
    entry_key = str(params.get("entry_key"))

    required_fields = ["title", "description"]
    missing = [field for field in required_fields if field not in params]

    if not entry_key:
        return {"status": "error", "message": get_error_message('json_manager', 'add_json_entry', 'Missing entry_key')}
    if missing:
        return {"status": "error", "message": get_error_message('json_manager', 'add_json_entry', f"Missing required fields: {', '.join(missing)}")}

    entry = {
        "type": "project",
        "title": params["title"],
        "description": params["description"],
        "status": params.get("status", "TBD")
    }

    filepath = os.path.join(os.getcwd(), 'data', filename)
    try:
        with open(filepath, "r", encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {"entries": {}}

    data.setdefault("entries", {})
    data["entries"][entry_key] = entry

    with open(filepath, "w", encoding='utf-8') as f:
        json.dump(data, f, indent=2)

    return {"status": "success", "message": get_success_message('json_manager', 'add_json_entry', {'filename': filename})}

def add_intent_route_entry(params):
    params = flatten_params(params)

    intent = params.get('intent')
    tool = params.get('tool')
    action = params.get('action')
    description = params.get('description')

    if not all([intent, tool, action, description]):
        return {'status': 'error', 'message': get_error_message('json_manager', 'add_json_entry', 'Missing required fields: intent, tool, action, description')}

    filename = 'intent_routes.json'
    filepath = os.path.join(os.getcwd(), 'data', filename)

    if not os.path.exists(filepath):
        data = {'entries': {}}
    else:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

    entries, was_wrapped = get_entries(data)

    entry_key = intent.lower().replace(' ', '_').replace('{', '').replace('}', '')

    if entry_key in entries:
        return {'status': 'error', 'message': get_error_message('json_manager', 'add_json_entry', f'Entry for intent "{intent}" already exists')}

    entry = {
        'icon': params.get('icon', '⚙️'),
        'intent': intent,
        'description': description,
        'tool_name': tool,
        'action': action
    }

    if 'params' in params:
        entry['params'] = params['params']

    entries[entry_key] = entry
    data = set_entries(data, entries, was_wrapped)
    safe_write_json(filepath, data)

    return {
        'status': 'success',
        'message': get_success_message('json_manager', 'add_json_entry', {'filename': filename}),
        'entry_key': entry_key
    }

def sort_json_entries(params):
    params = flatten_params(params)
    validate_flat_params(params)

    filename = os.path.basename(params['filename'])
    sort_key = params['sort_key']
    reverse = params.get('reverse', False)

    filepath = os.path.join(os.getcwd(), 'data', filename)

    if not os.path.exists(filepath):
        return {'status': 'error', 'message': get_error_message('json_manager', 'sort_json_entries', f'File "{filename}" not found')}

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    entries, was_wrapped = get_entries(data)

    if not entries:
        return {'status': 'error', 'message': get_error_message('json_manager', 'sort_json_entries', 'No entries to sort')}

    try:
        sorted_entries = dict(sorted(
            entries.items(),
            key=lambda item: item[1].get(sort_key, '') if isinstance(item[1], dict) else '',
            reverse=reverse
        ))
    except Exception as e:
        return {'status': 'error', 'message': get_error_message('json_manager', 'sort_json_entries', f'Failed to sort by "{sort_key}": {str(e)}')}

    data = set_entries(data, sorted_entries, was_wrapped)
    safe_write_json(filepath, data)

    return {
        'status': 'success',
        'message': get_success_message('json_manager', 'sort_json_entries', {'count': len(sorted_entries), 'field': sort_key}),
        'entry_count': len(sorted_entries)
    }

def log_content_entry(params):
    import time
    import uuid

    params = flatten_params(params)

    title = params.get('title')
    description = params.get('description')

    if not all([title, description]):
        return {'status': 'error', 'message': get_error_message('json_manager', 'add_json_entry', 'Missing required fields: title, description')}

    filename = 'orchestrate_brain.json'
    filepath = os.path.join(os.getcwd(), 'data', filename)

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {'entries': {}}

    if 'entries' not in data:
        data['entries'] = {}

    entry_key = f"content_{int(time.time())}_{str(uuid.uuid4())[:8]}"

    entry = {
        'type': 'content',
        'title': title,
        'description': description,
        'status': params.get('status', 'idea'),
        'related_area': params.get('related_area', 'content'),
        'tags': params.get('tags', []),
        'created_at': time.strftime('%Y-%m-%d')
    }

    if 'doc_id' in params:
        entry['doc_id'] = params['doc_id']

    data['entries'][entry_key] = entry

    safe_write_json(filepath, data)

    return {
        'status': 'success',
        'message': get_success_message('json_manager', 'add_json_entry', {'filename': filename}),
        'entry_key': entry_key
    }

def list_pending_leads(params):
    filename = 'orchestrate_private_beta.json'
    filepath = os.path.join(os.getcwd(), 'data', filename)

    if not os.path.exists(filepath):
        return {'status': 'error', 'message': get_error_message('json_manager', 'list_json_entries', f'File "{filename}" not found')}

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return {'status': 'error', 'message': get_error_message('json_manager', 'read_json_file', f'Invalid JSON: {e}')}

    entries, _ = get_entries(data)

    pending_leads = []
    fields_to_return = ['name', 'email', 'lead_score', 'exec_summary', 'raw_response']

    for key, entry in entries.items():
        if isinstance(entry, dict) and entry.get('status') == 'pending':
            lead = {'entry_key': key}
            for field in fields_to_return:
                if field in entry:
                    lead[field] = entry[field]
            pending_leads.append(lead)

    return {
        'status': 'success',
        'count': len(pending_leads),
        'leads': pending_leads
    }

def main():
    import argparse, json
    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    if args.action == 'add_json_entry':
        result = add_json_entry(params)
    elif args.action == 'read_json_file':
        result = read_json_file(params)
    elif args.action == 'delete_json_entry':
        result = delete_json_entry(params)
    elif args.action == 'create_json_file':
        result = create_json_file(params)
    elif args.action == 'update_json_entry':
        result = update_json_entry(params)
    elif args.action == 'upsert_json_entry':
        result = upsert_json_entry(params)
    elif args.action == 'batch_update_json_entries':
        result = batch_update_json_entries(params)
    elif args.action == 'batch_delete_json_entries':
        result = batch_delete_json_entries(params)
    elif args.action == 'insert_json_entry_from_template':
        result = insert_json_entry_from_template(params)
    elif args.action == 'create_json_file_from_template':
        result = create_json_file_from_template(params)
    elif args.action == 'add_field_to_json_entry':
        result = add_field_to_json_entry(params)
    elif args.action == 'batch_add_field_to_json_entries':
        result = batch_add_field_to_json_entries(params)
    elif args.action == 'read_json_entry':
        result = read_json_entry(params)
    elif args.action == 'search_json_entries':
        result = search_json_entries(params)
    elif args.action == 'list_json_entries':
        result = list_json_entries(params)
    elif args.action == 'log_thread_event':
        result = log_thread_event(params)
    elif args.action == 'batch_add_json_entries':
        result = batch_add_json_entries(params)
    elif args.action == 'log_task_entry':
        result = log_task_entry(params)
    elif args.action == 'log_resource_entry':
        result = log_resource_entry(params)
    elif args.action == 'log_project_entry':
        result = log_project_entry(params)
    elif args.action == 'add_intent_route_entry':
        result = add_intent_route_entry(params)
    elif args.action == 'sort_json_entries':
        result = sort_json_entries(params)
    elif args.action == 'log_content_entry':
        result = log_content_entry(params)
    elif args.action == 'list_pending_leads':
        result = list_pending_leads(params)
    else:
        result = {'status': 'error', 'message': f'Unknown action {args.action}'}

    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
