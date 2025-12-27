import os
import json
import time
import sys
import argparse
import subprocess
import glob
import fcntl
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

RULES_FILE = os.path.join(PROJECT_ROOT, 'data/automation_rules.json')
STATE_FILE = os.path.join(PROJECT_ROOT, 'data/automation_state.json')
EVENT_TYPES_FILE = os.path.join(PROJECT_ROOT, 'data/automation_events.json')
NDJSON_REGISTRY_FILE = os.path.join(PROJECT_ROOT, 'system_settings.ndjson')
EXECUTION_HISTORY_FILE = os.path.join(PROJECT_ROOT, 'data/automation_execution_history.json')


class FileLock:
    """Exclusive file lock - prevents race conditions"""
    def __init__(self, filepath, timeout=30):
        self.filepath = str(filepath)
        self.timeout = timeout
        self.lock_file = None
        self.acquired = False
    
    def __enter__(self):
        self.acquire()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False
    
    def acquire(self):
        lock_path = f"{self.filepath}.lock"
        os.makedirs(os.path.dirname(lock_path) or ".", exist_ok=True)
        
        start_time = time.time()
        while time.time() - start_time < self.timeout:
            try:
                self.lock_file = open(lock_path, 'w')
                fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.acquired = True
                return True
            except BlockingIOError:
                if self.lock_file:
                    self.lock_file.close()
                    self.lock_file = None
                time.sleep(0.1)
                continue
            except Exception:
                if self.lock_file:
                    self.lock_file.close()
                    self.lock_file = None
                raise
        
        raise TimeoutError(f"Could not acquire lock")
    
    def release(self):
        if not self.acquired:
            return
        try:
            if self.lock_file:
                fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
                self.lock_file.close()
                self.lock_file = None
            lock_path = f"{self.filepath}.lock"
            if os.path.exists(lock_path):
                os.remove(lock_path)
            self.acquired = False
        except Exception:
            pass


def read_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, 'r') as f:
        return json.load(f)


def write_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def atomic_update_entry_status(file_path, entry_key, new_status, extra_fields=None):
    """Atomically update a single entry's status with FileLock.

    Also tracks status_changed_at when status actually changes.
    """
    with FileLock(file_path):
        data = read_json(file_path)
        if 'entries' not in data or entry_key not in data['entries']:
            return False
        entry = data['entries'][entry_key]
        old_status = entry.get('status')
        entry['status'] = new_status
        entry['updated_at'] = datetime.now().isoformat()
        # Track when status actually changes
        if old_status != new_status:
            entry['status_changed_at'] = datetime.now().isoformat()
        if extra_fields:
            for k, v in extra_fields.items():
                entry[k] = v
        write_json(file_path, data)
        return True


def log_execution_history(rule_id, trigger_type, entry_id, action_name, result, duration_ms):
    """Append execution record to history log.

    Args:
        rule_id: ID of the rule that fired
        trigger_type: Type of trigger (entry_added, entry_updated, time, interval)
        entry_id: ID of entry processed (or 'n/a' for time/interval triggers)
        action_name: Full action name (tool.action)
        result: 'success', 'failed', 'timeout_failed', or 'error'
        duration_ms: Execution duration in milliseconds
    """
    history_entry = {
        'timestamp': datetime.now().isoformat(),
        'rule_id': rule_id,
        'trigger': trigger_type,
        'entry_id': entry_id,
        'action': action_name,
        'result': result,
        'duration_ms': duration_ms
    }

    with FileLock(EXECUTION_HISTORY_FILE):
        history = []
        if os.path.exists(EXECUTION_HISTORY_FILE):
            try:
                with open(EXECUTION_HISTORY_FILE, 'r') as f:
                    history = json.load(f)
            except (json.JSONDecodeError, IOError):
                history = []

        history.append(history_entry)

        # Auto-rotate: Keep last 30 days
        cutoff = datetime.now() - timedelta(days=30)
        history = [
            h for h in history
            if datetime.fromisoformat(h['timestamp']) > cutoff
        ]

        with open(EXECUTION_HISTORY_FILE, 'w') as f:
            json.dump(history, f, indent=2)


def get_execution_history(params):
    """Get execution history with optional filters.

    Args:
        params: {
            rule_id: Filter by rule ID (optional)
            since: ISO timestamp to filter from (optional)
            status: Filter by result status (optional)
            limit: Max entries to return (default 100)
        }

    Returns:
        List of execution history entries
    """
    rule_id_filter = params.get('rule_id')
    since_filter = params.get('since')
    status_filter = params.get('status')
    limit = params.get('limit', 100)

    history = []
    if os.path.exists(EXECUTION_HISTORY_FILE):
        try:
            with open(EXECUTION_HISTORY_FILE, 'r') as f:
                history = json.load(f)
        except (json.JSONDecodeError, IOError):
            history = []

    # Apply filters
    filtered = []
    for entry in history:
        if rule_id_filter and entry.get('rule_id') != rule_id_filter:
            continue
        if since_filter:
            entry_time = datetime.fromisoformat(entry['timestamp'])
            since_time = datetime.fromisoformat(since_filter)
            if entry_time < since_time:
                continue
        if status_filter and entry.get('result') != status_filter:
            continue
        filtered.append(entry)

    # Sort by timestamp descending (most recent first)
    filtered.sort(key=lambda x: x['timestamp'], reverse=True)

    return {
        'status': 'success',
        'entries': filtered[:limit],
        'total_count': len(filtered),
        'returned_count': min(len(filtered), limit)
    }


def load_tool_registry():
    tool_paths = {}
    if not os.path.exists(NDJSON_REGISTRY_FILE):
        return tool_paths
    try:
        with open(NDJSON_REGISTRY_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    if entry.get('action') == '__tool__':
                        tool_name = entry.get('tool')
                        script_path = entry.get('script_path')
                        if tool_name and script_path:
                            tool_paths[tool_name] = script_path
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        print(f'[REGISTRY ERROR] {e}', flush=True)
    return tool_paths


def resolve_context_values(params, context):
    if isinstance(params, dict):
        resolved_dict = {}
        for k, v in params.items():
            resolved_value = resolve_context_values(v, context)
            if isinstance(resolved_value, str) and resolved_value.startswith('{') and resolved_value.endswith('}') and resolved_value.count('{') == 1:
                placeholder = resolved_value[1:-1]
                if '.' in placeholder:
                    parts = placeholder.split('.')
                    value = context
                    resolved = False
                    try:
                        for part in parts:
                            if isinstance(value, dict):
                                value = value[part]
                            else:
                                break
                        else:
                            resolved = True
                            resolved_dict[k] = value
                    except (KeyError, TypeError):
                        pass
                    if not resolved:
                        continue
                elif placeholder not in context:
                    continue
                else:
                    resolved_dict[k] = resolved_value
            else:
                resolved_dict[k] = resolved_value
        return resolved_dict
    elif isinstance(params, list):
        return [resolve_context_values(item, context) for item in params]
    elif isinstance(params, str):
        import re
        pattern = r'\{([^}]+)\}'
        matches = re.findall(pattern, params)
        resolved = params
        for match in matches:
            if '.' in match:
                parts = match.split('.')
                value = context
                try:
                    for part in parts:
                        # Handle array indexing like participants[1]
                        if '[' in part and ']' in part:
                            key = part[:part.index('[')]
                            idx = int(part[part.index('[')+1:part.index(']')])
                            if isinstance(value, dict):
                                value = value[key][idx]
                            elif isinstance(value, list):
                                value = value[idx]
                            else:
                                raise KeyError
                        elif isinstance(value, dict):
                            value = value[part]
                        elif isinstance(value, list) and part.isdigit():
                            value = value[int(part)]
                        else:
                            raise KeyError
                    resolved = resolved.replace(f"{{{match}}}", str(value))
                except (KeyError, TypeError):
                    pass
            else:
                if match in context:
                    resolved = resolved.replace(f"{{{match}}}", str(context[match]))
        return resolved
    else:
        return params


def run_action(action, context, timeout=None, rule_id=None, trigger_type=None, entry_id=None):
    """Execute an action with optional timeout and execution history logging.

    Args:
        action: Action dict with tool, action, params
        context: Context dict for variable resolution
        timeout: Timeout in seconds (default from action or 30s)
        rule_id: Rule ID for history logging (optional)
        trigger_type: Trigger type for history logging (optional)
        entry_id: Entry ID for history logging (optional)

    Returns:
        dict with status and result, or timeout_failed status
    """
    # Get timeout from action, rule, or default to 30 seconds
    action_timeout = timeout or action.get('timeout', 30)

    try:
        if 'steps' in action:
            return run_workflow_steps(action['steps'], context, timeout=action_timeout, rule_id=rule_id, trigger_type=trigger_type, entry_id=entry_id)
        raw_params = action.get('params', {})
        resolved_params = resolve_context_values(raw_params, context)
        registry = load_tool_registry()
        tool_name = action['tool']
        action_name = f"{tool_name}.{action['action']}"

        if tool_name in registry:
            final_params = resolved_params.copy() if isinstance(resolved_params, dict) else {}
            final_params["bypass_enforcement"] = "automation_engine"
            execution_hub_path = os.path.join(PROJECT_ROOT, 'execution_hub.py')
            cmd = ['python3', execution_hub_path, 'execute_task', '--params', json.dumps({"tool_name": tool_name, "action": action['action'], "params": final_params})]
        else:
            script = os.path.join(PROJECT_ROOT, f"tools/{tool_name}.py")
            cmd = ['python3', script, action['action'], '--params', json.dumps(resolved_params)]

        start_time = time.time()
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=action_timeout)
            duration_ms = int((time.time() - start_time) * 1000)
        except subprocess.TimeoutExpired:
            duration_ms = int((time.time() - start_time) * 1000)
            print(f'[TIMEOUT] Action: {action_name}, Duration: {duration_ms}ms - killed', flush=True)
            # Log timeout to history
            if rule_id:
                log_execution_history(rule_id, trigger_type or 'unknown', entry_id or 'n/a', action_name, 'timeout_failed', duration_ms)
            return {'status': 'timeout_failed', 'message': f'Action timed out after {action_timeout}s', 'duration': duration_ms}

        if result.stdout:
            try:
                response = json.loads(result.stdout)
                status = response.get('status', '')
                if status == 'error':
                    print(f'❌ {action_name}: {response.get("message", "Unknown error")}', flush=True)
                    if rule_id:
                        log_execution_history(rule_id, trigger_type or 'unknown', entry_id or 'n/a', action_name, 'failed', duration_ms)
                elif status == 'success':
                    msg = response.get('message', '')
                    if msg and msg not in ['ok', 'OK', 'Success']:
                        print(f'✅ {action_name}: {msg}', flush=True)
                    if rule_id:
                        log_execution_history(rule_id, trigger_type or 'unknown', entry_id or 'n/a', action_name, 'success', duration_ms)
                else:
                    # No explicit status - assume success
                    if rule_id:
                        log_execution_history(rule_id, trigger_type or 'unknown', entry_id or 'n/a', action_name, 'success', duration_ms)
                return response
            except (json.JSONDecodeError, KeyError):
                if result.stderr:
                    print(f'⚠️  {action_name}: {result.stderr[:200]}', flush=True)
                # Log as success if no explicit error
                if rule_id:
                    log_execution_history(rule_id, trigger_type or 'unknown', entry_id or 'n/a', action_name, 'success', duration_ms)
        else:
            # No output - log as success
            if rule_id:
                log_execution_history(rule_id, trigger_type or 'unknown', entry_id or 'n/a', action_name, 'success', duration_ms)
        return {}
    except subprocess.TimeoutExpired:
        # Catch timeout at outer level too
        print(f'[TIMEOUT] Action timed out after {action_timeout}s - killed', flush=True)
        return {'status': 'timeout_failed', 'message': f'Action timed out after {action_timeout}s'}
    except Exception as e:
        print(f'❌ Action error: {str(e)}', flush=True)
        return {'status': 'error', 'message': str(e)}


def run_workflow_steps(steps, initial_context, timeout=30, rule_id=None, trigger_type=None, entry_id=None):
    """Execute workflow steps with timeout support and execution history logging.

    Args:
        steps: List of step dicts
        initial_context: Context dict for variable resolution
        timeout: Timeout per step in seconds (default 30s)
        rule_id: Rule ID for history logging (optional)
        trigger_type: Trigger type for history logging (optional)
        entry_id: Entry ID for history logging (optional)
    """
    context = initial_context.copy()
    previous_output = {}
    registry = load_tool_registry()
    for i, step in enumerate(steps):
        # Per-step timeout can override workflow timeout
        step_timeout = step.get('timeout', timeout)
        try:
            step_context = context.copy()
            step_context['prev'] = previous_output
            if step.get('type') == 'foreach':
                array_path = step.get('array')
                sub_steps = step.get('steps', [])
                try:
                    array_data = step_context
                    for part in array_path.split('.'):
                        array_data = array_data[part]
                    foreach_results = []
                    for idx, item in enumerate(array_data):
                        item_context = step_context.copy()
                        item_context['item'] = item
                        item_context['index'] = idx
                        for sub_step in sub_steps:
                            resolved_step = resolve_context_values(sub_step, item_context)
                            if resolved_step['tool'] in registry:
                                foreach_params = resolved_step['params'].copy() if isinstance(resolved_step['params'], dict) else {}
                                foreach_params["bypass_enforcement"] = "automation_engine"
                                execution_hub_path = os.path.join(PROJECT_ROOT, 'execution_hub.py')
                                cmd = ['python3', execution_hub_path, 'execute_task', '--params', json.dumps({"tool_name": resolved_step['tool'], "action": resolved_step['action'], "params": foreach_params})]
                            else:
                                script = os.path.join(PROJECT_ROOT, f"tools/{resolved_step['tool']}.py")
                                cmd = ['python3', script, resolved_step['action'], '--params', json.dumps(resolved_step['params'])]
                            try:
                                result = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=step_timeout)
                            except subprocess.TimeoutExpired:
                                print(f'[TIMEOUT] Foreach step {i+1} timed out after {step_timeout}s', flush=True)
                                return {"status": "timeout_failed", "message": f"Foreach step timed out after {step_timeout}s"}
                            try:
                                sub_output = json.loads(result.stdout.strip())
                            except json.JSONDecodeError:
                                sub_output = {"status": "completed", "output": result.stdout.strip()}
                            item_context['prev'] = sub_output
                        foreach_results.append(sub_output)
                    previous_output = {"results": foreach_results, "processed_count": len(foreach_results)}
                    continue
                except subprocess.TimeoutExpired:
                    return {"status": "timeout_failed", "message": f"Foreach step timed out after {step_timeout}s"}
                except Exception as e:
                    return {"status": "error", "message": f"Foreach step failed: {str(e)}"}
            raw_params = step.get('params', {})
            resolved_params = resolve_context_values(raw_params, step_context)
            if step['tool'] in registry:
                final_params = resolved_params.copy() if isinstance(resolved_params, dict) else {}
                final_params["bypass_enforcement"] = "automation_engine"
                execution_hub_path = os.path.join(PROJECT_ROOT, 'execution_hub.py')
                cmd = ['python3', execution_hub_path, 'execute_task', '--params', json.dumps({"tool_name": step['tool'], "action": step['action'], "params": final_params})]
            else:
                script = os.path.join(PROJECT_ROOT, f"tools/{step['tool']}.py")
                cmd = ['python3', script, step['action'], '--params', json.dumps(resolved_params)]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=step_timeout)
            except subprocess.TimeoutExpired:
                print(f'[TIMEOUT] Step {i+1} ({step["tool"]}.{step["action"]}) timed out after {step_timeout}s', flush=True)
                return {"status": "timeout_failed", "message": f"Step {i+1} timed out after {step_timeout}s"}
            try:
                step_output = json.loads(result.stdout.strip())
            except json.JSONDecodeError:
                step_output = {"status": "completed", "output": result.stdout.strip()}
            previous_output = step_output
            if step_output.get("status") == "error":
                return step_output
            if step_output.get("status") == "timeout_failed":
                return step_output
        except subprocess.TimeoutExpired:
            return {"status": "timeout_failed", "message": f"Step {i+1} timed out after {step_timeout}s"}
        except Exception as e:
            return {"status": "error", "message": f"Step {i+1} execution failed: {str(e)}"}
    return previous_output


def process_queue_entry_with_lock(file_path, key, entry, rule):
    """Process a single queue entry with FileLock to prevent duplicates."""

    # ATOMIC: Check status and mark as processing in one operation
    with FileLock(file_path):
        data = read_json(file_path)
        if 'entries' not in data or key not in data['entries']:
            print(f'[SKIP] {key} - entry not found', flush=True)
            return False

        current_status = data['entries'][key].get('status', '')

        # Skip if already processing, processed, failed, or timeout_failed
        if current_status in ('processing', 'processed', 'failed', 'timeout_failed'):
            print(f'[SKIP] {key} - already {current_status}', flush=True)
            return False

        # Mark as processing
        data['entries'][key]['status'] = 'processing'
        data['entries'][key]['updated_at'] = datetime.now().isoformat()
        write_json(file_path, data)

    print(f'[LOCKED] {key} -> processing', flush=True)

    # Build context from entry
    context = {"entry_key": key}
    for k, v in entry.items():
        if k != "entry_key":
            context[k] = v

    # Get timeout from rule (default 30s)
    rule_timeout = rule.get('timeout', 30)

    # Run the action with timeout
    try:
        result = run_action(rule["action"], context, timeout=rule_timeout)

        # Check if workflow timed out
        if isinstance(result, dict) and result.get('status') == 'timeout_failed':
            atomic_update_entry_status(file_path, key, 'timeout_failed', {'error': result.get('message', 'Timeout'), 'duration': result.get('duration')})
            print(f'[TIMEOUT_FAILED] {key}: {result.get("message")}', flush=True)
            return False

        # Check if workflow failed
        if isinstance(result, dict) and result.get('status') == 'error':
            atomic_update_entry_status(file_path, key, 'failed', {'error': result.get('message', 'Unknown error')})
            print(f'[FAILED] {key}: {result.get("message")}', flush=True)
            return False

        # Success - verify status
        with FileLock(file_path):
            current_data = read_json(file_path)
            current_status = current_data.get('entries', {}).get(key, {}).get('status')
            if current_status == 'processing':
                current_data['entries'][key]['status'] = 'processed'
                current_data['entries'][key]['updated_at'] = datetime.now().isoformat()
                write_json(file_path, current_data)
                print(f'[PROCESSED] {key} (auto-marked)', flush=True)
            else:
                print(f'[PROCESSED] {key}', flush=True)

        return True

    except Exception as e:
        atomic_update_entry_status(file_path, key, 'failed', {'error': str(e)})
        print(f'[ERROR] {key}: {str(e)}', flush=True)
        return False


def engine_loop():
    print(json.dumps({'status': 'ok', 'message': 'Automation Engine is running'}), flush=True)
    state = read_json(STATE_FILE)
    processed_this_session = set()

    while True:
        rules_data = read_json(RULES_FILE).get('rules', {})

        file_rules = {}
        for rule_key, rule in rules_data.items():
            # Skip disabled rules (defaults to enabled if not specified)
            if not rule.get('enabled', True):
                continue

            trigger = rule.get('trigger', {})
            trig_type = trigger.get('type')
            file_path = trigger.get('file')
            if file_path and not os.path.isabs(file_path):
                file_path = os.path.join(PROJECT_ROOT, file_path)
            if trig_type in ('entry_added', 'entry_updated'):
                if file_path not in file_rules:
                    file_rules[file_path] = {'entry_added': [], 'entry_updated': []}
                file_rules[file_path][trig_type].append((rule_key, rule))

        for file_path, type_rules in file_rules.items():
            new_data = read_json(file_path)
            old_data = state.get(file_path, {})
            new_entries = new_data.get('entries', {})
            old_entries = old_data.get('entries', {})

            for rule_key, rule in type_rules['entry_added']:
                test_expr = read_json(EVENT_TYPES_FILE).get('entry_added', {}).get('test')
                if not test_expr:
                    continue
                    
                for key, new_entry in new_entries.items():
                    current_status = new_entry.get('status', '')
                    if current_status in ('processed', 'processing', 'failed'):
                        continue
                    
                    session_key = f"{file_path}:{key}:added"
                    if session_key in processed_this_session:
                        continue
                    
                    old_entry = old_entries.get(key, {})
                    ctx = {'key': key, 'old_entry': old_entry, 'new_entry': new_entry}
                    
                    try:
                        if not eval(test_expr, {}, ctx):
                            continue
                    except:
                        continue
                    
                    rule_condition = rule.get("condition")
                    if rule_condition:
                        try:
                            if not eval(rule_condition, {}, ctx):
                                continue
                        except:
                            continue
                    
                    processed_this_session.add(session_key)
                    process_queue_entry_with_lock(file_path, key, new_entry, rule)

            for rule_key, rule in type_rules['entry_updated']:
                test_expr = read_json(EVENT_TYPES_FILE).get('entry_updated', {}).get('test')
                if not test_expr:
                    continue
                    
                for key, new_entry in new_entries.items():
                    if key not in old_entries:
                        continue
                    
                    current_status = new_entry.get('status', '')
                    if current_status in ('processing', 'failed'):
                        continue
                    
                    old_entry = old_entries[key]
                    ctx = {'key': key, 'old_entry': old_entry, 'new_entry': new_entry}
                    
                    try:
                        if not eval(test_expr, {}, ctx):
                            continue
                    except:
                        continue
                    
                    # Use status + rule_key for deduplication, NOT updated_at timestamp
                    # This prevents duplicate fires when updated_at changes between polls
                    entry_status = new_entry.get('status', '')
                    session_key = f"{file_path}:{key}:{rule_key}:{entry_status}"
                    if session_key in processed_this_session:
                        continue
                    
                    rule_condition = rule.get("condition")
                    if rule_condition:
                        try:
                            if not eval(rule_condition, {}, ctx):
                                continue
                        except:
                            continue
                    
                    processed_this_session.add(session_key)
                    context = {"entry_key": key}
                    for k, v in new_entry.items():
                        if k != "entry_key":
                            context[k] = v
                    print(f'[PROCESSING] {rule_key} -> {key}', flush=True)
                    run_action(rule["action"], context)

            state[file_path] = new_data

        for rule_key, rule in rules_data.items():
            # Skip disabled rules (defaults to enabled if not specified)
            if not rule.get('enabled', True):
                continue

            trigger = rule.get('trigger', {})
            trig_type = trigger.get('type')

            if trig_type == 'time':
                now = datetime.now()
                current_time_str = now.strftime('%H:%M')
                if trigger.get('at') == current_time_str or trigger.get('daily') == current_time_str:
                    print(f'[TRIGGER] {rule_key} (time)', flush=True)
                    result = run_action(rule['action'], {})
                    # Handle post_action with for_each
                    if 'post_action' in rule and result:
                        post = rule['post_action']
                        if 'for_each' in post:
                            array_key = post['for_each']
                            items = result.get(array_key, [])
                            condition = post.get('condition')
                            # Handle dict (iterate key-value pairs) or list
                            if isinstance(items, dict):
                                items_iter = [(k, v) for k, v in items.items()]
                            else:
                                items_iter = [(None, item) for item in items]
                            for item_key, item in items_iter:
                                # Check condition if exists
                                if condition:
                                    try:
                                        if not eval(condition, {"item": item, "datetime": datetime}):
                                            continue
                                    except Exception as e:
                                        print(f'[CONDITION ERROR] {e}', flush=True)
                                        continue
                                # Run the action with item context (include key for dicts)
                                item_context = {'item': item, 'item_key': item_key}
                                run_action(post['action'], item_context)

            elif trig_type == 'interval':
                interval_minutes = trigger.get('minutes', 5)
                last_execution = state.get('interval_executions', {}).get(rule_key)
                should_run = False
                if last_execution is None:
                    should_run = True
                else:
                    now = datetime.now()
                    last_time = datetime.fromisoformat(last_execution)
                    minutes_passed = (now - last_time).total_seconds() / 60
                    if minutes_passed >= interval_minutes:
                        should_run = True
                if should_run:
                    print(f'[TRIGGER] {rule_key} (interval)', flush=True)
                    result = run_action(rule['action'], {})
                    # Handle post_action with for_each (same as time triggers)
                    if 'post_action' in rule and result:
                        post = rule['post_action']
                        if 'for_each' in post:
                            array_key = post['for_each']
                            items = result.get(array_key, [])
                            condition = post.get('condition')
                            # Handle dict (iterate key-value pairs) or list
                            if isinstance(items, dict):
                                items_iter = [(k, v) for k, v in items.items()]
                            else:
                                items_iter = [(None, item) for item in items]
                            for item_key, item in items_iter:
                                # Check condition if exists
                                if condition:
                                    try:
                                        if not eval(condition, {"item": item, "datetime": datetime}):
                                            continue
                                    except Exception as e:
                                        print(f'[CONDITION ERROR] {e}', flush=True)
                                        continue
                                # Run the action with item context (include key for dicts)
                                item_context = {'item': item, 'item_key': item_key}
                                run_action(post['action'], item_context)
                    if 'interval_executions' not in state:
                        state['interval_executions'] = {}
                    state['interval_executions'][rule_key] = datetime.now().isoformat()

        write_json(STATE_FILE, state)
        
        if len(processed_this_session) > 10000:
            processed_this_session.clear()
        
        time.sleep(5)


def add_rule(params):
    rule_key = params.get('rule_key')
    rule_data = params.get('rule')
    skip_validation = params.get('skip_validation', False)

    if not rule_key or not isinstance(rule_data, dict):
        return {'status': 'error', 'message': 'rule_key and rule dict required'}

    # Validate rule before saving (unless explicitly skipped)
    if not skip_validation:
        validation = validate_rule({'rule': rule_data})
        if validation.get('status') == 'error':
            return {
                'status': 'error',
                'message': f'Rule validation failed: {validation.get("errors", [])}',
                'errors': validation.get('errors', [])
            }

    data = read_json(RULES_FILE)
    if 'rules' not in data:
        data['rules'] = {}
    if rule_key in data['rules']:
        return {'status': 'error', 'message': f'Rule "{rule_key}" already exists'}
    data['rules'][rule_key] = rule_data
    write_json(RULES_FILE, data)
    return {'status': 'success', 'message': f'Rule "{rule_key}" added.'}


def update_rule(params):
    rule_key = params.get('rule_key')
    rule_data = params.get('rule')
    skip_validation = params.get('skip_validation', False)

    if not rule_key or not isinstance(rule_data, dict):
        return {'status': 'error', 'message': 'rule_key and rule dict required'}

    # Validate rule before saving (unless explicitly skipped)
    if not skip_validation:
        validation = validate_rule({'rule': rule_data})
        if validation.get('status') == 'error':
            return {
                'status': 'error',
                'message': f'Rule validation failed: {validation.get("errors", [])}',
                'errors': validation.get('errors', [])
            }

    data = read_json(RULES_FILE)
    if 'rules' not in data or rule_key not in data['rules']:
        return {'status': 'error', 'message': f'Rule "{rule_key}" not found'}
    data['rules'][rule_key] = rule_data
    write_json(RULES_FILE, data)
    return {'status': 'success', 'message': f'Rule "{rule_key}" updated.'}


def delete_rule(params):
    rule_key = params.get('rule_key')
    if not rule_key:
        return {'status': 'error', 'message': 'rule_key required'}
    data = read_json(RULES_FILE)
    if 'rules' not in data or rule_key not in data['rules']:
        return {'status': 'error', 'message': f'Rule "{rule_key}" not found'}
    del data['rules'][rule_key]
    write_json(RULES_FILE, data)
    return {'status': 'success', 'message': f'Rule "{rule_key}" deleted.'}


def get_rule(params):
    rule_key = params.get('rule_key')
    if not rule_key:
        return {'status': 'error', 'message': 'rule_key required'}
    data = read_json(RULES_FILE)
    rules = data.get('rules', {})
    if rule_key not in rules:
        return {'status': 'error', 'message': f'Rule "{rule_key}" not found'}
    return {'status': 'success', 'rule_key': rule_key, 'rule': rules[rule_key]}


def get_rules(params):
    data = read_json(RULES_FILE)
    rules = data.get('rules', {})
    return {'status': 'ok', 'rules': rules, 'rule_count': len(rules)}


def list_rules(params):
    data = read_json(RULES_FILE)
    rules = data.get('rules', {})
    rule_list = []
    for rule_key, rule_data in rules.items():
        trigger = rule_data.get('trigger', {})
        rule_list.append({'rule_key': rule_key, 'trigger_type': trigger.get('type'), 'trigger_file': trigger.get('file'), 'has_condition': 'condition' in rule_data})
    return {'status': 'ok', 'rules': rule_list, 'rule_count': len(rule_list)}


def add_event_type(params):
    key = params.get('key')
    expr = params.get('test')
    if not key or not expr:
        return {'status': 'error', 'message': 'key and test required'}
    data = read_json(EVENT_TYPES_FILE)
    data[key] = {'test': expr}
    write_json(EVENT_TYPES_FILE, data)
    return {'status': 'success', 'message': f"Event type '{key}' added."}


def update_event_type(params):
    key = params.get('key')
    expr = params.get('test')
    if not key or not expr:
        return {'status': 'error', 'message': 'key and test required'}
    data = read_json(EVENT_TYPES_FILE)
    if key not in data:
        return {'status': 'error', 'message': 'Event type not found.'}
    data[key]['test'] = expr
    write_json(EVENT_TYPES_FILE, data)
    return {'status': 'success', 'message': f"Event type '{key}' updated."}


def get_event_types(params):
    data = read_json(EVENT_TYPES_FILE)
    return {'status': 'ok', 'events': data}


def dispatch_event(event_key, payload):
    rules_data = read_json(RULES_FILE).get('rules', {})
    matched = []
    for rule_key, rule in rules_data.items():
        trigger = rule.get('trigger', {})
        if trigger.get('type') == 'event' and trigger.get('event_key') == event_key:
            context = payload.copy()
            run_action(rule['action'], context)
            matched.append(rule_key)
    return {'status': 'ok', 'message': f'{len(matched)} event-based rule(s) triggered.'}


def retry_failed(params):
    """Reset failed entries back to queued for retry."""
    file_path = params.get('file')
    if not file_path:
        return {'status': 'error', 'message': 'file parameter required'}
    if not os.path.isabs(file_path):
        file_path = os.path.join(PROJECT_ROOT, file_path)

    with FileLock(file_path):
        data = read_json(file_path)
        entries = data.get('entries', {})
        reset_count = 0

        for key, entry in entries.items():
            if entry.get('status') == 'failed':
                entry['status'] = 'queued'
                entry['updated_at'] = datetime.now().isoformat()
                if 'error' in entry:
                    del entry['error']
                reset_count += 1

        write_json(file_path, data)

    return {'status': 'success', 'message': f'Reset {reset_count} failed entries to queued'}


def now():
    """Return current datetime for use in conditions."""
    return datetime.now()


def days(n):
    """Return timedelta of n days for use in conditions."""
    return timedelta(days=n)


def hours(n):
    """Return timedelta of n hours for use in conditions."""
    return timedelta(hours=n)


def minutes(n):
    """Return timedelta of n minutes for use in conditions."""
    return timedelta(minutes=n)


def parse_duration(value):
    """Parse duration string like '2d', '3h', '30m' to timedelta."""
    if isinstance(value, timedelta):
        return value
    if isinstance(value, (int, float)):
        return timedelta(seconds=value)
    if isinstance(value, str):
        value = value.strip().lower()
        if value.endswith('d'):
            return timedelta(days=float(value[:-1]))
        elif value.endswith('h'):
            return timedelta(hours=float(value[:-1]))
        elif value.endswith('m'):
            return timedelta(minutes=float(value[:-1]))
        elif value.endswith('s'):
            return timedelta(seconds=float(value[:-1]))
        else:
            return timedelta(seconds=float(value))
    return timedelta(0)


def is_older_than(timestamp_str, duration):
    """Check if a timestamp is older than specified duration.

    Args:
        timestamp_str: ISO timestamp string or datetime
        duration: timedelta, duration string ('2d', '3h'), or number of seconds

    Returns:
        True if timestamp is older than duration ago
    """
    if not timestamp_str:
        return False
    if isinstance(timestamp_str, str):
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
        except ValueError:
            return False
    elif isinstance(timestamp_str, datetime):
        timestamp = timestamp_str
    else:
        return False

    threshold = datetime.now() - parse_duration(duration)
    return timestamp < threshold


def evaluate_condition(condition, context):
    """Evaluate a condition string with time-aware functions.

    Provides these functions for conditions:
    - now(): Current datetime
    - days(n): timedelta of n days
    - hours(n): timedelta of n hours
    - minutes(n): timedelta of n minutes
    - is_older_than(timestamp, duration): Check if timestamp is older than duration

    Example conditions:
    - "is_older_than(entry.get('created_at'), '2d')"
    - "entry.get('status_changed_at') and now() - datetime.fromisoformat(entry['status_changed_at']) > days(2)"
    """
    eval_context = {
        'now': now,
        'days': days,
        'hours': hours,
        'minutes': minutes,
        'is_older_than': is_older_than,
        'datetime': datetime,
        'timedelta': timedelta,
    }
    eval_context.update(context)

    try:
        return eval(condition, {"__builtins__": {}}, eval_context)
    except Exception:
        return False


def load_tool_actions():
    """Load available tools and their actions from system_settings.ndjson."""
    tools = {}
    if not os.path.exists(NDJSON_REGISTRY_FILE):
        return tools

    try:
        with open(NDJSON_REGISTRY_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    if entry.get('action') == '__tool__':
                        tool_name = entry.get('tool')
                        if tool_name:
                            tools[tool_name] = {
                                'script_path': entry.get('script_path'),
                                'actions': set()
                            }
                    elif entry.get('tool') and entry.get('action') and entry.get('action') != '__tool__':
                        tool_name = entry.get('tool')
                        action_name = entry.get('action')
                        if tool_name in tools:
                            tools[tool_name]['actions'].add(action_name)
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass

    return tools


def find_similar_name(name, available_names, threshold=0.6):
    """Find similar names for helpful error messages."""
    from difflib import SequenceMatcher
    best_match = None
    best_ratio = 0

    for available in available_names:
        ratio = SequenceMatcher(None, name.lower(), available.lower()).ratio()
        if ratio > best_ratio and ratio >= threshold:
            best_ratio = ratio
            best_match = available

    return best_match


def validate_rule(params):
    """Validate a rule's tool/action references without saving.

    Returns validation result with specific errors for:
    - Tool not found (with suggestions)
    - Action not found for tool (with available actions)
    - Missing required params
    """
    rule = params.get('rule')
    if not rule:
        return {'status': 'error', 'message': 'rule parameter required'}

    tools = load_tool_actions()
    errors = []
    warnings = []

    def validate_action(action_def, step_name="action"):
        """Validate a single action definition."""
        tool_name = action_def.get('tool')
        action_name = action_def.get('action')

        if not tool_name:
            errors.append(f'{step_name}: tool not specified')
            return

        if tool_name not in tools:
            similar = find_similar_name(tool_name, tools.keys())
            if similar:
                errors.append(f'{step_name}: Tool "{tool_name}" not found. Did you mean "{similar}"?')
            else:
                errors.append(f'{step_name}: Tool "{tool_name}" not found. Available: {", ".join(sorted(tools.keys())[:10])}...')
            return

        if not action_name:
            errors.append(f'{step_name}: action not specified for tool "{tool_name}"')
            return

        available_actions = tools[tool_name].get('actions', set())
        if available_actions and action_name not in available_actions:
            similar = find_similar_name(action_name, available_actions)
            if similar:
                errors.append(f'{step_name}: Action "{action_name}" not found for tool "{tool_name}". Did you mean "{similar}"?')
            else:
                errors.append(f'{step_name}: Action "{action_name}" not found for tool "{tool_name}". Available: {", ".join(sorted(available_actions))}')

    # Validate main action
    action = rule.get('action', {})
    if 'steps' in action:
        for i, step in enumerate(action['steps']):
            if step.get('type') == 'foreach':
                for j, sub_step in enumerate(step.get('steps', [])):
                    validate_action(sub_step, f'steps[{i}].foreach.steps[{j}]')
            else:
                validate_action(step, f'steps[{i}]')
    else:
        validate_action(action)

    # Validate post_action if exists
    post_action = rule.get('post_action', {}).get('action')
    if post_action:
        validate_action(post_action, 'post_action')

    # Validate trigger
    trigger = rule.get('trigger', {})
    if not trigger.get('type'):
        errors.append('trigger: type not specified')
    elif trigger.get('type') in ('entry_added', 'entry_updated') and not trigger.get('file'):
        errors.append('trigger: file required for entry_added/entry_updated triggers')

    if errors:
        return {
            'status': 'error',
            'message': 'Rule validation failed',
            'errors': errors,
            'warnings': warnings
        }

    return {
        'status': 'success',
        'message': 'Rule validation passed',
        'warnings': warnings
    }


def dry_run_rule(params):
    """Test a rule without executing actions. Shows what WOULD happen.

    Args:
        params: {rule_id: str, file: str (optional, uses rule's trigger file if not provided)}

    Returns:
        {
            rule_id: str,
            would_fire: bool,
            matching_entries: [{id, reason}],
            actions_that_would_execute: [{tool, action, params}]
        }
    """
    rule_id = params.get('rule_id')
    if not rule_id:
        return {'status': 'error', 'message': 'rule_id required'}

    rules_data = read_json(RULES_FILE).get('rules', {})
    if rule_id not in rules_data:
        return {'status': 'error', 'message': f'Rule "{rule_id}" not found'}

    rule = rules_data[rule_id]
    trigger = rule.get('trigger', {})
    trig_type = trigger.get('type')
    file_path = params.get('file') or trigger.get('file')

    if file_path and not os.path.isabs(file_path):
        file_path = os.path.join(PROJECT_ROOT, file_path)

    matching_entries = []
    actions_would_execute = []

    if trig_type in ('entry_added', 'entry_updated') and file_path:
        data = read_json(file_path)
        entries = data.get('entries', {})

        # Load test expression from event types
        test_expr = read_json(EVENT_TYPES_FILE).get(trig_type, {}).get('test')
        rule_condition = rule.get('condition')

        for key, entry in entries.items():
            status = entry.get('status', '')

            # Skip already processed
            if status in ('processed', 'processing', 'failed', 'timeout_failed', 'permanently_failed'):
                continue

            # Simulate old_entry as empty for entry_added, same as current for entry_updated
            old_entry = {} if trig_type == 'entry_added' else entry
            ctx = {'key': key, 'old_entry': old_entry, 'new_entry': entry}

            # Test event type condition
            if test_expr:
                try:
                    if not eval(test_expr, {}, ctx):
                        continue
                except Exception:
                    continue

            # Test rule condition
            if rule_condition:
                try:
                    if not eval(rule_condition, {}, ctx):
                        continue
                except Exception:
                    continue

            # This entry would match
            reason = f"status={status}"
            if rule_condition:
                reason += f", condition={rule_condition}"
            matching_entries.append({'id': key, 'reason': reason})

            # Build context and resolve what action would run
            context = {"entry_key": key}
            context.update(entry)

            action = rule.get('action', {})
            if 'steps' in action:
                for step in action['steps']:
                    resolved = resolve_context_values(step, context)
                    actions_would_execute.append({
                        'tool': resolved.get('tool'),
                        'action': resolved.get('action'),
                        'params': resolved.get('params', {})
                    })
            else:
                resolved = resolve_context_values(action, context)
                actions_would_execute.append({
                    'tool': resolved.get('tool'),
                    'action': resolved.get('action'),
                    'params': resolved.get('params', {})
                })

    elif trig_type == 'time':
        # Time trigger - check if current time matches
        now = datetime.now()
        current_time = now.strftime('%H:%M')
        trigger_time = trigger.get('at') or trigger.get('daily')

        if current_time == trigger_time:
            matching_entries.append({'id': 'time_trigger', 'reason': f'current time {current_time} matches trigger'})
            action = rule.get('action', {})
            if 'steps' in action:
                for step in action['steps']:
                    actions_would_execute.append({
                        'tool': step.get('tool'),
                        'action': step.get('action'),
                        'params': step.get('params', {})
                    })
            else:
                actions_would_execute.append({
                    'tool': action.get('tool'),
                    'action': action.get('action'),
                    'params': action.get('params', {})
                })

    elif trig_type == 'interval':
        # Interval trigger - always would fire if checked
        interval = trigger.get('minutes', 5)
        matching_entries.append({'id': 'interval_trigger', 'reason': f'interval every {interval} minutes'})
        action = rule.get('action', {})
        if 'steps' in action:
            for step in action['steps']:
                actions_would_execute.append({
                    'tool': step.get('tool'),
                    'action': step.get('action'),
                    'params': step.get('params', {})
                })
        else:
            actions_would_execute.append({
                'tool': action.get('tool'),
                'action': action.get('action'),
                'params': action.get('params', {})
            })

    return {
        'status': 'success',
        'rule_id': rule_id,
        'would_fire': len(matching_entries) > 0,
        'matching_entries': matching_entries,
        'actions_that_would_execute': actions_would_execute
    }


def dry_run_all_rules(params):
    """Dry run all rules and return aggregate results."""
    rules_data = read_json(RULES_FILE).get('rules', {})
    results = []

    for rule_id in rules_data:
        result = dry_run_rule({'rule_id': rule_id})
        if result.get('would_fire'):
            results.append({
                'rule_id': rule_id,
                'matching_count': len(result.get('matching_entries', [])),
                'actions_count': len(result.get('actions_that_would_execute', []))
            })

    return {
        'status': 'success',
        'rules_that_would_fire': results,
        'total_rules_checked': len(rules_data),
        'total_rules_would_fire': len(results)
    }


def toggle_rule_enabled(params):
    """Toggle the enabled status of a rule.

    Args:
        params: {rule_key: str, enabled: bool (optional, toggles if not provided)}

    Returns:
        {status, message, rule_key, enabled}
    """
    rule_key = params.get('rule_key')
    enabled = params.get('enabled')  # None means toggle

    if not rule_key:
        return {'status': 'error', 'message': 'rule_key required'}

    with FileLock(RULES_FILE):
        data = read_json(RULES_FILE)
        rules = data.get('rules', {})

        if rule_key not in rules:
            return {'status': 'error', 'message': f'Rule "{rule_key}" not found'}

        # Toggle if enabled not specified, otherwise set to provided value
        current_enabled = rules[rule_key].get('enabled', True)
        new_enabled = not current_enabled if enabled is None else bool(enabled)

        rules[rule_key]['enabled'] = new_enabled
        write_json(RULES_FILE, data)

    return {
        'status': 'success',
        'message': f'Rule "{rule_key}" {"enabled" if new_enabled else "disabled"}',
        'rule_key': rule_key,
        'enabled': new_enabled
    }


def retry_failed_entries(params):
    """Scan for failed/timeout_failed entries eligible for retry with exponential backoff.

    Rule schema additions:
        max_retries: Max retry attempts (default 3)
        retry_delay_base: Base delay in minutes (default 5)

    Entry state additions:
        retry_count: Number of retries attempted
        last_retry: ISO timestamp of last retry
        next_retry: ISO timestamp when eligible for next retry

    Retry schedule: base * 3^attempt (5min, 15min, 45min by default)
    """
    file_path = params.get('file')
    rule_id = params.get('rule_id')
    max_retries = params.get('max_retries', 3)
    retry_delay_base = params.get('retry_delay_base', 5)  # minutes

    if not file_path:
        return {'status': 'error', 'message': 'file parameter required'}
    if not os.path.isabs(file_path):
        file_path = os.path.join(PROJECT_ROOT, file_path)

    now = datetime.now()
    retried = []
    permanently_failed = []

    with FileLock(file_path):
        data = read_json(file_path)
        entries = data.get('entries', {})

        for key, entry in entries.items():
            status = entry.get('status', '')

            # Only retry failed or timeout_failed entries
            if status not in ('failed', 'timeout_failed'):
                continue

            retry_count = entry.get('retry_count', 0)

            # Check if max retries exhausted
            if retry_count >= max_retries:
                if status != 'permanently_failed':
                    entry['status'] = 'permanently_failed'
                    entry['updated_at'] = now.isoformat()
                    permanently_failed.append(key)
                continue

            # Check if enough time has passed since last retry
            next_retry_str = entry.get('next_retry')
            if next_retry_str:
                next_retry_time = datetime.fromisoformat(next_retry_str)
                if now < next_retry_time:
                    continue  # Not yet eligible for retry

            # Calculate next retry delay: base * 3^attempt
            delay_minutes = retry_delay_base * (3 ** retry_count)
            next_retry = now + timedelta(minutes=delay_minutes)

            # Mark for retry
            entry['status'] = 'queued'
            entry['retry_count'] = retry_count + 1
            entry['last_retry'] = now.isoformat()
            entry['next_retry'] = next_retry.isoformat()
            entry['updated_at'] = now.isoformat()
            if 'error' in entry:
                entry['previous_error'] = entry['error']
                del entry['error']

            print(f'[RETRY] Entry {key} attempt {entry["retry_count"]}/{max_retries} for rule {rule_id or "unknown"}', flush=True)
            retried.append(key)

        write_json(file_path, data)

    return {
        'status': 'success',
        'message': f'Retried {len(retried)} entries, {len(permanently_failed)} marked permanently_failed',
        'retried': retried,
        'permanently_failed': permanently_failed
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    if args.action == 'run_engine':
        result = engine_loop()
    elif args.action == 'add_rule':
        result = add_rule(params)
    elif args.action == 'update_rule':
        result = update_rule(params)
    elif args.action == 'delete_rule':
        result = delete_rule(params)
    elif args.action == 'get_rule':
        result = get_rule(params)
    elif args.action == 'get_rules':
        result = get_rules(params)
    elif args.action == 'list_rules':
        result = list_rules(params)
    elif args.action == 'add_event_type':
        result = add_event_type(params)
    elif args.action == 'update_event_type':
        result = update_event_type(params)
    elif args.action == 'dispatch_event':
        result = dispatch_event(params.get('event_key'), params)
    elif args.action == 'get_event_types':
        result = get_event_types(params)
    elif args.action == 'retry_failed':
        result = retry_failed(params)
    elif args.action == 'retry_failed_entries':
        result = retry_failed_entries(params)
    elif args.action == 'dry_run_rule':
        result = dry_run_rule(params)
    elif args.action == 'dry_run_all_rules':
        result = dry_run_all_rules(params)
    elif args.action == 'validate_rule':
        result = validate_rule(params)
    elif args.action == 'get_execution_history':
        result = get_execution_history(params)
    elif args.action == 'toggle_rule_enabled':
        result = toggle_rule_enabled(params)
    else:
        result = {'status': 'error', 'message': f'Unknown action {args.action}'}

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()