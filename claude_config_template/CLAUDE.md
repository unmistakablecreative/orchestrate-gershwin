# OrchestrateOS - Claude Code Configuration

## Core Principles

- **Speed over perfection** - Ship fast, iterate faster
- **Fire-and-forget** - Use execution_hub.py, don't wait for confirmations
- **No verbosity** - Direct, concise responses only

## Tool Usage

**ALL tool calls go through execution_hub.py:**

```bash
python3 execution_hub.py execute_task --params '{
  "tool_name": "tool_name",
  "action": "action_name",
  "params": { ... }
}'
```

**DO NOT** call tools directly (blocked by permissions).

## Available Tools

The following tools are available via execution_hub:

| Tool | Description |
|------|-------------|
| `account` | Account management and settings |
| `buffer_engine` | Content buffer and scheduling |
| `claude_assistant` | Task queue processing |
| `convertkit_tool` | Email marketing integration |
| `docs` | Document creation and editing |
| `docs_vector_indexer` | Document search and indexing |
| `files` | File operations (read, write, grep) |
| `gamma_engine` | Presentation generation |
| `generate_skill` | Skill generation |
| `gershwin_github` | GitHub integration |
| `ideogram_tool` | Image generation |
| `json_manager` | JSON file management |
| `knowledge_vault` | Knowledge base storage |
| `media_manager` | Media file management |
| `mem_tool` | Memory/context management |
| `notion_tool` | Notion integration |
| `nylas_inbox` | Email inbox management |
| `readwise_tool` | Readwise integration |
| `session_tool` | Session management |
| `slide_designer` | Slide deck creation |
| `spark_file` | Quick notes and ideas |
| `system_settings` | System configuration |
| `terminal` | Terminal command execution |
| `todolist` | Todo list management |
| `writing_linter` | Writing quality checks |

## Data File Protection

**NEVER directly edit these files:**
- `data/claude_task_queue.json` → use `claude_assistant` tool
- `data/claude_task_results.json` → use `claude_assistant` tool
- `data/docs.db` → use `docs` tool
- `data/tasks.db` → use `claude_assistant` tool
- `credentials.json` → manual only
- `system_settings.ndjson` → use `system_settings` tool

## Semantic Memory (HTML Interfaces)

Available interfaces in `semantic_memory/`:
- `orchestrate_home.html` - Main dashboard
- `task_board.html` - Task management
- `doc_editor.html` - Document editing
- `spark_file.html` - Quick notes
- `media_manager.html` - Media files
- `todolist.html` - Todo lists
- `bullet_journal.html` - Journal entries
- `tool_dashboard.html` - Tool status

## Behavioral Notes

- User is impatient
- Hates unnecessary explanations
- Values execution over discussion
- If unclear, make best judgment and execute

---

**Remember:** You're here to execute, not to debate.
