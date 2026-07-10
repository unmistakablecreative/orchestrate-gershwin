#!/usr/bin/env python3
"""
gershwin_github.py - Standalone GitHub integration for Gershwin agents

12 actions covering repo management, code operations, PR workflow, and issue tracking.
Config stored in data/gershwin_github_config.json
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime

from response_helper import get_success_message, get_error_message

# Resolve paths
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
CONFIG_FILE = DATA_DIR / "gershwin_github_config.json"


def load_config():
    """Load GitHub config from JSON file."""
    if not CONFIG_FILE.exists():
        return {
            "github_token": "",
            "default_org": "",
            "default_branch": "main",
            "auto_init": True
        }
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)


def save_config(config):
    """Save GitHub config to JSON file."""
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def get_token():
    """Get GitHub token from config."""
    config = load_config()
    token = config.get("github_token", "")
    if not token:
        return None, {"status": "error", "message": "GitHub token not configured. Set github_token in data/gershwin_github_config.json"}
    return token, None


def run_gh_command(args, capture_output=True):
    """Run a gh CLI command."""
    token, error = get_token()
    if error:
        return error

    env = os.environ.copy()
    env["GH_TOKEN"] = token

    try:
        result = subprocess.run(
            ["gh"] + args,
            capture_output=capture_output,
            text=True,
            env=env,
            cwd=str(SCRIPT_DIR.parent)
        )
        if result.returncode != 0:
            return {"status": "error", "message": result.stderr.strip() or f"Command failed with code {result.returncode}"}
        return {"status": "success", "output": result.stdout.strip()}
    except FileNotFoundError:
        return {"status": "error", "message": "gh CLI not installed. Install with: brew install gh"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def run_git_command(args, cwd=None):
    """Run a git command."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            cwd=cwd or str(SCRIPT_DIR.parent)
        )
        if result.returncode != 0:
            return {"status": "error", "message": result.stderr.strip() or f"Command failed with code {result.returncode}"}
        return {"status": "success", "output": result.stdout.strip()}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ============================================================================
# REPO MANAGEMENT ACTIONS
# ============================================================================

def create_repo(params):
    """
    Create a new GitHub repository.
    Required: repo_name
    Optional: description, private (bool), auto_init (bool)
    """
    repo_name = params.get("repo_name")
    if not repo_name:
        return {"status": "error", "message": "repo_name is required"}

    config = load_config()
    description = params.get("description", "")
    private = params.get("private", False)
    auto_init = params.get("auto_init", config.get("auto_init", True))

    args = ["repo", "create", repo_name]

    if description:
        args.extend(["--description", description])
    if private:
        args.append("--private")
    else:
        args.append("--public")
    if auto_init:
        args.append("--add-readme")

    result = run_gh_command(args)
    if result.get("status") == "success":
        return {
            "status": "success",
            "message": get_success_message("gershwin_github", "create_repo", {"repo_name": repo_name}),
            "repo_url": result.get("output", "").strip()
        }
    return {
        "status": "error",
        "message": get_error_message("gershwin_github", "create_repo", result.get("message", "Unknown error"))
    }


def list_repos(params):
    """
    List repositories for configured org/user.
    Optional: org, limit (default 30)
    """
    config = load_config()
    org = params.get("org", config.get("default_org", ""))
    limit = params.get("limit", 30)

    args = ["repo", "list"]
    if org:
        args.append(org)
    args.extend(["--limit", str(limit), "--json", "name,description,isPrivate,url,updatedAt"])

    result = run_gh_command(args)
    if result.get("status") == "success":
        try:
            repos = json.loads(result["output"])
            return {
                "status": "success",
                "message": get_success_message("gershwin_github", "list_repos", {"count": len(repos)}),
                "repos": repos,
                "count": len(repos)
            }
        except json.JSONDecodeError:
            return {"status": "success", "output": result["output"]}
    return {
        "status": "error",
        "message": get_error_message("gershwin_github", "list_repos", result.get("message", "Unknown error"))
    }


def get_repo(params):
    """
    Get details for a specific repository.
    Required: repo_name
    """
    repo_name = params.get("repo_name")
    if not repo_name:
        return {"status": "error", "message": "repo_name is required"}

    config = load_config()
    org = config.get("default_org", "")
    full_name = f"{org}/{repo_name}" if org and "/" not in repo_name else repo_name

    args = ["repo", "view", full_name, "--json", "name,description,url,isPrivate,defaultBranchRef,createdAt,updatedAt,issues,pullRequests"]

    result = run_gh_command(args)
    if result.get("status") == "success":
        try:
            repo = json.loads(result["output"])
            return {
                "status": "success",
                "message": get_success_message("gershwin_github", "get_repo", {"repo_name": repo_name}),
                "repo": repo
            }
        except json.JSONDecodeError:
            return {"status": "success", "output": result["output"]}
    return {
        "status": "error",
        "message": get_error_message("gershwin_github", "get_repo", result.get("message", "Unknown error"))
    }


# ============================================================================
# CODE OPERATIONS
# ============================================================================

def push_code(params):
    """
    Push local code to remote repo.
    Required: repo_name, file_path (file or directory)
    Optional: branch, commit_message
    """
    repo_name = params.get("repo_name")
    file_path = params.get("file_path")
    if not repo_name:
        return {"status": "error", "message": "repo_name is required"}
    if not file_path:
        return {"status": "error", "message": "file_path is required"}

    config = load_config()
    branch = params.get("branch", config.get("default_branch", "main"))
    commit_message = params.get("commit_message", f"Push code via gershwin_github at {datetime.now().isoformat()}")
    org = config.get("default_org", "")

    # Resolve file path
    source_path = Path(file_path)
    if not source_path.is_absolute():
        source_path = SCRIPT_DIR.parent / file_path

    if not source_path.exists():
        return {"status": "error", "message": f"Path not found: {file_path}"}

    # Get repo URL
    full_name = f"{org}/{repo_name}" if org and "/" not in repo_name else repo_name
    token, error = get_token()
    if error:
        return error

    repo_url = f"https://{token}@github.com/{full_name}.git"

    # Create temp directory for git operations
    import tempfile
    import shutil

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Clone repo
        clone_result = run_git_command(["clone", repo_url, "repo"], cwd=str(tmp_path))
        if clone_result.get("status") != "success":
            return {"status": "error", "message": f"Failed to clone: {clone_result.get('message')}"}

        repo_dir = tmp_path / "repo"

        # Checkout branch
        run_git_command(["checkout", "-B", branch], cwd=str(repo_dir))

        # Copy files
        if source_path.is_file():
            dest = repo_dir / source_path.name
            shutil.copy2(source_path, dest)
        else:
            for item in source_path.iterdir():
                dest = repo_dir / item.name
                if item.is_file():
                    shutil.copy2(item, dest)
                else:
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(item, dest)

        # Add, commit, push
        run_git_command(["add", "-A"], cwd=str(repo_dir))
        commit_result = run_git_command(["commit", "-m", commit_message], cwd=str(repo_dir))
        if "nothing to commit" in commit_result.get("message", "").lower():
            return {"status": "success", "message": "No changes to push"}

        push_result = run_git_command(["push", "-u", "origin", branch], cwd=str(repo_dir))
        if push_result.get("status") != "success":
            return {"status": "error", "message": get_error_message("gershwin_github", "push_code", push_result.get("message", "Unknown error"))}

        return {
            "status": "success",
            "message": get_success_message("gershwin_github", "push_code", {"repo_name": full_name}),
            "branch": branch,
            "commit_message": commit_message
        }


def commit(params):
    """
    Stage and commit changes locally in a repo directory.
    Required: repo_name (directory name), message
    Optional: files (list of files to stage, defaults to all)
    """
    repo_name = params.get("repo_name")
    message = params.get("message")
    if not repo_name:
        return {"status": "error", "message": "repo_name is required"}
    if not message:
        return {"status": "error", "message": "message is required"}

    files = params.get("files", [])

    # Find repo directory
    repo_dir = SCRIPT_DIR.parent / repo_name
    if not repo_dir.exists():
        repo_dir = Path(repo_name)
    if not repo_dir.exists():
        return {"status": "error", "message": f"Repository directory not found: {repo_name}"}

    # Stage files
    if files:
        for f in files:
            add_result = run_git_command(["add", f], cwd=str(repo_dir))
            if add_result.get("status") != "success":
                return {"status": "error", "message": f"Failed to stage {f}: {add_result.get('message')}"}
    else:
        add_result = run_git_command(["add", "-A"], cwd=str(repo_dir))
        if add_result.get("status") != "success":
            return {"status": "error", "message": f"Failed to stage files: {add_result.get('message')}"}

    # Commit
    commit_result = run_git_command(["commit", "-m", message], cwd=str(repo_dir))
    if "nothing to commit" in commit_result.get("output", "").lower() or "nothing to commit" in commit_result.get("message", "").lower():
        return {"status": "success", "message": "No changes to commit"}

    if commit_result.get("status") != "success":
        return {"status": "error", "message": get_error_message("gershwin_github", "commit", commit_result.get("message", "Unknown error"))}

    return {
        "status": "success",
        "message": get_success_message("gershwin_github", "commit", {"message": message}),
        "output": commit_result.get("output", "")
    }


# ============================================================================
# BRANCH OPERATIONS
# ============================================================================

def create_branch(params):
    """
    Create a new branch from base.
    Required: repo_name, branch_name
    Optional: base_branch (defaults to config default_branch)
    """
    repo_name = params.get("repo_name")
    branch_name = params.get("branch_name")
    if not repo_name:
        return {"status": "error", "message": "repo_name is required"}
    if not branch_name:
        return {"status": "error", "message": "branch_name is required"}

    config = load_config()
    base_branch = params.get("base_branch", config.get("default_branch", "main"))
    org = config.get("default_org", "")
    full_name = f"{org}/{repo_name}" if org and "/" not in repo_name else repo_name

    # Use gh api to create branch via refs
    # First get the SHA of the base branch
    sha_args = ["api", f"repos/{full_name}/git/ref/heads/{base_branch}", "--jq", ".object.sha"]
    sha_result = run_gh_command(sha_args)
    if sha_result.get("status") != "success":
        return {"status": "error", "message": f"Failed to get base branch SHA: {sha_result.get('message')}"}

    base_sha = sha_result.get("output", "").strip()
    if not base_sha:
        return {"status": "error", "message": f"Could not find base branch: {base_branch}"}

    # Create new branch
    create_args = [
        "api", f"repos/{full_name}/git/refs",
        "-X", "POST",
        "-f", f"ref=refs/heads/{branch_name}",
        "-f", f"sha={base_sha}"
    ]
    create_result = run_gh_command(create_args)
    if create_result.get("status") != "success":
        return {"status": "error", "message": get_error_message("gershwin_github", "create_branch", create_result.get("message", "Unknown error"))}

    return {
        "status": "success",
        "message": get_success_message("gershwin_github", "create_branch", {"branch_name": branch_name}),
        "branch": branch_name,
        "base": base_branch
    }


def list_branches(params):
    """
    List branches in a repository.
    Required: repo_name
    """
    repo_name = params.get("repo_name")
    if not repo_name:
        return {"status": "error", "message": "repo_name is required"}

    config = load_config()
    org = config.get("default_org", "")
    full_name = f"{org}/{repo_name}" if org and "/" not in repo_name else repo_name

    args = ["api", f"repos/{full_name}/branches", "--jq", ".[].name"]
    result = run_gh_command(args)
    if result.get("status") == "success":
        branches = [b.strip() for b in result["output"].split("\n") if b.strip()]
        return {
            "status": "success",
            "message": get_success_message("gershwin_github", "list_branches", {"count": len(branches)}),
            "branches": branches,
            "count": len(branches)
        }
    return {
        "status": "error",
        "message": get_error_message("gershwin_github", "list_branches", result.get("message", "Unknown error"))
    }


# ============================================================================
# PR WORKFLOW
# ============================================================================

def open_pr(params):
    """
    Open a pull request.
    Required: repo_name, head_branch, title
    Optional: base_branch (defaults to config default_branch), body
    """
    repo_name = params.get("repo_name")
    head_branch = params.get("head_branch")
    title = params.get("title")
    if not repo_name:
        return {"status": "error", "message": "repo_name is required"}
    if not head_branch:
        return {"status": "error", "message": "head_branch is required"}
    if not title:
        return {"status": "error", "message": "title is required"}

    config = load_config()
    base_branch = params.get("base_branch", config.get("default_branch", "main"))
    body = params.get("body", "")
    org = config.get("default_org", "")
    full_name = f"{org}/{repo_name}" if org and "/" not in repo_name else repo_name

    args = ["pr", "create", "--repo", full_name, "--head", head_branch, "--base", base_branch, "--title", title]
    if body:
        args.extend(["--body", body])

    result = run_gh_command(args)
    if result.get("status") == "success":
        pr_url = result.get("output", "").strip()
        # Extract PR number from URL (e.g., https://github.com/org/repo/pull/42)
        pr_number = pr_url.split("/")[-1] if pr_url else "?"
        return {
            "status": "success",
            "message": get_success_message("gershwin_github", "open_pr", {"pr_number": pr_number, "pr_url": pr_url}),
            "pr_url": pr_url
        }
    return {
        "status": "error",
        "message": get_error_message("gershwin_github", "open_pr", result.get("message", "Unknown error"))
    }


def merge_pr(params):
    """
    Merge an open pull request.
    Required: repo_name, pr_number
    Optional: merge_method (merge, squash, rebase - defaults to merge)
    """
    repo_name = params.get("repo_name")
    pr_number = params.get("pr_number")
    if not repo_name:
        return {"status": "error", "message": "repo_name is required"}
    if not pr_number:
        return {"status": "error", "message": "pr_number is required"}

    config = load_config()
    merge_method = params.get("merge_method", "merge")
    org = config.get("default_org", "")
    full_name = f"{org}/{repo_name}" if org and "/" not in repo_name else repo_name

    args = ["pr", "merge", str(pr_number), "--repo", full_name]
    if merge_method == "squash":
        args.append("--squash")
    elif merge_method == "rebase":
        args.append("--rebase")
    else:
        args.append("--merge")
    args.append("--delete-branch")

    result = run_gh_command(args)
    if result.get("status") == "success":
        return {
            "status": "success",
            "message": get_success_message("gershwin_github", "merge_pr", {"pr_number": pr_number}),
            "pr_number": pr_number
        }
    return {
        "status": "error",
        "message": get_error_message("gershwin_github", "merge_pr", result.get("message", "Unknown error"))
    }


# ============================================================================
# ISSUE TRACKING
# ============================================================================

def list_issues(params):
    """
    List issues in a repository.
    Required: repo_name
    Optional: state (open, closed, all - defaults to open), labels, limit
    """
    repo_name = params.get("repo_name")
    if not repo_name:
        return {"status": "error", "message": "repo_name is required"}

    config = load_config()
    state = params.get("state", "open")
    labels = params.get("labels", "")
    limit = params.get("limit", 30)
    org = config.get("default_org", "")
    full_name = f"{org}/{repo_name}" if org and "/" not in repo_name else repo_name

    args = ["issue", "list", "--repo", full_name, "--state", state, "--limit", str(limit), "--json", "number,title,state,labels,createdAt,author"]
    if labels:
        args.extend(["--label", labels])

    result = run_gh_command(args)
    if result.get("status") == "success":
        try:
            issues = json.loads(result["output"])
            return {
                "status": "success",
                "message": get_success_message("gershwin_github", "list_issues", {"count": len(issues)}),
                "issues": issues,
                "count": len(issues)
            }
        except json.JSONDecodeError:
            return {"status": "success", "output": result["output"]}
    return {
        "status": "error",
        "message": get_error_message("gershwin_github", "list_issues", result.get("message", "Unknown error"))
    }


def create_issue(params):
    """
    Create a new issue.
    Required: repo_name, title
    Optional: body, labels (comma-separated), assignees (comma-separated)
    """
    repo_name = params.get("repo_name")
    title = params.get("title")
    if not repo_name:
        return {"status": "error", "message": "repo_name is required"}
    if not title:
        return {"status": "error", "message": "title is required"}

    config = load_config()
    body = params.get("body", "")
    labels = params.get("labels", "")
    assignees = params.get("assignees", "")
    org = config.get("default_org", "")
    full_name = f"{org}/{repo_name}" if org and "/" not in repo_name else repo_name

    args = ["issue", "create", "--repo", full_name, "--title", title]
    if body:
        args.extend(["--body", body])
    if labels:
        args.extend(["--label", labels])
    if assignees:
        args.extend(["--assignee", assignees])

    result = run_gh_command(args)
    if result.get("status") == "success":
        issue_url = result.get("output", "").strip()
        # Extract issue number from URL
        issue_number = issue_url.split("/")[-1] if issue_url else "?"
        return {
            "status": "success",
            "message": get_success_message("gershwin_github", "create_issue", {"issue_number": issue_number}),
            "issue_url": issue_url
        }
    return {
        "status": "error",
        "message": get_error_message("gershwin_github", "create_issue", result.get("message", "Unknown error"))
    }


def close_issue(params):
    """
    Close an issue.
    Required: repo_name, issue_number
    Optional: comment (add a comment before closing)
    """
    repo_name = params.get("repo_name")
    issue_number = params.get("issue_number")
    if not repo_name:
        return {"status": "error", "message": "repo_name is required"}
    if not issue_number:
        return {"status": "error", "message": "issue_number is required"}

    config = load_config()
    comment = params.get("comment", "")
    org = config.get("default_org", "")
    full_name = f"{org}/{repo_name}" if org and "/" not in repo_name else repo_name

    # Add comment if provided
    if comment:
        comment_args = ["issue", "comment", str(issue_number), "--repo", full_name, "--body", comment]
        run_gh_command(comment_args)

    # Close issue
    args = ["issue", "close", str(issue_number), "--repo", full_name]
    result = run_gh_command(args)
    if result.get("status") == "success":
        return {
            "status": "success",
            "message": get_success_message("gershwin_github", "close_issue", {"issue_number": issue_number}),
            "issue_number": issue_number
        }
    return {
        "status": "error",
        "message": get_error_message("gershwin_github", "close_issue", result.get("message", "Unknown error"))
    }


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def execute(action, params):
    """Main execution router using if/elif pattern."""
    if action == "create_repo":
        result = create_repo(params)
    elif action == "push_code":
        result = push_code(params)
    elif action == "commit":
        result = commit(params)
    elif action == "list_repos":
        result = list_repos(params)
    elif action == "get_repo":
        result = get_repo(params)
    elif action == "create_branch":
        result = create_branch(params)
    elif action == "list_branches":
        result = list_branches(params)
    elif action == "open_pr":
        result = open_pr(params)
    elif action == "merge_pr":
        result = merge_pr(params)
    elif action == "list_issues":
        result = list_issues(params)
    elif action == "create_issue":
        result = create_issue(params)
    elif action == "close_issue":
        result = close_issue(params)
    else:
        result = {"status": "error", "message": f"Unknown action: {action}"}

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"status": "error", "message": "Usage: python gershwin_github.py <action> [params_json]"}))
        sys.exit(1)

    action = sys.argv[1]
    params = {}
    if len(sys.argv) > 2:
        try:
            params = json.loads(sys.argv[2])
        except json.JSONDecodeError:
            print(json.dumps({"status": "error", "message": "Invalid JSON params"}))
            sys.exit(1)

    result = execute(action, params)
    print(json.dumps(result, indent=2))
