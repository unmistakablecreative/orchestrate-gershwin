#!/usr/bin/env python3
"""
Github Tool Universal

Auto-refactored by refactorize.py to match gold standard structure.
"""

import sys
import os
import subprocess
import json
import argparse

from typing import List


CREDENTIAL_PATH = os.path.join(os.path.dirname(__file__), "credentials.json")


def load_credential(key):
    try:
        with open(CREDENTIAL_PATH, "r") as f:
            return json.load(f).get(key)
    except Exception:
        return None


GITHUB_TOKEN = load_credential("github_access_token")


def run_git(command: List[str], path: str):
    try:
        result = subprocess.run(command, cwd=path, capture_output=True, text=True, check=True)
        return {"status": "success", "output": result.stdout.strip()}
    except subprocess.CalledProcessError as e:
        return {
            "status": "error",
            "message": e.stderr.strip() or str(e),
            "command": " ".join(command)
        }


def ensure_git_identity(path: str):
    subprocess.run(["git", "config", "user.name", "unmistakablecreative"], cwd=path)
    subprocess.run(["git", "config", "user.email", "srini@unmistakablemedia.com"], cwd=path)


def clone_repo(url, path):
    return run_git(["git", "clone", url, path], ".")


def init_repo(path):
    os.makedirs(path, exist_ok=True)
    result = run_git(["git", "init"], path)
    ensure_git_identity(path)
    return result


def set_remote(path, url):
    return run_git(["git", "remote", "add", "origin", url], path)


def add_files(path, files: List[str]):
    return run_git(["git", "add"] + files, path)


def commit_repo(path, message):
    ensure_git_identity(path)
    return run_git(["git", "commit", "-m", message], path)


def push_repo(path, branch="main"):
    ensure_git_identity(path)

    # Ensure main branch exists
    branch_check = run_git(["git", "rev-parse", "--verify", branch], path)
    if branch_check["status"] == "error":
        created = run_git(["git", "checkout", "-b", branch], path)
        if created["status"] != "success":
            return created

    # Patch token into remote
    patched = patch_remote_token(path)
    if patched["status"] != "success":
        return patched

    return run_git(["git", "push", "-u", "origin", branch], path)


def pull_repo(path, branch="main"):
    return run_git(["git", "pull", "origin", branch], path)


def patch_remote_token(path):
    if not GITHUB_TOKEN:
        return {"status": "error", "message": "❌ GitHub token not found."}
    try:
        result = subprocess.run(["git", "remote", "get-url", "origin"], cwd=path, capture_output=True, text=True, check=True)
        url = result.stdout.strip()
        if "@" not in url:
            authed = url.replace("https://", f"https://{GITHUB_TOKEN}@")
            subprocess.run(["git", "remote", "set-url", "origin", authed], cwd=path)
        return {"status": "success"}
    except subprocess.CalledProcessError as e:
        return {"status": "error", "message": f"❌ Failed to patch token: {str(e)}"}


def list_repos(root="./projects"):
    entries = []
    for dirpath, dirnames, filenames in os.walk(root):
        if ".git" in dirnames:
            branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=dirpath, capture_output=True, text=True)
            entries.append({
                "name": os.path.basename(dirpath),
                "path": dirpath,
                "branch": branch.stdout.strip() if branch.returncode == 0 else "unknown"
            })
            dirnames[:] = []  # Avoid recursion
    return {"status": "success", "repos": entries}


def main():
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    if args.action == 'add_files':
        result = add_files(**params)
    elif args.action == 'clone_repo':
        result = clone_repo(**params)
    elif args.action == 'commit_repo':
        result = commit_repo(**params)
    elif args.action == 'ensure_git_identity':
        result = ensure_git_identity(**params)
    elif args.action == 'init_repo':
        result = init_repo(**params)
    elif args.action == 'list_repos':
        result = list_repos(**params)
    elif args.action == 'load_credential':
        result = load_credential(**params)
    elif args.action == 'patch_remote_token':
        result = patch_remote_token(**params)
    elif args.action == 'pull_repo':
        result = pull_repo(**params)
    elif args.action == 'push_repo':
        result = push_repo(**params)
    elif args.action == 'run_git':
        result = run_git(**params)
    elif args.action == 'set_remote':
        result = set_remote(**params)
    else:
        result = {'status': 'error', 'message': f'Unknown action {args.action}'}

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()