#!/Users/srinivas/venv/bin/python3
"""
Verify Backfill Script
Verifies meta_description population across all backfill manifest collections.
"""

import json
import os
import glob

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_FILE = os.path.join(BASE_DIR, "data", "docs.json")
MANIFEST_PATTERN = os.path.join(BASE_DIR, "data", "backfill_groups_*.json")


def load_docs():
    """Load docs.json once."""
    if os.path.exists(DOCS_FILE):
        with open(DOCS_FILE, 'r') as f:
            return json.load(f)
    return {"docs": {}}


def verify_backfill() -> dict:
    """
    Verify meta_description population across all backfill manifests.

    1. Reads all manifest files matching data/backfill_groups_*.json
    2. For each manifest, collects all doc_ids across all groups
    3. Checks each doc for meta_description existence (non-empty)
    4. Outputs summary per collection with completion percentage

    Returns:
        {
            "status": "success",
            "collections": [
                {
                    "name": "Permanent Notes",
                    "total": 620,
                    "complete": 618,
                    "missing": 2,
                    "missing_ids": [...],
                    "percentage": 99.7
                }
            ],
            "overall_percentage": 99.5
        }
    """
    # Find all manifest files
    manifest_files = glob.glob(MANIFEST_PATTERN)

    if not manifest_files:
        return {
            "status": "error",
            "message": f"No manifest files found matching pattern: {MANIFEST_PATTERN}"
        }

    # Load docs.json once
    data = load_docs()
    all_docs = data.get("docs", {})

    collections = []
    total_all = 0
    complete_all = 0

    for manifest_path in sorted(manifest_files):
        try:
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
        except Exception as e:
            collections.append({
                "name": os.path.basename(manifest_path),
                "error": str(e)
            })
            continue

        collection_name = manifest.get("collection", os.path.basename(manifest_path))
        groups = manifest.get("groups", [])

        # Collect all doc_ids from all groups
        all_doc_ids = []
        for group in groups:
            all_doc_ids.extend(group.get("doc_ids", []))

        # Check each doc for meta_description
        complete_count = 0
        missing_ids = []

        for doc_id in all_doc_ids:
            doc = all_docs.get(doc_id)
            if doc:
                meta_desc = doc.get("meta_description", "")
                if meta_desc and isinstance(meta_desc, str) and meta_desc.strip():
                    complete_count += 1
                else:
                    missing_ids.append(doc_id)
            else:
                # Doc not found - count as missing
                missing_ids.append(doc_id)

        total = len(all_doc_ids)
        missing = len(missing_ids)
        percentage = round((complete_count / total * 100), 1) if total > 0 else 0.0

        collections.append({
            "name": collection_name,
            "total": total,
            "complete": complete_count,
            "missing": missing,
            "missing_ids": missing_ids,
            "percentage": percentage
        })

        total_all += total
        complete_all += complete_count

    overall_percentage = round((complete_all / total_all * 100), 1) if total_all > 0 else 0.0

    return {
        "status": "success",
        "collections": collections,
        "overall_percentage": overall_percentage
    }


# CLI dispatcher
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        # Default to verify_backfill action
        action = "verify_backfill"
    else:
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

    actions = {
        "verify_backfill": verify_backfill
    }

    if action in actions:
        result = actions[action](**params)
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps({"status": "error", "message": f"Unknown action: {action}"}))
