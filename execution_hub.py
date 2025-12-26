import os
import json
import subprocess
import argparse
import logging
from system_guard import validate_action, ContractViolation

NDJSON_REGISTRY_FILE = "system_settings.ndjson"
EXECUTION_LOG = "execution_log.json"
DEFAULT_TIMEOUT = 200

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

if not os.path.exists(EXECUTION_LOG):
    with open(EXECUTION_LOG, "w", encoding="utf-8") as f:
        json.dump({"executions": []}, f, indent=4)


def execute_tool(tool_name, action, params):
    registry = load_registry()
    if tool_name not in registry:
        return {"status": "error", "message": f"Tool '{tool_name}' not found."}

    tool_info = registry[tool_name]
    script_path = tool_info.get("path")

    if tool_info.get("locked", False):
        return {
            "status": "locked",
            "message": "Just enter the name and email of someone you want to refer.\nWhen they install Orchestrate, you’ll get instant unlock credits — and you can use those to unlock this tool."
        }

    if not script_path or not os.path.isfile(script_path):
        return {"status": "error", "message": f"Script for '{tool_name}' not found at {script_path}"}

    if action not in tool_info.get("actions", {}):
        return {"status": "error", "message": f"Action '{action}' not supported for tool '{tool_name}'"}

    try:
        validated_params = validate_action(tool_name, action, params)
    except ContractViolation as e:
        return {"status": "error", "message": str(e)}

    command = ["python3", script_path, action, "--params", json.dumps(validated_params)]

    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=DEFAULT_TIMEOUT, check=True)
        stdout_output = result.stdout.strip()
        try:
            output = json.loads(stdout_output)
        except json.JSONDecodeError:
            return {"status": "error", "message": "Invalid JSON output", "raw_output": stdout_output}

        log_execution(tool_name, action, validated_params, "success", output)
        return output

    except subprocess.TimeoutExpired:
        return {"status": "error", "message": f"Tool execution timed out after {DEFAULT_TIMEOUT} seconds."}

    except subprocess.CalledProcessError as e:
        log_execution(tool_name, action, validated_params, "failure", e.stderr.strip())
        return {"status": "error", "message": "Execution failed", "details": e.stderr.strip()}



def load_registry():
    if not os.path.exists(NDJSON_REGISTRY_FILE):
        logging.error("🚨 system_settings.ndjson not found.")
        return {}

    tools = {}

    with open(NDJSON_REGISTRY_FILE, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                tool = entry["tool"]
                action = entry["action"]
                locked = entry.get("locked", False)

                if tool not in tools:
                    tools[tool] = {"path": None, "actions": {}, "locked": False}
                if action == "__tool__":
                    tools[tool]["path"] = entry["script_path"]
                    tools[tool]["locked"] = locked
                else:
                    tools[tool]["actions"][action] = entry.get("params", [])
            except Exception as e:
                logging.warning(f"⚠️ Skipping bad entry in NDJSON: {e}")
    return tools




def log_execution(tool_name, action, params, status, output):
    with open(EXECUTION_LOG, "r", encoding="utf-8") as f:
        log_data = json.load(f)

    log_data["executions"].append({
        "tool": tool_name,
        "action": action,
        "params": params,
        "status": status,
        "output": output
    })

    with open(EXECUTION_LOG, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=4)

def main():
    parser = argparse.ArgumentParser(description="Orchestrate Execution Hub")
    parser.add_argument("action", help="Action to perform")
    parser.add_argument("--params", type=str, required=False, help="JSON-encoded parameters")
    args = parser.parse_args()

    if args.action == "execute_task":
        try:
            params_dict = json.loads(args.params) if args.params else {}
            tool_name = params_dict.get("tool_name")
            action = params_dict.get("action")
            tool_params = params_dict.get("params", {})

            if not tool_name or not action:
                raise ValueError("Missing tool_name or action.")

            result = execute_tool(tool_name, action, tool_params)
            print(json.dumps(result, indent=4))
        except Exception as e:
            logging.error(f"🚨 Exception: {e}")
            print(json.dumps({"status": "error", "message": str(e)}, indent=4))
    else:
        print(json.dumps({"status": "error", "message": "❌ Invalid action."}, indent=4))

if __name__ == "__main__":
    main()