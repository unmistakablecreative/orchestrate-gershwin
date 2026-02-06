---
name: orchestrate-gershwin
description: Execute OrchestrateOS Gershwin tools via API. Use when asked to run OrchestrateOS commands, manage tasks, create documents, post to social media, send emails, manage files, search content, or any automation task. Triggers on 'orchestrate', 'run task', 'execute', 'post to twitter', 'create doc', 'assign task', or any request matching available tools in the schema.
---

# OrchestrateOS Gershwin Skill

## Execution Pattern

All tool calls go through the ngrok endpoint via POST to `/execute_task`:

```bash
curl -s -X POST https://YOUR_NGROK_URL/execute_task \
  -H 'Content-Type: application/json' \
  -d '{"tool_name": "tool_name", "action": "action_name", "params": {...}}'
```

Replace `YOUR_NGROK_URL` with the active ngrok tunnel URL.

---

# Tool Schema Reference

## buffer_engine
Schedule and auto-publish content to social media platforms.

```
buffer_loop()
  - Runs the buffer posting loop
  - Params: none
  - Example: {"tool_name": "buffer_engine", "action": "buffer_loop", "params": {}}

post_to_platform(content, link, image_url)
  - Posts content to configured social platform
  - Params: content (required), link (optional), image_url (optional)
  - Example: {"tool_name": "buffer_engine", "action": "post_to_platform", "params": {"content": "This is a tweet.", "link": "https://example.com", "image_url": "https://img.url"}}
```

## check_credits
View your remaining unlock credits and tools currently unlocked.

```
check_credits()
  - Returns current credit balance
  - Params: none
```

## file_ops_tool
**DEPRECATED** - Use `terminal` tool instead. All file operations are now available in the terminal tool.

## github_tool_universal
Manage repos, commits, and pushes to GitHub from within GPT.

```
init_repo(path)
  - Initialize a new git repository
  - Params: path (required)
  - Example: {"tool_name": "github_tool_universal", "action": "init_repo", "params": {"path": "./repo"}}

status(path)
  - Get git status
  - Params: path (required)
  - Example: {"tool_name": "github_tool_universal", "action": "status", "params": {"path": "./repo"}}

clone_repo(url, path)
  - Clone a repository
  - Params: url (required), path (required)
  - Example: {"tool_name": "github_tool_universal", "action": "clone_repo", "params": {"url": "https://github.com/your/repo.git", "path": "./repo"}}

set_remote(path, url)
  - Set remote URL for repository
  - Params: path (required), url (required)
  - Example: {"tool_name": "github_tool_universal", "action": "set_remote", "params": {"path": "./repo", "url": "https://github.com/your/repo.git"}}

add_files(path, files)
  - Stage files for commit
  - Params: path (required), files (required, array)
  - Example: {"tool_name": "github_tool_universal", "action": "add_files", "params": {"path": "./repo", "files": ["file1.py", "file2.txt"]}}

commit_repo(path, message)
  - Commit staged changes
  - Params: path (required), message (required)
  - Example: {"tool_name": "github_tool_universal", "action": "commit_repo", "params": {"path": "./repo", "message": "Initial commit"}}

push_repo(path, branch)
  - Push to remote
  - Params: path (required), branch (required)
  - Example: {"tool_name": "github_tool_universal", "action": "push_repo", "params": {"path": "./repo", "branch": "main"}}

pull_repo(path, branch)
  - Pull from remote
  - Params: path (required), branch (required)
  - Example: {"tool_name": "github_tool_universal", "action": "pull_repo", "params": {"path": "./repo", "branch": "main"}}

archive_repo(path)
  - Archive a repository
  - Params: path (required)
  - Example: {"tool_name": "github_tool_universal", "action": "archive_repo", "params": {"path": "./repo"}}

list_repos()
  - List all repositories
  - Params: none
  - Example: {"tool_name": "github_tool_universal", "action": "list_repos", "params": {}}
```

## ideogram_tool
Generate beautiful AI-driven images for documents or social posts.

```
generate_image(input, options)
  - Generate an image from prompt
  - Params: input (required), options (optional: aspect_ratio, model)
  - Example: {"tool_name": "ideogram_tool", "action": "generate_image", "params": {"input": "A robot in a neon city", "options": {"aspect_ratio": "ASPECT_16_9", "model": "V_2"}}}
```

## json_manager
Save and manage tasks, notes, ideas, or any other structured info across your workspace.

```
create_json_file(filename)
  - Create a new JSON file
  - Params: filename (required)
  - Example: {"tool_name": "json_manager", "action": "create_json_file", "params": {"filename": "gray_content.json"}}

add_json_entry(filename, entry_key, entry_data)
  - Add entry to JSON file
  - Params: filename (required), entry_key (required), entry_data (required)
  - Example: {"tool_name": "json_manager", "action": "add_json_entry", "params": {"filename": "gray_content.json", "entry_key": "adhd_ep1", "entry_data": {"title": "Rituals for Late-Diagnosed Adults"}}}

batch_add_json_entries(filename, entries)
  - Add multiple entries at once
  - Params: filename (required), entries (required, array)
  - Example: {"tool_name": "json_manager", "action": "batch_add_json_entries", "params": {"filename": "gray_content.json", "entries": [{"entry_key": "ep1", "title": "First Episode", "status": "draft"}, {"entry_key": "ep2", "title": "Second Episode", "status": "published"}]}}

list_json_entries(filename)
  - List all entries in a JSON file
  - Params: filename (required)
  - Example: {"tool_name": "json_manager", "action": "list_json_entries", "params": {"filename": "gray_content.json"}}

read_json_entry(filename, entry_key)
  - Read a specific entry
  - Params: filename (required), entry_key (required)
  - Example: {"tool_name": "json_manager", "action": "read_json_entry", "params": {"filename": "gray_content.json", "entry_key": "adhd_ep1"}}

read_json_file(filename)
  - Read entire JSON file
  - Params: filename (required)
  - Example: {"tool_name": "json_manager", "action": "read_json_file", "params": {"filename": "gray_content.json"}}

update_json_entry(filename, entry_key, new_data)
  - Update an existing entry
  - Params: filename (required), entry_key (required), new_data (required)
  - Example: {"tool_name": "json_manager", "action": "update_json_entry", "params": {"filename": "gray_content.json", "entry_key": "adhd_ep1", "new_data": {"status": "published"}}}
```

## mem_tool
Capture personal insights or notes and sync them into Mem.

```
create_note(content)
  - Create a new note
  - Params: content (required)
  - Example: {"tool_name": "mem_tool", "action": "create_note", "params": {"content": "My note content here"}}

read_note(note_id)
  - Read a note by ID
  - Params: note_id (required)
  - Example: {"tool_name": "mem_tool", "action": "read_note", "params": {"note_id": "abc123"}}

delete_note(note_id)
  - Delete a note
  - Params: note_id (required)
  - Example: {"tool_name": "mem_tool", "action": "delete_note", "params": {"note_id": "abc123"}}

mem_it(input, instructions)
  - Process text with optional instructions
  - Params: input (required), instructions (optional)
  - Example: {"tool_name": "mem_tool", "action": "mem_it", "params": {"input": "Text to process", "instructions": "Optional instructions"}}

create_collection(title, description)
  - Create a collection
  - Params: title (required), description (required)
  - Example: {"tool_name": "mem_tool", "action": "create_collection", "params": {"title": "My Collection", "description": "Collection description"}}

delete_collection(collection_id)
  - Delete a collection
  - Params: collection_id (required)
  - Example: {"tool_name": "mem_tool", "action": "delete_collection", "params": {"collection_id": "abc123"}}

ping()
  - Test connection
  - Params: none
  - Example: {"tool_name": "mem_tool", "action": "ping", "params": {}}
```

## outline_editor
Create structured content documents with sections, links, and collections.

```
create_doc(title, content, collectionId, parentDocumentId)
  - Create a new document
  - Params: title (required), content (required), collectionId (optional), parentDocumentId (optional)
  - Example: {"tool_name": "outline_editor", "action": "create_doc", "params": {"title": "Test Title", "content": "Some content here.", "collectionId": "Inbox", "parentDocumentId": null}}

create_collection(name, description, color, icon, permission, sharing)
  - Create a new collection
  - Params: name (required), description (optional), color (optional), icon (optional), permission (optional), sharing (optional)

get_doc(doc_id)
  - Get document by ID
  - Params: doc_id (required)
  - Example: {"tool_name": "outline_editor", "action": "get_doc", "params": {"doc_id": "abc123"}}

get_url(doc_id)
  - Get document URL
  - Params: doc_id (required)
  - Example: {"tool_name": "outline_editor", "action": "get_url", "params": {"doc_id": "abc123"}}

update_doc(doc_id, title, text, append, publish)
  - Update an existing document
  - Params: doc_id (required), title (optional), text (optional), append (optional), publish (optional)
  - Example: {"tool_name": "outline_editor", "action": "update_doc", "params": {"doc_id": "abc123", "title": "Updated Title", "text": "Appended text", "append": true, "publish": false}}

append_section(doc_id, new_text)
  - Append section to document
  - Params: doc_id (required), new_text (required)
  - Example: {"tool_name": "outline_editor", "action": "append_section", "params": {"doc_id": "abc123", "new_text": "## New Section\nText goes here."}}

delete_doc(doc_id)
  - Delete a document
  - Params: doc_id (required)
  - Example: {"tool_name": "outline_editor", "action": "delete_doc", "params": {"doc_id": "abc123"}}

delete_collection(collection_id)
  - Delete a collection
  - Params: collection_id (required)
  - Example: {"tool_name": "outline_editor", "action": "delete_collection", "params": {"collection_id": "abc123"}}

export_doc(doc_id, filename)
  - Export document to file
  - Params: doc_id (required), filename (required)
  - Example: {"tool_name": "outline_editor", "action": "export_doc", "params": {"doc_id": "abc123", "filename": "blog.md"}}

import_doc_from_file(file_path, collectionId, parentDocumentId, template, publish)
  - Import document from file
  - Params: file_path (required), collectionId (optional), parentDocumentId (optional), template (optional), publish (optional)
  - Example: {"tool_name": "outline_editor", "action": "import_doc_from_file", "params": {"file_path": "compiled_posts/post.md", "collectionId": "abc123", "parentDocumentId": null, "template": false, "publish": true}}

list_docs(limit, offset, sort, direction)
  - List documents
  - Params: limit (optional), offset (optional), sort (optional), direction (optional)
  - Example: {"tool_name": "outline_editor", "action": "list_docs", "params": {"limit": 5, "offset": 0, "sort": "createdAt", "direction": "DESC"}}

move_doc(doc_id, collectionId, parentDocumentId)
  - Move document to different collection
  - Params: doc_id (required), collectionId (required), parentDocumentId (optional)
  - Example: {"tool_name": "outline_editor", "action": "move_doc", "params": {"doc_id": "xyz789", "collectionId": "abc123", "parentDocumentId": ""}}

search_docs(query, limit, offset)
  - Search documents
  - Params: query (required), limit (optional), offset (optional)
  - Example: {"tool_name": "outline_editor", "action": "search_docs", "params": {"query": "semantic execution", "limit": 5, "offset": 0}}
```

## readwise_tool
Import and explore highlights from your synced Readwise library.

```
fetch_books(page_size)
  - Fetch books from Readwise
  - Params: page_size (optional)
  - Example: {"tool_name": "readwise_tool", "action": "fetch_books", "params": {"page_size": 10}}

fetch_highlights(book_title)
  - Fetch highlights for a book
  - Params: book_title (required)
  - Example: {"tool_name": "readwise_tool", "action": "fetch_highlights", "params": {"book_title": "Atomic Habits"}}
```

## refer_user
Generate a referral package to share with others. Each successful referral earns 3 unlock credits.

```
refer_user(name, email)
  - Generate referral for a user
  - Params: name (required), email (required)
  - Example: {"tool_name": "refer_user", "action": "refer_user", "params": {"name": "Melissa Lima", "email": "melissa@example.com"}}
```

## system_control
Core system control for loading OrchestrateOS runtime.

```
load_orchestrate_os()
  - Load OrchestrateOS runtime
  - Params: none
  - Example: {"tool_name": "system_control", "action": "load_orchestrate_os", "params": {}}
```

## system_settings
Manage core config — tools, memory files, routing, and credentials.

```
set_credential(tool_name, value)
  - Set credential for a tool
  - Params: tool_name (required), value (required)
  - Example: {"tool_name": "system_settings", "action": "set_credential", "params": {"tool_name": "outline_editor", "value": "sk-outline-abc123"}}

add_tool(tool_name, script_path)
  - Add a new tool
  - Params: tool_name (required), script_path (required)
  - Example: {"tool_name": "system_settings", "action": "add_tool", "params": {"tool_name": "my_tool", "script_path": "tools/my_tool.py"}}

remove_tool(tool_name)
  - Remove a tool
  - Params: tool_name (required)
  - Example: {"tool_name": "system_settings", "action": "remove_tool", "params": {"tool_name": "my_tool"}}

add_action(tool_name, action_name, description, parameters)
  - Add action to a tool
  - Params: tool_name (required), action_name (required), description (optional), parameters (optional)
  - Example: {"tool_name": "system_settings", "action": "add_action", "params": {"tool_name": "json_manager", "action_name": "add_entry", "description": "Add JSON entry", "parameters": [{"name": "filename", "required": true}]}}

remove_action(tool_name, action_name)
  - Remove action from a tool
  - Params: tool_name (required), action_name (required)
  - Example: {"tool_name": "system_settings", "action": "remove_action", "params": {"tool_name": "json_manager", "action_name": "add_entry"}}

list_tools()
  - List all tools
  - Params: none
  - Example: {"tool_name": "system_settings", "action": "list_tools", "params": {}}

list_supported_actions()
  - List all supported actions
  - Params: none
  - Example: {"tool_name": "system_settings", "action": "list_supported_actions", "params": {}}

add_memory_file(path)
  - Add file to working memory
  - Params: path (required)
  - Example: {"tool_name": "system_settings", "action": "add_memory_file", "params": {"path": "data/important_context.json"}}

remove_memory_file(path)
  - Remove file from working memory
  - Params: path (required)
  - Example: {"tool_name": "system_settings", "action": "remove_memory_file", "params": {"path": "data/important_context.json"}}

list_memory_files()
  - List all memory files
  - Params: none
  - Example: {"tool_name": "system_settings", "action": "list_memory_files", "params": {}}

build_working_memory()
  - Build working memory from configured files
  - Params: none
  - Example: {"tool_name": "system_settings", "action": "build_working_memory", "params": {}}

refresh_runtime()
  - Refresh the runtime configuration
  - Params: none
  - Example: {"tool_name": "system_settings", "action": "refresh_runtime", "params": {}}
```

## terminal
Shell commands, file operations, and content search. Supports PDF, DOCX, CSV, HTML extraction.

```
# === Shell Commands ===

run_terminal_command(command)
  - Run a terminal command
  - Params: command (required)
  - Example: {"tool_name": "terminal", "action": "run_terminal_command", "params": {"command": "ls -la"}}

run_script_file(path)
  - Run a script file
  - Params: path (required)
  - Example: {"tool_name": "terminal", "action": "run_script_file", "params": {"path": "./deploy.sh"}}

stream_terminal_output(command)
  - Stream command output
  - Params: command (required)
  - Example: {"tool_name": "terminal", "action": "stream_terminal_output", "params": {"command": "ping google.com"}}

sanitize_command(command)
  - Check if command is safe to run
  - Params: command (required)
  - Example: {"tool_name": "terminal", "action": "sanitize_command", "params": {"command": "ls -la"}}

get_last_n_lines_of_output(command, n)
  - Tail output with line limit
  - Params: command (required), n (optional, default 10)
  - Example: {"tool_name": "terminal", "action": "get_last_n_lines_of_output", "params": {"command": "cat log.txt", "n": 10}}

list_directory_contents(path)
  - List directory contents
  - Params: path (required)
  - Example: {"tool_name": "terminal", "action": "list_directory_contents", "params": {"path": "/Users/srinivas"}}

list_files(path, recursive)
  - List files with optional recursion
  - Params: path (optional, default "."), recursive (optional, default false)
  - Example: {"tool_name": "terminal", "action": "list_files", "params": {"path": "tools", "recursive": true}}

# === File Operations ===

find_file(keyword)
  - Search for files in known directories
  - Params: keyword (required)
  - Example: {"tool_name": "terminal", "action": "find_file", "params": {"keyword": "invoice"}}

read_file(path, filename_fragment)
  - Read file with auto-detection for PDF, DOCX, CSV, HTML, or plain text
  - Params: path OR filename_fragment (one required)
  - Example: {"tool_name": "terminal", "action": "read_file", "params": {"path": "~/Documents/Orchestrate/dropzone/report.pdf"}}
  - Example: {"tool_name": "terminal", "action": "read_file", "params": {"filename_fragment": "invoice"}}

write_file(path, content)
  - Write content to a file (creates parent directories)
  - Params: path (required), content (required)
  - Example: {"tool_name": "terminal", "action": "write_file", "params": {"path": "output/notes.txt", "content": "My notes here"}}

append_file(path, content)
  - Append content to a file
  - Params: path (required), content (required)
  - Example: {"tool_name": "terminal", "action": "append_file", "params": {"path": "log.txt", "content": "\nNew log entry"}}

move_file(source, destination)
  - Move or rename a file
  - Params: source (required), destination (required)
  - Example: {"tool_name": "terminal", "action": "move_file", "params": {"source": "old.txt", "destination": "new.txt"}}

copy_file(source, destination)
  - Copy a file
  - Params: source (required), destination (required)
  - Example: {"tool_name": "terminal", "action": "copy_file", "params": {"source": "original.txt", "destination": "backup.txt"}}

delete_file(path)
  - Delete a file
  - Params: path (required)
  - Example: {"tool_name": "terminal", "action": "delete_file", "params": {"path": "temp.txt"}}

replace_lines(path, start_line, end_line, new_content)
  - Replace a range of lines in a file
  - Params: path (required), start_line (required), end_line (optional), new_content (required)
  - Example: {"tool_name": "terminal", "action": "replace_lines", "params": {"path": "config.py", "start_line": 10, "end_line": 15, "new_content": "# Updated config\nDEBUG = True"}}

# === Content Search ===

grep_content(pattern, path, type, max_results, case_insensitive)
  - Search file contents for a pattern (uses ripgrep or grep)
  - Params: pattern (required), path (optional, default "."), type (optional, e.g. "py", "json"), max_results (optional, default 100), case_insensitive (optional, default false)
  - Example: {"tool_name": "terminal", "action": "grep_content", "params": {"pattern": "def main", "path": "tools", "type": "py"}}
  - Example: {"tool_name": "terminal", "action": "grep_content", "params": {"pattern": "TODO", "case_insensitive": true}}
```

## unlock_tool
Manually unlock tools using credits or referral triggers.

```
unlock_tool(tool_name)
  - Unlock a specific tool
  - Params: tool_name (required)
  - Example: {"tool_name": "unlock_tool", "action": "unlock_tool", "params": {"tool_name": "outline_editor"}}

list_marketplace_tools()
  - List all marketplace tools with status
  - Params: none
  - Example: {"tool_name": "unlock_tool", "action": "list_marketplace_tools", "params": {}}

get_credits_balance()
  - Get current credit balance
  - Params: none
  - Example: {"tool_name": "unlock_tool", "action": "get_credits_balance", "params": {}}
```

## automation_engine
Event-driven automation engine for triggering workflows based on file changes, schedules, and custom events.

```
run_engine()
  - Start the automation engine loop
  - Params: none
  - Example: {"tool_name": "automation_engine", "action": "run_engine", "params": {}}

add_rule(rule_key, rule)
  - Add a new automation rule
  - Params: rule_key (required), rule (required)
  - Example: {"tool_name": "automation_engine", "action": "add_rule", "params": {"rule_key": "my_rule", "rule": {"trigger": {"type": "entry_added", "file": "data/my_queue.json"}, "action": {"tool": "json_manager", "action": "update_json_entry"}}}}

update_rule(rule_key, rule)
  - Update an existing rule
  - Params: rule_key (required), rule (required)
  - Example: {"tool_name": "automation_engine", "action": "update_rule", "params": {"rule_key": "my_rule", "rule": {"trigger": {"type": "time", "at": "09:00"}}}}

delete_rule(rule_key)
  - Delete an automation rule
  - Params: rule_key (required)
  - Example: {"tool_name": "automation_engine", "action": "delete_rule", "params": {"rule_key": "my_rule"}}

get_rule(rule_key)
  - Get a specific rule
  - Params: rule_key (required)
  - Example: {"tool_name": "automation_engine", "action": "get_rule", "params": {"rule_key": "my_rule"}}

get_rules()
  - Get all automation rules
  - Params: none
  - Example: {"tool_name": "automation_engine", "action": "get_rules", "params": {}}

list_rules()
  - List rules with summary
  - Params: none
  - Example: {"tool_name": "automation_engine", "action": "list_rules", "params": {}}

validate_rule(rule)
  - Validate a rule without saving
  - Params: rule (required)
  - Example: {"tool_name": "automation_engine", "action": "validate_rule", "params": {"rule": {}}}

dry_run_rule(rule_id)
  - Test what a rule would do
  - Params: rule_id (required)
  - Example: {"tool_name": "automation_engine", "action": "dry_run_rule", "params": {"rule_id": "my_rule"}}

toggle_rule_enabled(rule_key, enabled)
  - Enable or disable a rule
  - Params: rule_key (required), enabled (required)
  - Example: {"tool_name": "automation_engine", "action": "toggle_rule_enabled", "params": {"rule_key": "my_rule", "enabled": false}}

retry_failed(file)
  - Retry failed entries
  - Params: file (required)
  - Example: {"tool_name": "automation_engine", "action": "retry_failed", "params": {"file": "data/my_queue.json"}}

get_execution_history(rule_id, since, status, limit)
  - Get execution history with filters
  - Params: rule_id (optional), since (optional), status (optional), limit (optional)
  - Example: {"tool_name": "automation_engine", "action": "get_execution_history", "params": {"limit": 50}}

add_event_type(key, test)
  - Add a new event type
  - Params: key (required), test (required)
  - Example: {"tool_name": "automation_engine", "action": "add_event_type", "params": {"key": "status_changed", "test": "new_entry.get('status') != old_entry.get('status')"}}

get_event_types()
  - Get all event types
  - Params: none
  - Example: {"tool_name": "automation_engine", "action": "get_event_types", "params": {}}
```
