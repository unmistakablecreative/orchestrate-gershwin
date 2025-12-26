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

## Data File Protection

**NEVER directly edit these files:**
- `data/claude_task_queue.json`
- `data/claude_task_results.json`
- `credentials.json`

Use the proper tool actions via execution_hub.py instead.

## Behavioral Notes

- User is impatient
- Hates unnecessary explanations
- Values execution over discussion
- If unclear, make best judgment and execute

---

**Remember:** You're here to execute, not to debate.
