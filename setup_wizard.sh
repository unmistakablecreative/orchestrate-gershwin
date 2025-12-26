#!/bin/bash

# Terminal Wizard for Custom GPT Setup (User-Friendly Edition)
# Auto-updates ngrok URL, uses clipboard automation, emoji-friendly
# Can accept ngrok domain as argument (from entrypoint.sh) or prompt user

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
INSTRUCTIONS_FILE="$SCRIPT_DIR/custom_instructions_test.json"
YAML_FILE="$SCRIPT_DIR/openapi_test.yaml"

# Check if ngrok domain was passed as argument
if [ -n "$1" ]; then
    NGROK_DOMAIN="$1"
else
    # Prompt user for ngrok domain
    clear
    echo ""
    echo "🚀 OrchestrateOS Setup Wizard"
    echo ""
    echo "This takes about 2 minutes. We'll set up your Custom GPT together."
    echo ""
    read -p "Press ENTER to start..."

    clear
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📋 Step 1 of 3: Get Your ngrok Domain"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Your Docker container should be running."
    echo "It shows an ngrok domain that looks like this:"
    echo ""
    echo "  upright-constantly-grub.ngrok-free.app"
    echo ""
    echo "Copy that domain and paste it here."
    echo "(Don't worry about https:// - we'll add that)"
    echo ""
    read -p "Enter your ngrok domain: " NGROK_DOMAIN
fi

# Clean up the domain (remove https://, http://, trailing slashes)
NGROK_DOMAIN=$(echo "$NGROK_DOMAIN" | sed 's|^https\?://||' | sed 's|/$||')

# Validate domain format
if [[ ! $NGROK_DOMAIN =~ \.ngrok-free\.app$ ]]; then
    echo ""
    echo "⚠️  That doesn't look right. It should end with:"
    echo "    .ngrok-free.app"
    echo ""
    echo "Example: upright-constantly-grub.ngrok-free.app"
    echo ""
    read -p "Try again - Enter your ngrok domain: " NGROK_DOMAIN
    NGROK_DOMAIN=$(echo "$NGROK_DOMAIN" | sed 's|^https\?://||' | sed 's|/$||')
fi

# Build full URL
NGROK_URL="https://$NGROK_DOMAIN"

# Update YAML file with ngrok URL (behind the scenes)
echo ""
echo "✅ Got it! Updating your configuration..."
sed -i '' "s|https://YOUR-NGROK-URL-HERE.ngrok-free.app|$NGROK_URL|g" "$YAML_FILE"
echo "✅ Configuration updated"
sleep 1

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
echo "  2. Set Model to: GPT-4o (recommended)"
echo "  3. Under Capabilities, UNCHECK 'Web search'"
echo "  4. Find the 'Instructions' box"
echo "  5. Click inside it"
echo "  6. Press Command+V (Mac) or Ctrl+V (Windows)"
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
