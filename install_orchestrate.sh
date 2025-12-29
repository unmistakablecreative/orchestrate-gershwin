#!/bin/bash
#
# OrchestrateOS Gershwin Native macOS Installer
# Installation only - wizard is separate
#

set -e

INSTALL_DIR="/Applications/OrchestrateOS.app/Contents/Resources/orchestrate"
SUPPORT_DIR="$HOME/Library/Application Support/OrchestrateOS"
LAUNCHAGENT_DIR="$HOME/Library/LaunchAgents"
ORCHESTRATE_DOCS="/Users/$(whoami)/Documents/Orchestrate"
REPO_URL="https://github.com/unmistakablecreative/orchestrate-gershwin.git"
BIN_ID="694f0af6ae596e708fb2bd68"
API_KEY='$2a$10$MoavwaWsCucy2FkU/5ycV.lBTPWoUq4uKHhCi9Y47DOHWyHFL3o2C'

# Get credentials from environment
NGROK_TOKEN="${NGROK_TOKEN_INPUT}"
NGROK_DOMAIN="${NGROK_DOMAIN_INPUT}"
NGROK_DOMAIN=$(echo "$NGROK_DOMAIN" | sed 's|^https\?://||' | sed 's|/$||')

echo "📦 Installing Homebrew..."
if ! command -v brew &>/dev/null; then
  NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  if [[ $(uname -m) == 'arm64' ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  else
    eval "$(/usr/local/bin/brew shellenv)"
  fi
fi

echo "🐍 Installing Python..."
if ! command -v python3.11 &>/dev/null && ! command -v python3.12 &>/dev/null; then
  brew install python@3.11 -q
fi

if command -v python3.12 &>/dev/null; then
  PYTHON_PATH=$(command -v python3.12)
elif command -v python3.11 &>/dev/null; then
  PYTHON_PATH=$(command -v python3.11)
else
  echo "❌ ERROR: Could not find Homebrew Python"
  exit 1
fi

echo "📝 Installing gettext..."
if ! command -v envsubst &>/dev/null; then
  brew install gettext -q
  brew link --force gettext
fi

echo "📦 Installing Python dependencies..."
$PYTHON_PATH -m pip install --break-system-packages \
  fastapi \
  uvicorn \
  watchdog \
  requests \
  httpx \
  python-multipart \
  pyyaml \
  aiofiles \
  pdfplumber \
  pillow \
  beautifulsoup4 \
  python-docx \
  PyPDF2 \
  reportlab \
  requests-oauthlib \
  markdown2

echo "🤖 Installing Claude Code CLI..."
if ! command -v claude &>/dev/null; then
  curl -fsSL https://claude.ai/install.sh | bash
fi

echo "🌐 Installing ngrok..."
if ! command -v ngrok &>/dev/null; then
  brew install ngrok/ngrok/ngrok -q
fi

echo "🔐 Configuring ngrok..."
ngrok config add-authtoken "$NGROK_TOKEN"

echo "📁 Creating directories..."
mkdir -p "$(dirname "$INSTALL_DIR")" || { echo "❌ Failed to create install dir"; exit 1; }
mkdir -p "$SUPPORT_DIR" || { echo "❌ Failed to create support dir"; exit 1; }
mkdir -p "$LAUNCHAGENT_DIR" || { echo "❌ Failed to create launch agent dir"; exit 1; }
mkdir -p "$ORCHESTRATE_DOCS/dropzone" || { echo "❌ Failed to create dropzone"; exit 1; }
mkdir -p "$ORCHESTRATE_DOCS/vault/watch_books" || { echo "❌ Failed to create watch_books"; exit 1; }
mkdir -p "$ORCHESTRATE_DOCS/vault/watch_transcripts" || { echo "❌ Failed to create watch_transcripts"; exit 1; }
mkdir -p "$ORCHESTRATE_DOCS/orchestrate_exports/markdown" || { echo "❌ Failed to create exports"; exit 1; }

echo "📂 Cloning OrchestrateOS repository..."
if [ -d "$INSTALL_DIR/.git" ]; then
  cd "$INSTALL_DIR"
  git pull --quiet
else
  rm -rf "$INSTALL_DIR" 2>/dev/null || true
  git clone "$REPO_URL" "$INSTALL_DIR" --quiet
fi

echo "📊 Registering installation..."
IDENTITY_FILE="$SUPPORT_DIR/system_identity.json"
if [ ! -f "$IDENTITY_FILE" ]; then
  UUID=$(uuidgen | tr '[:upper:]' '[:lower:]')
  USER_ID="orch-${UUID}"
  TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  echo "{\"user_id\": \"$USER_ID\", \"installed_at\": \"$TIMESTAMP\", \"ngrok_domain\": \"$NGROK_DOMAIN\"}" > "$IDENTITY_FILE"
  
  LEDGER_RESPONSE=$(curl -s -X GET "https://api.jsonbin.io/v3/b/$BIN_ID/latest" -H "X-Master-Key: $API_KEY")
  if echo "$LEDGER_RESPONSE" | jq -e '.record' &>/dev/null; then
    PAYLOAD=$(echo "$LEDGER_RESPONSE" | jq --arg uid "$USER_ID" --arg ts "$TIMESTAMP" \
      '.record.installs[$uid] = {referral_count: 0, referral_credits: 3, tools_unlocked: ["json_manager"], timestamp: $ts} |
       {filename: .record.filename, installs: .record.installs}')
    curl -s -X PUT "https://api.jsonbin.io/v3/b/$BIN_ID" -H "Content-Type: application/json" -H "X-Master-Key: $API_KEY" -d "$PAYLOAD" > /dev/null
  fi
fi

echo "🌐 Starting services..."
pkill -f "ngrok http" 2>/dev/null || true
pkill -f "uvicorn jarvis:app" 2>/dev/null || true
sleep 1

ngrok http --domain="$NGROK_DOMAIN" 8000 > /dev/null 2>&1 &
sleep 2

cd "$INSTALL_DIR"
$PYTHON_PATH -m uvicorn jarvis:app --host 0.0.0.0 --port 8000 > "$SUPPORT_DIR/server.log" 2>&1 &
sleep 2

echo "⚡ Setting up auto-start..."
PLIST_FILE="$LAUNCHAGENT_DIR/com.orchestrateos.engine.plist"

cat > "$PLIST_FILE" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.orchestrateos.engine</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>cd $INSTALL_DIR && ngrok http --domain=$NGROK_DOMAIN 8000 > /dev/null 2>&1 & sleep 2 && $PYTHON_PATH -m uvicorn jarvis:app --host 0.0.0.0 --port 8000</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>$INSTALL_DIR</string>
    <key>StandardOutPath</key>
    <string>$SUPPORT_DIR/orchestrate.log</string>
    <key>StandardErrorPath</key>
    <string>$SUPPORT_DIR/orchestrate.error.log</string>
</dict>
</plist>
PLISTEOF

launchctl unload "$PLIST_FILE" 2>/dev/null || true
launchctl load "$PLIST_FILE"

echo "🔄 Setting up auto-update..."
UPDATE_PLIST_FILE="$LAUNCHAGENT_DIR/com.orchestrateos.autoupdate.plist"

cat > "$UPDATE_PLIST_FILE" <<UPDATEEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.orchestrateos.autoupdate</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_PATH</string>
        <string>$INSTALL_DIR/tools/system_settings.py</string>
        <string>refresh_runtime</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>3</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>WorkingDirectory</key>
    <string>$INSTALL_DIR</string>
    <key>StandardOutPath</key>
    <string>$SUPPORT_DIR/autoupdate.log</string>
    <key>StandardErrorPath</key>
    <string>$SUPPORT_DIR/autoupdate.error.log</string>
</dict>
</plist>
UPDATEEOF

launchctl unload "$UPDATE_PLIST_FILE" 2>/dev/null || true
launchctl load "$UPDATE_PLIST_FILE"

echo "💾 Generating GPT config files..."
mkdir -p "$INSTALL_DIR/data"
echo "{ \"token\": \"$NGROK_TOKEN\", \"domain\": \"$NGROK_DOMAIN\" }" > "$INSTALL_DIR/data/ngrok.json"

export NGROK_DOMAIN
export DOMAIN="$NGROK_DOMAIN"
export SAFE_DOMAIN=$(echo "$NGROK_DOMAIN" | sed 's|https://||g' | sed 's|[-.]|_|g')

if [ -f "$INSTALL_DIR/openapi_template.yaml" ] && [ -f "$INSTALL_DIR/instructions_template.json" ]; then
  envsubst < "$INSTALL_DIR/openapi_template.yaml" > "$SUPPORT_DIR/openapi.yaml"
  envsubst < "$INSTALL_DIR/instructions_template.json" > "$SUPPORT_DIR/custom_instructions.json"
fi

echo "✅ Installation complete!"