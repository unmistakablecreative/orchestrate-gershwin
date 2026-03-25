---
name: orchestrate-gershwin
description: Execute OrchestrateOS Gershwin tools via API. Use when asked to run OrchestrateOS commands, manage JSON data, create/edit documents, capture tasks/notes, run terminal commands, manage system settings, or unlock tools. Triggers on 'orchestrate', 'run task', 'execute task', 'save to json', 'create doc', 'add note', 'bullet journal', 'check credits', or any request matching available tools.
---

# OrchestrateOS Gershwin Skill

OrchestrateOS is a personal AI operating system. This skill lets Claude AI execute tasks against a running Gershwin instance via API.

## Quick Start

All tool calls go through the `/execute_task` endpoint:

```bash
curl -X POST https://YOUR_NGROK_URL/execute_task \
  -H 'Content-Type: application/json' \
  -d '{"tool_name": "TOOL_NAME", "action": "ACTION_NAME", "params": {...}}'
```

Replace `YOUR_NGROK_URL` with the active ngrok tunnel URL.

---

# Core Tools Reference

## json_manager

**Purpose:** Save and manage structured data (tasks, notes, ideas, queues) in JSON files.

### Common Patterns

**Create a new data file:**
```json
{
  "tool_name": "json_manager",
  "action": "create_json_file",
  "params": {"filename": "my_projects.json"}
}
```

**Add an entry:**
```json
{
  "tool_name": "json_manager",
  "action": "add_json_entry",
  "params": {
    "filename": "my_projects.json",
    "entry_key": "proj_001",
    "entry_data": {
      "title": "Build landing page",
      "status": "in_progress",
      "priority": "high"
    }
  }
}
```

**Add multiple entries at once:**
```json
{
  "tool_name": "json_manager",
  "action": "batch_add_json_entries",
  "params": {
    "filename": "ideas.json",
    "entries": [
      {"entry_key": "idea_1", "title": "AI newsletter", "category": "content"},
      {"entry_key": "idea_2", "title": "Podcast series", "category": "content"}
    ]
  }
}
```

**Read specific entry:**
```json
{
  "tool_name": "json_manager",
  "action": "read_json_entry",
  "params": {
    "filename": "my_projects.json",
    "entry_key": "proj_001"
  }
}
```

**List all entries:**
```json
{
  "tool_name": "json_manager",
  "action": "list_json_entries",
  "params": {
    "filename": "my_projects.json",
    "max_results": 20
  }
}
```

**Update an entry:**
```json
{
  "tool_name": "json_manager",
  "action": "update_json_entry",
  "params": {
    "filename": "my_projects.json",
    "entry_key": "proj_001",
    "new_data": {"status": "completed"}
  }
}
```

**Read entire file:**
```json
{
  "tool_name": "json_manager",
  "action": "read_json_file",
  "params": {"filename": "my_projects.json"}
}
```

---

## doc_editor

**Purpose:** Create, search, and link documents with bidirectional linking. Local document database with collections.

### Common Patterns

**Create a new document:**
```json
{
  "tool_name": "doc_editor",
  "action": "create_doc",
  "params": {
    "title": "Meeting Notes - March 2026",
    "content": "## Attendees\n- Alice\n- Bob\n\n## Discussion\n...",
    "collection": "Notes",
    "convert_markdown": true
  }
}
```

**Read a document by ID:**
```json
{
  "tool_name": "doc_editor",
  "action": "read_doc",
  "params": {"doc_id": "abc123"}
}
```

**Retrieve by title and collection:**
```json
{
  "tool_name": "doc_editor",
  "action": "retrieve_doc",
  "params": {
    "title": "Meeting Notes - March 2026",
    "collection": "Notes"
  }
}
```

**Search documents:**
```json
{
  "tool_name": "doc_editor",
  "action": "search_docs",
  "params": {
    "query": "project roadmap",
    "max_results": 10,
    "collection": "Projects"
  }
}
```

**List documents in a collection:**
```json
{
  "tool_name": "doc_editor",
  "action": "list_docs",
  "params": {"collection": "Inbox"}
}
```

**Append to a document:**
```json
{
  "tool_name": "doc_editor",
  "action": "append_doc",
  "params": {
    "doc_id": "abc123",
    "content": "\n\n## Update\nNew section added.",
    "convert_markdown": true
  }
}
```

**Update/replace content:**
```json
{
  "tool_name": "doc_editor",
  "action": "update_doc",
  "params": {
    "doc_id": "abc123",
    "find": "draft",
    "replace": "published"
  }
}
```

**Replace a specific section:**
```json
{
  "tool_name": "doc_editor",
  "action": "replace_section",
  "params": {
    "doc_id": "abc123",
    "section_header": "## Status",
    "new_content": "## Status\n\nCompleted on March 20, 2026.",
    "convert_markdown": true
  }
}
```

**Link documents (bidirectional):**
```json
{
  "tool_name": "doc_editor",
  "action": "link_docs",
  "params": {
    "source_doc_id": "abc123",
    "target_doc_id": "def456"
  }
}
```

**Read document links:**
```json
{
  "tool_name": "doc_editor",
  "action": "read_links",
  "params": {"doc_id": "abc123"}
}
```

**Read backlinks (who links to this doc):**
```json
{
  "tool_name": "doc_editor",
  "action": "read_backlinks",
  "params": {"doc_id": "abc123"}
}
```

**Delete a document:**
```json
{
  "tool_name": "doc_editor",
  "action": "delete_doc",
  "params": {"doc_id": "abc123"}
}
```

**Search within a single document:**
```json
{
  "tool_name": "doc_editor",
  "action": "search_within_doc",
  "params": {
    "doc_id": "abc123",
    "query": "action items"
  }
}
```

---

## bullet_journal

**Purpose:** Rapid capture for tasks, notes, and events. Uses bullet journal method with collections.

### Entry Types
- `task` - Things to do
- `note` - Information to remember
- `event` - Things that happened or scheduled

### Status Values
- `pending` - Not started (default for tasks)
- `done` - Completed
- `migrated` - Moved to another collection
- `cancelled` - No longer needed

### Common Patterns

**Add a task:**
```json
{
  "tool_name": "bullet_journal",
  "action": "add_entry",
  "params": {
    "collection": "Daily",
    "type": "task",
    "content": "Review Q1 metrics"
  }
}
```

**Add a note:**
```json
{
  "tool_name": "bullet_journal",
  "action": "add_entry",
  "params": {
    "collection": "Ideas",
    "type": "note",
    "content": "Idea: Build a Chrome extension for quick capture"
  }
}
```

**Add an event:**
```json
{
  "tool_name": "bullet_journal",
  "action": "add_entry",
  "params": {
    "collection": "March 2026",
    "type": "event",
    "content": "Product launch webinar at 2pm"
  }
}
```

**Batch add multiple entries:**
```json
{
  "tool_name": "bullet_journal",
  "action": "batch_add_entries",
  "params": {
    "entries": [
      {"collection": "Daily", "type": "task", "content": "Email marketing team"},
      {"collection": "Daily", "type": "task", "content": "Update roadmap doc"},
      {"collection": "Daily", "type": "note", "content": "New competitor launched"}
    ]
  }
}
```

**List entries in a collection:**
```json
{
  "tool_name": "bullet_journal",
  "action": "list_entries",
  "params": {
    "collection": "Daily",
    "type": "task",
    "status": "pending",
    "limit": 20
  }
}
```

**Mark task as done:**
```json
{
  "tool_name": "bullet_journal",
  "action": "update_status",
  "params": {
    "entry_key": "entry_20260320_001",
    "status": "done"
  }
}
```

**Batch update status:**
```json
{
  "tool_name": "bullet_journal",
  "action": "batch_update_status",
  "params": {
    "entry_keys": ["entry_001", "entry_002", "entry_003"],
    "status": "done"
  }
}
```

**Delete an entry:**
```json
{
  "tool_name": "bullet_journal",
  "action": "delete_entry",
  "params": {"entry_key": "entry_20260320_001"}
}
```

**Batch delete entries:**
```json
{
  "tool_name": "bullet_journal",
  "action": "batch_delete_entries",
  "params": {
    "entry_keys": ["entry_001", "entry_002"]
  }
}
```

**Get all collections:**
```json
{
  "tool_name": "bullet_journal",
  "action": "get_collections",
  "params": {}
}
```

---

## terminal

**Purpose:** Run shell commands, file operations, and content search. Supports PDF, DOCX, CSV, HTML extraction.

### Common Patterns

**Run a command:**
```json
{
  "tool_name": "terminal",
  "action": "run_terminal_command",
  "params": {"command": "ls -la ~/Documents"}
}
```

**Find a file:**
```json
{
  "tool_name": "terminal",
  "action": "find_file",
  "params": {"keyword": "invoice"}
}
```

**Read a file (auto-detects PDF, DOCX, CSV, HTML, text):**
```json
{
  "tool_name": "terminal",
  "action": "read_file",
  "params": {"path": "~/Documents/report.pdf"}
}
```

**Read file by name fragment:**
```json
{
  "tool_name": "terminal",
  "action": "read_file",
  "params": {"filename_fragment": "budget"}
}
```

**Write a file:**
```json
{
  "tool_name": "terminal",
  "action": "write_file",
  "params": {
    "path": "output/summary.txt",
    "content": "Report generated on March 20, 2026..."
  }
}
```

**Append to a file:**
```json
{
  "tool_name": "terminal",
  "action": "append_file",
  "params": {
    "path": "logs/activity.log",
    "content": "\n2026-03-20: Processed 150 records"
  }
}
```

**Move/rename a file:**
```json
{
  "tool_name": "terminal",
  "action": "move_file",
  "params": {
    "source": "draft.txt",
    "destination": "final.txt"
  }
}
```

**Search file contents (grep):**
```json
{
  "tool_name": "terminal",
  "action": "grep_content",
  "params": {
    "pattern": "TODO",
    "path": "tools",
    "type": "py",
    "case_insensitive": true
  }
}
```

**List files:**
```json
{
  "tool_name": "terminal",
  "action": "list_files",
  "params": {
    "path": "semantic_memory",
    "recursive": true
  }
}
```

---

## system_settings

**Purpose:** Manage core config - tools, memory files, routing, and credentials.

### Common Patterns

**List all tools:**
```json
{
  "tool_name": "system_settings",
  "action": "list_tools",
  "params": {}
}
```

**List all supported actions:**
```json
{
  "tool_name": "system_settings",
  "action": "list_supported_actions",
  "params": {}
}
```

**Add a new tool:**
```json
{
  "tool_name": "system_settings",
  "action": "add_tool",
  "params": {
    "tool_name": "my_custom_tool",
    "script_path": "tools/my_custom_tool.py",
    "locked": false,
    "referral_unlock_cost": 0
  }
}
```

**Remove a tool:**
```json
{
  "tool_name": "system_settings",
  "action": "remove_tool",
  "params": {"tool_name": "my_custom_tool"}
}
```

**Add an action to a tool:**
```json
{
  "tool_name": "system_settings",
  "action": "add_action",
  "params": {
    "tool_name": "my_custom_tool",
    "action_name": "process_data",
    "description": "Process incoming data",
    "parameters": ["input_file", "output_format"]
  }
}
```

**Remove an action:**
```json
{
  "tool_name": "system_settings",
  "action": "remove_action",
  "params": {
    "tool_name": "my_custom_tool",
    "action_name": "process_data"
  }
}
```

**Set API credential:**
```json
{
  "tool_name": "system_settings",
  "action": "set_credential",
  "params": {
    "tool_name": "openai",
    "value": "sk-..."
  }
}
```

**Add memory file:**
```json
{
  "tool_name": "system_settings",
  "action": "add_memory_file",
  "params": {"path": "data/context.json"}
}
```

**Remove memory file:**
```json
{
  "tool_name": "system_settings",
  "action": "remove_memory_file",
  "params": {"path": "data/context.json"}
}
```

**List memory files:**
```json
{
  "tool_name": "system_settings",
  "action": "list_memory_files",
  "params": {}
}
```

**Build working memory:**
```json
{
  "tool_name": "system_settings",
  "action": "build_working_memory",
  "params": {}
}
```

**Refresh runtime:**
```json
{
  "tool_name": "system_settings",
  "action": "refresh_runtime",
  "params": {}
}
```

---

## unlock_tool

**Purpose:** Unlock marketplace tools using credits earned from referrals.

### Common Patterns

**List marketplace tools:**
```json
{
  "tool_name": "unlock_tool",
  "action": "list_marketplace_tools",
  "params": {}
}
```

**Unlock a specific tool:**
```json
{
  "tool_name": "unlock_tool",
  "action": "unlock_tool",
  "params": {"tool_name": "automation_engine"}
}
```

**Check credits balance:**
```json
{
  "tool_name": "unlock_tool",
  "action": "get_credits_balance",
  "params": {}
}
```

---

## check_credits

**Purpose:** View remaining unlock credits and currently unlocked tools.

### Common Patterns

**Check credits:**
```json
{
  "tool_name": "check_credits",
  "action": "check_credits",
  "params": {}
}
```

---

## refer_user

**Purpose:** Generate referral packages to share. Each successful referral earns +3 credits.

### Common Patterns

**Refer a user:**
```json
{
  "tool_name": "refer_user",
  "action": "refer_user",
  "params": {
    "name": "John Smith",
    "email": "john@example.com"
  }
}
```

---

# Quick Reference Examples

## Check Your Credits
```bash
curl -X POST https://YOUR_NGROK_URL/execute_task \
  -H 'Content-Type: application/json' \
  -d '{"tool_name": "check_credits", "action": "check_credits", "params": {}}'
```

## Create a Quick Note
```bash
curl -X POST https://YOUR_NGROK_URL/execute_task \
  -H 'Content-Type: application/json' \
  -d '{"tool_name": "bullet_journal", "action": "add_entry", "params": {"collection": "Daily", "type": "note", "content": "Remember to follow up on proposal"}}'
```

## Save Structured Data
```bash
curl -X POST https://YOUR_NGROK_URL/execute_task \
  -H 'Content-Type: application/json' \
  -d '{"tool_name": "json_manager", "action": "add_json_entry", "params": {"filename": "contacts.json", "entry_key": "john_doe", "entry_data": {"name": "John Doe", "email": "john@example.com"}}}'
```

## Create a Document
```bash
curl -X POST https://YOUR_NGROK_URL/execute_task \
  -H 'Content-Type: application/json' \
  -d '{"tool_name": "doc_editor", "action": "create_doc", "params": {"title": "Project Brief", "content": "# Overview\n\nThis project aims to...", "collection": "Projects", "convert_markdown": true}}'
```

## Unlock a Premium Tool
```bash
curl -X POST https://YOUR_NGROK_URL/execute_task \
  -H 'Content-Type: application/json' \
  -d '{"tool_name": "unlock_tool", "action": "unlock_tool", "params": {"tool_name": "automation_engine"}}'
```

---

# Marketplace Tools (Unlockable)

These tools require credits to unlock:

| Tool | Credits | Description |
|------|---------|-------------|
| readwise_tool | 3 | Import highlights from Readwise library |
| ideogram_tool | 5 | Generate AI images |
| buffer_engine | 7 | Social media scheduling |
| github_tool_universal | 7 | GitHub repo management |
| automation_engine | 9 | Event-driven workflow automation |
| claude_assistant | 12 | Claude Code task queue |

**Earn credits:** Each successful referral = +3 credits

---

*OrchestrateOS Gershwin - Your Personal AI Operating System*
