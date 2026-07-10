
// Config-driven architecture - load configuration
let CONFIG = {};
async function loadConfig() {
    try {
        const response = await fetch(window.CONFIG_PATH || './config.json');
        CONFIG = await response.json();
        console.log('[Config] Loaded:', Object.keys(CONFIG));
    } catch (e) {
        console.warn('[Config] Failed to load, using defaults:', e);
        CONFIG = window.DEFAULT_CONFIG || {};
    }
}

// Initialize on load
document.addEventListener('DOMContentLoaded', async () => {
    await loadConfig();
    if (typeof init === 'function') init();
    if (typeof initialize === 'function') initialize();
    if (typeof render === 'function') render();
});

// TODO: Replace hardcoded columns with CONFIG.columns
// Original columns: ["todo", "in_progress", "done"]


        let tools = [];
        let userCredits = 0;
        let pendingUnlock = null;
        let pendingCredTool = null;
        let currentCategory = 'all';

        const API = window.location.origin;

        // Icon mapping by category/type
        const iconMap = {
            'ai': '🤖',
            'email': '📧',
            'calendar': '📅',
            'docs': '📄',
            'analytics': '📊',
            'social': '📱',
            'automation': '⚡',
            'integration': '🔗',
            'content': '✍️',
            'storage': '💾',
            'search': '🔍',
            'media': '🎬',
            'default': '🔧'
        };

        // Color classes for variety
        const colorClasses = ['blue', 'purple', 'green', 'orange', 'red'];

        // Category mapping
        const categoryMap = {
            'claude_assistant': 'ai',
            'ai_writer': 'ai',
            'automation_engine': 'ai',
            'nylas_inbox': 'integration',
            'google_calendar': 'integration',
            'google_ads': 'integration',
            'hubspot': 'integration',
            'notion': 'integration',
            'stripe': 'integration',
            'slack': 'integration',
            'docs': 'content',
            'doc_editor': 'content',
            'newsletter_tool': 'content',
            'blog': 'content',
            'articles': 'content',
            'podcast': 'content',
            'files': 'productivity',
            'tasks': 'productivity',
            'codebase_index': 'productivity',
            'system_settings': 'productivity'
        };

        document.addEventListener('DOMContentLoaded', loadData);

        async function loadData() {
            await Promise.all([loadToolCatalog(), loadCredits()]);
            renderTools();
        }

        async function loadToolCatalog() {
            try {
                const res = await fetch(`${API}/get_tool_catalog`);
                const data = await res.json();
                if (data.status === 'success') {
                    tools = data.tools;
                    document.getElementById('totalTools').textContent = data.total;
                    document.getElementById('unlockedTools').textContent = data.unlocked_count;
                    document.getElementById('lockedTools').textContent = data.total - data.unlocked_count;
                }
            } catch (e) {
                console.error('Failed to load catalog:', e);
                showToast('Failed to load apps', 'error');
            }
        }

        async function loadCredits() {
            try {
                const res = await fetch(`${API}/execute_task`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({tool_name: 'check_credits', action: 'check_credits', params: {}})
                });
                const data = await res.json();
                if (data.status === 'success') {
                    userCredits = data.credits || 0;
                    document.getElementById('creditsValue').textContent = userCredits;
                }
            } catch (e) {
                console.error('Failed to load credits:', e);
            }
        }

        function getIcon(toolName) {
            const cat = categoryMap[toolName] || 'default';
            return iconMap[cat] || iconMap.default;
        }

        function getCategory(toolName) {
            return categoryMap[toolName] || 'productivity';
        }

        function filterTools() {
            renderTools();
        }

        function filterCategory(cat) {
            currentCategory = cat;
            document.querySelectorAll('.category-btn').forEach(btn => {
                btn.classList.remove('active');
                if (btn.textContent.toLowerCase().includes(cat) || (cat === 'all' && btn.textContent === 'All Apps')) {
                    btn.classList.add('active');
                }
            });
            renderTools();
        }

        function renderTools() {
            const grid = document.getElementById('toolsGrid');
            const search = document.getElementById('searchInput').value.toLowerCase();

            // Filter out internal tools
            const hiddenTools = ['unlock_tool', 'system_control', 'check_credits', 'refer_user'];
            let visible = tools.filter(t => !hiddenTools.includes(t.name));

            // Search filter
            if (search) {
                visible = visible.filter(t =>
                    t.label.toLowerCase().includes(search) ||
                    t.description.toLowerCase().includes(search) ||
                    t.name.toLowerCase().includes(search)
                );
            }

            // Category filter
            if (currentCategory !== 'all') {
                visible = visible.filter(t => getCategory(t.name) === currentCategory);
            }

            // Sort: unlocked first, then by cost
            visible.sort((a, b) => {
                if (a.unlocked && !b.unlocked) return -1;
                if (!a.unlocked && b.unlocked) return 1;
                return (a.cost || 0) - (b.cost || 0);
            });

            if (!visible.length) {
                grid.innerHTML = '<div class="loading"><p>No apps found</p></div>';
                return;
            }

            grid.innerHTML = visible.map((tool, idx) => {
                const canAfford = userCredits >= (tool.cost || 0);
                const hasCreds = localStorage.getItem('creds_' + tool.name) === 'true';
                const colorClass = colorClasses[idx % colorClasses.length];
                const icon = getIcon(tool.name);
                const isFree = !tool.cost || tool.cost === 0;

                let badge = '';
                if (tool.unlocked) {
                    badge = '<span class="tool-badge unlocked">Unlocked</span>';
                } else if (isFree) {
                    badge = '<span class="tool-badge free">Free</span>';
                } else {
                    badge = '<span class="tool-badge locked">Locked</span>';
                }

                let actions = '';
                if (!tool.unlocked && tool.cost > 0) {
                    actions = `
                        <button class="btn btn-primary" onclick="showUnlockModal('${tool.name}', '${tool.label}', ${tool.cost})" ${!canAfford ? 'disabled title="Need more credits"' : ''}>
                            Unlock
                        </button>
                        <button class="btn btn-refer" onclick="showReferralModal()">+ Refer</button>
                    `;
                } else if (tool.unlocked && tool.requires_credentials) {
                    actions = `
                        <button class="btn ${hasCreds ? 'btn-success' : 'btn-secondary'}" onclick="showCredentialsModal('${tool.name}', '${tool.label}', ${JSON.stringify(tool.credential_fields || []).replace(/"/g, '&quot;')})">
                            ${hasCreds ? '✓ Configured' : 'Configure'}
                        </button>
                    `;
                } else if (tool.unlocked) {
                    actions = '<span style="color:var(--green);font-size:13px;">✓ Ready</span>';
                }

                return `
                <div class="tool-card ${tool.unlocked ? '' : 'locked'}">
                    <div class="tool-icon ${colorClass}">${icon}</div>
                    <div class="tool-header">
                        <div>
                            <div class="tool-name">${tool.label}</div>
                        </div>
                        ${badge}
                    </div>
                    <div class="tool-desc">${tool.description || 'No description available'}</div>
                    <div class="tool-footer">
                        <div class="tool-cost ${isFree ? 'free' : 'paid'}">
                            ${isFree ? 'Free' : tool.cost + ' credits'}
                        </div>
                        <div class="tool-actions">
                            ${actions}
                        </div>
                    </div>
                </div>
                `;
            }).join('');
        }

        function showUnlockModal(name, label, cost) {
            pendingUnlock = {name, label, cost};
            document.getElementById('unlockToolName').textContent = label;
            document.getElementById('unlockCost').textContent = cost;
            document.getElementById('unlockModal').classList.add('active');
        }

        function showCredentialsModal(name, label, fields) {
            pendingCredTool = {name, label, fields};
            document.getElementById('credToolName').textContent = label;
            document.getElementById('credentialFields').innerHTML = fields.map(f =>
                `<input type="text" id="cred_${f}" placeholder="${f}">`
            ).join('');
            document.getElementById('credentialsModal').classList.add('active');
        }

        function showReferralModal() {
            document.getElementById('referralModal').classList.add('active');
        }

        function closeModal(id) {
            document.getElementById(id).classList.remove('active');
        }

        async function confirmUnlock() {
            if (!pendingUnlock) return;
            closeModal('unlockModal');

            try {
                const res = await fetch(`${API}/execute_task`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        tool_name: 'unlock_tool',
                        action: 'unlock_tool',
                        params: {tool_name: pendingUnlock.name}
                    })
                });
                const data = await res.json();

                if (data.status === 'success') {
                    showToast(`${pendingUnlock.label} unlocked!`, 'success');
                    await loadData();

                    const unlockedTool = tools.find(t => t.name === pendingUnlock.name);
                    if (unlockedTool && unlockedTool.requires_credentials && unlockedTool.credential_fields?.length > 0) {
                        setTimeout(() => {
                            showCredentialsModal(unlockedTool.name, unlockedTool.label, unlockedTool.credential_fields);
                        }, 500);
                    }
                } else {
                    showToast(data.message || data.error || 'Unlock failed', 'error');
                }
            } catch (e) {
                showToast('Unlock failed: ' + e.message, 'error');
            }
            pendingUnlock = null;
        }

        async function saveCredentials() {
            if (!pendingCredTool) return;

            const values = {};
            for (const f of pendingCredTool.fields) {
                const input = document.getElementById('cred_' + f);
                if (input && input.value.trim()) {
                    values[f] = input.value.trim();
                }
            }

            if (Object.keys(values).length === 0) {
                showToast('Please enter at least one credential', 'error');
                return;
            }

            closeModal('credentialsModal');

            try {
                const res = await fetch(`${API}/execute_task`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        tool_name: 'system_settings',
                        action: 'set_credential',
                        params: {tool_name: pendingCredTool.name, value: JSON.stringify(values)}
                    })
                });
                const data = await res.json();

                if (data.status === 'success' || !data.error) {
                    localStorage.setItem('creds_' + pendingCredTool.name, 'true');
                    showToast('Credentials saved!', 'success');
                    renderTools();
                } else {
                    showToast(data.message || 'Failed to save', 'error');
                }
            } catch (e) {
                showToast('Save failed: ' + e.message, 'error');
            }
            pendingCredTool = null;
        }

        async function submitReferral() {
            const name = document.getElementById('referralName').value.trim();
            const email = document.getElementById('referralEmail').value.trim();

            if (!name || !email) {
                showToast('Please enter name and email', 'error');
                return;
            }

            closeModal('referralModal');

            try {
                const res = await fetch(`${API}/execute_task`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        tool_name: 'refer_user',
                        action: 'refer_user',
                        params: {name, email}
                    })
                });
                const data = await res.json();

                if (data.status === 'success') {
                    showToast('Referral sent! +3 credits', 'success');
                    document.getElementById('referralName').value = '';
                    document.getElementById('referralEmail').value = '';
                    await loadData();
                } else {
                    showToast(data.message || 'Referral failed', 'error');
                }
            } catch (e) {
                showToast('Referral failed: ' + e.message, 'error');
            }
        }

        function showToast(msg, type = 'info') {
            const toast = document.getElementById('toast');
            toast.textContent = msg;
            toast.className = 'toast show ' + type;
            setTimeout(() => toast.classList.remove('show'), 3000);
        }
    

