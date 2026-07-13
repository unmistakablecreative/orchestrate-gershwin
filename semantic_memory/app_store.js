// Tool display configuration - loaded from app_store_config.json
let TOOL_CONFIG = {
    preInstalled: [],
    hidden: [],
    displayInfo: {}
};

let toolsData = [];
let accountData = { credits: 0, credits_earned: 0 };
let profileData = { name: "User", initials: "--" };

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    await loadConfig();
    loadTools();
    loadAccountData();
    loadProfileData();
    setupEventListeners();
});

async function loadConfig() {
    try {
        const response = await fetch('app_store_config.json');
        if (response.ok) {
            TOOL_CONFIG = await response.json();
        } else {
            console.error('Failed to load app_store_config.json');
        }
    } catch (error) {
        console.error('Error loading config:', error);
    }
}

async function executeTask(toolName, action, params = {}) {
    try {
        const response = await fetch('/execute_task', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                tool_name: toolName,
                action: action,
                params: params
            })
        });
        return await response.json();
    } catch (error) {
        console.error('Execute task error:', error);
        return { status: 'error', message: error.message };
    }
}

async function loadTools() {
    const result = await executeTask('system_settings', 'list_tools');

    if (result.status === 'success' && result.tools) {
        toolsData = processTools(result.tools);
        renderTools(toolsData);
    } else {
        document.getElementById('tools-grid').innerHTML = `
            <div class="loading">
                <p>Unable to load tools. Please refresh.</p>
            </div>
        `;
    }
}

function processTools(tools) {
    const processed = [];
    const seen = new Set();

    for (const tool of tools) {
        const toolName = tool.tool || tool.name;

        if (TOOL_CONFIG.hidden.includes(toolName) || seen.has(toolName)) continue;

        if (toolName === 'docs' && seen.has('doc_editor')) continue;
        if (toolName === 'doc_editor') seen.add('docs');

        seen.add(toolName);

        const displayInfo = TOOL_CONFIG.displayInfo[toolName] || {
            name: toolName.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
            icon: '🔧',
            iconClass: 'icon-gray'
        };

        const isPreInstalled = TOOL_CONFIG.preInstalled.includes(toolName);
        const isLocked = tool.locked === true && !isPreInstalled;

        processed.push({
            name: toolName,
            displayName: displayInfo.name,
            icon: displayInfo.icon,
            iconClass: displayInfo.iconClass,
            open_url: displayInfo.open_url || null,
            description: tool.description || 'No description available',
            locked: isLocked,
            preInstalled: isPreInstalled,
            cost: tool.referral_unlock_cost || 0
        });
    }

    return processed.sort((a, b) => {
        if (a.preInstalled && !b.preInstalled) return -1;
        if (!a.preInstalled && b.preInstalled) return 1;
        if (!a.locked && b.locked) return -1;
        if (a.locked && !b.locked) return 1;
        return a.cost - b.cost;
    });
}

function renderTools(tools, filter = 'all') {
    const grid = document.getElementById('tools-grid');

    const filtered = tools.filter(tool => {
        if (filter === 'all') return true;
        if (filter === 'unlocked') return !tool.locked || tool.preInstalled;
        if (filter === 'locked') return tool.locked && !tool.preInstalled;
        return true;
    });

    if (filtered.length === 0) {
        grid.innerHTML = `<div class="loading"><p>No tools found</p></div>`;
        return;
    }

    grid.innerHTML = filtered.map(tool => {
        const statusClass = tool.preInstalled ? 'pre-installed' : (tool.locked ? 'locked' : 'unlocked');
        const statusText = tool.preInstalled ? 'Open' : (tool.locked ? 'Locked' : 'Unlocked');
        const statusIcon = tool.preInstalled ? '✓' : (tool.locked ? '🔒' : '✓');
        const badgeClickable = tool.open_url ? `onclick="window.parent.postMessage({type:'open_url',url:'${tool.open_url}'},'*')" style="cursor:pointer"` : '';

        let unlockSection = '';
        if (tool.locked && !tool.preInstalled) {
            unlockSection = `
                <div class="unlock-info">
                    <div class="unlock-cost">
                        <span>🎫</span>
                        <span>${tool.cost} credit${tool.cost !== 1 ? 's' : ''}</span>
                    </div>
                    <button class="unlock-btn"
                            onclick="unlockTool('${tool.name}', ${tool.cost})">
                        Install
                    </button>
                </div>
            `;
        }

        return `
            <div class="tool-card ${tool.locked && !tool.preInstalled ? 'locked' : ''} ${tool.preInstalled ? 'pre-installed' : ''}">
                <span class="status-badge ${statusClass}" ${badgeClickable}>${statusIcon} ${statusText}</span>
                <div class="tool-header">
                    <div class="tool-icon ${tool.iconClass}">${tool.icon}</div>
                    <div class="tool-info">
                        <div class="tool-name">${tool.displayName}</div>
                        <div class="tool-description">${tool.description}</div>
                    </div>
                </div>
                ${unlockSection}
            </div>
        `;
    }).join('');
}

async function loadAccountData() {
    const result = await executeTask('account', 'check');

    if (result.status === 'success') {
        const data = result.data || result;
        accountData = {
            credits: data.credits || result.credits || 0,
            credits_earned: data.credits_earned || data.referrals_sent || result.referrals_sent || 0
        };

        document.getElementById('credits-balance').textContent = accountData.credits;
    }
}

async function loadProfileData() {
    try {
        const response = await fetch('../data/system_identity.json');
        if (response.ok) {
            const data = await response.json();
            if (data.name) {
                profileData.name = data.name;
                const words = data.name.trim().split(/\s+/);
                if (words.length >= 2) {
                    profileData.initials = (words[0][0] + words[words.length - 1][0]).toUpperCase();
                } else if (words.length === 1 && words[0].length >= 2) {
                    profileData.initials = words[0].substring(0, 2).toUpperCase();
                } else {
                    profileData.initials = words[0][0].toUpperCase();
                }
            }
        }
    } catch (error) {
        console.error('Error loading profile data:', error);
    }
    updateProfileUI();
}

function updateProfileUI() {
    const icon = document.getElementById('profile-icon');
    if (icon) icon.textContent = profileData.initials;
    const avatar = document.getElementById('profile-modal-avatar');
    if (avatar) avatar.textContent = profileData.initials;
    const name = document.getElementById('profile-modal-name');
    if (name) name.textContent = profileData.name;
    const credits = document.getElementById('profile-credits-value');
    if (credits) credits.textContent = accountData.credits;
}

function openProfileModal() {
    document.getElementById('profile-credits-value').textContent = accountData.credits;
    document.getElementById('profile-modal').style.display = 'flex';
}

function closeProfileModal() {
    document.getElementById('profile-modal').style.display = 'none';
}

async function purchaseCredits(amount) {
    const result = await executeTask('account', 'purchase_credits', { amount: amount });
    if (result.status === 'success') {
        await loadAccountData();
        updateProfileUI();
    } else {
        showToast(result.message || 'Failed to purchase credits', 'error');
    }
}

async function updateBilling() {
    const result = await executeTask('account', 'get_billing_portal', {});
    if (result.status === 'success' && result.url) {
        window.open(result.url, '_blank');
    } else {
        showToast(result.message || 'Unable to open billing portal', 'error');
    }
}

async function unlockTool(toolName, cost) {
    if (accountData.credits < cost) {
        showToast('Not enough credits to unlock this tool', 'error');
        return;
    }

    // Check if this tool requires an API key
    const displayInfo = TOOL_CONFIG.displayInfo[toolName] || {};
    if (displayInfo.requires_api_key) {
        showApiKeyModal(toolName, displayInfo.api_key_field, cost);
        return;
    }

    await proceedWithUnlock(toolName);
}

async function showApiKeyModal(toolName, apiKeyField, cost) {
    const modal = document.getElementById('api-key-modal');
    const toolNameEl = document.getElementById('api-key-tool-name');
    const input = document.getElementById('api-key-input');
    const confirmBtn = document.getElementById('api-key-confirm');
    
    toolNameEl.textContent = TOOL_CONFIG.displayInfo[toolName]?.name || toolName;
    input.value = '';
    modal.style.display = 'flex';
    input.focus();
    
    // Store context for confirm handler
    modal.dataset.toolName = toolName;
    modal.dataset.apiKeyField = apiKeyField;
}

async function confirmApiKey() {
    const modal = document.getElementById('api-key-modal');
    const input = document.getElementById('api-key-input');
    const apiKey = input.value.trim();
    
    if (!apiKey) {
        showToast('Please enter an API key', 'error');
        return;
    }
    
    const toolName = modal.dataset.toolName;
    const apiKeyField = modal.dataset.apiKeyField;
    
    await executeTask("system_settings", "set_credential", { tool_name: toolName, value: apiKey });

    closeApiKeyModal();
    await proceedWithUnlock(toolName);
}

function closeApiKeyModal() {
    document.getElementById('api-key-modal').style.display = 'none';
}

async function proceedWithUnlock(toolName) {
    const result = await executeTask('account', 'unlock', { tool_id: toolName });

    if (result.status === 'success') {
        // Toast removed - card flip provides visual feedback

        // Post message to parent for dynamic sidebar unlock
        if (window.parent !== window) {
            const displayInfo = TOOL_CONFIG.displayInfo[toolName] || {};
            const payload = {
                type: 'tool_unlocked',
                tool_name: toolName,
                display_name: displayInfo.name || toolName.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
                icon: displayInfo.icon || '🔧',
                icon_class: displayInfo.iconClass || 'icon-gray',
                open_url: displayInfo.open_url || null
            };
            window.parent.postMessage(payload, '*');

            // Special case: claude_assistant gets additional message type
            if (toolName === 'claude_assistant') {
                window.parent.postMessage({ type: 'claude_assistant_unlocked' }, '*');
            }
        }

        if (toolName === 'claude_assistant' && window.parent !== window) {
            window.parent.claudeAssistantUnlocked = true;

            // Trigger claude login via shell execution
            executeTask('shell', 'run', {
                command: 'CLAUDE_BIN=$(which claude 2>/dev/null || find ~/Library -name claude -type f 2>/dev/null | head -1) && [ -n "$CLAUDE_BIN" ] && "$CLAUDE_BIN" login'
            });
            // postMessage already handled the home transition - no redirect needed
        }

        await Promise.all([loadTools(), loadAccountData()]);
    } else {
        showToast(result.message || 'Failed to unlock tool', 'error');
    }
}

async function sendReferral() {
    const email = document.getElementById('referral-email').value.trim();

    if (!email || !email.includes('@')) {
        showToast('Please enter a valid email address', 'error');
        return;
    }

    const result = await executeTask('account', 'refer', { emails: email });

    if (result.status === 'success') {
        showToast(result.message || 'Referral sent! +1 credit', 'success');
        document.getElementById('referral-email').value = '';
        await loadAccountData();
    } else {
        showToast(result.message || 'Failed to send referral', 'error');
    }
}

// Listen for profile modal trigger from parent sidebar
window.addEventListener('message', (e) => {
    if (e.data && e.data.type === 'open_profile_modal') {
        openProfileModal();
    }
});

function setupEventListeners() {
    document.querySelectorAll('.filter-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.filter-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            renderTools(toolsData, tab.dataset.filter);
        });
    });

    document.getElementById('send-referral').addEventListener('click', sendReferral);

    document.getElementById('referral-email').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendReferral();
    });
}

function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast ${type} show`;

    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}
