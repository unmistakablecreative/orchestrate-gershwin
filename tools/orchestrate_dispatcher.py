#!/usr/bin/env python3
"""
Orchestrate Dispatcher

Auto-refactored by refactorize.py to match gold standard structure.
"""

import sys
import os
import json
import argparse

import inspect
import importlib


DEFAULT_TEMPLATE_DIR = (
    '/Users/srinivas/Orchestrate Github/orchestrate-jarvis/compositions/')


def dispatch_action(params):
    try:
        tool_name = params['tool_name']
        action_name = params['action']
        action_params = params['params']
        tool_module = importlib.import_module(f'tools.{tool_name}')
        action_func = getattr(tool_module, action_name)
        result = action_func(action_params)
        return result
    except Exception as e:
        return {'status': 'error', 'message': f'❌ Dispatch failed: {str(e)}'}


def load_actions(params):
    filename = params.get('filename')
    folder_path = params.get('template_dir', os.path.join(os.getcwd(),
        'compositions'))
    try:
        if filename:
            filepath = os.path.join(folder_path, filename)
            if not os.path.exists(filepath):
                return {'status': 'error', 'message':
                    f'❌ File not found: {filepath}'}
            with open(filepath, 'r') as f:
                data = json.load(f)
            if 'entries' in data and 'status' in data['entries']:
                data = data['entries']
            return {'status': 'success', 'data': data}
        for filename in os.listdir(folder_path):
            if filename.endswith('.json'):
                filepath = os.path.join(folder_path, filename)
                with open(filepath, 'r') as f:
                    data = json.load(f)
                if 'entries' in data and 'status' in data['entries']:
                    data = data['entries']
                if data.get('status') == 'ready':
                    return {'status': 'success', 'data': data}
        return {'status': 'error', 'message': '❌ No ready file found.'}
    except Exception as e:
        return {'status': 'error', 'message':
            f'❌ Failed to load actions: {str(e)}'}


def read_file(filename):
    filepath = os.path.join(DEFAULT_TEMPLATE_DIR, filename)
    if not os.path.exists(filepath):
        return {'status': 'error', 'message': f'❌ File not found: {filename}'}
    if os.path.getsize(filepath) == 0:
        return {'status': 'error', 'message': f'⚠️ File is empty: {filename}'}
    with open(filepath, 'r', encoding='utf-8') as f:
        try:
            content = json.load(f)
            return {'status': 'success', 'content': content}
        except json.JSONDecodeError as e:
            return {'status': 'error', 'message':
                f'❌ JSON decode error in {filename}: {str(e)}'}


def cli_main():
    parser = argparse.ArgumentParser(description='Orchestrate Dispatcher CLI')
    parser.add_argument('action', help='Action to perform')
    parser.add_argument('--params', type=str, required=False, help=
        'JSON-encoded parameters for the action')
    args = parser.parse_args()
    try:
        params = json.loads(args.params) if args.params else {}
    except json.JSONDecodeError:
        print(json.dumps({'status': 'error', 'message':
            '❌ Invalid JSON format.'}, indent=4))
        return
    if args.action == 'dispatch_batch':
        result = main(params)
    else:
        result = {'status': 'error', 'message':
            f'❌ Unknown action: {args.action}'}
    print(json.dumps(result, indent=4))


def main():
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    if args.action == 'cli_main':
        result = cli_main()
    elif args.action == 'dispatch_action':
        result = dispatch_action(params)
    elif args.action == 'load_actions':
        result = load_actions(params)
    elif args.action == 'read_file':
        result = read_file(**params)
    else:
        result = {'status': 'error', 'message': f'Unknown action {args.action}'}

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()