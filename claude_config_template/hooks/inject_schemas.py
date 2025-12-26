#!/usr/bin/env python3
"""
Auto-inject relevant tool schemas from system_settings.ndjson based on user prompt.
Reduces token bloat by only loading schemas for tools mentioned in the message.
"""
import json
import sys
from pathlib import Path

def extract_tool_names(user_message):
    """Extract potential tool names from user message."""
    settings_path = Path(__file__).parent.parent.parent / "system_settings.ndjson"
    if not settings_path.exists():
        return []

    valid_tools = set()
    with open(settings_path) as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                if "tool" in entry:
                    valid_tools.add(entry["tool"])
            except:
                continue

    # Find tool names mentioned in message
    mentioned_tools = set()
    message_lower = user_message.lower()

    for tool in valid_tools:
        # Check for exact tool name or common variations
        if tool in message_lower or tool.replace("_", " ") in message_lower:
            mentioned_tools.add(tool)

    return mentioned_tools

def get_tool_schemas(tool_names):
    """Get schemas for specific tools from system_settings.ndjson."""
    if not tool_names:
        return ""

    settings_path = Path(__file__).parent.parent.parent / "system_settings.ndjson"
    if not settings_path.exists():
        return ""

    schemas = []
    with open(settings_path) as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                if entry.get("tool") in tool_names:
                    # Only include actions with descriptions (user-facing)
                    if entry.get("description") and entry.get("action") != "__tool__":
                        schemas.append(entry)
            except:
                continue

    return schemas

def format_schema_output(schemas):
    """Format schemas into readable injection text."""
    if not schemas:
        return ""

    output = ["<system-reminder>", "Available Tool Actions (auto-injected):", ""]

    current_tool = None
    for schema in schemas:
        tool = schema["tool"]
        action = schema["action"]

        if tool != current_tool:
            if current_tool is not None:
                output.append("")
            output.append(f"Tool: {tool}")
            current_tool = tool

        output.append(f"  Action: {action}")
        if "params" in schema:
            output.append(f"    Required params: {', '.join(schema['params'])}")
        if "example" in schema:
            output.append(f"    Example: {json.dumps(schema['example'])}")
        if "description" in schema:
            output.append(f"    Description: {schema['description']}")

    output.append("")
    output.append("Use execution_hub.py to call these actions.")
    output.append("</system-reminder>")
    return "\n".join(output)

# Main execution
try:
    input_data = json.load(sys.stdin)
    user_message = input_data.get("prompt", "")

    if not user_message:
        sys.exit(0)

    # Extract and get schemas for mentioned tools
    tool_names = extract_tool_names(user_message)
    if not tool_names:
        sys.exit(0)

    schemas = get_tool_schemas(tool_names)
    output = format_schema_output(schemas)

    if output:
        print(output)

except Exception as e:
    # Silently fail - hooks shouldn't break the workflow
    sys.exit(0)
