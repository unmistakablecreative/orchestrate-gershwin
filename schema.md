# OrchestrateOS Schema

Auto-generated tool and action reference.

---

## automation_engine 🔒

Event-driven automation engine for triggering workflows.

**Actions:**
- `add_event_type`
- `add_rule`
- `delete_rule`
- `dry_run_rule`
- `get_event_types`
- `get_execution_history`
- `get_rule`
- `get_rules`
- `list_rules`
- `retry_failed`
- `run_engine`
- `toggle_rule_enabled`
- `update_rule`
- `validate_rule`

## buffer_engine 🔒

Schedule and auto-publish content to social media platforms.

**Actions:**
- `buffer_loop`
- `post_to_platform`

## bullet_journal

Rapid capture for tasks, notes, and events.

**Actions:**
- `add_entry`
- `batch_add_entries`
- `batch_delete_entries`
- `batch_update_status`
- `delete_entry`
- `get_collections`
- `list_entries`
- `update_status`

## check_credits

View your remaining unlock credits and tools currently unlocked.

**Actions:**
- `check_credits`

## claude_assistant 🔒

Task queue for Claude Code autonomous execution.

**Actions:**
- `assign_task`
- `cancel_task`
- `check_task_status`
- `clear_queue`
- `execute_queue`
- `get_staged_tasks`
- `log_task_completion`
- `mark_task_in_progress`
- `process_queue`
- `stage_task`

## doc_editor

Create, search, and link documents with bidirectional links.

**Actions:**
- `append_doc`
- `create_doc`
- `delete_doc`
- `link_docs`
- `list_docs`
- `read_backlinks`
- `read_doc`
- `read_links`
- `replace_section`
- `retrieve_doc`
- `search_docs`
- `search_within_doc`
- `unlink_docs`
- `update_doc`

## github_tool_universal 🔒

Manage repos, commits, and pushes to GitHub from within GPT.

**Actions:**
- `add_files`
- `archive_repo`
- `clone_repo`
- `commit_repo`
- `init_repo`
- `list_repos`
- `pull_repo`
- `push_repo`
- `set_remote`
- `status`

## ideogram_tool 🔒

Generate beautiful AI-driven images for documents or social posts.

**Actions:**
- `generate_image`

## json_manager

Save and manage tasks, notes, ideas, or any structured info.

**Actions:**
- `add_json_entry`
- `batch_add_json_entries`
- `create_json_file`
- `list_json_entries`
- `read_json_entry`
- `read_json_file`
- `update_json_entry`

## readwise_tool 🔒

Import and explore highlights from your synced Readwise library.

**Actions:**
- `fetch_books`
- `fetch_highlights`

## refer_user

Generate a referral package to share with others.

**Actions:**
- `refer_user`

## session_tool

Thread/session state management.

## system_settings

Manage core config — tools, memory files, routing, and credentials.

**Actions:**
- `add_action`
- `add_memory_file`
- `add_tool`
- `build_working_memory`
- `list_memory_files`
- `list_supported_actions`
- `list_tools`
- `refresh_runtime`
- `remove_action`
- `remove_memory_file`
- `remove_tool`
- `set_credential`

## terminal

Run safe shell commands, tail logs, or stream live output.

**Actions:**
- `append_file`
- `check_safe`
- `find_file`
- `ls`
- `move_file`
- `read_file`
- `run_terminal_command`
- `script`
- `stream`
- `tail`
- `write_file`

## unlock_tool

Manually unlock tools using credits or referral triggers.

**Actions:**
- `get_credits_balance`
- `list_marketplace_tools`
- `unlock_tool`
