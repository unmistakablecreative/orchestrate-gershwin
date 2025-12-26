#!/bin/bash

APP_PATH="$(dirname "$0")/Orchestrate Engine.app"

echo "🛠 Removing quarantine flag from: $APP_PATH"
xattr -dr com.apple.quarantine "$APP_PATH"

echo "🚀 Launching Orchestrate..."
open "$APP_PATH"
