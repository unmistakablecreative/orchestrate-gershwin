#!/usr/bin/env python3
"""
Ideogram Tool

Auto-refactored by refactorize.py to match gold standard structure.
"""

import sys
import json
import argparse
import os

import requests


CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "credentials.json")
IDEOGRAM_URL = "https://api.ideogram.ai/generate"


def load_api_key():
    if os.path.exists(CREDENTIALS_FILE):
        with open(CREDENTIALS_FILE, "r") as f:
            creds = json.load(f)
        return creds.get("ideogram_api_key")
    return None


def generate_image(params):
    api_key = load_api_key()
    if not api_key:
        return {"status": "error", "message": "Missing API key in credentials.json"}

    headers = {"Api-Key": api_key, "Content-Type": "application/json"}
    prompt = params.get("input", "")
    options = params.get("options", {})
    aspect_ratio = options.get("aspect_ratio", "ASPECT_16_9")
    model = options.get("model", "V_2")

    payload = {
        "image_request": {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "model": model
        }
    }

    response = requests.post(IDEOGRAM_URL, headers=headers, json=payload)

    try:
        return response.json() if response.status_code == 200 else {
            "status": "error",
            "message": "API request failed"
        }
    except json.JSONDecodeError:
        return {"status": "error", "message": "Invalid JSON response from Ideogram."}


def run(params):
    action = params.get("action")
    if action == "generate_image":
        return generate_image(params)
    return {"status": "error", "message": f"Unknown action '{action}'."}


def main():
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    if args.action == 'generate_image':
        result = generate_image(params)
    elif args.action == 'load_api_key':
        result = load_api_key()
    elif args.action == 'run':
        result = run(params)
    else:
        result = {'status': 'error', 'message': f'Unknown action {args.action}'}

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()