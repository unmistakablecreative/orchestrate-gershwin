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

  if [ -f "$OUTPUT_DIR/referrer.txt" ]; then
    REFERRER_ID=$(cat "$OUTPUT_DIR/referrer.txt")
  else
    REFERRER_ID=""
  fi

  LEDGER=$(curl -s -X GET "https://api.jsonbin.io/v3/b/$BIN_ID/latest" -H "X-Master-Key: $API_KEY")
  INSTALLS=$(echo "$LEDGER" | jq '.record.installs')

  INSTALLS=$(echo "$INSTALLS" | jq --arg uid "$USER_ID" --arg ts "$TIMESTAMP" \
    '.[$uid] = { referral_count: 0, referral_credits: 0, tools_unlocked: ["json_manager"], timestamp: $ts }')

  if [ "$REFERRER_ID" != "" ]; then
    INSTALLS=$(echo "$INSTALLS" | jq --arg rid "$REFERRER_ID" \
      'if .[$rid] != null then .[$rid].referral_count += 1 | .[$rid].referral_credits += 1 else . end')
  fi

  FINAL=$(jq -n --argjson installs "$INSTALLS" '{filename: "install_ledger.json", installs: $installs}')
  echo "$FINAL" | curl -s -X PUT "https://api.jsonbin.io/v3/b/$BIN_ID" \
    -H "Content-Type: application/json" -H "X-Master-Key: $API_KEY" --data @-

  echo '{ "referral_count": 0, "referral_credits": 0, "tools_unlocked": ["json_manager"] }' > "$STATE_DIR/referrals.json"
fi

RUNTIME_DIR="/opt/orchestrate-core-runtime"

if [ ! -d "$RUNTIME_DIR/.git" ]; then
  git clone https://github.com/unmistakablecreative/orchestrate-core-runtime.git "$RUNTIME_DIR"
fi

mkdir -p "$RUNTIME_DIR/data"
echo '{ "token": "'$NGROK_TOKEN'", "domain": "'$NGROK_DOMAIN'" }' > "$RUNTIME_DIR/data/ngrok.json"

cd "$RUNTIME_DIR"
envsubst < openapi_template.yaml > "$OUTPUT_DIR/openapi.yaml"
envsubst < instructions_template.json > "$OUTPUT_DIR/custom_instructions.json"

echo "📎 === CUSTOM INSTRUCTIONS ===" > "$OUTPUT_DIR/_paste_into_gpt.txt"
cat "$OUTPUT_DIR/custom_instructions.json" >> "$OUTPUT_DIR/_paste_into_gpt.txt"
echo -e "\n\n📎 === OPENAPI.YAML ===" >> "$OUTPUT_DIR/_paste_into_gpt.txt"
cat "$OUTPUT_DIR/openapi.yaml" >> "$OUTPUT_DIR/_paste_into_gpt.txt"

ngrok config add-authtoken "$NGROK_TOKEN"
ngrok http --domain="$NGROK_DOMAIN" 8000 > /dev/null &

sleep 3
exec uvicorn jarvis:app --host 0.0.0.0 --port 8000
