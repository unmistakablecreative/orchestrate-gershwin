#!/usr/bin/env python3
"""
Setup Script Runner

Auto-refactored by refactorize.py to match gold standard structure.
"""

import json
import os
import sys
import subprocess


def run_setup_script(script_path):
    """
    Execute a setup script from the mounted documents directory.

    Args:
        script_path: Relative path to script (e.g., "setup_claude_auth.sh")

    Returns:
        dict with status, message, and optional stdout/stderr
    """
    try:
        # Build full path to mounted setup script
        full_script_path = os.path.join(os.path.expanduser("~/Documents/Orchestrate"), script_path)

        if not os.path.exists(full_script_path):
            return {
                "status": "error",
                "message": f"❌ Setup script not found at {full_script_path}"
            }

        # Make executable
        os.chmod(full_script_path, 0o755)

        print(f"🔧 Executing setup script: {full_script_path}", file=sys.stderr)

        # Execute the script
        result = subprocess.run(
            ["bash", full_script_path],
            capture_output=True,
            text=True,
            timeout=300  # 5 min timeout for OAuth flows
        )

        if result.returncode == 0:
            return {
                "status": "success",
                "message": "✅ Authentication complete! Tool is ready to use.",
                "stdout": result.stdout
            }
        else:
            return {
                "status": "error",
                "message": f"❌ Authentication failed: {result.stderr}",
                "stdout": result.stdout,
                "returncode": result.returncode
            }

    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "message": "⏱️ Authentication timed out after 5 minutes. Please try again."
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"❌ Failed to run setup: {str(e)}"
        }


def main():
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    if args.action == 'run_setup_script':
        result = run_setup_script(**params)
    else:
        result = {'status': 'error', 'message': f'Unknown action {args.action}'}

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()