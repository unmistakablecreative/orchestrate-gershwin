#!/usr/bin/env python3
"""
generate_test_suite.py - Generates ordered, stateful test groups for Gershwin
Produces gershwin_test_suite.json with groups that have setup -> test -> cleanup phases.
Tests that depend on previous results have capture/inject metadata.
"""

import json
from datetime import datetime

GERSHWIN_DIR = "/Users/srinivas/Orchestrate Github/orchestrate-gershwin"
OUTPUT_PATH = f"{GERSHWIN_DIR}/gershwin_test_suite.json"


def build_test_groups():
    """Build ordered test groups with capture/inject dependencies."""

    groups = []

    # ============================================
    # GROUP 1: json_manager (stateful)
    # ============================================
    json_manager_group = {
        "group_name": "json_manager",
        "description": "JSON file operations - create, add entries, read, cleanup",
        "ordered": True,
        "tests": [
            # 1. Create the test fixture file
            {
                "tool_name": "json_manager",
                "action": "create_json_file",
                "params": {
                    "filename": "gershwin_test_fixture.json"
                },
                "capture_as": "json_create"
            },
            # 2. Add an entry to the file
            {
                "tool_name": "json_manager",
                "action": "add_json_entry",
                "params": {
                    "filename": "gershwin_test_fixture.json",
                    "entry_key": "test_entry_001",
                    "entry_data": {"test_field": "test_value", "number": 42}
                },
                "capture_as": "json_add_entry"
            },
            # 3. List entries
            {
                "tool_name": "json_manager",
                "action": "list_json_entries",
                "params": {
                    "filename": "gershwin_test_fixture.json"
                }
            },
            # 4. Read specific entry
            {
                "tool_name": "json_manager",
                "action": "read_json_entry",
                "params": {
                    "filename": "gershwin_test_fixture.json",
                    "entry_key": "test_entry_001"
                }
            },
            # 5. Read full file
            {
                "tool_name": "json_manager",
                "action": "read_json_file",
                "params": {
                    "filename": "gershwin_test_fixture.json"
                }
            },
            # 6. Cleanup - delete the test file
            {
                "tool_name": "json_manager",
                "action": "delete_json_file",
                "params": {
                    "filename": "gershwin_test_fixture.json"
                },
                "cleanup": True
            }
        ]
    }
    groups.append(json_manager_group)

    # ============================================
    # GROUP 2: doc_editor (stateful with doc_id capture)
    # ============================================
    doc_editor_group = {
        "group_name": "doc_editor",
        "description": "Document operations - create doc, search, read, check links, cleanup",
        "ordered": True,
        "tests": [
            # 1. Create test document
            {
                "tool_name": "doc_editor",
                "action": "create_doc",
                "params": {
                    "title": "Gershwin Test Doc",
                    "content": "Test content for automated testing. This document validates the doc_editor tool.",
                    "collection": "test"
                },
                "capture_as": "doc_create",
                "capture_key": "doc_id"
            },
            # 2. Search for the doc
            {
                "tool_name": "doc_editor",
                "action": "search_docs",
                "params": {
                    "query": "Gershwin Test"
                }
            },
            # 3. Read the created doc (needs doc_id from step 1)
            {
                "tool_name": "doc_editor",
                "action": "read_doc",
                "params": {},
                "inject": [
                    {
                        "capture_from": "doc_create",
                        "capture_key": "doc_id",
                        "inject_as": "doc_id"
                    }
                ]
            },
            # 4. List docs in collection
            {
                "tool_name": "doc_editor",
                "action": "list_docs",
                "params": {
                    "collection": "test"
                }
            },
            # 5. Read links (needs doc_id)
            {
                "tool_name": "doc_editor",
                "action": "read_links",
                "params": {},
                "inject": [
                    {
                        "capture_from": "doc_create",
                        "capture_key": "doc_id",
                        "inject_as": "doc_id"
                    }
                ]
            },
            # 6. Read backlinks (needs doc_id)
            {
                "tool_name": "doc_editor",
                "action": "read_backlinks",
                "params": {},
                "inject": [
                    {
                        "capture_from": "doc_create",
                        "capture_key": "doc_id",
                        "inject_as": "doc_id"
                    }
                ]
            },
            # 7. Search within doc (needs doc_id)
            {
                "tool_name": "doc_editor",
                "action": "search_within_doc",
                "params": {
                    "query": "automated"
                },
                "inject": [
                    {
                        "capture_from": "doc_create",
                        "capture_key": "doc_id",
                        "inject_as": "doc_id"
                    }
                ]
            },
            # 8. Cleanup - delete the test doc
            {
                "tool_name": "doc_editor",
                "action": "delete_doc",
                "params": {},
                "inject": [
                    {
                        "capture_from": "doc_create",
                        "capture_key": "doc_id",
                        "inject_as": "doc_id"
                    }
                ],
                "cleanup": True
            }
        ]
    }
    groups.append(doc_editor_group)

    # ============================================
    # GROUP 3: Stateless (no ordering needed)
    # ============================================
    stateless_group = {
        "group_name": "stateless",
        "description": "Read-only stateless operations that can run in any order",
        "ordered": False,
        "tests": [
            # system_settings
            {
                "tool_name": "system_settings",
                "action": "list_tools",
                "params": {}
            },
            {
                "tool_name": "system_settings",
                "action": "list_supported_actions",
                "params": {}
            },
            {
                "tool_name": "system_settings",
                "action": "list_memory_files",
                "params": {}
            },
            # unlock_tool
            {
                "tool_name": "unlock_tool",
                "action": "list_marketplace_tools",
                "params": {}
            },
            {
                "tool_name": "unlock_tool",
                "action": "get_credits_balance",
                "params": {}
            },
            # check_credits
            {
                "tool_name": "check_credits",
                "action": "check_credits",
                "params": {}
            },
            # terminal
            {
                "tool_name": "terminal",
                "action": "ls",
                "params": {
                    "path": "."
                }
            },
            {
                "tool_name": "terminal",
                "action": "read_file",
                "params": {
                    "filename": "jarvis.py"
                }
            },
            {
                "tool_name": "terminal",
                "action": "check_safe",
                "params": {}
            },
            # bullet_journal
            {
                "tool_name": "bullet_journal",
                "action": "list_entries",
                "params": {}
            },
            {
                "tool_name": "bullet_journal",
                "action": "get_collections",
                "params": {}
            }
        ]
    }
    groups.append(stateless_group)

    return groups


def count_tests(groups):
    """Count total tests across all groups."""
    return sum(len(g["tests"]) for g in groups)


def main():
    groups = build_test_groups()
    total_tests = count_tests(groups)

    output = {
        "description": "Ordered, stateful test suite for Gershwin installation validation",
        "generated_at": datetime.now().isoformat(),
        "group_count": len(groups),
        "test_count": total_tests,
        "groups": groups
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Generated {total_tests} tests in {len(groups)} groups -> {OUTPUT_PATH}")

    # Print summary
    print("\nGroups:")
    for g in groups:
        ordered_str = "ORDERED" if g["ordered"] else "unordered"
        print(f"  {g['group_name']}: {len(g['tests'])} tests ({ordered_str})")

        # Show capture/inject dependencies
        for t in g["tests"]:
            if "capture_as" in t:
                print(f"    -> {t['action']}: captures as '{t['capture_as']}'")
            if "inject" in t:
                for inj in t["inject"]:
                    print(f"    <- {t['action']}: injects {inj['inject_as']} from '{inj['capture_from']}'")


if __name__ == "__main__":
    main()
