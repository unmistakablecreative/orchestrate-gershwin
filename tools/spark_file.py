#!/usr/bin/env python3
"""
spark_file.py - Zero-friction idea capture tool

One input. No folders. No tags. No decision fatigue.
Semantic search surfaces connected ideas when relevant.

Actions:
- add_entry: Store a new spark (content only)
- search: Semantic similarity search
- recent: Get chronologically recent entries
- export: Export all entries (json/markdown)
"""

import argparse
import json
import os
import sqlite3
import struct
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np

from response_helper import get_success_message, get_error_message

# Constants
SPARK_DB_FILE = "data/spark_file.db"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSIONS = 384

# Lazy-load model
_model = None


def get_project_root() -> str:
    """Get project root directory."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_db_path() -> str:
    """Get full path to spark_file.db."""
    return os.path.join(get_project_root(), SPARK_DB_FILE)


def get_embedding_model():
    """Lazy-load sentence-transformers model."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _model


def pack_embedding(embedding: np.ndarray) -> bytes:
    """Pack numpy array to BLOB."""
    return struct.pack(f'{EMBEDDING_DIMENSIONS}f', *embedding)


def unpack_embedding(blob: bytes) -> np.ndarray:
    """Unpack BLOB to numpy array of floats."""
    return np.array(struct.unpack(f'{EMBEDDING_DIMENSIONS}f', blob))


def init_db() -> sqlite3.Connection:
    """Initialize database and return connection."""
    db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    conn.execute("""
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            embedding BLOB NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_entries_created_at ON entries(created_at DESC)")
    conn.commit()

    return conn


def add_entry(params: Dict) -> Dict:
    """Store a new spark entry.

    Args:
        params: {"content": str}

    Returns:
        {"status": "success", "id": int, "message": str}
    """
    content = params.get("content")
    if not content or not content.strip():
        return {"status": "error", "message": get_error_message("spark_file", "add_entry", "content is required")}

    content = content.strip()
    created_at = datetime.now(timezone.utc).isoformat()

    # Generate embedding
    model = get_embedding_model()
    embedding = model.encode(content, convert_to_numpy=True)
    embedding_blob = pack_embedding(embedding)

    conn = init_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO entries (content, created_at, embedding) VALUES (?, ?, ?)",
        (content, created_at, embedding_blob)
    )
    entry_id = cur.lastrowid
    conn.commit()
    conn.close()

    return {
        "status": "success",
        "id": entry_id,
        "message": get_success_message("spark_file", "add_entry", {})
    }


def search(params: Dict) -> Dict:
    """Semantic similarity search.

    Args:
        params: {"query": str, "limit": int (optional, default 10)}

    Returns:
        {"status": "success", "query": str, "results": [...], "count": int}
    """
    query = params.get("query")
    if not query or not query.strip():
        return {"status": "error", "message": get_error_message("spark_file", "search", "query is required")}

    query = query.strip()
    limit = params.get("limit", 10)

    db_path = get_db_path()
    if not os.path.exists(db_path):
        return {"status": "success", "query": query, "results": [], "count": 0, "message": get_success_message("spark_file", "search", {"count": 0})}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT id, content, created_at, embedding FROM entries")
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return {"status": "success", "query": query, "results": [], "count": 0, "message": get_success_message("spark_file", "search", {"count": 0})}

    # Build embeddings matrix
    entry_ids = []
    entry_embeddings_list = []
    entry_by_id = {}

    for row in rows:
        entry_id = row["id"]
        entry_ids.append(entry_id)
        entry_embeddings_list.append(unpack_embedding(row["embedding"]))
        entry_by_id[entry_id] = {
            "id": entry_id,
            "content": row["content"],
            "created_at": row["created_at"]
        }

    entry_matrix = np.vstack(entry_embeddings_list)
    entry_norms = np.linalg.norm(entry_matrix, axis=1)

    # Generate query embedding
    model = get_embedding_model()
    query_embedding = model.encode(query, convert_to_numpy=True)
    query_norm = np.linalg.norm(query_embedding)

    if query_norm == 0:
        return {"status": "success", "query": query, "results": [], "count": 0}

    # Compute cosine similarities
    dot_products = np.dot(entry_matrix, query_embedding)
    similarities = dot_products / (entry_norms * query_norm + 1e-10)

    # Get top results
    top_indices = np.argsort(similarities)[::-1][:limit]

    results = []
    for idx in top_indices:
        entry_id = entry_ids[idx]
        entry = entry_by_id[entry_id]
        similarity = float(similarities[idx])
        if similarity > 0.1:  # Filter out very low matches
            results.append({
                "id": entry["id"],
                "content": entry["content"],
                "created_at": entry["created_at"],
                "similarity": round(similarity, 3)
            })

    return {
        "status": "success",
        "query": query,
        "results": results,
        "count": len(results),
        "message": get_success_message("spark_file", "search", {"count": len(results)})
    }


def recent(params: Dict) -> Dict:
    """Get chronologically recent entries.

    Args:
        params: {"limit": int (optional, default 20)}

    Returns:
        {"status": "success", "entries": [...], "count": int}
    """
    limit = params.get("limit", 20)

    db_path = get_db_path()
    if not os.path.exists(db_path):
        return {"status": "success", "entries": [], "count": 0, "message": get_success_message("spark_file", "recent", {"count": 0})}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        "SELECT id, content, created_at FROM entries ORDER BY created_at DESC LIMIT ?",
        (limit,)
    )
    rows = cur.fetchall()
    conn.close()

    entries = [
        {
            "id": row["id"],
            "content": row["content"],
            "created_at": row["created_at"]
        }
        for row in rows
    ]

    return {
        "status": "success",
        "entries": entries,
        "count": len(entries),
        "message": get_success_message("spark_file", "recent", {"count": len(entries)})
    }


def export(params: Dict) -> Dict:
    """Export all entries.

    Args:
        params: {"format": str (optional, "json" or "markdown", default "json")}

    Returns:
        {"status": "success", "format": str, "data": str/list, "count": int}
    """
    fmt = params.get("format", "json").lower()
    if fmt not in ("json", "markdown"):
        return {"status": "error", "message": get_error_message("spark_file", "export", "format must be 'json' or 'markdown'")}

    db_path = get_db_path()
    if not os.path.exists(db_path):
        return {"status": "success", "format": fmt, "data": [] if fmt == "json" else "", "count": 0, "message": get_success_message("spark_file", "export", {"filename": "spark_file"})}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT id, content, created_at FROM entries ORDER BY created_at ASC")
    rows = cur.fetchall()
    conn.close()

    entries = [
        {
            "id": row["id"],
            "content": row["content"],
            "created_at": row["created_at"]
        }
        for row in rows
    ]

    if fmt == "json":
        return {
            "status": "success",
            "format": "json",
            "data": entries,
            "count": len(entries),
            "message": get_success_message("spark_file", "export", {"filename": "spark_file.json"})
        }
    else:
        # Markdown format
        lines = ["# Spark File Export", ""]
        for entry in entries:
            lines.append(f"## {entry['created_at']}")
            lines.append("")
            lines.append(entry["content"])
            lines.append("")
            lines.append("---")
            lines.append("")

        return {
            "status": "success",
            "format": "markdown",
            "data": "\n".join(lines),
            "count": len(entries),
            "message": get_success_message("spark_file", "export", {"filename": "spark_file.md"})
        }


def main():
    parser = argparse.ArgumentParser(description="Spark File - Zero-friction idea capture")
    parser.add_argument("action", help="Action to perform")
    parser.add_argument("--params", type=str, default="{}", help="JSON params")

    args = parser.parse_args()
    action = args.action

    try:
        params = json.loads(args.params)
    except json.JSONDecodeError as e:
        print(json.dumps({"status": "error", "message": f"Invalid JSON params: {e}"}))
        sys.exit(1)

    if action == "add_entry":
        result = add_entry(params)
    elif action == "search":
        result = search(params)
    elif action == "recent":
        result = recent(params)
    elif action == "export":
        result = export(params)
    else:
        result = {"status": "error", "message": f"Unknown action: {action}"}

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
