#!/usr/bin/env python3
"""Replace the script section in task_board.html with DB-based version"""
import re

# Read the original file
with open('/Users/srinivas/Orchestrate Github/orchestrate-gershwin/semantic_memory/task_board.html', 'r') as f:
    html_content = f.read()

# Read the new script content
with open('/Users/srinivas/Orchestrate Github/orchestrate-gershwin/semantic_memory/task_board_db_script.txt', 'r') as f:
    new_script = f.read()

# Find and replace the script section
# The script section is the one after </style> and contains the main JS code
# It starts with <script> and ends with </script> right before </body>

# Pattern to match the main script block (the one with QUEUE_FILES, pollActiveTasks, etc)
# This is typically the last script block before </body>
pattern = r'(<script>\s*const API_BASE.*?</script>)(\s*</body>)'

def replace_script(match):
    return new_script + match.group(2)

new_html = re.sub(pattern, replace_script, html_content, flags=re.DOTALL)

# Verify the replacement worked
if 'get_active_tasks' in new_html and 'QUEUE_FILES' not in new_html:
    # Write the updated file
    with open('/Users/srinivas/Orchestrate Github/orchestrate-gershwin/semantic_memory/task_board.html', 'w') as f:
        f.write(new_html)
    print("SUCCESS: Replaced JSON polling with DB-based approach")
    print("- Removed QUEUE_FILES constant")
    print("- Added get_active_tasks, get_recent_tasks, get_staged_tasks API calls")
else:
    print("ERROR: Replacement did not work as expected")
    print(f"Contains get_active_tasks: {'get_active_tasks' in new_html}")
    print(f"Contains QUEUE_FILES: {'QUEUE_FILES' in new_html}")
