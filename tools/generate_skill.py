#!/usr/bin/env python3
"""
Generate Skill - Creates orchestrate-gershwin.skill for Claude Code
Reads system_settings.ndjson + orchestrate_app_store.json, injects ngrok domain,
outputs .skill zip file containing SKILL.md + schema.md
"""

import os
import sys
import json
import argparse
import zipfile
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUNTIME_DIR = os.path.dirname(BASE_DIR)
SYSTEM_REGISTRY = os.path.join(RUNTIME_DIR, "system_settings.ndjson")
APP_STORE_PATH = os.path.join(RUNTIME_DIR, "data", "orchestrate_app_store.json")
STATE_DIR = os.path.expanduser("~/Library/Application Support/OrchestrateOS")
NGROK_CONFIG_PATH = os.path.join(RUNTIME_DIR, "data", "ngrok.json")
OUTPUT_DIR = os.path.expanduser("~/Downloads")


def load_ngrok_domain():
    """Load ngrok domain from config"""
    try:
        with open(NGROK_CONFIG_PATH, 'r') as f:
            config = json.load(f)
            return config.get("domain", "YOUR_NGROK_DOMAIN")
    except Exception:
        return "YOUR_NGROK_DOMAIN"


def load_system_registry():
    """Load tools and actions from system_settings.ndjson"""
    tools = {}
    try:
        with open(SYSTEM_REGISTRY, 'r') as f:
            for line in f:
                if line.strip():
                    entry = json.loads(line.strip())
                    tool_name = entry.get("tool")
                    action = entry.get("action")

                    if not tool_name:
                        continue

                    if tool_name not in tools:
                        tools[tool_name] = {
                            "description": entry.get("description", ""),
                            "locked": entry.get("locked", False),
                            "actions": []
                        }

                    if action and action != "__tool__":
                        tools[tool_name]["actions"].append({
                            "name": action,
                            "description": entry.get("description", ""),
                            "params": entry.get("params", {})
                        })
    except Exception as e:
        print(f"Warning: Could not load system registry: {e}", file=sys.stderr)

    return tools


def load_app_store():
    """Load marketplace tools from orchestrate_app_store.json"""
    try:
        with open(APP_STORE_PATH, 'r') as f:
            data = json.load(f)
            return data.get("entries", {})
    except Exception:
        return {}


def generate_skill_md(domain, tools, app_store):
    """Generate SKILL.md content"""

    # Get unlocked tools
    unlocked_tools = {k: v for k, v in tools.items() if not v.get("locked", True)}

    skill_md = f"""---
name: orchestrate-gershwin
description: OrchestrateOS - Your personal AI operating system. Execute tasks, manage tools, and automate workflows via natural language.
---

# OrchestrateOS Skill

Your personal AI operating system running at `https://{domain}`

## How to Execute Tasks

All commands go through the `/execute_task` endpoint:

```bash
curl -X POST "https://{domain}/execute_task" \\
  -H "Content-Type: application/json" \\
  -d '{{
    "tool_name": "TOOL_NAME",
    "action": "ACTION_NAME",
    "params": {{}}
  }}'
```

## Available Tools

"""

    # Add unlocked tools
    for tool_name, tool_data in sorted(unlocked_tools.items()):
        actions = tool_data.get("actions", [])
        if not actions:
            continue

        skill_md += f"### {tool_name}\n\n"

        for action in actions[:5]:  # Limit to 5 actions per tool
            action_name = action.get("name", "")
            desc = action.get("description", "")[:100]
            skill_md += f"- `{action_name}` - {desc}\n"

        if len(actions) > 5:
            skill_md += f"- ... and {len(actions) - 5} more actions\n"

        skill_md += "\n"

    # Add marketplace section
    skill_md += """## Marketplace Tools

The following tools can be unlocked with referral credits:

"""

    for tool_name, meta in sorted(app_store.items(), key=lambda x: x[1].get("priority", 99)):
        label = meta.get("label", tool_name)
        desc = meta.get("description", "")[:80]
        cost = meta.get("referral_unlock_cost", 0)
        skill_md += f"- **{label}** ({cost} credits) - {desc}\n"

    skill_md += f"""

## Quick Reference

### Check Credits
```bash
curl -X POST "https://{domain}/execute_task" \\
  -H "Content-Type: application/json" \\
  -d '{{"tool_name": "check_credits", "action": "check_credits", "params": {{}}}}'
```

### Unlock a Tool
```bash
curl -X POST "https://{domain}/execute_task" \\
  -H "Content-Type: application/json" \\
  -d '{{"tool_name": "unlock_tool", "action": "unlock_tool", "params": {{"tool_name": "TOOL_NAME"}}}}'
```

### Refer a Friend (+3 credits)
```bash
curl -X POST "https://{domain}/execute_task" \\
  -H "Content-Type: application/json" \\
  -d '{{"tool_name": "refer_user", "action": "refer_user", "params": {{"name": "Friend Name", "email": "friend@email.com"}}}}'
```

## Dashboard

View your tools and credits at: `https://{domain}/semantic_memory/tool_dashboard.html`

---
Generated: {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")} UTC
"""

    return skill_md


def generate_schema_md(domain, tools):
    """Generate schema.md with detailed action schemas"""

    schema_md = f"""# OrchestrateOS Action Schema

Base URL: `https://{domain}`

## Endpoint

POST `/execute_task`

### Request Format

```json
{{
  "tool_name": "string",
  "action": "string",
  "params": {{}}
}}
```

### Response Format

```json
{{
  "status": "success|error",
  "message": "string",
  ...additional fields based on action
}}
```

## Tool Actions

"""

    unlocked_tools = {k: v for k, v in tools.items() if not v.get("locked", True)}

    for tool_name, tool_data in sorted(unlocked_tools.items()):
        actions = tool_data.get("actions", [])
        if not actions:
            continue

        schema_md += f"### {tool_name}\n\n"

        for action in actions:
            action_name = action.get("name", "")
            desc = action.get("description", "")
            params = action.get("params", {})

            schema_md += f"#### `{action_name}`\n\n"
            schema_md += f"{desc}\n\n"

            if params:
                schema_md += "**Parameters:**\n```json\n"
                schema_md += json.dumps(params, indent=2)
                schema_md += "\n```\n\n"
            else:
                schema_md += "**Parameters:** None required\n\n"

        schema_md += "---\n\n"

    return schema_md


def generate_skill(params=None):
    """Main function to generate .skill file"""

    # Ensure output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Load data
    domain = load_ngrok_domain()
    tools = load_system_registry()
    app_store = load_app_store()

    if domain == "YOUR_NGROK_DOMAIN":
        return {
            "status": "error",
            "message": "ngrok domain not configured. Run installer first."
        }

    # Generate content
    skill_md = generate_skill_md(domain, tools, app_store)
    schema_md = generate_schema_md(domain, tools)

    # Create .skill zip file
    skill_filename = "orchestrate-gershwin.skill"
    skill_path = os.path.join(OUTPUT_DIR, skill_filename)

    with zipfile.ZipFile(skill_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Must be in a folder matching skill name for Claude to accept it
        zf.writestr("orchestrate-gershwin/SKILL.md", skill_md)

    file_size = os.path.getsize(skill_path)

    return {
        "status": "success",
        "message": f"Skill file generated: {skill_path}",
        "skill_path": skill_path,
        "file_size_bytes": file_size,
        "domain": domain,
        "tools_included": len([t for t in tools.values() if not t.get("locked", True)]),
        "marketplace_tools": len(app_store),
        "instructions": f"""
To use this skill with Claude Code:

1. Open Claude Code
2. Click Settings > Skills
3. Click "Install from file"
4. Select: {skill_path}

Your OrchestrateOS skill will be active for all Claude Code sessions.
"""
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()

    params = json.loads(args.params) if args.params else {}

    if args.action == 'generate_skill':
        result = generate_skill(params)
    else:
        result = {'status': 'error', 'message': f'Unknown action {args.action}'}

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
