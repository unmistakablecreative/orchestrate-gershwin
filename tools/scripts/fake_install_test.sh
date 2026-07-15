#!/bin/bash
# Test runner for config-driven dependency progress bar prototype
# Starts bootstrap server, opens browser, runs fake_install.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROGRESS_FILE="/tmp/gershwin_progress.json"
SERVER_PID_FILE="/tmp/gershwin_server.pid"
CONFIG_FILE="$SCRIPT_DIR/install_config.json"

# Clean up function
cleanup() {
    echo "Cleaning up..."
    if [ -f "$SERVER_PID_FILE" ]; then
        kill $(cat "$SERVER_PID_FILE") 2>/dev/null
        rm "$SERVER_PID_FILE"
    fi
}

trap cleanup EXIT

# Reset progress file
echo '{"current": "", "message": "", "index": 0, "total": 10, "percent": 0, "done": false}' > "$PROGRESS_FILE"

# Create inline Python server script with /config endpoint
PYTHON_SERVER=$(cat <<'PYEOF'
import http.server
import json
import os
import sys

class ProgressHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress logging

    def do_GET(self):
        script_dir = sys.argv[1] if len(sys.argv) > 1 else '.'

        if self.path == '/progress':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            try:
                with open('/tmp/gershwin_progress.json', 'r') as f:
                    self.wfile.write(f.read().encode())
            except:
                self.wfile.write(b'{"current": "", "message": "", "index": 0, "total": 10, "percent": 0, "done": false}')

        elif self.path == '/config':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            config_path = os.path.join(script_dir, 'install_config.json')
            try:
                with open(config_path, 'r') as f:
                    self.wfile.write(f.read().encode())
            except:
                self.wfile.write(b'{"title": "Setup", "subtitle": "Installing...", "complete_title": "Done", "complete_sub": "Complete"}')

        elif self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            html_path = os.path.join(script_dir, 'dep_progress.html')
            with open(html_path, 'r') as f:
                self.wfile.write(f.read().encode())

        else:
            self.send_response(404)
            self.end_headers()

if __name__ == '__main__':
    server = http.server.HTTPServer(('localhost', 8766), ProgressHandler)
    print('Progress server running at http://localhost:8766')
    server.serve_forever()
PYEOF
)

echo "Starting progress server on localhost:8766..."
echo "$PYTHON_SERVER" | python3 - "$SCRIPT_DIR" &
SERVER_PID=$!
echo $SERVER_PID > "$SERVER_PID_FILE"

# Wait for server to start
sleep 1

# Open browser
echo "Opening browser..."
open "http://localhost:8766"

# Wait a moment for browser to load
sleep 1

# Run the fake installer
echo "Running fake installer..."
"$SCRIPT_DIR/fake_install.sh"

echo ""
echo "Test complete! Check the browser to see the progress bar."
echo "Press Ctrl+C to stop the server."

# Keep server running until user interrupts
wait $SERVER_PID
