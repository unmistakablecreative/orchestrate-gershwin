#!/bin/bash
# ideogram_generate.sh - Single image generation

if [ "$#" -lt 2 ]; then
    echo "ERROR: Usage: $0 PROMPT FILENAME [SAVE_DIR]"
    exit 1
fi

PROMPT="$1"
FILENAME="$2"
SAVE_DIR="${3:-/Users/srinivas/Orchestrate Github/orchestrate-jarvis/blog_images/Eagle Update/}"

# Get script directory for credentials
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load API key
API_KEY=$(python3 -c "
import json
try:
    with open('$SCRIPT_DIR/credentials.json', 'r') as f:
        creds = json.load(f)
    print(creds.get('ideogram_api_key', ''))
except:
    print('')
")

if [ -z "$API_KEY" ]; then
    echo "ERROR: No API key found"
    exit 1
fi

# Create save directory
mkdir -p "$SAVE_DIR"
SAVE_PATH="$SAVE_DIR/$FILENAME"

ENDPOINT="https://api.ideogram.ai/generate"

echo "Generating: $FILENAME"

# Build JSON payload (escape quotes in prompt)
ESCAPED_PROMPT=$(echo "$PROMPT" | sed 's/"/\\"/g')
PAYLOAD=$(cat << EOF
{
  "image_request": {
    "prompt": "$ESCAPED_PROMPT",
    "aspect_ratio": "ASPECT_16_9"
  }
}
EOF
)

# Make API call
RESPONSE=$(curl -s -X POST "$ENDPOINT" \
  -H "Api-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD")

# Extract image URL
IMAGE_URL=$(echo "$RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if 'data' in data and len(data['data']) > 0:
        print(data['data'][0].get('url', ''))
except:
    print('')
")

if [ -n "$IMAGE_URL" ] && [ "$IMAGE_URL" != "" ]; then
    curl -s -o "$SAVE_PATH" "$IMAGE_URL"
    if [ -f "$SAVE_PATH" ]; then
        echo "SUCCESS: Saved to $SAVE_PATH"
        exit 0
    else
        echo "ERROR: Failed to download image"
        exit 1
    fi
else
    echo "ERROR: No image URL in response"
    echo "Response: $RESPONSE"
    exit 1
fi