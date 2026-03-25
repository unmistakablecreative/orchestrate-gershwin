# OrchestrateOS Gershwin - Action Schema

Complete reference of all tools, actions, and parameters.

## Endpoint

```
POST /execute_task
Content-Type: application/json
```

### Request Format

```json
{
  "tool_name": "string",
  "action": "string",
  "params": {}
}
```

### Response Format

```json
{
  "status": "success | error",
  "message": "string",
  ...additional fields
}
```

---

# Tools

## json_manager

Save and manage tasks, notes, ideas, or any structured info.

| Action | Parameters | Description |
|--------|------------|-------------|
| `create_json_file` | `filename` (required) | Create a new JSON file |
| `add_json_entry` | `entry_key` (required), `filename` (required), `entry_data` (required) | Add entry to JSON file |
| `batch_add_json_entries` | `entries` (required array), `filename` (required) | Add multiple entries at once |
| `list_json_entries` | `filename` (required), `max_results` (optional), `offset` (optional) | List all entries in file |
| `read_json_entry` | `entry_key` (required), `filename` (required) | Read a specific entry |
| `read_json_file` | `filename` (required) | Read entire JSON file |
| `update_json_entry` | `entry_key` (required), `filename` (required), `new_data` (required) | Update existing entry |

---

## doc_editor

Create, search, and link documents with bidirectional links.

| Action | Parameters | Description |
|--------|------------|-------------|
| `create_doc` | `title` (required), `content` (required), `collection` (required), `convert_markdown` (optional) | Create new document |
| `read_doc` | `doc_id` (required) | Read document by ID |
| `update_doc` | `doc_id` (required), `find` (optional), `replace` (optional), `title` (optional), `collection` (optional) | Update document |
| `delete_doc` | `doc_id` (required) | Delete a document |
| `search_docs` | `query` (required), `max_results` (optional), `status` (optional), `has_field` (optional), `collection` (optional), `min_words` (optional), `max_words` (optional) | Search documents |
| `list_docs` | `collection` (required), `min_words` (optional), `max_words` (optional) | List documents in collection |
| `link_docs` | `source_doc_id` (required), `target_doc_id` (required) | Create bidirectional link |
| `unlink_docs` | `source_doc_id` (required), `target_doc_id` (required) | Remove link between docs |
| `read_links` | `doc_id` (required) | Get outgoing links |
| `read_backlinks` | `doc_id` (required) | Get incoming links |
| `append_doc` | `doc_id` (required), `content` (required), `convert_markdown` (optional) | Append content to doc |
| `replace_section` | `doc_id` (required), `section_header` (required), `new_content` (required), `convert_markdown` (optional) | Replace a section |
| `retrieve_doc` | `title` (required), `collection` (required) | Get doc by title and collection |
| `search_within_doc` | `doc_id` (required), `query` (required) | Search within single doc |

---

## bullet_journal

Rapid capture for tasks, notes, and events.

| Action | Parameters | Description |
|--------|------------|-------------|
| `add_entry` | `collection` (required), `content` (required), `type` (required: task/note/event) | Add single entry |
| `list_entries` | `collection` (optional), `limit` (optional), `status` (optional), `type` (optional) | List entries with filters |
| `update_status` | `entry_key` (required), `status` (required: pending/done/migrated/cancelled) | Update entry status |
| `delete_entry` | `entry_key` (required) | Delete an entry |
| `get_collections` | none | Get all collections |
| `batch_update_status` | `entry_keys` (required array), `status` (required) | Update multiple entries |
| `batch_add_entries` | `entries` (required array of {collection, type, content}) | Add multiple entries |
| `batch_delete_entries` | `entry_keys` (required array) | Delete multiple entries |

---

## terminal

Run safe shell commands, tail logs, or stream live output.

| Action | Parameters | Description |
|--------|------------|-------------|
| `run_terminal_command` | `command` (required) | Execute shell command |
| `find_file` | `filename` (optional), `filename_fragment` (optional), `keyword` (optional) | Search for files |
| `read_file` | `filename` (optional), `filename_fragment` (optional), `path` (optional) | Read file (PDF/DOCX/CSV/HTML/text) |
| `write_file` | `content` (required), `filename` (optional), `path` (optional), `text` (optional) | Write content to file |
| `append_file` | `content` (required), `filename` (optional), `path` (optional), `text` (optional) | Append to file |
| `move_file` | `destination` (required), `from` (optional), `source` (optional), `to` (optional) | Move/rename file |
| `grep_content` | `pattern` (required), `path` (optional), `type` (optional), `max_results` (optional), `case_insensitive` (optional), `context` (optional) | Search file contents |
| `check_safe` | none | Check if command is safe |
| `ls` | none | List directory |
| `script` | none | Run script file |
| `stream` | none | Stream command output |
| `tail` | none | Tail file output |

---

## system_settings

Manage core config - tools, memory files, routing, and credentials.

| Action | Parameters | Description |
|--------|------------|-------------|
| `set_credential` | `tool_name` (required), `value` (required) | Set API credential |
| `add_tool` | `locked` (optional), `referral_unlock_cost` (optional), `script_path` (required), `tool_name` (required) | Register new tool |
| `remove_tool` | `tool_name` (required) | Remove a tool |
| `add_action` | `action_name` (required), `description` (optional), `parameters` (optional), `tool_name` (required) | Add action to tool |
| `remove_action` | `action_name` (required), `tool_name` (required) | Remove action from tool |
| `list_tools` | none | List all registered tools |
| `list_supported_actions` | none | List all supported actions |
| `add_memory_file` | `path` (required) | Add file to working memory |
| `remove_memory_file` | `path` (required) | Remove file from memory |
| `list_memory_files` | none | List all memory files |
| `build_working_memory` | none | Build working memory |
| `refresh_runtime` | none | Refresh runtime config |

---

## unlock_tool

Manually unlock tools using credits or referral triggers.

| Action | Parameters | Description |
|--------|------------|-------------|
| `unlock_tool` | `tool_name` (required) | Unlock a specific tool |
| `list_marketplace_tools` | none | List all marketplace tools |
| `get_credits_balance` | none | Get current credit balance |

---

## check_credits

View your remaining unlock credits and tools currently unlocked.

| Action | Parameters | Description |
|--------|------------|-------------|
| `check_credits` | none | Check credits balance |

---

## refer_user

Generate a referral package to share with others.

| Action | Parameters | Description |
|--------|------------|-------------|
| `refer_user` | `email` (required), `name` (required) | Generate referral (+3 credits) |

---

## session_tool

Thread/session state management.

| Action | Parameters | Description |
|--------|------------|-------------|
| (internal) | - | Manages session state |

---

# Locked Tools (Require Credits)

## readwise_tool (3 credits)

Import and explore highlights from your synced Readwise library.

| Action | Parameters | Description |
|--------|------------|-------------|
| `fetch_books` | `api_key` (optional), `page_size` (optional) | Fetch books from Readwise |
| `fetch_highlights` | `api_key` (optional), `book_title` (required) | Fetch highlights for book |

---

## ideogram_tool (5 credits)

Generate beautiful AI-driven images for documents or social posts.

| Action | Parameters | Description |
|--------|------------|-------------|
| `generate_image` | `input` (required), `options` (optional: aspect_ratio, model) | Generate AI image |

---

## buffer_engine (7 credits)

Schedule and auto-publish content to social media platforms.

| Action | Parameters | Description |
|--------|------------|-------------|
| `buffer_loop` | none | Run buffer posting loop |
| `post_to_platform` | `content` (required) | Post to social platform |

---

## github_tool_universal (7 credits)

Manage repos, commits, and pushes to GitHub from within GPT.

| Action | Parameters | Description |
|--------|------------|-------------|
| `init_repo` | `path` (required) | Initialize git repo |
| `status` | none | Get git status |
| `clone_repo` | `url` (required), `path` (required) | Clone repository |
| `set_remote` | `path` (required), `url` (required) | Set remote URL |
| `add_files` | `path` (required), `files` (required array) | Stage files |
| `commit_repo` | `path` (required), `message` (required) | Commit changes |
| `push_repo` | `path` (required), `branch` (required) | Push to remote |
| `pull_repo` | `path` (required), `branch` (required) | Pull from remote |
| `archive_repo` | none | Archive repository |
| `list_repos` | `root` (optional) | List repositories |

---

## automation_engine (9 credits)

Event-driven automation engine for triggering workflows.

| Action | Parameters | Description |
|--------|------------|-------------|
| `run_engine` | none | Start automation engine |
| `add_rule` | `rule` (required), `rule_key` (required), `skip_validation` (optional) | Add automation rule |
| `update_rule` | `rule` (required), `rule_key` (required), `skip_validation` (optional) | Update existing rule |
| `delete_rule` | `rule_key` (required) | Delete a rule |
| `get_rule` | `rule_key` (required) | Get specific rule |
| `get_rules` | none | Get all rules |
| `list_rules` | none | List rules summary |
| `validate_rule` | `rule` (required) | Validate rule syntax |
| `dry_run_rule` | `file` (optional), `rule_id` (required) | Test rule execution |
| `toggle_rule_enabled` | `enabled` (required), `rule_key` (required) | Enable/disable rule |
| `retry_failed` | `file` (required) | Retry failed entries |
| `get_execution_history` | `limit` (optional), `rule_id` (optional), `since` (optional), `status` (optional) | Get execution logs |
| `add_event_type` | `key` (required), `test` (required) | Add custom event type |
| `get_event_types` | none | Get all event types |

---

## claude_assistant (12 credits)

Task queue for Claude Code autonomous execution.

| Action | Parameters | Description |
|--------|------------|-------------|
| `assign_task` | `description` (required), `priority` (optional), `context` (optional), `create_output_doc` (optional), `doc_id` (optional), `task_id` (optional), `agent_id` (optional), `auto_execute` (optional), `batch_id` (optional), `campaign_id` (optional), `cascade_type` (optional) | Queue a task |
| `check_task_status` | `task_id` (required) | Check task status |
| `process_queue` | `agent_id` (optional), `peek` (optional) | Get queued tasks |
| `execute_queue` | `agent_id` (optional), `parallel` (optional) | Execute queued tasks |
| `stage_task` | `description` (required), `preset` (optional) | Stage task for later |
| `get_staged_tasks` | none | Get staged tasks |
| `cancel_task` | `remove` (optional), `task_id` (required) | Cancel a task |
| `clear_queue` | none | Clear all queued tasks |
| `mark_task_in_progress` | `card_title` (optional), `task_id` (required) | Mark task started |
| `log_task_completion` | `actions_taken` (optional), `card_stat` (optional), `card_title` (optional), `errors` (optional), `execution_time_seconds` (optional), `output` (optional), `output_summary` (optional), `status` (required), `task_id` (required) | Log task completion |

---

*Generated from system_settings.ndjson - OrchestrateOS Gershwin*
