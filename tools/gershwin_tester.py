#!/usr/bin/env python3
"""
Gershwin Tester - Automated tool validation for installer readiness

Tests each tool action against localhost:5004/execute_task endpoint.
Returns structured results for agent to create a test report doc.

Actions:
- run_all_tests: Execute all test cases from gershwin_test_cases.json
- run_single_test: Run one specific test case
"""

import argparse
import json
import os
import sys
import requests
from datetime import datetime, timezone
from typing import Dict, List, Any

# Constants
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_CASES_FILE = os.path.join(BASE_DIR, "data", "gershwin_test_cases.json")
GERSHWIN_ENDPOINT = "http://localhost:5004/execute_task"


def load_test_cases() -> List[Dict]:
    """Load test cases from JSON file."""
    if not os.path.exists(TEST_CASES_FILE):
        return []
    with open(TEST_CASES_FILE, 'r') as f:
        return json.load(f)


def substitute_variables(params: Dict, captured: Dict) -> Dict:
    """Replace ${var} placeholders with captured values."""
    result = {}
    for key, value in params.items():
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            var_name = value[2:-1]
            result[key] = captured.get(var_name, value)
        elif isinstance(value, dict):
            result[key] = substitute_variables(value, captured)
        else:
            result[key] = value
    return result


def execute_test(tool_name: str, action: str, params: Dict) -> Dict:
    """Execute a single test against the Gershwin endpoint."""
    payload = {
        "tool_name": tool_name,
        "action": action,
        "params": params
    }

    try:
        response = requests.post(GERSHWIN_ENDPOINT, json=payload, timeout=30)
        result = response.json()
        return {
            "http_status": response.status_code,
            "response": result,
            "status": result.get("status", "unknown")
        }
    except requests.exceptions.ConnectionError:
        return {
            "http_status": 0,
            "response": {"error": "Connection refused - is Gershwin server running?"},
            "status": "error"
        }
    except requests.exceptions.Timeout:
        return {
            "http_status": 0,
            "response": {"error": "Request timed out"},
            "status": "error"
        }
    except json.JSONDecodeError:
        return {
            "http_status": response.status_code,
            "response": {"error": "Invalid JSON response", "raw": response.text[:500]},
            "status": "error"
        }
    except Exception as e:
        return {
            "http_status": 0,
            "response": {"error": str(e)},
            "status": "error"
        }


def run_all_tests(params: Dict) -> Dict:
    """
    Run all test cases from gershwin_test_cases.json.

    Returns structured results with pass/fail counts and output_action
    for agent to create a test report doc.
    """
    test_cases = load_test_cases()

    if not test_cases:
        return {
            "status": "error",
            "message": "No test cases found in gershwin_test_cases.json"
        }

    results = []
    passed = 0
    failed = 0
    captured_values = {}

    # Build dependency map
    dependency_map = {}
    for tc in test_cases:
        if tc.get("depends_on"):
            dependency_map[tc["name"]] = tc["depends_on"]

    # Execute tests in order
    for tc in test_cases:
        test_name = tc["name"]
        tool_name = tc["tool_name"]
        action = tc["action"]
        params_raw = tc.get("params", {})
        expected_status = tc.get("expected_status", "success")

        # Check dependency
        if tc.get("depends_on"):
            dep_name = tc["depends_on"]
            dep_result = next((r for r in results if r["name"] == dep_name), None)
            if dep_result and dep_result["passed"] is False:
                results.append({
                    "name": test_name,
                    "tool": tool_name,
                    "action": action,
                    "passed": None,
                    "skipped": True,
                    "reason": f"Dependency {dep_name} failed"
                })
                continue

        # Substitute captured variables
        params_resolved = substitute_variables(params_raw, captured_values)

        # Execute test
        exec_result = execute_test(tool_name, action, params_resolved)

        # Check if passed
        actual_status = exec_result.get("status", "unknown")
        test_passed = (actual_status == expected_status)

        # Capture values if specified
        if tc.get("capture") and test_passed:
            capture_key = tc["capture"]
            response = exec_result.get("response", {})
            # Try common response fields
            captured_value = (
                response.get(capture_key) or
                response.get("id") or
                response.get("deck_id") or
                response.get("task_id") or
                response.get("entry_id")
            )
            if captured_value:
                captured_values[capture_key] = captured_value

        if test_passed:
            passed += 1
        else:
            failed += 1

        results.append({
            "name": test_name,
            "tool": tool_name,
            "action": action,
            "passed": test_passed,
            "expected": expected_status,
            "actual": actual_status,
            "http_status": exec_result.get("http_status"),
            "response_preview": str(exec_result.get("response", {}))[:200]
        })

    # Build report content
    timestamp = datetime.now(timezone.utc).isoformat()
    total = passed + failed
    pass_rate = round((passed / total * 100), 1) if total > 0 else 0

    report_lines = [
        f"# Gershwin Test Report",
        f"",
        f"**Run Time:** {timestamp}",
        f"**Endpoint:** {GERSHWIN_ENDPOINT}",
        f"**Total Tests:** {total}",
        f"**Passed:** {passed}",
        f"**Failed:** {failed}",
        f"**Pass Rate:** {pass_rate}%",
        f"",
        f"---",
        f"",
        f"## Results by Tool",
        f""
    ]

    # Group by tool
    tools_tested = {}
    for r in results:
        tool = r["tool"]
        if tool not in tools_tested:
            tools_tested[tool] = []
        tools_tested[tool].append(r)

    for tool, tool_results in tools_tested.items():
        tool_passed = sum(1 for r in tool_results if r.get("passed") is True)
        tool_total = len(tool_results)
        report_lines.append(f"### {tool} ({tool_passed}/{tool_total})")
        report_lines.append("")

        for r in tool_results:
            if r.get("skipped"):
                icon = "⏭️"
                status_text = f"SKIPPED - {r.get('reason', 'dependency failed')}"
            elif r.get("passed"):
                icon = "✅"
                status_text = "PASS"
            else:
                icon = "❌"
                status_text = f"FAIL (expected {r.get('expected')}, got {r.get('actual')})"

            report_lines.append(f"- {icon} **{r['action']}**: {status_text}")

        report_lines.append("")

    # Add failures detail section if any
    failures = [r for r in results if r.get("passed") is False]
    if failures:
        report_lines.append("---")
        report_lines.append("")
        report_lines.append("## Failure Details")
        report_lines.append("")
        for f in failures:
            report_lines.append(f"### {f['name']}")
            report_lines.append(f"- Tool: {f['tool']}")
            report_lines.append(f"- Action: {f['action']}")
            report_lines.append(f"- HTTP Status: {f.get('http_status')}")
            report_lines.append(f"- Response: {f.get('response_preview', 'N/A')}")
            report_lines.append("")

    report_content = "\n".join(report_lines)

    return {
        "status": "success",
        "pass_count": passed,
        "fail_count": failed,
        "total": total,
        "pass_rate": pass_rate,
        "results": results,
        "report_content": report_content,
        "output_action": {
            "instruction": "Create a doc with the test report using docs.create_doc",
            "tool_name": "docs",
            "action": "create_doc",
            "params": {
                "title": f"Gershwin Test Report - {timestamp[:10]}",
                "content": report_content,
                "collection": "Test Reports",
                "convert_markdown": True
            }
        },
        "message": f"Gershwin test suite complete: {passed}/{total} passed ({pass_rate}%). Create a doc with the report."
    }


def run_system_check(params: Dict) -> Dict:
    """
    Check the health of the Gershwin installation environment.
    Verifies LaunchAgents, ngrok, identity, Turso, directories, and deps.
    Returns structured pass/fail per check.
    """
    import subprocess
    import importlib

    checks = []
    home = os.path.expanduser("~")
    app_support = os.path.join(home, "Library", "Application Support", "OrchestrateOS")
    identity_path = os.path.join(app_support, "data", "system_identity.json")
    ngrok_bin = os.path.join(home, ".local", "bin", "ngrok")

    def check(name, passed, detail=""):
        checks.append({"name": name, "passed": passed, "detail": detail})

    # 1. Jarvis responding on 5004
    try:
        r = requests.get("http://localhost:5004/", timeout=5)
        check("Jarvis running on :5004", True, f"HTTP {r.status_code}")
    except Exception as e:
        check("Jarvis running on :5004", False, str(e))

    # 2. system_identity.json exists and fully populated
    required_identity_fields = ["user_id", "name", "ngrok_url", "ngrok_authtoken"]
    if os.path.exists(identity_path):
        try:
            with open(identity_path) as f:
                identity = json.load(f)
            missing = [k for k in required_identity_fields if not identity.get(k)]
            if missing:
                check("system_identity.json populated", False, f"Missing fields: {missing}")
            else:
                check("system_identity.json populated", True, f"user_id={identity.get('user_id')}")
        except Exception as e:
            check("system_identity.json populated", False, str(e))
    else:
        check("system_identity.json exists", False, f"Not found at {identity_path}")
        identity = {}

    # 3. ngrok binary exists
    check("ngrok binary at ~/.local/bin/ngrok", os.path.exists(ngrok_bin), ngrok_bin)

    # 4. ngrok process running
    try:
        result = subprocess.run(["pgrep", "-x", "ngrok"], capture_output=True, text=True)
        running = result.returncode == 0
        check("ngrok process running", running, result.stdout.strip() if running else "not found")
    except Exception as e:
        check("ngrok process running", False, str(e))

    # 5. LaunchAgents loaded
    for agent in ["io.orchestrateos.jarvis", "io.orchestrateos.ngrok"]:
        try:
            result = subprocess.run(["launchctl", "list", agent], capture_output=True, text=True)
            loaded = result.returncode == 0
            check(f"LaunchAgent: {agent}", loaded, "loaded" if loaded else result.stderr.strip())
        except Exception as e:
            check(f"LaunchAgent: {agent}", False, str(e))

    # 6. Required directories exist
    required_dirs = [
        os.path.join(app_support, "data"),
        os.path.join(app_support, "semantic_memory"),
        os.path.join(home, "Library", "Logs", "OrchestrateOS"),
    ]
    for d in required_dirs:
        check(f"Directory exists: {d.replace(home, '~')}", os.path.exists(d))

    # 7. Critical Python deps importable
    critical_deps = ["fastapi", "uvicorn", "watchdog", "httpx", "requests", "anthropic"]
    for dep in critical_deps:
        try:
            importlib.import_module(dep)
            check(f"Python dep: {dep}", True)
        except ImportError:
            check(f"Python dep: {dep}", False, "not importable")

    # 8. Turso registration — verify user exists
    try:
        user_id = identity.get("user_id", "")
        if user_id:
            r = requests.post(
                "http://localhost:5004/execute_task",
                json={"tool_name": "account", "action": "get_credits", "params": {}},
                timeout=10
            )
            result = r.json()
            credits = result.get("credits")
            check("Turso registration", result.get("status") == "success", f"credits={credits}")
        else:
            check("Turso registration", False, "no user_id in identity")
    except Exception as e:
        check("Turso registration", False, str(e))

    # Summary
    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)
    all_passed = passed == total
    timestamp = datetime.now(timezone.utc).isoformat()

    return {
        "status": "success",
        "timestamp": timestamp,
        "all_passed": all_passed,
        "passed": passed,
        "total": total,
        "checks": checks
    }


def run_single_test(params: Dict) -> Dict:
    """
    Run a single test case.

    Required:
    - tool_name: tool to test
    - action: action to test
    - params: params to send

    Optional:
    - expected_status: what status to expect (default: success)
    """
    tool_name = params.get("tool_name")
    action = params.get("action")
    test_params = params.get("params", {})
    expected_status = params.get("expected_status", "success")

    if not tool_name or not action:
        return {
            "status": "error",
            "message": "tool_name and action are required"
        }

    exec_result = execute_test(tool_name, action, test_params)
    actual_status = exec_result.get("status", "unknown")
    passed = (actual_status == expected_status)

    return {
        "status": "success",
        "test": {
            "tool": tool_name,
            "action": action,
            "params": test_params
        },
        "passed": passed,
        "expected": expected_status,
        "actual": actual_status,
        "http_status": exec_result.get("http_status"),
        "response": exec_result.get("response"),
        "message": f"Test {'PASSED' if passed else 'FAILED'}: {tool_name}.{action}"
    }


def main():
    parser = argparse.ArgumentParser(description="Gershwin Tester - Tool validation suite")
    parser.add_argument("action", help="Action to perform")
    parser.add_argument("--params", type=str, default="{}", help="JSON params")

    args = parser.parse_args()
    action = args.action

    try:
        params = json.loads(args.params)
    except json.JSONDecodeError as e:
        print(json.dumps({"status": "error", "message": f"Invalid JSON params: {e}"}))
        sys.exit(1)

    if action == "run_all_tests":
        result = run_all_tests(params)
    elif action == "run_single_test":
        result = run_single_test(params)
    elif action == "run_system_check":
        result = run_system_check(params)
    else:
        result = {"status": "error", "message": f"Unknown action: {action}"}

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
