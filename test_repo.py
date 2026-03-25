#!/usr/bin/env python3
"""
test_repo.py - Runs a test suite against a repo's server
Executes tests IN ORDER, capturing values from responses and injecting them into subsequent tests.

Usage: python3 test_repo.py <repo_name>
Example: python3 test_repo.py 8th-harmony
"""

import subprocess
import time
import requests
import json
import sys
import os

REPO_INDEX_PATH = "/Users/srinivas/Orchestrate Github/orchestrate-jarvis/data/repo_index.json"


def load_repo_config(repo_name: str) -> dict:
    """Load repo configuration from repo_index.json."""
    with open(REPO_INDEX_PATH) as f:
        index = json.load(f)

    if repo_name not in index:
        print(f"❌ Unknown repo: '{repo_name}'")
        print(f"Available repos: {', '.join(index.keys())}")
        sys.exit(1)

    return index[repo_name]


def start_jarvis(repo_dir: str, port: int):
    """Start jarvis server and wait for it to be ready."""
    base_url = f"http://localhost:{port}"
    proc = subprocess.Popen(
        ["/Users/srinivas/venv/bin/uvicorn", "jarvis:app", "--host", "0.0.0.0", "--port", str(port)],
        cwd=repo_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    # Wait for server to be ready
    for _ in range(30):
        try:
            r = requests.get(f"{base_url}/", timeout=1)
            if r.status_code == 200:
                print(f"✅ Jarvis started on port {port}")
                return proc
        except Exception:
            pass
        time.sleep(0.5)

    proc.kill()
    raise RuntimeError(f"Failed to start jarvis on port {port}")


def extract_value(data: dict, key: str):
    """Extract a value from response data, handling nested structures."""
    # Direct key access
    if key in data:
        return data[key]

    # Check in common response wrappers
    for wrapper in ["result", "data", "response"]:
        if wrapper in data and isinstance(data[wrapper], dict):
            if key in data[wrapper]:
                return data[wrapper][key]

    # Check if the entire response is the value (for simple returns)
    if isinstance(data.get("result"), str) and key == "doc_id":
        return data["result"]

    return None


def inject_captured_values(test: dict, captured: dict) -> dict:
    """Inject captured values into test params based on inject metadata."""
    if "inject" not in test:
        return test

    # Deep copy params to avoid mutating original
    params = dict(test.get("params", {}))

    for injection in test["inject"]:
        capture_from = injection["capture_from"]
        capture_key = injection["capture_key"]
        inject_as = injection["inject_as"]

        if capture_from in captured:
            captured_data = captured[capture_from]
            value = extract_value(captured_data, capture_key) if isinstance(captured_data, dict) else captured_data

            if value is not None:
                params[inject_as] = value
                print(f"      💉 Injected {inject_as}={value} from {capture_from}")
            else:
                print(f"      ⚠️  Could not extract '{capture_key}' from {capture_from}")

    return {**test, "params": params}


def validate_response(data, expect_error=False):
    """Validate that response has proper structure."""
    if not isinstance(data, dict):
        return False, "Response is not a dict"

    if "status" not in data and "error" not in data:
        return False, "Missing both 'status' and 'error' keys"

    if expect_error:
        is_error = data.get("status") == "error" or "error" in data
        return is_error, "Expected error but got success" if not is_error else "OK"

    # Check for error status
    if data.get("status") == "error":
        return False, f"Got error: {data.get('message', data.get('error', 'unknown'))}"

    return True, "OK"


def run_test(test: dict, captured: dict, index: int, group_name: str, base_url: str) -> dict:
    """Run a single test and return result."""
    tool = test["tool_name"]
    action = test["action"]
    params = test.get("params", {})
    expect_error = test.get("expect_error", False)
    capture_as = test.get("capture_as")

    # Inject any captured values
    test = inject_captured_values(test, captured)
    params = test.get("params", {})

    result = {
        "group": group_name,
        "tool": tool,
        "action": action,
        "passed": False,
        "reason": ""
    }

    try:
        resp = requests.post(
            f"{base_url}/execute_task",
            json={"tool_name": tool, "action": action, "params": params},
            timeout=15
        )

        try:
            data = resp.json()
        except Exception:
            result["reason"] = f"Non-JSON response: {resp.status_code}"
            print(f"  [{index}] {tool}.{action} ❌ Non-JSON response")
            return result

        passed, reason = validate_response(data, expect_error)
        result["passed"] = passed
        result["reason"] = reason
        result["status_code"] = resp.status_code

        # Capture values if this test has capture_as
        if passed and capture_as:
            capture_key = test.get("capture_key")
            if capture_key:
                # Capture specific key
                value = extract_value(data, capture_key)
                if value is not None:
                    captured[capture_as] = {capture_key: value}
                    print(f"      📸 Captured {capture_as}.{capture_key}={value}")
                else:
                    # Store full response for later extraction attempts
                    captured[capture_as] = data
                    print(f"      📸 Captured full response as {capture_as}")
            else:
                # Store full response
                captured[capture_as] = data
                print(f"      📸 Captured full response as {capture_as}")

        status_icon = "✅" if passed else "❌"
        print(f"  [{index}] {tool}.{action} {status_icon}")

    except requests.Timeout:
        result["reason"] = "Timeout (15s)"
        print(f"  [{index}] {tool}.{action} ❌ Timeout")

    except Exception as e:
        result["reason"] = str(e)
        print(f"  [{index}] {tool}.{action} ❌ {str(e)[:50]}")

    return result


def run_group(group: dict, captured: dict, start_index: int, base_url: str) -> tuple:
    """Run all tests in a group, respecting order for stateful groups."""
    group_name = group["group_name"]
    tests = group["tests"]
    ordered = group.get("ordered", False)

    print(f"\n{'='*60}")
    print(f"GROUP: {group_name} ({'ORDERED' if ordered else 'unordered'})")
    print(f"  {group['description']}")
    print(f"{'='*60}")

    results = []
    index = start_index

    for test in tests:
        result = run_test(test, captured, index, group_name, base_url)
        results.append(result)
        index += 1

        # For ordered groups, if a setup test fails (not cleanup), we might want to skip dependent tests
        # But we continue anyway to report all failures
        if ordered and not result["passed"] and not test.get("cleanup", False):
            print(f"      ⚠️  Ordered test failed - subsequent tests may also fail")

    return results, index


def run_tests(test_file: str, base_url: str):
    """Execute all test groups from the test suite."""
    with open(test_file) as f:
        suite = json.load(f)

    print(f"\n🧪 Running {suite['test_count']} tests in {suite['group_count']} groups...\n")

    all_results = []
    captured = {}  # Stores captured values across groups
    index = 1

    for group in suite["groups"]:
        group_results, index = run_group(group, captured, index, base_url)
        all_results.extend(group_results)

    return all_results


def print_summary(results, repo_dir: str):
    """Print test summary and save results."""
    passed = sum(1 for r in results if r["passed"])
    total = len(results)

    print(f"\n{'='*60}")
    print(f"TEST SUITE: {passed}/{total} passed")
    print(f"{'='*60}")

    # Group results by group name
    by_group = {}
    for r in results:
        group = r.get("group", "unknown")
        if group not in by_group:
            by_group[group] = {"passed": 0, "failed": 0, "results": []}
        if r["passed"]:
            by_group[group]["passed"] += 1
        else:
            by_group[group]["failed"] += 1
        by_group[group]["results"].append(r)

    print("\nBy group:")
    for group_name, data in by_group.items():
        status = "✅" if data["failed"] == 0 else "❌"
        print(f"  {status} {group_name}: {data['passed']}/{data['passed'] + data['failed']} passed")

    failures = [r for r in results if not r["passed"]]
    if failures:
        print(f"\n❌ FAILURES ({len(failures)}):")
        for r in failures:
            print(f"  {r['tool']}.{r['action']} — {r['reason']}")

    passes = [r for r in results if r["passed"]]
    if passes:
        print(f"\n✅ PASSED ({len(passes)}):")
        for r in passes:
            print(f"  {r['tool']}.{r['action']}")

    # Save results to file
    results_path = os.path.join(repo_dir, "test_results.json")
    with open(results_path, "w") as f:
        json.dump({
            "passed": passed,
            "total": total,
            "pass_rate": f"{(passed/total*100):.1f}%" if total > 0 else "N/A",
            "by_group": {k: {"passed": v["passed"], "failed": v["failed"]} for k, v in by_group.items()},
            "results": results
        }, f, indent=2)
    print(f"\nResults saved to {results_path}")

    if passed == total:
        print("\n✅ ALL TESTS PASSED")
        sys.exit(0)
    else:
        print(f"\n❌ {total - passed} TESTS FAILED")
        sys.exit(1)


def print_usage():
    """Print usage information."""
    print("Usage: python3 test_repo.py <repo_name>")
    print()
    print("Runs the test suite for the specified repo.")
    print()
    print("Example:")
    print("  python3 test_repo.py 8th-harmony")
    print("  python3 test_repo.py gershwin")
    print()
    print("The repo must be defined in repo_index.json with dir, port, and test_suite.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print_usage()
        sys.exit(1)

    repo_name = sys.argv[1]
    config = load_repo_config(repo_name)

    repo_dir = config["dir"]
    port = config["port"]
    test_file = os.path.join(repo_dir, config["test_suite"])
    base_url = f"http://localhost:{port}"

    print(f"🎯 Testing repo: {repo_name}")
    print(f"   Dir: {repo_dir}")
    print(f"   Port: {port}")
    print(f"   Test suite: {test_file}")

    proc = start_jarvis(repo_dir, port)
    try:
        results = run_tests(test_file, base_url)
        print_summary(results, repo_dir)
    finally:
        proc.terminate()
        proc.wait()
        print("\n🛑 Server stopped")
