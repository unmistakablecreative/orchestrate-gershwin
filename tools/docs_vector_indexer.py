"""
Docs Vector Indexer — Standalone tool for building and querying doc embeddings.

Creates data/docs_vector_index.json with:
- metadata (total_docs, last_updated, embedding_model, embedding_dimensions)
- embeddings dict keyed by doc_id
- doc_metadata dict with title and collection

Uses all-MiniLM-L6-v2 via sentence-transformers (384 dimensions).
"""

import json
import os
import re
import sys
import sqlite3
import time
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional
from html.parser import HTMLParser

# Constants
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "docs.db")
VECTOR_INDEX_FILE = "data/docs_vector_index.json"
STATUS_MARKER_FILE = "data/docs_vector_index_status.json"
FAISS_INDEX_FILE = "data/docs_faiss.index"
FAISS_ID_MAP_FILE = "data/docs_faiss_id_map.json"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSIONS = 384

# Lazy-load sentence-transformers model
_model = None

# FAISS index cache
_faiss_index = None
_faiss_id_map = None


def get_embedding_model():
    """Lazy-load the sentence-transformers model."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _model


def warm_embedding_model() -> Dict:
    """Pre-load embedding model. Call at Jarvis boot."""
    start = time.time()
    model = get_embedding_model()
    # Run a dummy encode to fully initialize CUDA/MPS if available
    model.encode(["warmup"], convert_to_numpy=True)
    elapsed = time.time() - start
    return {"status": "success", "load_time_seconds": round(elapsed, 2)}


def _get_faiss_index():
    """Load FAISS index, caching in memory."""
    global _faiss_index
    if _faiss_index is None:
        import faiss
        if os.path.exists(FAISS_INDEX_FILE):
            _faiss_index = faiss.read_index(FAISS_INDEX_FILE)
        else:
            return None
    return _faiss_index


def _get_faiss_id_map():
    """Load FAISS ID map, caching in memory."""
    global _faiss_id_map
    if _faiss_id_map is None:
        if os.path.exists(FAISS_ID_MAP_FILE):
            with open(FAISS_ID_MAP_FILE, 'r') as f:
                _faiss_id_map = json.load(f)
        else:
            return None
    return _faiss_id_map


def _invalidate_faiss_cache():
    """Clear cached FAISS index (call after sync_new_docs)."""
    global _faiss_index, _faiss_id_map
    _faiss_index = None
    _faiss_id_map = None


def _rebuild_faiss_index(embeddings: dict):
    """Rebuild FAISS index from embeddings dict."""
    import faiss
    doc_ids = list(embeddings.keys())
    vectors = np.array([embeddings[did] for did in doc_ids], dtype='float32')
    faiss.normalize_L2(vectors)
    faiss_index = faiss.IndexFlatIP(EMBEDDING_DIMENSIONS)
    faiss_index.add(vectors)
    faiss.write_index(faiss_index, FAISS_INDEX_FILE)
    with open(FAISS_ID_MAP_FILE, 'w') as f:
        json.dump(doc_ids, f)
    _invalidate_faiss_cache()


class HTMLStripper(HTMLParser):
    """Strip HTML tags and return plain text."""
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.text = []

    def handle_data(self, d):
        self.text.append(d)

    def get_data(self):
        return ' '.join(self.text)


def strip_html(html_content: str) -> str:
    """Remove HTML tags and return plain text."""
    if not html_content:
        return ""
    stripper = HTMLStripper()
    try:
        stripper.feed(html_content)
        return stripper.get_data()
    except:
        # Fallback: regex strip
        return re.sub(r'<[^>]+>', ' ', html_content)


def get_db():
    """Get SQLite connection with Row factory for dict-like access."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def load_docs() -> Dict:
    """Load docs from SQLite database."""
    if not os.path.exists(DB_PATH):
        return {"docs": {}}

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, content, collection FROM docs")
    rows = cursor.fetchall()
    conn.close()

    docs = {}
    for row in rows:
        docs[row["id"]] = {
            "title": row["title"],
            "content": row["content"],
            "collection": row["collection"]
        }

    return {"docs": docs}


def load_vector_index() -> Dict:
    """Load existing vector index if it exists."""
    if not os.path.exists(VECTOR_INDEX_FILE):
        return None
    with open(VECTOR_INDEX_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_vector_index(index_data: Dict) -> None:
    """Save vector index to file."""
    with open(VECTOR_INDEX_FILE, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, indent=2)


def write_status(status: str, details: Dict = None) -> None:
    """Write status marker file for async completion tracking."""
    status_data = {
        "status": status,
        "timestamp": datetime.now().isoformat(),
        "details": details or {}
    }
    with open(STATUS_MARKER_FILE, 'w', encoding='utf-8') as f:
        json.dump(status_data, f, indent=2)


def build_index() -> Dict:
    """
    Build the complete docs vector index.

    Reads all docs from docs.json, strips HTML from content,
    embeds title + content for each doc, and writes to docs_vector_index.json.
    """
    write_status("in_progress", {"started_at": datetime.now().isoformat()})

    try:
        # Load model
        print("Loading embedding model...")
        model = get_embedding_model()

        # Load docs
        print("Loading docs.json...")
        docs_data = load_docs()
        docs = docs_data.get("docs", {})
        total_docs = len(docs)
        print(f"Found {total_docs} docs to embed")

        embeddings = {}
        doc_metadata = {}

        # Process each doc
        for i, (doc_id, doc) in enumerate(docs.items()):
            if (i + 1) % 50 == 0:
                print(f"Progress: {i + 1}/{total_docs} docs embedded")

            # Prepare text: strip HTML from content
            title = doc.get("title", "")
            content = doc.get("content", "")
            plain_content = strip_html(content)
            text = f"{title} {plain_content}".strip()

            # Generate embedding
            if text:
                embedding = model.encode([text], convert_to_numpy=True)[0].tolist()
            else:
                # Empty doc — use zero vector
                embedding = [0.0] * EMBEDDING_DIMENSIONS

            embeddings[doc_id] = embedding
            doc_metadata[doc_id] = {
                "title": title,
                "collection": doc.get("collection", "Unknown")
            }

        # Build index structure
        index_data = {
            "metadata": {
                "total_docs": total_docs,
                "last_updated": datetime.now().isoformat(),
                "embedding_model": EMBEDDING_MODEL_NAME,
                "embedding_dimensions": EMBEDDING_DIMENSIONS
            },
            "embeddings": embeddings,
            "doc_metadata": doc_metadata
        }

        # Save
        print("Saving vector index...")
        save_vector_index(index_data)

        # Build FAISS index
        print("Building FAISS index...")
        _rebuild_faiss_index(embeddings)

        write_status("completed", {
            "total_docs": total_docs,
            "completed_at": datetime.now().isoformat()
        })

        print(f"Done! Indexed {total_docs} docs to {VECTOR_INDEX_FILE}")

        return {
            "status": "success",
            "total_docs": total_docs,
            "index_file": VECTOR_INDEX_FILE
        }

    except Exception as e:
        write_status("error", {"error": str(e)})
        return {
            "status": "error",
            "message": str(e)
        }


def semantic_search(query: str, top_k: int = 10, collection: str = None) -> Dict:
    """
    Semantic search across docs using FAISS.

    Args:
        query: Search query
        top_k: Number of results to return
        collection: Optional collection filter

    Returns:
        Dict with results containing doc_id, title, collection, similarity
    """
    import faiss

    # Load index
    index_data = load_vector_index()
    if not index_data:
        return {
            "status": "error",
            "message": "Vector index not found. Run build_index first."
        }

    doc_meta = index_data.get("doc_metadata", {})

    # Try FAISS index first
    faiss_index = _get_faiss_index()
    id_map = _get_faiss_id_map()

    if faiss_index is None or id_map is None:
        # Fallback to brute-force if FAISS index doesn't exist
        embeddings = index_data.get("embeddings", {})
        if not embeddings:
            return {
                "status": "error",
                "message": "No embeddings in index."
            }

        # Generate query embedding
        model = get_embedding_model()
        query_embedding = model.encode([query], convert_to_numpy=True)[0]

        # Calculate similarities (brute-force fallback)
        results = []
        for doc_id, embedding in embeddings.items():
            if collection and doc_meta.get(doc_id, {}).get("collection") != collection:
                continue
            doc_vec = np.array(embedding)
            similarity = np.dot(query_embedding, doc_vec) / (
                np.linalg.norm(query_embedding) * np.linalg.norm(doc_vec) + 1e-8
            )
            results.append({
                "doc_id": doc_id,
                "title": doc_meta.get(doc_id, {}).get("title", "Unknown"),
                "collection": doc_meta.get(doc_id, {}).get("collection", "Unknown"),
                "similarity": float(similarity)
            })
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return {
            "status": "success",
            "query": query,
            "results": results[:top_k]
        }

    # Generate query embedding
    model = get_embedding_model()
    query_embedding = model.encode([query], convert_to_numpy=True)[0]

    # Normalize query vector for cosine similarity via inner product
    query_vec = query_embedding.reshape(1, -1).astype('float32')
    faiss.normalize_L2(query_vec)

    # Search FAISS (over-fetch for collection filter)
    distances, indices = faiss_index.search(query_vec, top_k * 3)

    results = []
    for i, idx in enumerate(indices[0]):
        if idx == -1:
            continue
        doc_id = id_map[idx]
        # Collection filter
        if collection and doc_meta.get(doc_id, {}).get("collection") != collection:
            continue
        results.append({
            "doc_id": doc_id,
            "title": doc_meta.get(doc_id, {}).get("title", "Unknown"),
            "collection": doc_meta.get(doc_id, {}).get("collection", "Unknown"),
            "similarity": float(distances[0][i])
        })
        if len(results) >= top_k:
            break

    return {
        "status": "success",
        "query": query,
        "results": results
    }


def sync_new_docs() -> Dict:
    """
    Sync new docs to the vector index.

    1. Load docs.json — get all current doc_ids
    2. Load docs_vector_index.json — get all indexed doc_ids
    3. Find doc_ids in docs.json NOT in vector index (new docs)
    4. Find doc_ids in vector index NOT in docs.json (deleted docs) — remove those
    5. For each new doc: embed title + content, add to index
    6. Save updated index
    7. Return count of added and removed
    """
    # Load docs
    docs_data = load_docs()
    docs = docs_data.get("docs", {})
    current_doc_ids = set(docs.keys())

    # Load existing index
    index_data = load_vector_index()
    if not index_data:
        return {
            "status": "error",
            "message": "Vector index not found. Run build_index first."
        }

    indexed_doc_ids = set(index_data.get("embeddings", {}).keys())

    # Find new docs (in docs.json but not in index)
    new_doc_ids = current_doc_ids - indexed_doc_ids

    # Find deleted docs (in index but not in docs.json)
    deleted_doc_ids = indexed_doc_ids - current_doc_ids

    # Remove deleted docs from index
    for doc_id in deleted_doc_ids:
        if doc_id in index_data["embeddings"]:
            del index_data["embeddings"][doc_id]
        if doc_id in index_data.get("doc_metadata", {}):
            del index_data["doc_metadata"][doc_id]

    # Embed new docs
    added_count = 0
    if new_doc_ids:
        model = get_embedding_model()

        for doc_id in new_doc_ids:
            doc = docs.get(doc_id, {})
            title = doc.get("title", "")
            content = doc.get("content", "")
            plain_content = strip_html(content)
            text = f"{title} {plain_content}".strip()

            # Generate embedding
            if text:
                embedding = model.encode([text], convert_to_numpy=True)[0].tolist()
            else:
                embedding = [0.0] * EMBEDDING_DIMENSIONS

            index_data["embeddings"][doc_id] = embedding
            if "doc_metadata" not in index_data:
                index_data["doc_metadata"] = {}
            index_data["doc_metadata"][doc_id] = {
                "title": title,
                "collection": doc.get("collection", "Unknown")
            }
            added_count += 1

    # Update metadata
    index_data["metadata"]["total_docs"] = len(index_data["embeddings"])
    index_data["metadata"]["last_updated"] = datetime.now().isoformat()

    # Save
    save_vector_index(index_data)

    # Rebuild FAISS index
    _rebuild_faiss_index(index_data["embeddings"])

    removed_count = len(deleted_doc_ids)
    print(f"Sync complete: {added_count} docs added, {removed_count} docs removed")

    return {
        "status": "success",
        "added": added_count,
        "removed": removed_count,
        "total_indexed": len(index_data["embeddings"])
    }


# Action definitions for execution_hub
ACTIONS = {
    "build_index": {
        "description": "Build complete docs vector index. Embeds all docs from docs.json. Long-running for 400+ docs.",
        "params": {}
    },
    "semantic_search": {
        "description": "Semantic search across docs using FAISS for fast similarity lookup.",
        "params": {
            "query": {"type": "string", "required": True, "description": "Search query"},
            "top_k": {"type": "integer", "required": False, "default": 10, "description": "Number of results"},
            "collection": {"type": "string", "required": False, "default": None, "description": "Filter by collection"}
        }
    },
    "sync_new_docs": {
        "description": "Sync new docs to vector index. Adds new docs, removes deleted docs.",
        "params": {}
    },
    "warm_embedding_model": {
        "description": "Pre-load embedding model at boot. Returns load time in seconds.",
        "params": {}
    }
}


def execute(action, params):
    """Standard OrchestrateOS execute entry point."""
    if action == "build_index":
        return build_index()
    elif action == "semantic_search":
        return semantic_search(
            params.get("query"),
            params.get("top_k", 10),
            params.get("collection")
        )
    elif action == "sync_new_docs":
        return sync_new_docs()
    elif action == "warm_embedding_model":
        return warm_embedding_model()
    else:
        return {"status": "error", "message": f"Unknown action: {action}"}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"status": "error", "message": "No action specified"}))
        sys.exit(1)

    action = sys.argv[1]

    # Parse --params JSON
    params = {}
    for i, arg in enumerate(sys.argv):
        if arg == "--params" and i + 1 < len(sys.argv):
            params = json.loads(sys.argv[i + 1])
            break

    # Flatten nested params wrapper if present
    if "params" in params and isinstance(params["params"], dict):
        params = params["params"]

    result = execute(action, params)
    print(json.dumps(result, indent=2))
