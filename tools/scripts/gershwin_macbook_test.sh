#!/bin/bash
# Gershwin MacBook Test - Full Client-Server Registration Flow
# Tests: Bootstrap → Jarvis → /generate_identity → Central accounts.py registration → first_run.html
# Run from orchestrate-gershwin directory

# ========== CONFIG ==========
PORT=8765
CONFIG_FILE="/tmp/gershwin_config.json"
GERSHWIN_DIR="/Users/srinivas/Orchestrate Github/orchestrate-gershwin"
CENTRAL_SERVER="https://app.orchestrateos.io/execute_task"

# Clean up any previous test
rm -f "$CONFIG_FILE"

# ========== SECTION 1: Bootstrap Server with Full Form ==========
cat > /tmp/gershwin_bootstrap_server.py << 'PYSERVER'
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import urllib.parse

CONFIG_FILE = "/tmp/gershwin_config.json"

HTML_FORM = """<!DOCTYPE html>
<html>
<head>
    <title>Gershwin MacBook Test</title>
    <style>
        body { font-family: -apple-system, sans-serif; background: #1a1a2e; color: #eee;
               display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; padding: 20px; box-sizing: border-box; }
        .container { background: #16213e; padding: 40px; border-radius: 12px; width: 500px; max-width: 100%; }
        h1 { margin-top: 0; color: #a855f7; }
        p { color: #888; font-size: 14px; margin-bottom: 20px; }
        input { width: 100%; padding: 14px; margin: 8px 0 16px 0; border: 1px solid #333;
                border-radius: 6px; background: #0f0f23; color: #fff; box-sizing: border-box; font-size: 16px; }
        input:focus { border-color: #6366f1; outline: none; }
        button { width: 100%; padding: 14px; background: linear-gradient(90deg, #6366f1, #a855f7);
                 border: none; border-radius: 6px; color: #fff; font-weight: bold; cursor: pointer; font-size: 16px; margin-top: 10px; }
        button:hover { opacity: 0.9; }
        label { display: block; color: #aaa; font-size: 13px; font-weight: 500; }
        .section { margin-bottom: 24px; padding-bottom: 24px; border-bottom: 1px solid #333; }
        .section:last-of-type { border-bottom: none; margin-bottom: 0; padding-bottom: 0; }
        h3 { color: #6366f1; margin: 0 0 12px 0; font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px; }
        .hint { color: #666; font-size: 12px; margin-top: -12px; margin-bottom: 16px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎹 Gershwin MacBook Test</h1>
        <p>Full client-server registration test. Fill in your details to register with the central OrchestrateOS server.</p>
        <form method="POST" action="/submit">
            <div class="section">
                <h3>Your Info</h3>
                <label>Name</label>
                <input type="text" name="name" placeholder="Srini Kadamati" required>

                <label>Email</label>
                <input type="email" name="email" placeholder="srini@example.com" required>
            </div>

            <div class="section">
                <h3>Ngrok Configuration</h3>
                <label>Ngrok Authtoken</label>
                <input type="text" name="ngrok_authtoken" placeholder="2up3BdDUd9Var3zdSB0ym2gJv0C_..." required>
                <p class="hint">Get from dashboard.ngrok.com/get-started/your-authtoken</p>

                <label>Ngrok Tunnel URL</label>
                <input type="text" name="tunnel_url" placeholder="supposedly-faithful-termite.ngrok-free.app" required>
                <p class="hint">Your reserved ngrok domain (without https://)</p>
            </div>

            <button type="submit">Start Installation →</button>
        </form>
    </div>
</body>
</html>"""

SUCCESS_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>Installing Gershwin...</title>
    <style>
        body { font-family: -apple-system, sans-serif; background: #1a1a2e; color: #eee;
               display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .container { background: #16213e; padding: 40px; border-radius: 12px; text-align: center; }
        h1 { color: #22c55e; }
        p { color: #888; }
        .spinner { width: 40px; height: 40px; border: 3px solid rgba(255,255,255,0.1);
                   border-top-color: #a855f7; border-radius: 50%; animation: spin 1s linear infinite; margin: 20px auto; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .steps { text-align: left; margin-top: 20px; }
        .step { padding: 8px 0; color: #666; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 Installing Gershwin</h1>
        <div class="spinner"></div>
        <p>Setting up your OrchestrateOS instance...</p>
        <div class="steps">
            <div class="step">✓ Config saved</div>
            <div class="step">→ Starting Jarvis server</div>
            <div class="step">→ Connecting ngrok tunnel</div>
            <div class="step">→ Registering with central server</div>
            <div class="step">→ Redirecting to first_run.html</div>
        </div>
    </div>
</body>
</html>"""

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(HTML_FORM.encode())

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode()
        params = urllib.parse.parse_qs(post_data)

        name = params.get("name", [""])[0]
        email = params.get("email", [""])[0]
        ngrok_authtoken = params.get("ngrok_authtoken", [""])[0]
        tunnel_url = params.get("tunnel_url", [""])[0]

        # Strip protocol if provided
        tunnel_url = tunnel_url.replace("https://", "").replace("http://", "").strip("/")

        config = {
            "name": name,
            "email": email,
            "ngrok_authtoken": ngrok_authtoken,
            "tunnel_url": tunnel_url
        }

        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)

        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(SUCCESS_HTML.encode())

    def log_message(self, format, *args):
        pass

if __name__ == "__main__":
    server = HTTPServer(("localhost", 8765), Handler)
    print("Bootstrap server running on http://localhost:8765")
    server.serve_forever()
PYSERVER

echo "=========================================="
echo "  GERSHWIN MACBOOK TEST"
echo "  Full Client-Server Registration Flow"
echo "=========================================="
echo ""
echo "Config will be written to: $CONFIG_FILE"
echo ""

# Start the bootstrap server in background
python3 /tmp/gershwin_bootstrap_server.py &
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

# ========== SECTION 4: Start Jarvis ==========
echo ""
echo "Starting Jarvis on port 5004..."
cd "$GERSHWIN_DIR"

uvicorn jarvis:app --host 0.0.0.0 --port 5004 &
JARVIS_PID=$!

echo "Waiting for Jarvis to initialize..."
sleep 3

# ========== SECTION 5: Start Ngrok Tunnel ==========
echo ""
echo "Starting ngrok tunnel to port 5004..."
ngrok http --url=$TUNNEL_URL 5004 &
NGROK_PID=$!

echo "Waiting for ngrok tunnel to connect..."
sleep 3

# ========== SECTION 6: Generate Identity ==========
echo ""
echo "Calling /generate_identity to create system_identity.json..."
curl -s -X POST "http://localhost:5004/generate_identity" -H "Content-Type: application/json" -d '{}'

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
  -d "{\"tool_name\": \"accounts\", \"action\": \"register_user\", \"params\": {\"system_id\": \"$SYSTEM_ID\", \"name\": \"$NAME\", \"email\": \"$EMAIL\", \"ngrok_tunnel\": \"$TUNNEL_URL\"}}")

echo "Registration response: $REGISTER_RESPONSE"

# ========== SECTION 8: Browser Redirect ==========
FIRST_RUN_URL="https://${TUNNEL_URL}/semantic_memory/first_run.html"
echo ""
echo "Opening: $FIRST_RUN_URL"
open "$FIRST_RUN_URL"

echo ""
echo "=========================================="
echo "  TEST COMPLETE"
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
