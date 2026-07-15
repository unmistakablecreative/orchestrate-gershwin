#!/bin/bash
# Config-driven fake dependency installer
# Reads from install_config.json, writes progress to /tmp/gershwin_progress.json

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/install_config.json"
PROGRESS_FILE="/tmp/gershwin_progress.json"

# Read packages from config using Python
PACKAGES_JSON=$(python3 -c "
import json
with open('$CONFIG_FILE') as f:
    config = json.load(f)
for pkg in config['packages']:
    print(pkg['name'] + '|' + pkg['message'])
")

# Convert to arrays
NAMES=()
MESSAGES=()
while IFS='|' read -r name message; do
    NAMES+=("$name")
    MESSAGES+=("$message")
done <<< "$PACKAGES_JSON"

TOTAL=${#NAMES[@]}

# Clear any existing progress
echo '{"current": "", "message": "", "index": 0, "total": '"$TOTAL"', "percent": 0, "done": false}' > "$PROGRESS_FILE"

for i in "${!NAMES[@]}"; do
    pkg="${NAMES[$i]}"
    msg="${MESSAGES[$i]}"
    index=$((i + 1))
    percent=$((index * 100 / TOTAL))

    # Write progress with message
    python3 -c "
import json
progress = {
    'current': '$pkg',
    'message': '$msg',
    'index': $index,
    'total': $TOTAL,
    'percent': $percent,
    'done': False
}
with open('$PROGRESS_FILE', 'w') as f:
    json.dump(progress, f)
"

    echo "[$index/$TOTAL] $pkg - $msg"

    # Sleep 1-2 seconds randomly
    sleep_time=$(awk -v min=1 -v max=2 'BEGIN{srand(); print min+rand()*(max-min)}')
    sleep "$sleep_time"
done

# Mark as done
echo '{"current": "complete", "message": "All done!", "index": '"$TOTAL"', "total": '"$TOTAL"', "percent": 100, "done": true}' > "$PROGRESS_FILE"
echo "All packages installed!"
