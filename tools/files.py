"""
files.py - File operations tool with SQLite operation logging

All file operations are logged to files.db for caching and audit trail.
"""

import os
import json
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime

from response_helper import get_success_message, get_error_message

__tool__ = "files"

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "files.db"

SAFE_EXTENSIONS = (".py", ".json", ".md", ".txt", ".csv", ".tsv", ".yaml", ".yml", ".html", ".env", ".swift", ".sh")


def _init_db():
    """Initialize files.db with file_ops table if not exists."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS file_ops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation TEXT NOT NULL,
            path TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            metadata TEXT
        )
    """)
    conn.commit()
    conn.close()


def _log_operation(operation: str, path: str, metadata: dict = None):
    """Log a file operation to files.db."""
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO file_ops (operation, path, timestamp, metadata) VALUES (?, ?, ?, ?)",
        (
            operation,
            str(path),
            datetime.now().isoformat(),
            json.dumps(metadata) if metadata else None
        )
    )
    conn.commit()
    conn.close()


def _resolve_path(filename: str) -> Path:
    """Resolve filename to absolute path within project."""
    if os.path.isabs(filename):
        return Path(filename)

    # Try relative to project root
    full_path = PROJECT_ROOT / filename
    if full_path.exists():
        return full_path

    # Search common directories
    search_dirs = [
        PROJECT_ROOT / "tools",
        PROJECT_ROOT / "data",
        PROJECT_ROOT / "semantic_memory",
        PROJECT_ROOT,
    ]

    for search_dir in search_dirs:
        candidate = search_dir / filename
        if candidate.exists():
            return candidate

    # Return project-relative path even if doesn't exist
    return PROJECT_ROOT / filename


def read_file_text(params: dict) -> dict:
    """
    Read a text file and return its contents.

    Args:
        params: dict with 'filename' or 'path' key

    Returns:
        dict with status, content, and metadata
    """
    filename = params.get("filename") or params.get("path")
    if not filename:
        return {"status": "error", "message": "Missing 'filename' or 'path' parameter"}

    file_path = _resolve_path(filename)

    if not file_path.exists():
        return {"status": "error", "message": get_error_message("files", "read_file_text", f"{filename} not found")}

    if not file_path.suffix.lower() in SAFE_EXTENSIONS:
        return {"status": "error", "message": get_error_message("files", "read_file_text", f"Unsupported file type: {file_path.suffix}")}

    try:
        content = file_path.read_text(encoding="utf-8")

        # Log the read operation
        _log_operation("read", str(file_path), {
            "size": len(content),
            "lines": content.count("\n") + 1
        })

        return {
            "status": "success",
            "message": get_success_message("files", "read_file_text", {"filename": file_path.name, "size": len(content)}),
            "content": content,
            "path": str(file_path),
            "size": len(content),
            "lines": content.count("\n") + 1
        }
    except Exception as e:
        return {"status": "error", "message": get_error_message("files", "read_file_text", str(e))}


def write_file(params: dict) -> dict:
    """
    Write content to a file.

    Args:
        params: dict with 'filename'/'path' and 'content' keys

    Returns:
        dict with status and metadata
    """
    filename = params.get("filename") or params.get("path")
    content = params.get("content", "")

    if not filename:
        return {"status": "error", "message": "Missing 'filename' or 'path' parameter"}

    file_path = _resolve_path(filename)

    # Ensure parent directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        existed = file_path.exists()
        old_size = file_path.stat().st_size if existed else 0

        file_path.write_text(content, encoding="utf-8")

        # Log the write operation
        _log_operation("write", str(file_path), {
            "new_size": len(content),
            "old_size": old_size,
            "created": not existed
        })

        return {
            "status": "success",
            "message": get_success_message("files", "write_file", {"filename": file_path.name}),
            "path": str(file_path),
            "size": len(content)
        }
    except Exception as e:
        return {"status": "error", "message": get_error_message("files", "write_file", str(e))}


def list_files(params: dict) -> dict:
    """
    List files in a directory.

    Args:
        params: dict with optional 'path', 'pattern', 'recursive' keys

    Returns:
        dict with status and list of files
    """
    path = params.get("path", ".")
    pattern = params.get("pattern", "*")
    recursive = params.get("recursive", False)

    dir_path = _resolve_path(path)

    if not dir_path.exists():
        return {"status": "error", "message": get_error_message("files", "list_files", f"Directory not found: {path}")}

    if not dir_path.is_dir():
        return {"status": "error", "message": get_error_message("files", "list_files", f"Not a directory: {path}")}

    try:
        if recursive:
            files = list(dir_path.rglob(pattern))
        else:
            files = list(dir_path.glob(pattern))

        file_list = []
        for f in files:
            if f.is_file():
                file_list.append({
                    "name": f.name,
                    "path": str(f),
                    "size": f.stat().st_size,
                    "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat()
                })

        # Log the list operation
        _log_operation("list", str(dir_path), {
            "pattern": pattern,
            "recursive": recursive,
            "count": len(file_list)
        })

        return {
            "status": "success",
            "message": get_success_message("files", "list_files", {"count": len(file_list)}),
            "path": str(dir_path),
            "count": len(file_list),
            "files": file_list
        }
    except Exception as e:
        return {"status": "error", "message": get_error_message("files", "list_files", str(e))}


def grep_content(params: dict) -> dict:
    """
    Search file contents for a pattern.

    Args:
        params: dict with 'pattern', optional 'path', 'type' keys

    Returns:
        dict with matches
    """
    pattern = params.get("pattern")
    if not pattern:
        return {"status": "error", "message": get_error_message("files", "grep_content", "Missing 'pattern' parameter")}

    path = params.get("path", ".")
    file_type = params.get("type", "*")

    search_path = _resolve_path(path)

    if not search_path.exists():
        return {"status": "error", "message": get_error_message("files", "grep_content", f"Path not found: {path}")}

    matches = []
    glob_pattern = f"*.{file_type}" if file_type != "*" else "*"

    try:
        if search_path.is_file():
            files = [search_path]
        else:
            files = list(search_path.rglob(glob_pattern))

        for f in files:
            if not f.is_file():
                continue
            if f.suffix.lower() not in SAFE_EXTENSIONS:
                continue

            try:
                content = f.read_text(encoding="utf-8")
                for i, line in enumerate(content.split("\n"), 1):
                    if pattern in line:
                        matches.append({
                            "file": str(f),
                            "line_number": i,
                            "text": line.strip()
                        })
            except:
                continue

        # Log the grep operation
        _log_operation("grep", str(search_path), {
            "pattern": pattern,
            "file_type": file_type,
            "match_count": len(matches)
        })

        return {
            "status": "success",
            "message": get_success_message("files", "grep_content", {"count": len(matches), "pattern": pattern}),
            "pattern": pattern,
            "count": len(matches),
            "matches": matches
        }
    except Exception as e:
        return {"status": "error", "message": get_error_message("files", "grep_content", str(e))}


def find_file(params: dict) -> dict:
    """
    Find files by name pattern.

    Args:
        params: dict with 'filename' or 'pattern' key

    Returns:
        dict with matching files
    """
    filename = params.get("filename") or params.get("pattern")
    if not filename:
        return {"status": "error", "message": get_error_message("files", "find_file", "Missing 'filename' or 'pattern' parameter")}

    path = params.get("path", ".")
    search_path = _resolve_path(path)

    if not search_path.exists():
        return {"status": "error", "message": get_error_message("files", "find_file", f"Path not found: {path}")}

    try:
        matches = []
        for f in search_path.rglob(f"*{filename}*"):
            if f.is_file():
                matches.append({
                    "name": f.name,
                    "path": str(f),
                    "size": f.stat().st_size
                })

        # Log the find operation
        _log_operation("find", str(search_path), {
            "pattern": filename,
            "match_count": len(matches)
        })

        if matches:
            return {
                "status": "success",
                "message": get_success_message("files", "find_file", {"filename": filename}),
                "pattern": filename,
                "count": len(matches),
                "matches": matches
            }
        else:
            return {
                "status": "error",
                "message": get_error_message("files", "find_file", f"No files matching '{filename}' found"),
                "pattern": filename,
                "count": 0,
                "matches": []
            }
    except Exception as e:
        return {"status": "error", "message": get_error_message("files", "find_file", str(e))}


def get_operation_history(params: dict) -> dict:
    """
    Get recent file operation history from files.db.

    Args:
        params: dict with optional 'limit', 'operation', 'path' keys

    Returns:
        dict with operation history
    """
    _init_db()

    limit = params.get("limit", 50)
    operation_filter = params.get("operation")
    path_filter = params.get("path")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    query = "SELECT id, operation, path, timestamp, metadata FROM file_ops"
    conditions = []
    values = []

    if operation_filter:
        conditions.append("operation = ?")
        values.append(operation_filter)

    if path_filter:
        conditions.append("path LIKE ?")
        values.append(f"%{path_filter}%")

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY timestamp DESC LIMIT ?"
    values.append(limit)

    cursor.execute(query, values)
    rows = cursor.fetchall()
    conn.close()

    history = []
    for row in rows:
        history.append({
            "id": row[0],
            "operation": row[1],
            "path": row[2],
            "timestamp": row[3],
            "metadata": json.loads(row[4]) if row[4] else None
        })

    return {
        "status": "success",
        "message": get_success_message("files", "get_operation_history", {"count": len(history)}),
        "count": len(history),
        "history": history
    }


def execute(action: str, params: dict) -> dict:
    """Main dispatch function for execution_hub compatibility."""
    if action == "read_file_text":
        return read_file_text(params)
    elif action == "write_file" or action == "write_file_text":
        return write_file(params)
    elif action == "list_files":
        return list_files(params)
    elif action == "grep_content":
        return grep_content(params)
    elif action == "find_file":
        return find_file(params)
    elif action == "get_operation_history":
        return get_operation_history(params)
    else:
        return {"status": "error", "message": f"Unknown action: {action}"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="File operations tool")
    parser.add_argument("action", help="Action to perform")
    parser.add_argument("--params", type=str, default="{}", help="JSON params")

    args = parser.parse_args()
    params = json.loads(args.params)

    result = execute(args.action, params)
    print(json.dumps(result, indent=2))
