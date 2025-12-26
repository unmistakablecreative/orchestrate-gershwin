# OrchestrateOS Beta Sandbox

**Purpose:** Testing environment for new features without disrupting production users.

## What's Different from Production?

### 1. Terminal Wizard Integration
- **Location:** `setup_wizard.sh` in root directory
- **What it does:** Auto-launches after Docker setup, guides user through Custom GPT creation via clipboard automation
- **User flow:** Enter ngrok domain once → Command+V 3x → Done
- **Result:** Self-service onboarding, no manual hand-holding needed

### 2. Test JSONBin Ledger
- **Production BIN_ID:** `68292fcf8561e97a50162139`
- **Test BIN_ID:** `TEST_BIN_ID_HERE` (update before building DMG)
- **Why separate:** Prevents test installs from polluting production referral data

### 3. Modified entrypoint.sh
- Starts FastAPI in background (not `exec`)
- Launches `setup_wizard.sh` after system is ready
- Passes ngrok domain to wizard automatically
- Keeps FastAPI running after wizard completes

## Building Test DMG

```bash
# From orchestrate_test_installer folder (outside this repo)
cd "/Users/srinivas/Orchestrate Github/orchestrate_test_installer"
./build_test_dmg.sh
```

This builds from the sandbox repo and creates a test DMG.

## Testing the Flow

1. **Open Docker Desktop**
2. **Run test DMG**
3. **Follow prompts:**
   - Enter ngrok token (saved to container state)
   - Enter ngrok domain (auto-passed to wizard)
4. **System starts, wizard auto-launches**
5. **Command+V 3x to create Custom GPT**
6. **Type "Load OrchestrateOS" to verify**

## What to Validate

- [ ] Wizard launches automatically after FastAPI starts
- [ ] Wizard receives ngrok domain without re-prompting
- [ ] Clipboard automation works (3x Command+V)
- [ ] Custom GPT connects successfully
- [ ] No manual file editing required
- [ ] User never sees VS Code or config files
- [ ] Total onboarding time: 2-3 minutes (vs 20-30 mins manual)

## Known Issues

- Test JSONBin credentials not set yet (update BIN_ID and API_KEY in entrypoint.sh:34-35)
- Need to test on fresh install (no existing container state)

## Next Steps

Once validated:
1. Create production JSONBin test ledger
2. Update credentials in entrypoint.sh
3. Build and distribute test DMG to beta users
4. Collect feedback on wizard UX
5. Iterate on friction points
6. Merge successful changes to production repo
