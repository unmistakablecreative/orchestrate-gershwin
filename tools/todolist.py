#!/usr/bin/env python3
"""
todolist.py - Simple task management tool

Actions:
- add_task: Add a new task
- complete_task: Mark a task as completed
- delete_task: Delete a task
- list_tasks: Get all tasks
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from typing import Dict

from response_helper import get_success_message, get_error_message


TODO_DB_FILE = "data/todos.db"


def get_project_root() -> str:
    """Get project root directory."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_db_path() -> str:
    """Get full path to todos.db."""
    return os.path.join(get_project_root(), TODO_DB_FILE)


def init_db() -> sqlite3.Connection:
    """Initialize database and return connection."""
    db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            completed INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            completed_at TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_completed ON tasks(completed)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at DESC)")
    conn.commit()

    return conn


def add_task(params: Dict) -> Dict:
    """Add a new task.

    Args:
        params: {"content": str}

    Returns:
        {"status": "success", "id": int, "message": str}
    """
    content = params.get("content")
    if not content or not content.strip():
        return {"status": "error", "message": get_error_message("todolist", "add_task", "content is required")}

    content = content.strip()
    created_at = datetime.now(timezone.utc).isoformat()

    conn = init_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO tasks (content, completed, created_at) VALUES (?, 0, ?)",
        (content, created_at)
    )
    task_id = cur.lastrowid
    conn.commit()
    conn.close()

    return {
        "status": "success",
        "id": task_id,
        "message": get_success_message("todolist", "add_task", {"title": content})
    }


def complete_task(params: Dict) -> Dict:
    """Mark a task as completed.

    Args:
        params: {"id": int}

    Returns:
        {"status": "success", "message": str}
    """
    task_id = params.get("id")
    if task_id is None:
        return {"status": "error", "message": get_error_message("todolist", "complete_task", "id is required")}

    try:
        task_id = int(task_id)
    except (ValueError, TypeError):
        return {"status": "error", "message": get_error_message("todolist", "complete_task", "id must be an integer")}

    completed_at = datetime.now(timezone.utc).isoformat()

    conn = init_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE tasks SET completed = 1, completed_at = ? WHERE id = ?",
        (completed_at, task_id)
    )
    affected = cur.rowcount
    conn.commit()
    conn.close()

    if affected == 0:
        return {"status": "error", "message": get_error_message("todolist", "complete_task", f"Task {task_id} not found")}

    # Fetch task title for message
    conn = init_db()
    cur = conn.cursor()
    cur.execute("SELECT content FROM tasks WHERE id = ?", (task_id,))
    row = cur.fetchone()
    conn.close()
    title = row["content"] if row else f"Task {task_id}"

    return {
        "status": "success",
        "message": get_success_message("todolist", "complete_task", {"title": title})
    }


def delete_task(params: Dict) -> Dict:
    """Delete a task.

    Args:
        params: {"id": int}

    Returns:
        {"status": "success", "message": str}
    """
    task_id = params.get("id")
    if task_id is None:
        return {"status": "error", "message": get_error_message("todolist", "delete_task", "id is required")}

    try:
        task_id = int(task_id)
    except (ValueError, TypeError):
        return {"status": "error", "message": get_error_message("todolist", "delete_task", "id must be an integer")}

    conn = init_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    affected = cur.rowcount
    conn.commit()
    conn.close()

    if affected == 0:
        return {"status": "error", "message": get_error_message("todolist", "delete_task", f"Task {task_id} not found")}

    return {
        "status": "success",
        "message": get_success_message("todolist", "delete_task", {})
    }


def list_tasks(params: Dict) -> Dict:
    """Get all tasks.

    Args:
        params: {"show_completed": bool (optional, default False)}

    Returns:
        {"status": "success", "tasks": [...], "count": int}
    """
    show_completed = params.get("show_completed", False)

    db_path = get_db_path()
    if not os.path.exists(db_path):
        return {"status": "success", "tasks": [], "count": 0, "message": get_success_message("todolist", "list_tasks", {"count": 0})}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if show_completed:
        cur.execute("SELECT id, content, completed, created_at, completed_at FROM tasks ORDER BY completed ASC, created_at DESC")
    else:
        cur.execute("SELECT id, content, completed, created_at, completed_at FROM tasks WHERE completed = 0 ORDER BY created_at DESC")

    rows = cur.fetchall()
    conn.close()

    tasks = [
        {
            "id": row["id"],
            "content": row["content"],
            "completed": bool(row["completed"]),
            "created_at": row["created_at"],
            "completed_at": row["completed_at"]
        }
        for row in rows
    ]

    return {
        "status": "success",
        "tasks": tasks,
        "count": len(tasks),
        "message": get_success_message("todolist", "list_tasks", {"count": len(tasks)})
    }


def main():
    parser = argparse.ArgumentParser(description="Todo List - Simple task management")
    parser.add_argument("action", help="Action to perform")
    parser.add_argument("--params", type=str, default="{}", help="JSON params")

    args = parser.parse_args()
    action = args.action

    try:
        params = json.loads(args.params)
    except json.JSONDecodeError as e:
        print(json.dumps({"status": "error", "message": f"Invalid JSON params: {e}"}))
        sys.exit(1)

    if action == "add_task":
        result = add_task(params)
    elif action == "complete_task":
        result = complete_task(params)
    elif action == "delete_task":
        result = delete_task(params)
    elif action == "list_tasks":
        result = list_tasks(params)
    else:
        result = {"status": "error", "message": f"Unknown action: {action}"}

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
