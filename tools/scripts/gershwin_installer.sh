#!/bin/bash
# Gershwin Installer - Full Client-Server Registration Flow
# Installs OrchestrateOS to ~/Library/Application Support/OrchestrateOS
# Run from orchestrate-gershwin directory

# ========== CONFIG ==========
PORT=8765
CONFIG_FILE="$HOME/gershwin_config.json"
SCRIPT_DIR=$(cd $(dirname $0) && pwd)
GERSHWIN_DIR="$HOME/Library/Application Support/OrchestrateOS"
CENTRAL_SERVER="https://app.orchestrateos.io/execute_task"

# Add user Python bin to PATH so pip-installed binaries are found
export PATH="$HOME/Library/Python/3.9/bin:$HOME/Library/Python/3.10/bin:$HOME/Library/Python/3.11/bin:$HOME/.local/bin:$PATH"

# Dependency checks
# Auto-install ngrok if missing (no sudo, no brew, silent)
if ! command -v ngrok &>/dev/null; then
    NGROK_DIR="$HOME/.local/bin"
    mkdir -p "$NGROK_DIR"
    ARCH=$(uname -m)
    if [ "$ARCH" = "arm64" ]; then
        NGROK_URL="https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-darwin-arm64.zip"
    else
        NGROK_URL="https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-darwin-amd64.zip"
    fi
    curl -sL "$NGROK_URL" -o /tmp/ngrok.zip
    unzip -q -o /tmp/ngrok.zip -d "$NGROK_DIR"
    rm -f /tmp/ngrok.zip
    export PATH="$NGROK_DIR:$PATH"
fi

# Clone repo if missing, then install dependencies
if [ ! -d "$GERSHWIN_DIR" ]; then
    echo "Gershwin directory not found. Cloning repository..."
    GERSHWIN_PARENT=$(dirname "$GERSHWIN_DIR")
    mkdir -p "$GERSHWIN_PARENT"
    git clone https://github.com/unmistakablecreative/orchestrate-gershwin.git "$GERSHWIN_DIR"

    # Copy LaunchAgent plist files
    mkdir -p ~/Library/LaunchAgents
    mkdir -p ~/Library/Logs/OrchestrateOS
    cp "$GERSHWIN_DIR/tools/launchagents/"*.plist ~/Library/LaunchAgents/
    # LaunchAgents will auto-start on next login — do NOT load them now to avoid port conflict during install

    # Copy skill file to Documents
    if [ -f "$GERSHWIN_DIR/orchestrate-gershwin.skill" ]; then
        cp "$GERSHWIN_DIR/orchestrate-gershwin.skill" ~/Documents/
    fi
fi
echo "Installing dependencies..."
pip3 install -r "$GERSHWIN_DIR/requirements.txt" --quiet

# Clean up any previous test
rm -f "$CONFIG_FILE"

# ========== SECTION 1: Bootstrap Server Serving Static HTML ==========
cat > $HOME/gershwin_bootstrap_server.py << 'PYSERVER'
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import os

CONFIG_FILE = os.path.expanduser("~/gershwin_config.json")
GERSHWIN_DIR = os.path.expanduser("~/Library/Application Support/OrchestrateOS")
BOOTSTRAP_HTML_PATH = os.path.join(GERSHWIN_DIR, "semantic_memory", "installer_bootstrap.html")

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        with open(BOOTSTRAP_HTML_PATH, 'r') as f:
            self.wfile.write(f.read().encode())

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode()

        try:
            data = json.loads(post_data)
        except json.JSONDecodeError:
            data = {}

        name = data.get("name", "")
        email = data.get("email", "")
        ngrok_authtoken = data.get("ngrok_authtoken", "")
        ngrok_url = data.get("ngrok_url", "")

        ngrok_url = ngrok_url.replace("https://", "").replace("http://", "").strip("/")

        config = {
            "name": name,
            "email": email,
            "ngrok_authtoken": ngrok_authtoken,
            "tunnel_url": ngrok_url
        }

        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)

        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"status": "success"}).encode())

    def log_message(self, format, *args):
        pass

if __name__ == "__main__":
    server = HTTPServer(("localhost", 8765), Handler)
    print("Bootstrap server running on http://localhost:8765")
    server.serve_forever()
PYSERVER

echo "=========================================="
echo "  ORCHESTRATEOS INSTALLER"
echo "  Full Client-Server Registration Flow"
echo "=========================================="
echo ""
echo "Config will be written to: $CONFIG_FILE"
echo ""

# Start the bootstrap server in background
python3 $HOME/gershwin_bootstrap_server.py &
BOOTSTRAP_PID=$!

sleep 1

# Open browser to the form
echo "Opening browser to bootstrap form..."
open "http://localhost:$PORT"

# Poll for the config file
echo "Waiting for form submission..."
while [ ! -f "$CONFIG_FILE" ]; do
    sleep 1
done

# ========== SECTION 2: Read Config ==========
echo ""
echo "Form submitted! Reading config..."

NAME=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['name'])")
EMAIL=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['email'])")
NGROK_AUTHTOKEN=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['ngrok_authtoken'])")
TUNNEL_URL=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['tunnel_url'])")

echo "Name: $NAME"
echo "Email: $EMAIL"
echo "Tunnel URL: $TUNNEL_URL"

# Kill the bootstrap server
echo "Killing bootstrap server..."
kill $BOOTSTRAP_PID 2>/dev/null
sleep 1

# ========== SECTION 3: Configure ngrok ==========
echo ""
echo "Configuring ngrok authtoken..."
ngrok config add-authtoken "$NGROK_AUTHTOKEN"

# ========== SECTION 4: Kill anything on 5004, then start Jarvis ==========
echo ""
echo "Clearing port 5004..."
lsof -ti :5004 | xargs kill -9 2>/dev/null || true
sleep 1

echo "Starting Jarvis on port 5004..."
cd "$GERSHWIN_DIR"

python3 -m uvicorn jarvis:app --host 0.0.0.0 --port 5004 &
JARVIS_PID=$!

echo "Waiting for Jarvis to initialize..."
sleep 3

# ========== SECTION 5: Kill any existing ngrok tunnel, then start ==========
echo ""
echo "Clearing existing ngrok tunnel..."
pkill -f "ngrok http" 2>/dev/null || true
sleep 1

echo "Starting ngrok tunnel to port 5004..."
ngrok http --domain=$TUNNEL_URL 5004 &
NGROK_PID=$!

echo "Waiting for ngrok tunnel to connect..."
sleep 3

# ========== SECTION 6: Generate Identity ==========
echo ""
echo "Calling /generate_identity to create system_identity.json..."
rm -f "$GERSHWIN_DIR/data/system_identity.json"
curl -s -X POST "http://localhost:5004/generate_identity" -H "Content-Type: application/json" -d "{\"name\": \"$NAME\", \"email\": \"$EMAIL\"}"

sleep 1

# ========== SECTION 7: Register with Central Server ==========
echo ""
echo "Reading system_id from system_identity.json..."
SYSTEM_ID=$(python3 -c "import json; print(json.load(open('$GERSHWIN_DIR/data/system_identity.json'))['user_id'])")
echo "System ID: $SYSTEM_ID"

echo ""
echo "Registering with central server at app.orchestrateos.io..."
REGISTER_RESPONSE=$(curl -s -X POST "$CENTRAL_SERVER" \
  -H "Content-Type: application/json" \
  -d "{\"tool_name\": \"account\", \"action\": \"register_user\", \"params\": {\"system_id\": \"$SYSTEM_ID\", \"name\": \"$NAME\", \"email\": \"$EMAIL\", \"ngrok_tunnel\": \"$TUNNEL_URL\"}}")

echo "Registration response: $REGISTER_RESPONSE"

# ========== SECTION 8: Browser Redirect ==========
FIRST_RUN_URL="https://${TUNNEL_URL}/semantic_memory/first_run.html"
echo ""
echo "Opening: $FIRST_RUN_URL"
open "$FIRST_RUN_URL"

echo ""
echo "=========================================="
echo "  INSTALLATION COMPLETE"
echo "=========================================="
echo ""
echo "Jarvis PID: $JARVIS_PID"
echo "Ngrok PID: $NGROK_PID"
echo "System ID: $SYSTEM_ID"
echo "Tunnel URL: $TUNNEL_URL"
echo "First Run: $FIRST_RUN_URL"
echo ""
echo "To stop everything: kill $JARVIS_PID $NGROK_PID"
echo ""
