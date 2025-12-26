#!/usr/bin/env python3
"""
Referral Engine

Auto-refactored by refactorize.py to match gold standard structure.
"""

import sys
import os
import json
import subprocess

import time
import shutil
from zipfile import ZipFile
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import threading


BASE_DIR = '/opt/orchestrate-core-runtime/referral_base'
TEMP_DIR = '/tmp/referral_build'
OUTPUT_DIR = '/opt/orchestrate-core-runtime/app'
WATCH_PATH = '/opt/orchestrate-core-runtime/data'
NETLIFY_SITE = '36144ab8-5036-40bf-837e-c678a5da2be0'


def build_and_deploy_zip(referrer_id, name, email):
    import requests

    # Clean out old ZIPs
    for file in os.listdir(OUTPUT_DIR):
        if file.endswith(".zip"):
            os.remove(os.path.join(OUTPUT_DIR, file))

    safe_name = name.replace(" ", "_").lower()
    zip_name = f'referral_{safe_name}.zip'
    zip_path = os.path.join(OUTPUT_DIR, zip_name)

    # Reset temp dir
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
    os.makedirs(TEMP_DIR, exist_ok=True)

    # Validate base package dir
    if not os.path.exists(BASE_DIR):
        print(f"❌ BASE_DIR not found: {BASE_DIR}")
        return

    # Copy all contents from base to temp
    for file in os.listdir(BASE_DIR):
        src = os.path.join(BASE_DIR, file)
        dest = os.path.join(TEMP_DIR, file)
        if os.path.isdir(src):
            if os.path.exists(dest):
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
        else:
            shutil.copy2(src, dest)

    # Determine user identity
    user_id = referrer_id
    identity_path = '/container_state/system_identity.json'
    if os.path.exists(identity_path):
        try:
            with open(identity_path) as idf:
                identity = json.load(idf)
                loaded_id = identity.get("user_id")
                if loaded_id and loaded_id.lower() != "unknown":
                    user_id = loaded_id
        except Exception as e:
            print(f"⚠️ Failed to read system identity: {e}")

    # Write referrer into bundle
    with open(os.path.join(TEMP_DIR, 'referrer.txt'), 'w') as f:
        f.write(user_id)

    # Create output dir if needed
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ✅ Build the ZIP file
    try:
        with ZipFile(zip_path, 'w') as zipf:
            for root, _, files in os.walk(TEMP_DIR):
                for file in files:
                    abs_path = os.path.join(root, file)
                    arcname = os.path.relpath(abs_path, TEMP_DIR)
                    zipf.write(abs_path, arcname)
        print(f"✅ Built referral zip: {zip_path}")
    except Exception as e:
        print(f"❌ Failed to build zip: {e}")
        return

    if not os.path.exists(zip_path):
        print("❌ ZIP file not found after build. Aborting deploy.")
        return

    # ✅ Deploy to Netlify
    os.chdir(OUTPUT_DIR)
    deploy_cmd = [
        "/usr/local/bin/netlify", "deploy",
        "--auth", os.environ.get("NETLIFY_AUTH_TOKEN", ""),
        "--dir=.", "--prod",
        "--message", f"referral_{referrer_id}",
        "--site", NETLIFY_SITE
    ]

    print("🚚 Deploying to Netlify...")
    result = subprocess.run(deploy_cmd, capture_output=True, text=True)

    print("---- NETLIFY STDOUT ----")
    print(result.stdout)
    print("---- NETLIFY STDERR ----")
    print(result.stderr)

    if result.returncode != 0:
        print("❌ Netlify deploy failed.")
        return

    referral_url = f"https://stalwart-kangaroo-dd7c11.netlify.app/{zip_name}"
    print(f"🌐 Live URL: {referral_url}")

    # ✅ Fire webhook
    WEBHOOK_URL = "https://hooks.airtable.com/workflows/v1/genericWebhook/appHggDD1APShGNiZ/wflGBzCgFTzCbwJud/wtrQuynZz6WuEUGSB"
    payload = {
        "referrer_id": referrer_id,
        "name": name,
        "email": email,
        "referral_url": referral_url
    }

    try:
        response = requests.post(WEBHOOK_URL, json=payload)
        if response.status_code == 200:
            print("✅ Webhook delivered successfully")
        else:
            print(f"❌ Webhook failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Exception sending webhook: {e}")


def start_referral_watcher():
    observer = Observer()
    handler = ReferralHandler()
    observer.schedule(handler, path=WATCH_PATH, recursive=False)
    observer.start()
    print('👀 Watching referrals.json for changes...')

    def monitor():
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()

    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    monitor()


def main():
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    if args.action == 'build_and_deploy_zip':
        result = build_and_deploy_zip(**params)
    elif args.action == 'start_referral_watcher':
        result = start_referral_watcher()
    else:
        result = {'status': 'error', 'message': f'Unknown action {args.action}'}

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()