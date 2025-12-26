#!/usr/bin/env python3
"""
Buffer Engine

Auto-refactored by refactorize.py to match gold standard structure.
"""

import sys
import json
import os

import time
from datetime import datetime
from zoneinfo import ZoneInfo
from requests_oauthlib import OAuth1Session


def load_credential(key):
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        cred_path = os.path.join(base_dir, "credentials.json")
        with open(cred_path, "r") as f:
            creds = json.load(f)
        return creds.get(key)
    except Exception:
        return None


def post_to_platform(params):
    content = params.get("content", "").strip()
    if not content:
        return {"status": "error", "message": "❌ Content is required."}

    url = "https://api.twitter.com/2/tweets"
    payload = {"text": content}

    TWITTER_API_KEY = load_credential("twitter_api_key")
    TWITTER_API_SECRET = load_credential("twitter_api_secret")
    TWITTER_ACCESS_TOKEN = load_credential("twitter_access_token")
    TWITTER_ACCESS_SECRET = load_credential("twitter_access_secret")

    if not all([TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET]):
        return {"status": "error", "message": "❌ Missing one or more Twitter credentials."}

    oauth = OAuth1Session(
        TWITTER_API_KEY,
        TWITTER_API_SECRET,
        TWITTER_ACCESS_TOKEN,
        TWITTER_ACCESS_SECRET
    )

    try:
        response = oauth.post(url, json=payload)
        response.raise_for_status()
        return {"status": "success", "message": "✅ Tweet posted successfully", "data": response.json()}
    except Exception as e:
        return {"status": "error", "message": "❌ Twitter API error", "error": str(e)}


def buffer_loop():
    while True:
        try:
            with open("data/campaign_rules.json", "r") as f:
                rules = json.load(f).get("entries", {})

            with open("data/post_queue.json", "r") as f:
                queue = json.load(f).get("entries", {})

            now = datetime.now(ZoneInfo("America/Los_Angeles"))
            today = now.strftime("%a").lower()
            now_time = now.strftime("%H:%M")

            for campaign_id, rule in rules.items():
                if today not in rule.get("days", []):
                    continue

                allowed_slots = rule.get("timeslots", [])
                max_posts = rule.get("max_posts_per_day", 1)

                published_today = [
                    p for p in queue.values()
                    if p.get("campaign_id") == campaign_id and p.get("status") == "published"
                    and p.get("published_time", "").startswith(now.strftime("%Y-%m-%d"))
                ]

                published_count = len(published_today)
                slots_ready = [s for s in allowed_slots if now_time >= s]
                slots_remaining = max(0, min(len(slots_ready), max_posts - published_count))

                if slots_remaining == 0:
                    continue

                for post in queue.values():
                    if slots_remaining == 0:
                        break
                    if post.get("campaign_id") != campaign_id or post.get("status") != "scheduled":
                        continue

                    full_content = f"{post.get('content', '').strip()}\n{post.get('link', '').strip()}"
                    result = post_to_platform({"content": full_content})
                    post["status"] = "published"
                    post["published_time"] = now.isoformat()
                    post["response"] = result
                    slots_remaining -= 1

            with open("data/post_queue.json", "w") as f:
                json.dump({"entries": queue}, f, indent=2)

        except Exception as e:
            print(f"❌ Loop error: {e}")

        time.sleep(60)


def main():
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    if args.action == 'buffer_loop':
        result = buffer_loop()
    elif args.action == 'load_credential':
        result = load_credential(**params)
    elif args.action == 'post_to_platform':
        result = post_to_platform(params)
    else:
        result = {'status': 'error', 'message': f'Unknown action {args.action}'}

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()