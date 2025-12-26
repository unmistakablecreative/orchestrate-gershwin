#!/bin/bash

# Terminal Wizard for Custom GPT Setup (User-Friendly Edition)
# Auto-updates ngrok URL, uses clipboard automation, emoji-friendly
# Can accept ngrok domain as argument (from entrypoint.sh) or prompt user

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
INSTRUCTIONS_FILE="$HOME/Documents/Orchestrate/custom_instructions.json"
YAML_FILE="$HOME/Documents/Orchestrate/openapi.yaml"

# ngrok domain is passed as argument (already configured by Docker)
NGROK_DOMAIN="$1"

# Wait for Docker to finish generating config files
echo "⏳ Waiting for config files to be generated..."
while [ ! -f "$INSTRUCTIONS_FILE" ] || [ ! -f "$YAML_FILE" ]; do
    sleep 1
done
echo "✅ Config files ready"
sleep 1

# Ensure Homebrew bin is in PATH
if ! grep -q '/opt/homebrew/bin' "$HOME/.zshrc" 2>/dev/null; then
    echo 'export PATH="/opt/homebrew/bin:$PATH"' >> "$HOME/.zshrc"
    export PATH="/opt/homebrew/bin:$PATH"
fi

# Check if Claude Code is installed
if ! command -v claude &> /dev/null; then
    clear
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "⚠️  Claude Code Not Found"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "OrchestrateOS needs Claude Code for autonomous execution."
    echo ""
    echo "To install:"
    echo ""
    echo "  1. Open a new Terminal window"
    echo "  2. Run: brew install anthropics/claude/claude"
    echo "  3. Come back here and press ENTER"
    echo ""
    read -p "Press ENTER after you've installed Claude Code..."

    # Check again
    if ! command -v claude &> /dev/null; then
        echo ""
        echo "⚠️  Still can't find Claude Code."
        echo "Make sure you ran: brew install anthropics/claude/claude"
        echo ""
        echo "Then close this Terminal and run Orchestrate Engine again."
        exit 1
    fi
fi

# Ensure Claude is authenticated
if ! claude --version &> /dev/null; then
    clear
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🔐 Claude Code Authentication"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Claude Code needs to be authenticated."
    echo ""
    echo "A browser window will open for login."
    echo ""
    read -p "Press ENTER to authenticate Claude Code..."

    claude /login

    echo ""
    echo "✅ Claude Code authenticated"
    sleep 2
fi

clear
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🌐 Step 2 of 3: Open GPT Editor"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Opening your browser..."
echo ""
open "https://chatgpt.com/gpts/editor"
sleep 2
echo "✅ Browser opened"
echo ""
read -p "Press ENTER when you see the GPT editor..."

clear
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📝 Step 3 of 3: Three Copy/Pastes"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "We'll copy things to your clipboard."
echo "You just press Command+V (or Ctrl+V) to paste."
echo ""
echo "Ready? Let's go! 💪"
echo ""
read -p "Press ENTER to continue..."

# Part 1: Instructions
clear
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 Paste #1: Instructions"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "✅ Copied instructions to your clipboard!"
cat "$INSTRUCTIONS_FILE" | pbcopy
echo ""
echo "Now in your browser:"
echo ""
echo "  1. Click the 'Configure' tab"
echo "  2. Find the 'Instructions' box"
echo "  3. Click inside it"
echo "  4. Press Command+V (Mac) or Ctrl+V (Windows)"
echo ""
read -p "Press ENTER after you paste..."

# Part 2: Conversation Starter
clear
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "💬 Paste #2: Conversation Starter"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "✅ Copied conversation starter to your clipboard!"
echo "Load OrchestrateOS" | pbcopy
echo ""
echo "Now in your browser:"
echo ""
echo "  1. Scroll down to 'Conversation starters'"
echo "  2. Click the first empty box"
echo "  3. Press Command+V (Mac) or Ctrl+V (Windows)"
echo ""
read -p "Press ENTER after you paste..."

# Part 3: OpenAPI Schema
clear
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔌 Paste #3: API Connection"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "✅ Copied API schema to your clipboard!"
cat "$YAML_FILE" | pbcopy
echo ""
echo "Now in your browser:"
echo ""
echo "  1. Scroll down to 'Actions'"
echo "  2. Click 'Create new action'"
echo "  3. You'll see a big text box with some code"
echo "  4. Select ALL that code and delete it"
echo "  5. Press Command+V (Mac) or Ctrl+V (Windows)"
echo "  6. Click the 'Save' button (top right)"
echo ""
read -p "Press ENTER after you paste and save..."

# Test
clear
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🧪 Test Your Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Almost done! Let's make sure it works."
echo ""
echo "In your browser:"
echo ""
echo "  1. Click 'Preview' (top right corner)"
echo "  2. In the chat that appears, type:"
echo ""
echo "     Load OrchestrateOS"
echo ""
echo "  3. Press ENTER"
echo ""
echo "You should see a table with your tools appear."
echo ""
echo "If you see the table → SUCCESS! 🎉"
echo "If nothing happens → Let us know and we'll help troubleshoot"
echo ""
read -p "Press ENTER when you've tested it..."

# Done
clear
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Setup Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🎉 Your Custom GPT is ready to use!"
echo ""
echo "You can now:"
echo "  • Assign tasks from your Custom GPT"
echo "  • Run 'Load OrchestrateOS' anytime to see your tools"
echo "  • Unlock new tools as you earn credits"
echo ""
echo "Need help? Just ask in your Custom GPT chat!"
echo ""
