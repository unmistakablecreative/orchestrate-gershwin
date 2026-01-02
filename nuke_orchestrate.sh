#!/bin/bash
#
# nuke_orchestrate.sh
# Removes ALL traces of OrchestrateOS for clean reinstall testing
#

set -e

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "💥 OrchestrateOS Complete Removal"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "⚠️  This will remove:"
echo "   • All OrchestrateOS files and data"
echo "   • Python packages (fastapi, uvicorn, etc.)"
echo "   • Ngrok config and authtoken"
echo "   • LaunchAgent"
echo "   • All running processes"
echo ""
read -p "Continue? (y/N): " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "Cancelled."
  exit 0
fi

echo ""
echo "🔪 Nuking OrchestrateOS..."
echo ""

# ============================================
# 1. KILL ALL RUNNING PROCESSES
# ============================================
echo "⏹️  Killing processes..."
pkill -f "ngrok http" 2>/dev/null && echo "   ✅ Killed ngrok" || echo "   ℹ️  ngrok not running"
pkill -f "uvicorn jarvis:app" 2>/dev/null && echo "   ✅ Killed FastAPI server" || echo "   ℹ️  FastAPI not running"
pkill -f "com.orchestrateos.engine" 2>/dev/null || true
sleep 1

# ============================================
# 2. UNLOAD AND REMOVE LAUNCHAGENT
# ============================================
echo ""
echo "🗑️  Removing LaunchAgent..."
PLIST="$HOME/Library/LaunchAgents/com.orchestrateos.engine.plist"
if [ -f "$PLIST" ]; then
  launchctl unload "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  echo "   ✅ LaunchAgent removed"
else
  echo "   ℹ️  LaunchAgent not found"
fi

# ============================================
# 3. REMOVE APP BUNDLE
# ============================================
echo ""
echo "📦 Removing app bundle..."
if [ -d "/Applications/OrchestrateOS.app" ]; then
  rm -rf "/Applications/OrchestrateOS.app"
  echo "   ✅ App bundle removed"
else
  echo "   ℹ️  App bundle not found"
fi

# ============================================
# 4. REMOVE APPLICATION SUPPORT
# ============================================
echo ""
echo "🗂️  Removing Application Support..."
if [ -d "$HOME/Library/Application Support/OrchestrateOS" ]; then
  rm -rf "$HOME/Library/Application Support/OrchestrateOS"
  echo "   ✅ Application Support removed"
else
  echo "   ℹ️  Application Support not found"
fi

# ============================================
# 5. REMOVE USER DOCUMENTS
# ============================================
echo ""
echo "📄 Removing user documents..."
if [ -d "$HOME/Documents/Orchestrate" ]; then
  rm -rf "$HOME/Documents/Orchestrate"
  echo "   ✅ User documents removed"
else
  echo "   ℹ️  User documents not found"
fi

# ============================================
# 6. REMOVE PYTHON PACKAGES
# ============================================
echo ""
echo "🐍 Removing Python packages..."
PYTHON_CMD=$(command -v python3.12 2>/dev/null || command -v python3.11 2>/dev/null || echo "python3")

PACKAGES="fastapi uvicorn watchdog requests httpx python-multipart pyyaml aiofiles"
for pkg in $PACKAGES; do
  $PYTHON_CMD -m pip uninstall -y $pkg --break-system-packages 2>/dev/null && echo "   ✅ Removed $pkg" || echo "   ℹ️  $pkg not installed"
done

# ============================================
# 7. REMOVE NGROK CONFIG
# ============================================
echo ""
echo "🌐 Removing ngrok config..."
if [ -d "$HOME/.ngrok2" ]; then
  rm -rf "$HOME/.ngrok2"
  echo "   ✅ Ngrok config removed"
else
  echo "   ℹ️  Ngrok config not found"
fi

# ============================================
# 8. CLEAN HOMEBREW CACHE (optional)
# ============================================
echo ""
echo "🧹 Cleaning Homebrew cache..."
if command -v brew &>/dev/null; then
  brew cleanup -s 2>/dev/null || true
  echo "   ✅ Homebrew cache cleaned"
else
  echo "   ℹ️  Homebrew not installed"
fi

# ============================================
# DONE
# ============================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ OrchestrateOS Completely Removed"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Your system is now clean. You can run the installer again"
echo "to test a fresh installation."
echo ""
