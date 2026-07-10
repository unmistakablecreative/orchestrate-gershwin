#!/usr/bin/env python3
"""
knowledge_vault.py - Local vector search tool

Pure local semantic search. No external API calls.
Uses pre-existing embeddings from knowledge_base.db (SQLite).
Supports single and batch queries.
"""

import json
import os
import sys
import argparse
import sqlite3
import struct
import numpy as np
from typing import Dict, List, Optional, Union
from response_helper import get_success_message, get_error_message

# Constants
KNOWLEDGE_DB_FILE = "data/knowledge_base.db"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSIONS = 384

# Lazy-load model
_model = None


def get_embedding_model():
    """Lazy-load sentence-transformers model."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _model


def get_project_root() -> str:
    """Get project root directory."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(script_dir)


def unpack_embedding(blob: bytes) -> np.ndarray:
    """Unpack BLOB to numpy array of floats."""
    return np.array(struct.unpack(f'{EMBEDDING_DIMENSIONS}f', blob))


def _strip_empty_fields(obj):
    """Recursively strip empty strings, None values, and empty lists from dicts/lists."""
    if isinstance(obj, dict):
        return {k: _strip_empty_fields(v) for k, v in obj.items()
                if v is not None and v != "" and v != []}
    elif isinstance(obj, list):
        return [_strip_empty_fields(item) for item in obj]
    return obj


def search_knowledge(query, top_k: int = 10, source_filter: str = None,
                     book_filter: str = None, author_filter: str = None) -> Dict:
    """Unified semantic search across all knowledge sources.

    Searches highlights, code, and docs in one query or batch of queries.
    Use source_filter to limit to specific source_type (highlight, code, doc).

    Args:
        query: Either a string (single query) or list of strings (batch queries).
               Batch mode encodes all queries in one model.encode() call for efficiency.
        top_k: Number of results per query
        source_filter: Filter by source_type (highlight, code, doc)
        book_filter: Filter by book title
        author_filter: Filter by author

    Returns:
        Single query: {"status": "success", "query": str, "results": [...], "count": int}
        Batch query: {"status": "success", "results": {"query1": [...], "query2": [...]}}
    """
    project_root = get_project_root()
    db_path = os.path.join(project_root, KNOWLEDGE_DB_FILE)

    if not os.path.exists(db_path):
        return {"status": "error", "message": "Knowledge base not found. Run migration script first."}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Build query with filters
    sql = """
        SELECT h.id, h.text, h.book_title, h.author, h.note, h.source_type,
               h.tags, h.location, h.location_type, h.highlighted_at, h.document_tags,
               e.vector
        FROM highlights h
        JOIN embeddings e ON h.id = e.highlight_id
        WHERE 1=1
    """
    params = []

    if source_filter:
        sql += " AND h.source_type = ?"
        params.append(source_filter)

    if book_filter:
        sql += " AND LOWER(h.book_title) LIKE ?"
        params.append(f"%{book_filter.lower()}%")

    if author_filter:
        sql += " AND LOWER(h.author) LIKE ?"
        params.append(f"%{author_filter.lower()}%")

    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()

    if not rows:
        if isinstance(query, list):
            return {"status": "success", "results": {q: [] for q in query}, "message": "No items match filters"}
        return {"status": "success", "query": query, "results": [], "message": "No items match filters"}

    # Prepare item embeddings matrix
    item_ids = []
    item_embeddings_list = []
    item_by_id = {}

    for row in rows:
        item_id = row["id"]
        item_ids.append(item_id)
        item_embeddings_list.append(unpack_embedding(row["vector"]))
        item_by_id[item_id] = dict(row)

    item_embeddings_matrix = np.vstack(item_embeddings_list)
    item_norms = np.linalg.norm(item_embeddings_matrix, axis=1)

    # Batch or single query handling
    is_batch = isinstance(query, list)
    queries = query if is_batch else [query]

    # Generate all query embeddings in one call (key optimization)
    model = get_embedding_model()
    query_embeddings = model.encode(queries, convert_to_numpy=True)

    def _build_result(item, similarity):
        """Build result dict based on source_type."""
        source_type = item.get("source_type", "highlight")
        if source_type == "code":
            return {
                "text": item["text"],
                "source_type": source_type,
                "function_name": item.get("function_name"),
                "file_path": item.get("file_path"),
                "line_number": item.get("line_number"),
                "_similarity": similarity
            }
        else:
            return {
                "text": item["text"],
                "book_title": item.get("book_title"),
                "author": item.get("author"),
                "_similarity": similarity
            }

    all_results = {}

    for q_idx, q_text in enumerate(queries):
        q_emb = query_embeddings[q_idx]
        q_norm = np.linalg.norm(q_emb)

        if q_norm == 0:
            all_results[q_text] = []
            continue

        # Compute cosine similarities for all items at once
        dot_products = np.dot(item_embeddings_matrix, q_emb)
        similarities = dot_products / (item_norms * q_norm + 1e-10)

        # Get top_k indices
        top_indices = np.argsort(similarities)[::-1][:top_k]

        results = []
        for idx in top_indices:
            item_id = item_ids[idx]
            item = item_by_id[item_id]
            result = _build_result(item, float(similarities[idx]))
            results.append(result)

        # Strip internal sort key and empty fields
        for r in results:
            del r["_similarity"]
        results = [_strip_empty_fields(r) for r in results]

        all_results[q_text] = results

    # Return format based on single vs batch
    if is_batch:
        return {"status": "success", "results": all_results}
    else:
        count = len(all_results[query])
        return {
            "status": "success",
            "message": get_success_message("knowledge_vault", "search_knowledge", {"count": count}),
            "query": query,
            "results": all_results[query],
            "count": count
        }


def chunk_text(text: str, title: str, target_words: int = 500) -> List[str]:
    """Split text into chunks on paragraph boundaries, prefixed with title.

    Args:
        text: The full text to chunk
        title: Document title to prefix each chunk
        target_words: Target words per chunk (default 500)

    Returns:
        List of chunks, each prefixed with title
    """
    import re

    # Replace paragraph tags with newlines BEFORE stripping HTML
    # This preserves paragraph boundaries from <p>...</p> content
    clean_text = re.sub(r'</p>\s*<p[^>]*>', '\n', text)
    clean_text = re.sub(r'<br\s*/?>', '\n', clean_text)
    clean_text = re.sub(r'</?(p|div|section|article)[^>]*>', '\n', clean_text)

    # Strip remaining HTML tags
    clean_text = re.sub(r'<[^>]+>', '', clean_text)
    clean_text = clean_text.strip()

    if not clean_text:
        return []

    # Try splitting on single newlines first (handles HTML-derived content)
    paragraphs = re.split(r'\n+', clean_text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    if not paragraphs:
        return []

    def _chunk_from_paragraphs(paras: List[str]) -> List[str]:
        """Build chunks from paragraph list."""
        result = []
        current_chunk = []
        current_word_count = 0

        for para in paras:
            para_words = len(para.split())

            if current_word_count + para_words > target_words and current_chunk:
                chunk_content = ' '.join(current_chunk)
                result.append(f"{title}: {chunk_content}")
                current_chunk = [para]
                current_word_count = para_words
            else:
                current_chunk.append(para)
                current_word_count += para_words

        if current_chunk:
            chunk_content = ' '.join(current_chunk)
            result.append(f"{title}: {chunk_content}")

        return result

    chunks = _chunk_from_paragraphs(paragraphs)

    # Check if any chunk exceeds 2x target_words — if so, fall back to word-based split
    max_allowed = target_words * 2
    oversized = any(len(c.split()) > max_allowed for c in chunks)

    if oversized:
        # Fall back to simple word-count-based splitting
        words = clean_text.split()
        chunks = []
        for i in range(0, len(words), target_words):
            chunk_words = words[i:i + target_words]
            chunk_content = ' '.join(chunk_words)
            chunks.append(f"{title}: {chunk_content}")

    return chunks


def upsert_doc(doc_id: str, text: str, title: str, source_type: str,
               author: str = "") -> Dict:
    """Insert or update a doc in knowledge_base. Handles chunking for long documents.

    Deletes existing chunks for doc_id first, then inserts new chunks.
    Each chunk gets id: {doc_id}_chunk_{N}

    Args:
        doc_id: The document ID from docs.db
        text: Full text content (HTML will be stripped during chunking)
        title: Document title (used as prefix for each chunk)
        source_type: Tag for source_type column (e.g., 'permanent_note', 'blog_post')
        author: Author name (optional)

    Returns:
        {status, chunks_created}
    """
    project_root = get_project_root()
    kb_db_path = os.path.join(project_root, KNOWLEDGE_DB_FILE)

    if not os.path.exists(kb_db_path):
        return {"status": "error", "message": get_error_message("knowledge_vault", "upsert_doc", "Knowledge base not found")}

    # First delete any existing chunks for this doc
    delete_result = delete_doc(doc_id)
    if delete_result.get("status") == "error" and "not found" not in delete_result.get("message", "").lower():
        return delete_result

    # Chunk the text
    chunks = chunk_text(text, title, target_words=500)

    if not chunks:
        return {"status": "success", "chunks_created": 0, "message": "No content to index"}

    # Generate embeddings for all chunks at once
    model = get_embedding_model()
    embeddings = model.encode(chunks, convert_to_numpy=True)

    # Insert into knowledge_base.db
    kb_conn = sqlite3.connect(kb_db_path)
    kb_cur = kb_conn.cursor()

    inserted = 0
    for i, chunk_content in enumerate(chunks):
        chunk_id = f"{doc_id}_chunk_{i}"
        embedding_blob = struct.pack(f'{EMBEDDING_DIMENSIONS}f', *embeddings[i])

        try:
            kb_cur.execute("""
                INSERT OR REPLACE INTO highlights
                (id, text, book_title, author, note, tags, location, location_type,
                 highlighted_at, document_tags, source_type)
                VALUES (?, ?, ?, ?, '', '', '', '', '', '', ?)
            """, (chunk_id, chunk_content, title, author, source_type))

            kb_cur.execute("""
                INSERT OR REPLACE INTO embeddings (highlight_id, vector)
                VALUES (?, ?)
            """, (chunk_id, embedding_blob))

            inserted += 1
        except Exception as e:
            print(f"Error inserting chunk {chunk_id}: {e}", file=sys.stderr)

    kb_conn.commit()
    kb_conn.close()

    return {
        "status": "success",
        "message": get_success_message("knowledge_vault", "upsert_doc", {}),
        "doc_id": doc_id,
        "chunks_created": inserted
    }


def delete_doc(doc_id: str) -> Dict:
    """Delete all chunks for a doc from knowledge_base.

    Args:
        doc_id: The document ID (will delete all {doc_id}_chunk_N entries)

    Returns:
        {status, deleted_count}
    """
    project_root = get_project_root()
    kb_db_path = os.path.join(project_root, KNOWLEDGE_DB_FILE)

    if not os.path.exists(kb_db_path):
        return {"status": "error", "message": get_error_message("knowledge_vault", "delete_doc", "Knowledge base not found")}

    kb_conn = sqlite3.connect(kb_db_path)
    kb_cur = kb_conn.cursor()

    # Delete embeddings first (foreign key style cleanup)
    kb_cur.execute("""
        DELETE FROM embeddings WHERE highlight_id LIKE ?
    """, (f"{doc_id}_chunk_%",))
    embedding_deleted = kb_cur.rowcount

    # Delete highlights
    kb_cur.execute("""
        DELETE FROM highlights WHERE id LIKE ?
    """, (f"{doc_id}_chunk_%",))
    highlight_deleted = kb_cur.rowcount

    kb_conn.commit()
    kb_conn.close()

    return {
        "status": "success",
        "message": get_success_message("knowledge_vault", "delete_doc", {}),
        "doc_id": doc_id,
        "deleted_count": highlight_deleted
    }


def bulk_import_docs(collection: str, source_type: str = "doc",
                     chunk_size: int = 500) -> Dict:
    """Import docs from docs.db into knowledge_base.db with embeddings.

    Reads all docs from the specified collection, chunks them, generates
    embeddings, and inserts into knowledge_base.db.

    Args:
        collection: Collection name in docs.db to import from
        source_type: Tag for source_type column (e.g., 'podcast_transcript')
        chunk_size: Target words per chunk (default 500)

    Returns:
        {status, docs_imported, chunks_created}
    """
    project_root = get_project_root()
    docs_db_path = os.path.join(project_root, "data/docs.db")
    kb_db_path = os.path.join(project_root, KNOWLEDGE_DB_FILE)

    if not os.path.exists(docs_db_path):
        return {"status": "error", "message": get_error_message("knowledge_vault", "bulk_import_docs", "docs.db not found")}

    # Read docs from collection
    docs_conn = sqlite3.connect(docs_db_path)
    docs_conn.row_factory = sqlite3.Row
    docs_cur = docs_conn.cursor()

    docs_cur.execute(
        "SELECT id, title, content FROM docs WHERE collection = ?",
        (collection,)
    )
    docs = docs_cur.fetchall()
    docs_conn.close()

    if not docs:
        return {"status": "error", "message": get_error_message("knowledge_vault", "bulk_import_docs", f"No docs found in collection: {collection}")}

    # Prepare all chunks first
    all_chunks = []  # [(chunk_id, text, title)]
    for doc in docs:
        doc_id = doc["id"]
        title = doc["title"]
        content = doc["content"] or ""

        chunks = chunk_text(content, title, chunk_size)

        for i, chunk in enumerate(chunks):
            chunk_id = f"{doc_id}_chunk_{i}"
            all_chunks.append((chunk_id, chunk, title))

    if not all_chunks:
        return {"status": "success", "docs_imported": len(docs), "chunks_created": 0,
                "message": "No content to import (all docs empty)"}

    # Generate embeddings for all chunks at once (efficient batch encoding)
    model = get_embedding_model()
    chunk_texts = [c[1] for c in all_chunks]
    embeddings = model.encode(chunk_texts, convert_to_numpy=True, show_progress_bar=True)

    # Insert into knowledge_base.db
    kb_conn = sqlite3.connect(kb_db_path)
    kb_cur = kb_conn.cursor()

    inserted = 0
    for i, (chunk_id, chunk_text_val, title) in enumerate(all_chunks):
        # Pack embedding as BLOB
        embedding_blob = struct.pack(f'{EMBEDDING_DIMENSIONS}f', *embeddings[i])

        try:
            # Insert highlight row
            kb_cur.execute("""
                INSERT OR REPLACE INTO highlights
                (id, text, book_title, author, note, tags, location, location_type,
                 highlighted_at, document_tags, source_type)
                VALUES (?, ?, ?, ?, '', '', '', '', '', '', ?)
            """, (chunk_id, chunk_text_val, title, "Unmistakable Creative Podcast", source_type))

            # Insert embedding
            kb_cur.execute("""
                INSERT OR REPLACE INTO embeddings (highlight_id, vector)
                VALUES (?, ?)
            """, (chunk_id, embedding_blob))

            inserted += 1
        except Exception as e:
            print(f"Error inserting chunk {chunk_id}: {e}", file=sys.stderr)

    kb_conn.commit()
    kb_conn.close()

    return {
        "status": "success",
        "message": get_success_message("knowledge_vault", "bulk_import_docs", {"count": inserted}),
        "docs_imported": len(docs),
        "chunks_created": inserted,
        "source_type": source_type,
        "collection": collection
    }


def get_stats() -> Dict:
    """Get knowledge base statistics."""
    project_root = get_project_root()
    db_path = os.path.join(project_root, KNOWLEDGE_DB_FILE)

    if not os.path.exists(db_path):
        return {"status": "error", "message": get_error_message("knowledge_vault", "get_stats", "Knowledge base not found")}

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM highlights")
    total_items = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM embeddings")
    total_embeddings = cur.fetchone()[0]

    cur.execute("SELECT source_type, COUNT(*) FROM highlights GROUP BY source_type")
    source_counts = {row[0] or "unknown": row[1] for row in cur.fetchall()}

    conn.close()

    return {
        "status": "success",
        "message": get_success_message("knowledge_vault", "get_stats", {"doc_count": total_items}),
        "total_items": total_items,
        "total_embeddings": total_embeddings,
        "sources": source_counts
    }


def execute(action, params):
    """Standard OrchestrateOS execute pattern."""
    if action == "search_knowledge":
        return search_knowledge(
            query=params.get("query"),
            top_k=params.get("top_k", 10),
            source_filter=params.get("source_filter"),
            book_filter=params.get("book_filter"),
            author_filter=params.get("author_filter")
        )
    elif action == "batch_search":
        queries = params.get("queries", [])
        top_k = params.get("top_k", 3)
        source_filter = params.get("source_filter")
        results = {}
        for query in queries:
            result = search_knowledge(
                query=query,
                top_k=top_k,
                source_filter=source_filter
            )
            if result.get("status") == "success":
                results[query] = result.get("results", [])
            else:
                results[query] = []
        return {
            "status": "success",
            "message": get_success_message("knowledge_vault", "batch_search", {"count": len(queries)}),
            "results": results
        }
    elif action == "get_stats":
        return get_stats()
    elif action == "bulk_import_docs":
        return bulk_import_docs(
            collection=params.get("collection"),
            source_type=params.get("source_type", "doc"),
            chunk_size=params.get("chunk_size", 500)
        )
    elif action == "upsert_doc":
        return upsert_doc(
            doc_id=params.get("doc_id"),
            text=params.get("text"),
            title=params.get("title"),
            source_type=params.get("source_type"),
            author=params.get("author", "")
        )
    elif action == "delete_doc":
        return delete_doc(
            doc_id=params.get("doc_id")
        )
    else:
        return {"status": "error", "message": f"Unknown action: {action}", "available": ["search_knowledge", "batch_search", "get_stats", "bulk_import_docs", "upsert_doc", "delete_doc"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["search_knowledge", "batch_search", "get_stats", "bulk_import_docs", "upsert_doc", "delete_doc"])
    parser.add_argument("--params", type=str, default="{}")
    args = parser.parse_args()

    params = json.loads(args.params)
    result = execute(args.action, params)
    print(json.dumps(result, indent=2))
