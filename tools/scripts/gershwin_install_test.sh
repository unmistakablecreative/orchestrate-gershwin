#!/bin/bash
# Gershwin Handoff Test - Bootstrap → Jarvis → first_run.html
# Tests the data handoff from bootstrap form to Jarvis startup
# Run from orchestrate-gershwin directory

# ========== SECTION 1: Bootstrap Server ==========
# Captures ngrok URL via form, writes to JSON
# VALIDATED: Form capture to JSON works

PORT=8765
CONFIG_FILE="/tmp/gershwin_installer_config.json"
GERSHWIN_DIR="/Users/srinivas/Orchestrate Github/orchestrate-gershwin"

# Clean up any previous test
rm -f "$CONFIG_FILE"

# Create the embedded Python server (simplified - just ngrok URL)
cat > /tmp/gershwin_form_server.py << 'PYSERVER'
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import urllib.parse

CONFIG_FILE = "/tmp/gershwin_installer_config.json"

HTML_FORM = """<!DOCTYPE html>
<html>
<head>
    <title>Gershwin Handoff Test</title>
    <style>
        body { font-family: -apple-system, sans-serif; background: #1a1a2e; color: #eee;
               display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .container { background: #16213e; padding: 40px; border-radius: 12px; width: 500px; }
        h1 { margin-top: 0; color: #a855f7; }
        p { color: #888; font-size: 14px; margin-bottom: 20px; }
        input { width: 100%; padding: 14px; margin: 10px 0; border: 1px solid #333;
                border-radius: 6px; background: #0f0f23; color: #fff; box-sizing: border-box; font-size: 16px; }
        button { width: 100%; padding: 14px; background: linear-gradient(90deg, #6366f1, #a855f7);
                 border: none; border-radius: 6px; color: #fff; font-weight: bold; cursor: pointer; font-size: 16px; }
        button:hover { opacity: 0.9; }
        label { display: block; margin-top: 15px; color: #888; font-size: 13px; }
        code { background: #0f0f23; padding: 4px 8px; border-radius: 4px; color: #00d4ff; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎹 Handoff Test</h1>
        <p>Testing bootstrap → jarvis handoff. Enter your ngrok tunnel URL (the one you already have running).</p>
        <form method="POST" action="/submit">
            <label>Ngrok Tunnel URL</label>
            <input type="text" name="tunnel_url" placeholder="supposedly-faithful-termite.ngrok-free.app" required>
            <p style="margin-top: 20px; color: #666;">This will start Jarvis and redirect to <code>{tunnel_url}/semantic_memory/first_run.html</code></p>
            <button type="submit">Start Jarvis →</button>
        </form>
    </div>
</body>
</html>"""

SUCCESS_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>Starting Jarvis...</title>
    <style>
        body { font-family: -apple-system, sans-serif; background: #1a1a2e; color: #eee;
               display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .container { background: #16213e; padding: 40px; border-radius: 12px; text-align: center; }
        h1 { color: #22c55e; }
        p { color: #888; }
        .spinner { width: 40px; height: 40px; border: 3px solid rgba(255,255,255,0.1);
                   border-top-color: #a855f7; border-radius: 50%; animation: spin 1s linear infinite; margin: 20px auto; }
        @keyframes spin { to { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 Starting Jarvis</h1>
        <div class="spinner"></div>
        <p>Redirecting to first_run.html in a moment...</p>
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

        tunnel_url = params.get("tunnel_url", [""])[0]
        # Strip protocol if provided
        tunnel_url = tunnel_url.replace("https://", "").replace("http://", "").strip("/")

        config = {
            "tunnel_url": tunnel_url
        }

        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)

        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(SUCCESS_HTML.encode())

    def log_message(self, format, *args):
        pass  # Suppress server logs

if __name__ == "__main__":
    server = HTTPServer(("localhost", 8765), Handler)
    print("Bootstrap server running on http://localhost:8765")
    server.serve_forever()
PYSERVER

echo "=========================================="
echo "  GERSHWIN HANDOFF TEST"
echo "  Bootstrap → Jarvis → first_run.html"
echo "=========================================="
echo ""
echo "Config will be written to: $CONFIG_FILE"
echo ""

# Start the bootstrap server in background
python3 /tmp/gershwin_form_server.py &
BOOTSTRAP_PID=$!

# Give server a moment to start
sleep 1

# Open browser to the form
echo "Opening browser to bootstrap form..."
open "http://localhost:$PORT"

# Poll for the config file
echo "Waiting for form submission..."
while [ ! -f "$CONFIG_FILE" ]; do
    sleep 1
done

# ========== SECTION 2: Jarvis Startup ==========
# Reads URL from JSON, starts uvicorn jarvis:app
# THIS IS WHAT WE'RE TESTING

echo ""
echo "Form submitted! Reading config..."

# Read the tunnel URL from config
TUNNEL_URL=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['tunnel_url'])")
echo "Tunnel URL: $TUNNEL_URL"

# Kill the bootstrap server
echo "Killing bootstrap server..."
kill $BOOTSTRAP_PID 2>/dev/null

# Small delay to ensure port is freed
sleep 1

# ========== SECTION 3: Start Jarvis ==========
echo ""
echo "Starting Jarvis on port 5004..."
cd "$GERSHWIN_DIR"

# Start uvicorn in background
uvicorn jarvis:app --host 0.0.0.0 --port 5004 &
JARVIS_PID=$!

# Wait for Jarvis to start
echo "Waiting for Jarvis to initialize..."
sleep 3

# ========== SECTION 3.5: Start Ngrok Tunnel ==========
echo ""
echo "Configuring ngrok authtoken for test account..."
ngrok config add-authtoken 2up3BdDUd9Var3zdSB0ym2gJv0C_5PRgyUMNUTMR2ksN6VXXV

echo "Starting ngrok tunnel to port 5004..."
ngrok http --url=$TUNNEL_URL 5004 &
NGROK_PID=$!

# Wait for ngrok to establish tunnel
echo "Waiting for ngrok tunnel to connect..."
sleep 3

# ========== SECTION 4: Browser Redirect ==========
# Transitions from localhost bootstrap to ngrok/first_run.html
# THIS IS WHAT WE'RE TESTING

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
echo "Tunnel URL: $TUNNEL_URL"
echo "First Run: $FIRST_RUN_URL"
echo ""
echo "To stop everything: kill $JARVIS_PID $NGROK_PID"
echo ""

# ========== SECTION 5: Repo Pull (FUTURE) ==========
# Clone orchestrate-gershwin, install deps
# ADD LATER AFTER HANDOFF VALIDATED

# ========== SECTION 6: Ngrok Config (FUTURE) ==========
# Configure ngrok with token, start tunnel
# ADD LATER AFTER HANDOFF VALIDATED
