#!/bin/bash
#
# OrchestrateOS Native macOS Installer
# Handles complete setup: dependencies, Claude Code CLI, repo clone, ngrok, FastAPI, LaunchAgent
#

set -e

INSTALL_DIR="/Applications/OrchestrateOS.app/Contents/Resources/orchestrate"
SUPPORT_DIR="$HOME/Library/Application Support/OrchestrateOS"
LAUNCHAGENT_DIR="$HOME/Library/LaunchAgents"
REPO_URL="https://github.com/unmistakablecreative/orchestrate-gershwin.git"
BIN_ID="694f0af6ae596e708fb2bd68"
API_KEY='$2a$10$MoavwaWsCucy2FkU/5ycV.lBTPWoUq4uKHhCi9Y47DOHWyHFL3o2C'

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 OrchestrateOS Native Installer"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ============================================
# 1. CHECK DEPENDENCIES
# ============================================
echo "📋 Checking dependencies..."

# Check Xcode Command Line Tools
if ! xcode-select -p &>/dev/null; then
  echo "   ⏳ Installing Xcode Command Line Tools..."
  xcode-select --install
  echo "   ⚠️  Please complete the Xcode CLT installation, then run this script again."
  exit 1
else
  echo "   ✅ Xcode Command Line Tools"
fi

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
  echo "   ❌ Python 3.10+ required (found $PYTHON_VERSION)"
  echo "   Install via: brew install python@3.11"
  exit 1
else
  echo "   ✅ Python $PYTHON_VERSION"
fi

# Check pip
if ! python3 -m pip --version &>/dev/null; then
  echo "   ❌ pip not found. Install: python3 -m ensurepip"
  exit 1
else
  echo "   ✅ pip available"
fi

# ============================================
# 2. INSTALL PYTHON DEPENDENCIES
# ============================================
echo ""
echo "📦 Installing Python dependencies..."

DEPS="fastapi uvicorn watchdog requests httpx python-multipart pyyaml aiofiles"
for dep in $DEPS; do
  if python3 -c "import $dep" 2>/dev/null; then
    echo "   ✅ $dep"
  else
    echo "   ⏳ Installing $dep..."
    python3 -m pip install "$dep" -q
    echo "   ✅ $dep installed"
  fi
done

# ============================================
# 3. INSTALL CLAUDE CODE CLI
# ============================================
echo ""
echo "📦 Installing Claude Code CLI..."

CLAUDE_INSTALLED=false

if command -v claude &>/dev/null; then
  CLAUDE_INSTALLED=true
  echo "   ✅ Claude Code already installed"
else
  # Try brew first
  if command -v brew &>/dev/null; then
    echo "   ⏳ Trying Homebrew install..."
    if brew install claude-code 2>/dev/null; then
      CLAUDE_INSTALLED=true
      echo "   ✅ Installed via Homebrew"
    fi
  fi

  # Fallback to direct install
  if [ "$CLAUDE_INSTALLED" = false ]; then
    echo "   ⏳ Trying direct install..."
    if curl -fsSL https://claude.ai/install.sh | bash 2>/dev/null; then
      CLAUDE_INSTALLED=true
      echo "   ✅ Installed via direct download"
    fi
  fi

  if [ "$CLAUDE_INSTALLED" = false ]; then
    echo "   ⚠️  Claude Code install failed - manual setup may be needed"
    echo "      See: https://docs.claude.com/en/docs/claude-code/installation"
  fi
fi

# ============================================
# 4. CLONE ORCHESTRATE-GERSHWIN REPO
# ============================================
echo ""
echo "📂 Setting up OrchestrateOS..."

mkdir -p "$(dirname "$INSTALL_DIR")"

if [ -d "$INSTALL_DIR/.git" ]; then
  echo "   ⏳ Updating existing installation..."
  cd "$INSTALL_DIR"
  git pull --quiet
  echo "   ✅ Updated to latest"
else
  echo "   ⏳ Cloning orchestrate-gershwin..."
  rm -rf "$INSTALL_DIR" 2>/dev/null || true
  git clone "$REPO_URL" "$INSTALL_DIR" --quiet
  echo "   ✅ Cloned to $INSTALL_DIR"
fi

# ============================================
# 5. PROMPT FOR NGROK CREDENTIALS
# ============================================
echo ""
echo "🔐 Ngrok Setup"
echo ""
echo "You need an ngrok account with a static domain."
echo "Get one free at: https://dashboard.ngrok.com/get-started/your-authtoken"
echo ""

read -p "Enter your ngrok authtoken: " NGROK_TOKEN
read -p "Enter your ngrok domain (e.g. clever-bear.ngrok-free.app): " NGROK_DOMAIN

# Clean domain
NGROK_DOMAIN=$(echo "$NGROK_DOMAIN" | sed 's|^https\?://||' | sed 's|/$||')

if [[ ! $NGROK_DOMAIN =~ \. ]]; then
  echo "   ⚠️  Domain doesn't look valid. Continuing anyway..."
fi

# Configure ngrok
if command -v ngrok &>/dev/null; then
  ngrok config add-authtoken "$NGROK_TOKEN"
  echo "   ✅ Ngrok configured"
else
  echo "   ⏳ Installing ngrok..."
  if command -v brew &>/dev/null; then
    brew install ngrok/ngrok/ngrok --quiet
    ngrok config add-authtoken "$NGROK_TOKEN"
    echo "   ✅ Ngrok installed and configured"
  else
    echo "   ❌ ngrok not found. Install: brew install ngrok/ngrok/ngrok"
    exit 1
  fi
fi

# ============================================
# 6. START NGROK TUNNEL AND FASTAPI SERVER
# ============================================
echo ""
echo "🌐 Starting services..."

# Kill any existing processes
pkill -f "ngrok http" 2>/dev/null || true
pkill -f "uvicorn jarvis:app" 2>/dev/null || true
sleep 1

# Start ngrok in background
ngrok http --domain="$NGROK_DOMAIN" 8000 > /dev/null 2>&1 &
NGROK_PID=$!
echo "   ✅ Ngrok tunnel started (PID: $NGROK_PID)"

sleep 2

# Start FastAPI server
cd "$INSTALL_DIR"
python3 -m uvicorn jarvis:app --host 0.0.0.0 --port 8000 > "$SUPPORT_DIR/server.log" 2>&1 &
SERVER_PID=$!
echo "   ✅ FastAPI server started (PID: $SERVER_PID)"

sleep 2

# ============================================
# 7. CREATE SYSTEM IDENTITY AND REGISTER INSTALL
# ============================================
echo ""
echo "📊 Registering installation..."

mkdir -p "$SUPPORT_DIR"

IDENTITY_FILE="$SUPPORT_DIR/system_identity.json"

if [ ! -f "$IDENTITY_FILE" ]; then
  UUID=$(uuidgen | tr '[:upper:]' '[:lower:]')
  USER_ID="orch-${UUID}"
  TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

  echo "{\"user_id\": \"$USER_ID\", \"installed_at\": \"$TIMESTAMP\", \"ngrok_domain\": \"$NGROK_DOMAIN\"}" > "$IDENTITY_FILE"

  # Register in JSONBin ledger
  LEDGER_RESPONSE=$(curl -s -X GET "https://api.jsonbin.io/v3/b/$BIN_ID/latest" -H "X-Master-Key: $API_KEY")

  if echo "$LEDGER_RESPONSE" | jq -e '.record' &>/dev/null; then
    # Update existing ledger
    PAYLOAD=$(echo "$LEDGER_RESPONSE" | jq --arg uid "$USER_ID" --arg ts "$TIMESTAMP" \
      '.record.installs[$uid] = {referral_count: 0, referral_credits: 3, tools_unlocked: ["json_manager"], timestamp: $ts} |
       {filename: .record.filename, installs: .record.installs}')

    curl -s -X PUT "https://api.jsonbin.io/v3/b/$BIN_ID" \
      -H "Content-Type: application/json" \
      -H "X-Master-Key: $API_KEY" \
      -d "$PAYLOAD" > /dev/null

    echo "   ✅ Install registered: $USER_ID"
  else
    # Initialize new ledger
    INIT_PAYLOAD=$(jq -n --arg uid "$USER_ID" --arg ts "$TIMESTAMP" \
      '{filename: "install_ledger.json", installs: {($uid): {referral_count: 0, referral_credits: 3, tools_unlocked: ["json_manager"], timestamp: $ts}}}')

    curl -s -X PUT "https://api.jsonbin.io/v3/b/$BIN_ID" \
      -H "Content-Type: application/json" \
      -H "X-Master-Key: $API_KEY" \
      -d "$INIT_PAYLOAD" > /dev/null

    echo "   ✅ Ledger initialized with: $USER_ID"
  fi
else
  echo "   ✅ Already registered"
  USER_ID=$(jq -r '.user_id' "$IDENTITY_FILE")
fi

# ============================================
# 8. INSTALL LAUNCHAGENT FOR AUTO-START
# ============================================
echo ""
echo "⚡ Setting up auto-start..."

mkdir -p "$LAUNCHAGENT_DIR"

PLIST_FILE="$LAUNCHAGENT_DIR/com.orchestrateos.engine.plist"

cat > "$PLIST_FILE" << EOF
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
        <string>cd $INSTALL_DIR && ngrok http --domain=$NGROK_DOMAIN 8000 > /dev/null 2>&1 &amp; sleep 2 &amp;&amp; python3 -m uvicorn jarvis:app --host 0.0.0.0 --port 8000</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$SUPPORT_DIR/engine.log</string>
    <key>StandardErrorPath</key>
    <string>$SUPPORT_DIR/engine_error.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
EOF

launchctl unload "$PLIST_FILE" 2>/dev/null || true
launchctl load "$PLIST_FILE"
echo "   ✅ LaunchAgent installed (auto-starts on login)"

# ============================================
# 9. SAVE CONFIG AND LAUNCH SETUP WIZARD
# ============================================
echo ""
echo "💾 Saving configuration..."

mkdir -p "$INSTALL_DIR/data"
echo "{ \"token\": \"$NGROK_TOKEN\", \"domain\": \"$NGROK_DOMAIN\" }" > "$INSTALL_DIR/data/ngrok.json"
echo "   ✅ Config saved"

# Export for envsubst
export NGROK_DOMAIN
export DOMAIN="$NGROK_DOMAIN"
export SAFE_DOMAIN=$(echo "$NGROK_DOMAIN" | sed 's|https://||g' | sed 's|[-.]|_|g')

if [ -f "$INSTALL_DIR/openapi_template.yaml" ] && [ -f "$INSTALL_DIR/instructions_template.json" ]; then
  envsubst < "$INSTALL_DIR/openapi_template.yaml" > "$SUPPORT_DIR/openapi.yaml"
  envsubst < "$INSTALL_DIR/instructions_template.json" > "$SUPPORT_DIR/custom_instructions.json"
  echo "   ✅ GPT config files generated"
fi

# ============================================
# 10. LAUNCH SETUP WIZARD IN NEW TERMINAL
# ============================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎉 OrchestrateOS Installation Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Your system is running at: https://$NGROK_DOMAIN"
echo "User ID: $USER_ID"
echo ""
echo "Config files saved to: $SUPPORT_DIR"
echo "Install directory: $INSTALL_DIR"
echo ""

if [ -f "$INSTALL_DIR/setup_wizard.sh" ]; then
  echo "Launching Custom GPT setup wizard..."
  sleep 1
  osascript -e "tell application \"Terminal\" to do script \"'$INSTALL_DIR/setup_wizard.sh' '$NGROK_DOMAIN'\""
else
  echo "⚠️  Setup wizard not found. Manual setup required."
  echo "   Copy contents from $SUPPORT_DIR/ to your Custom GPT."
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Done! Your OrchestrateOS is ready."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
