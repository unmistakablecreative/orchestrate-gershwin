#!/usr/bin/env python3
"""
Mash Tool

Auto-refactored by refactorize.py to match gold standard structure.
"""

import os
import sys
import json

import random


def spin_game(params):
    categories = ['home', 'car', 'career', 'partner']
    options = {k: params.get(k, []) for k in categories}
    spin = int(params.get('spin', 3))
    result = {}
    for cat in categories:
        items = options.get(cat, [])[:]
        idx = 0
        while len(items) > 1:
            idx = (idx + spin - 1) % len(items)
            items.pop(idx)
        result[cat] = items[0] if items else '🛑 No options'
    return {'status': 'success', 'data': result}


def main():
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    if args.action == 'spin_game':
        result = spin_game(params)
    else:
        result = {'status': 'error', 'message': f'Unknown action {args.action}'}

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()