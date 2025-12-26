#!/bin/bash
export PYTHONPATH="$PYTHONPATH:/opt/orchestrate-core-runtime"
USER_DIR="/orchestrate_user"
STATE_DIR="/container_state"
OUTPUT_DIR="/app"
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
  read -p "🔐 Enter your ngrok authtoken: " NGROK_TOKEN
fi
if [ -z "$NGROK_DOMAIN" ]; then
  read -p "🌐 Enter your ngrok domain (e.g. clever-bear.ngrok-free.app): " NGROK_DOMAIN
fi

export NGROK_TOKEN
export NGROK_DOMAIN
export DOMAIN="$NGROK_DOMAIN"
export SAFE_DOMAIN=$(echo "$NGROK_DOMAIN" | sed 's|https://||g' | sed 's|[-.]|_|g')

IDENTITY_FILE="$STATE_DIR/system_identity.json"
if [ ! -f "$IDENTITY_FILE" ]; then
  UUID=$(cat /proc/sys/kernel/random/uuid)
  USER_ID="orch-${UUID}"
  TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  echo "{\"user_id\": \"$USER_ID\", \"installed_at\": \"$TIMESTAMP\"}" > "$IDENTITY_FILE"
  
  # Ledger sync
  BIN_ID="68292fcf8561e97a50162139"
  API_KEY='$2a$10$MoavwaWsCucy2FkU/5ycV.lBTPWoUq4uKHhCi9Y47DOHWyHFL3o2C'
  
  # DEBUG: Check what's in both directories
  echo "DEBUG: Contents of /app:"
  ls -la /app/
  echo "DEBUG: Contents of /referral_data:"
  ls -la /referral_data/
  echo "DEBUG: Looking for: /referral_data/referrer.txt"
  
  if [ -f "/referral_data/referrer.txt" ]; then
    REFERRER_ID=$(cat "/referral_data/referrer.txt" | tr -d '\n\r' | xargs)
    echo "DEBUG: Found referrer ID: '$REFERRER_ID'"
    echo "DEBUG: Referrer ID length: ${#REFERRER_ID}"
  else
    REFERRER_ID=""
    echo "DEBUG: No referrer file found"
  fi
  
  echo "DEBUG: Fetching ledger from JSONBin..."
  LEDGER=$(curl -s -X GET "https://api.jsonbin.io/v3/b/$BIN_ID/latest" -H "X-Master-Key: $API_KEY")
  INSTALLS=$(echo "$LEDGER" | jq '.record.installs')
  
  # Add new user entry
  INSTALLS=$(echo "$INSTALLS" | jq --arg uid "$USER_ID" --arg ts "$TIMESTAMP" \
    '.[$uid] = { referral_count: 0, referral_credits: 3, tools_unlocked: ["json_manager"], timestamp: $ts }')
  
  if [ "$REFERRER_ID" != "" ]; then
    echo "DEBUG: About to credit referrer: '$REFERRER_ID'"
    # Check if referrer exists
    REFERRER_EXISTS=$(echo "$INSTALLS" | jq --arg rid "$REFERRER_ID" 'has($rid)')
    echo "DEBUG: Referrer exists in ledger: $REFERRER_EXISTS"
    
    if [ "$REFERRER_EXISTS" = "true" ]; then
      CURRENT_CREDITS=$(echo "$INSTALLS" | jq --arg rid "$REFERRER_ID" '.[$rid].referral_credits')
      echo "DEBUG: Current referrer credits: $CURRENT_CREDITS"
      
      INSTALLS=$(echo "$INSTALLS" | jq --arg rid "$REFERRER_ID" \
        'if .[$rid] != null then .[$rid].referral_count += 1 | .[$rid].referral_credits += 3 else . end')
      
      NEW_CREDITS=$(echo "$INSTALLS" | jq --arg rid "$REFERRER_ID" '.[$rid].referral_credits')
      echo "DEBUG: New referrer credits: $NEW_CREDITS"
      echo "DEBUG: Referrer crediting completed successfully"
    else
      echo "DEBUG: ERROR - Referrer ID not found in ledger!"
    fi
  else
    echo "DEBUG: No referrer to credit (empty or missing referrer.txt)"
  fi
  
  echo "DEBUG: Updating JSONBin ledger..."
  FINAL=$(jq -n --argjson installs "$INSTALLS" '{filename: "install_ledger.json", installs: $installs}')
  echo "$FINAL" | curl -s -X PUT "https://api.jsonbin.io/v3/b/$BIN_ID" \
    -H "Content-Type: application/json" -H "X-Master-Key: $API_KEY" --data @-
  echo "DEBUG: JSONBin update completed"
  
  echo '{ "referral_count": 0, "referral_credits": 3, "tools_unlocked": ["json_manager"] }' > "$STATE_DIR/referrals.json"
fi

RUNTIME_DIR="/opt/orchestrate-core-runtime"
if [ ! -d "$RUNTIME_DIR/.git" ]; then
  git clone https://github.com/unmistakablecreative/orchestrate-beta-sandbox.git "$RUNTIME_DIR"
fi

mkdir -p "$RUNTIME_DIR/data"
echo '{ "token": "'$NGROK_TOKEN'", "domain": "'$NGROK_DOMAIN'" }' > "$RUNTIME_DIR/data/ngrok.json"
cd "$RUNTIME_DIR"

# Writable GPT output path inside Docker (host-mapped)
GPT_FILE="/orchestrate_user/_paste_into_gpt.txt"
rm -f "$GPT_FILE"

if [ -f "openapi_template.yaml" ] && [ -f "instructions_template.json" ]; then
  envsubst < openapi_template.yaml > /orchestrate_user/openapi.yaml
  envsubst < instructions_template.json > /orchestrate_user/custom_instructions.json
  echo "📎 === CUSTOM INSTRUCTIONS ===" > "$GPT_FILE"
  cat /orchestrate_user/custom_instructions.json >> "$GPT_FILE"
  echo -e "\n\n📎 === OPENAPI.YAML ===" >> "$GPT_FILE"
  cat /orchestrate_user/openapi.yaml >> "$GPT_FILE"
else
  echo "⚠️ Template files missing. You can still run Orchestrate." > "$GPT_FILE"
fi

echo ""
echo "📄 Instruction file content:"
cat "$GPT_FILE"

# Launch tunnel + FastAPI
ngrok config add-authtoken "$NGROK_TOKEN"
ngrok http --domain="$NGROK_DOMAIN" 8000 > /dev/null &
sleep 3
exec uvicorn jarvis:app --host 0.0.0.0 --port 8000