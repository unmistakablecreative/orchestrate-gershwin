#!/usr/bin/env python3
"""
Generate gershwin_system_map.json with complete directory structure and file paths.
"""
import os
import json
from datetime import datetime
from pathlib import Path

def get_file_info(filepath):
    """Get file metadata."""
    try:
        stat = os.stat(filepath)
        return {
            "size_bytes": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "extension": Path(filepath).suffix or None
        }
    except:
        return {"size_bytes": 0, "modified": None, "extension": None}

def build_directory_tree(root_path, ignore_patterns=None):
    """Recursively build directory tree structure."""
    if ignore_patterns is None:
        ignore_patterns = ['.git', '__pycache__', '.DS_Store', '*.pyc', 'node_modules']

    def should_ignore(name):
        for pattern in ignore_patterns:
            if pattern.startswith('*'):
                if name.endswith(pattern[1:]):
                    return True
            elif name == pattern:
                return True
        return False

    tree = {
        "name": os.path.basename(root_path),
        "path": root_path,
        "type": "directory",
        "children": []
    }

    try:
        entries = sorted(os.listdir(root_path))
    except PermissionError:
        return tree

    for entry in entries:
        if should_ignore(entry):
            continue

        full_path = os.path.join(root_path, entry)

        if os.path.isdir(full_path):
            child_tree = build_directory_tree(full_path, ignore_patterns)
            tree["children"].append(child_tree)
        else:
            file_info = get_file_info(full_path)
            tree["children"].append({
                "name": entry,
                "path": full_path,
                "type": "file",
                **file_info
            })

    return tree

def collect_all_files(root_path, ignore_patterns=None):
    """Collect flat list of all files with paths."""
    if ignore_patterns is None:
        ignore_patterns = ['.git', '__pycache__', '.DS_Store', '*.pyc', 'node_modules']

    def should_ignore(name):
        for pattern in ignore_patterns:
            if pattern.startswith('*'):
                if name.endswith(pattern[1:]):
                    return True
            elif name == pattern:
                return True
        return False

    all_files = []
    all_directories = []

    for dirpath, dirnames, filenames in os.walk(root_path):
        # Filter out ignored directories
        dirnames[:] = [d for d in dirnames if not should_ignore(d)]

        rel_dir = os.path.relpath(dirpath, root_path)
        if rel_dir != '.':
            all_directories.append({
                "path": dirpath,
                "relative_path": rel_dir,
                "name": os.path.basename(dirpath)
            })

        for filename in filenames:
            if should_ignore(filename):
                continue

            full_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(full_path, root_path)
            file_info = get_file_info(full_path)

            all_files.append({
                "path": full_path,
                "relative_path": rel_path,
                "name": filename,
                **file_info
            })

    return all_files, all_directories

def categorize_files(files):
    """Categorize files by type/extension."""
    categories = {
        "python": [],
        "json": [],
        "html": [],
        "javascript": [],
        "css": [],
        "markdown": [],
        "database": [],
        "config": [],
        "other": []
    }

    extension_map = {
        ".py": "python",
        ".json": "json",
        ".ndjson": "json",
        ".html": "html",
        ".js": "javascript",
        ".css": "css",
        ".md": "markdown",
        ".db": "database",
        ".sqlite": "database",
        ".yaml": "config",
        ".yml": "config",
        ".toml": "config",
        ".ini": "config",
        ".gitignore": "config",
    }

    for f in files:
        ext = f.get("extension", "")
        name = f.get("name", "")

        category = extension_map.get(ext, None)
        if category is None:
            category = extension_map.get(name, "other")

        categories[category].append(f["relative_path"])

    return categories

def main():
    root_path = "/Users/srinivas/Orchestrate Github/orchestrate-gershwin"
    output_path = os.path.join(root_path, "gershwin_system_map.json")

    print(f"Scanning: {root_path}")

    # Build the tree structure
    tree = build_directory_tree(root_path)

    # Collect flat file list
    all_files, all_directories = collect_all_files(root_path)

    # Categorize files
    categories = categorize_files(all_files)

    # Build the system map
    system_map = {
        "generated_at": datetime.now().isoformat(),
        "root_path": root_path,
        "summary": {
            "total_files": len(all_files),
            "total_directories": len(all_directories),
            "files_by_category": {k: len(v) for k, v in categories.items()}
        },
        "directory_tree": tree,
        "all_files": all_files,
        "all_directories": all_directories,
        "files_by_category": categories
    }

    # Write output
    with open(output_path, 'w') as f:
        json.dump(system_map, f, indent=2)

    print(f"Generated: {output_path}")
    print(f"Total files: {len(all_files)}")
    print(f"Total directories: {len(all_directories)}")
    print(f"\nFiles by category:")
    for cat, paths in categories.items():
        if paths:
            print(f"  {cat}: {len(paths)}")

if __name__ == "__main__":
    main()
