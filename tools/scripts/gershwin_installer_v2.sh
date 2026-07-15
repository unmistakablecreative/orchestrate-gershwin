#!/bin/bash
# Gershwin Installer V2 - Full Client-Server Registration Flow
# Installs OrchestrateOS to ~/Library/Application Support/OrchestrateOS

# ========== CONFIG ==========
PORT=8765
CONFIG_FILE="$HOME/gershwin_config.json"
GERSHWIN_DIR="$HOME/Library/Application Support/OrchestrateOS"
CENTRAL_SERVER="https://app.orchestrateos.io/execute_task"

# Add user Python bin to PATH so pip-installed binaries are found
export PATH="$HOME/Library/Python/3.9/bin:$HOME/Library/Python/3.10/bin:$HOME/Library/Python/3.11/bin:$HOME/.local/bin:$PATH"

# Auto-install ngrok if missing
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

# Clone repo if missing
if [ ! -d "$GERSHWIN_DIR" ]; then
    echo "Gershwin directory not found. Cloning repository..."
    mkdir -p "$(dirname "$GERSHWIN_DIR")"
    git clone https://github.com/unmistakablecreative/orchestrate-gershwin.git "$GERSHWIN_DIR"

    # Copy skill file to Documents
    if [ -f "$GERSHWIN_DIR/orchestrate-gershwin.skill" ]; then
        cp "$GERSHWIN_DIR/orchestrate-gershwin.skill" ~/Documents/
    fi
fi

# ========== DEPENDENCY PROGRESS SERVER ==========
echo "Installing dependencies..."

# Initialize progress file
echo '{"current": "Initializing...", "message": "Starting installation", "index": 0, "total": 0, "percent": 0, "done": false}' > /tmp/gershwin_progress.json

# Create progress server
cat > /tmp/gershwin_dep_progress_server.py << 'PYSERVER'
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import os

GERSHWIN_DIR = os.path.expanduser("~/Library/Application Support/OrchestrateOS")
PROGRESS_FILE = "/tmp/gershwin_progress.json"
DEP_PROGRESS_HTML = os.path.join(GERSHWIN_DIR, "semantic_memory", "dep_progress.html")
INSTALL_CONFIG = os.path.join(GERSHWIN_DIR, "install_config.json")

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/progress":
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            try:
                with open(PROGRESS_FILE, 'r') as f:
                    self.wfile.write(f.read().encode())
            except:
                self.wfile.write(b'{"current": "Initializing...", "index": 0, "total": 0, "percent": 0, "done": false}')
        elif self.path == "/config":
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            try:
                with open(INSTALL_CONFIG, 'r') as f:
                    self.wfile.write(f.read().encode())
            except:
                self.wfile.write(b'{"packages": []}')
        else:
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            try:
                with open(DEP_PROGRESS_HTML, 'r') as f:
                    self.wfile.write(f.read().encode())
            except Exception as e:
                self.wfile.write(f"<html><body><h1>Loading...</h1><p>{e}</p></body></html>".encode())

    def log_message(self, format, *args):
        pass

if __name__ == "__main__":
    server = HTTPServer(("localhost", 8766), Handler)
    print("Dependency progress server running on http://localhost:8766")
    server.serve_forever()
PYSERVER

# Start progress server
python3 /tmp/gershwin_dep_progress_server.py &
DEP_PROGRESS_PID=$!
sleep 1

# Open browser to progress page
open "http://localhost:8766"

# Read packages from install_config.json and install each one
INSTALL_CONFIG_PATH="$GERSHWIN_DIR/install_config.json"
PACKAGES=$(python3 -c "import json; pkgs=json.load(open('$INSTALL_CONFIG_PATH'))['packages']; print('\n'.join(p['name']+'|||'+p['message'] for p in pkgs))")
TOTAL=$(echo "$PACKAGES" | wc -l | tr -d ' ')
INDEX=0

echo "$PACKAGES" | while read -r LINE; do
    if [ -n "$LINE" ]; then
        PACKAGE=$(echo "$LINE" | awk -F'[|][|][|]' '{print $1}')
        MESSAGE=$(echo "$LINE" | awk -F'[|][|][|]' '{print $2}')
        INDEX=$((INDEX + 1))
        PERCENT=$((INDEX * 100 / TOTAL))

        # Update progress file
        python3 -c "
import json
progress = {
    'current': '$PACKAGE',
    'message': '$MESSAGE',
    'index': $INDEX,
    'total': $TOTAL,
    'percent': $PERCENT,
    'done': False
}
with open('/tmp/gershwin_progress.json', 'w') as f:
    json.dump(progress, f)
"

        # Install the package
        pip3 install "$PACKAGE" --quiet 2>/dev/null
    fi
done

# Mark as done
python3 -c "
import json
progress = {
    'current': 'Complete',
    'message': 'All dependencies installed',
    'index': $TOTAL,
    'total': $TOTAL,
    'percent': 100,
    'done': True
}
with open('/tmp/gershwin_progress.json', 'w') as f:
    json.dump(progress, f)
"

# Wait for user to see completion, then kill server
sleep 2
kill $DEP_PROGRESS_PID 2>/dev/null

rm -f "$CONFIG_FILE"

# ========== SECTION 1: Bootstrap ==========
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
        ngrok_url = data.get("ngrok_url", "").replace("https://", "").replace("http://", "").strip("/")
        config = {
            "name": data.get("name", ""),
            "email": data.get("email", ""),
            "ngrok_authtoken": data.get("ngrok_authtoken", ""),
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
echo "=========================================="
echo ""

python3 $HOME/gershwin_bootstrap_server.py &
BOOTSTRAP_PID=$!
sleep 1

echo "Opening browser to bootstrap form..."
open "http://localhost:$PORT"

echo "Waiting for form submission..."
while [ ! -f "$CONFIG_FILE" ]; do
    sleep 1
done

# ========== SECTION 2: Read Config ==========
echo "Form submitted! Reading config..."
NAME=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['name'])")
EMAIL=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['email'])")
NGROK_AUTHTOKEN=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['ngrok_authtoken'])")
TUNNEL_URL=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['tunnel_url'])")

echo "Name: $NAME"
echo "Email: $EMAIL"
echo "Tunnel URL: $TUNNEL_URL"

kill $BOOTSTRAP_PID 2>/dev/null
sleep 1

# ========== SECTION 3: Configure ngrok ==========
echo "Configuring ngrok authtoken..."
ngrok config add-authtoken "$NGROK_AUTHTOKEN"

# ========== SECTION 4: Start Jarvis ==========
echo "Starting Jarvis on port 5004..."
cd "$GERSHWIN_DIR"
python3 -m uvicorn jarvis:app --host 0.0.0.0 --port 5004 &
JARVIS_PID=$!
echo "Waiting for Jarvis to initialize..."
sleep 3

# ========== SECTION 5: Start ngrok ==========
echo "Starting ngrok tunnel to port 5004..."
ngrok http --domain=$TUNNEL_URL 5004 &
NGROK_PID=$!
echo "Waiting for ngrok tunnel to connect..."
sleep 3

# ========== SECTION 6: Generate Identity ==========
echo "Calling /generate_identity to create system_identity.json..."
rm -f "$GERSHWIN_DIR/data/system_identity.json"
curl -s -X POST "http://localhost:5004/generate_identity" -H "Content-Type: application/json" -d "{\"name\": \"$NAME\", \"email\": \"$EMAIL\"}"
sleep 1

# ========== SECTION 7: Register with Central Server ==========
echo "Reading system_id from system_identity.json..."
SYSTEM_ID=$(python3 -c "import json; print(json.load(open('$GERSHWIN_DIR/data/system_identity.json'))['user_id'])")
echo "System ID: $SYSTEM_ID"

echo "Registering with central server..."
REGISTER_RESPONSE=$(curl -s -X POST "$CENTRAL_SERVER" \
  -H "Content-Type: application/json" \
  -d "{\"tool_name\": \"account\", \"action\": \"register_user\", \"params\": {\"system_id\": \"$SYSTEM_ID\", \"name\": \"$NAME\", \"email\": \"$EMAIL\", \"ngrok_tunnel\": \"$TUNNEL_URL\"}}")
echo "Registration response: $REGISTER_RESPONSE"

# ========== SECTION 8: Install LaunchAgents (after everything is working) ==========
echo "Installing LaunchAgents for auto-start on next login..."
mkdir -p ~/Library/LaunchAgents
mkdir -p ~/Library/Logs/OrchestrateOS
cp "$GERSHWIN_DIR/tools/launchagents/"*.plist ~/Library/LaunchAgents/

# ========== SECTION 9: Browser Redirect ==========
FIRST_RUN_URL="https://${TUNNEL_URL}/semantic_memory/first_run.html"
echo "Opening: $FIRST_RUN_URL"
open "$FIRST_RUN_URL"

echo ""
echo "=========================================="
echo "  INSTALLATION COMPLETE"
echo "=========================================="
echo "Jarvis PID: $JARVIS_PID"
echo "Ngrok PID: $NGROK_PID"
echo "System ID: $SYSTEM_ID"
echo "Tunnel URL: $TUNNEL_URL"
echo "First Run: $FIRST_RUN_URL"
echo ""
echo "To stop everything: kill $JARVIS_PID $NGROK_PID"
