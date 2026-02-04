#!/bin/bash
#
# Claude Code Authentication Setup for OrchestrateOS
# Installs Claude Code CLI (if needed) and triggers OAuth authentication
#

echo "=== Claude Code Authentication Setup ==="
echo ""

# Check for Node.js (required for Claude Code)
if ! command -v node &>/dev/null; then
    echo "Node.js is required for Claude Code."
    echo ""
    if command -v brew &>/dev/null; then
        echo "Installing Node.js via Homebrew..."
        brew install node
    else
        echo "Please install Node.js first: https://nodejs.org/"
        echo "Or install Homebrew: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
        exit 1
    fi
fi

# Check for Claude Code CLI
if ! command -v claude &>/dev/null; then
    echo "Installing Claude Code CLI..."
    npm install -g @anthropic-ai/claude-code
    if [ $? -ne 0 ]; then
        echo "Failed to install Claude Code. Try: sudo npm install -g @anthropic-ai/claude-code"
        exit 1
    fi
    echo "Claude Code installed."
else
    echo "Claude Code CLI found: $(claude --version 2>/dev/null || echo 'installed')"
fi

echo ""
echo "Starting Claude Code authentication..."
echo "Your browser will open for OAuth sign-in."
echo "Sign in with your Claude Pro or Team account."
echo ""

# Trigger Claude Code authentication
claude setup-token

if [ $? -eq 0 ]; then
    echo ""
    echo "=== Authentication Complete ==="
    echo "Claude Assistant is ready for autonomous task execution."
    echo "You can now assign tasks through OrchestrateOS."
else
    echo ""
    echo "Authentication may not have completed."
    echo "You can retry by running: claude setup-token"
fi
