#!/bin/bash
export PYTHONPATH="$PYTHONPATH:/Applications/OrchestrateOS.app/Contents/Resources/orchestrate"
USER_DIR="$HOME/Documents/Orchestrate"
STATE_DIR="$HOME/Library/Application Support/OrchestrateOS"
OUTPUT_DIR="/Applications/OrchestrateOS.app/Contents/Resources/orchestrate/app"
RUNTIME_DIR="/tmp/runtime"
mkdir -p "$USER_DIR/dropzone"
mkdir -p "$USER_DIR/vault/watch_books"
mkdir -p "$USER_DIR/vault/watch_transcripts"
mkdir -p "$USER_DIR/orchestrate_exports/markdown"
mkdir -p "$STATE_DIR"

# Create Claude Code queue files for autonomous execution
echo '{"tasks": {}}' > "$USER_DIR/claude_task_queue.json"
echo '{"results": {}}' > "$USER_DIR/claude_task_results.json"

# Prompt if not passed in
if [ -z "$NGROK_TOKEN" ]; then
  read -p "Enter your ngrok authtoken: " NGROK_TOKEN
fi
if [ -z "$NGROK_DOMAIN" ]; then
  read -p "Enter your ngrok domain (e.g. clever-bear.ngrok-free.app): " NGROK_DOMAIN
fi

export NGROK_TOKEN
export NGROK_DOMAIN
export DOMAIN="$NGROK_DOMAIN"
export SAFE_DOMAIN=$(echo "$NGROK_DOMAIN" | sed 's|https://||g' | sed 's|[-.]|_|g')

IDENTITY_FILE="$STATE_DIR/system_identity.json"
if [ ! -f "$IDENTITY_FILE" ]; then
  UUID=$(uuidgen | tr '[:upper:]' '[:lower:]')
  USER_ID="orch-${UUID}"
  TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  echo "{\"user_id\": \"$USER_ID\", \"installed_at\": \"$TIMESTAMP\"}" > "$IDENTITY_FILE"

  # Ledger sync
  BIN_ID="68292fcf8561e97a50162139"
  API_KEY='$2a$10$MoavwaWsCucy2FkU/5ycV.lBTPWoUq4uKHhCi9Y47DOHWyHFL3o2C'

  REFERRAL_DATA_DIR="/Applications/OrchestrateOS.app/Contents/Resources/orchestrate/referral_data"

  if [ -f "$REFERRAL_DATA_DIR/referrer.txt" ]; then
    REFERRER_ID=$(cat "$REFERRAL_DATA_DIR/referrer.txt" | tr -d '\n\r' | xargs)
  else
    REFERRER_ID=""
  fi

  LEDGER=$(curl -s -X GET "https://api.jsonbin.io/v3/b/$BIN_ID/latest" -H "X-Master-Key: $API_KEY")
  INSTALLS=$(echo "$LEDGER" | jq '.record.installs')

  # Add new user entry
  INSTALLS=$(echo "$INSTALLS" | jq --arg uid "$USER_ID" --arg ts "$TIMESTAMP" \
    '.[$uid] = { referral_count: 0, referral_credits: 3, tools_unlocked: ["json_manager"], timestamp: $ts }')

  if [ "$REFERRER_ID" != "" ]; then
    # Check if referrer exists
    REFERRER_EXISTS=$(echo "$INSTALLS" | jq --arg rid "$REFERRER_ID" 'has($rid)')

    if [ "$REFERRER_EXISTS" = "true" ]; then
      INSTALLS=$(echo "$INSTALLS" | jq --arg rid "$REFERRER_ID" \
        'if .[$rid] != null then .[$rid].referral_count += 1 | .[$rid].referral_credits += 3 else . end')
    fi
  fi

  FINAL=$(jq -n --argjson installs "$INSTALLS" '{filename: "install_ledger.json", installs: $installs}')
  echo "$FINAL" | curl -s -X PUT "https://api.jsonbin.io/v3/b/$BIN_ID" \
    -H "Content-Type: application/json" -H "X-Master-Key: $API_KEY" --data @-

  echo '{ "referral_count": 0, "referral_credits": 3, "tools_unlocked": ["json_manager"] }' > "$STATE_DIR/referrals.json"
fi

RUNTIME_DIR="/Applications/OrchestrateOS.app/Contents/Resources/orchestrate"
if [ ! -d "$RUNTIME_DIR/.git" ]; then
  git clone https://github.com/unmistakablecreative/orchestrate-beta-sandbox.git "$RUNTIME_DIR"
fi

mkdir -p "$RUNTIME_DIR/data"
echo '{ "token": "'$NGROK_TOKEN'", "domain": "'$NGROK_DOMAIN'" }' > "$RUNTIME_DIR/data/ngrok.json"
cd "$RUNTIME_DIR"

# Writable GPT output path
GPT_FILE="$USER_DIR/_paste_into_gpt.txt"
rm -f "$GPT_FILE"

if [ -f "openapi_template.yaml" ] && [ -f "instructions_template.json" ]; then
  envsubst < openapi_template.yaml > "$USER_DIR/openapi.yaml"
  envsubst < instructions_template.json > "$USER_DIR/custom_instructions.json"
  echo "=== CUSTOM INSTRUCTIONS ===" > "$GPT_FILE"
  cat "$USER_DIR/custom_instructions.json" >> "$GPT_FILE"
  echo -e "\n\n=== OPENAPI.YAML ===" >> "$GPT_FILE"
  cat "$USER_DIR/openapi.yaml" >> "$GPT_FILE"
else
  echo "Template files missing. You can still run Orchestrate." > "$GPT_FILE"
fi

echo ""
echo "Instruction file content:"
cat "$GPT_FILE"

# Launch tunnel + FastAPI
ngrok config add-authtoken "$NGROK_TOKEN"
ngrok http --domain="$NGROK_DOMAIN" 8000 > /dev/null &
sleep 3
exec uvicorn jarvis:app --host 0.0.0.0 --port 8000
