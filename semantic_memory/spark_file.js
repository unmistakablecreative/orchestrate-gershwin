
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


        const API = window.location.origin;
        let currentTab = 'recent';
        let searchResults = [];

        document.addEventListener('DOMContentLoaded', () => {
            loadRecent();
            setupInputHandlers();
        });

        function setupInputHandlers() {
            const input = document.getElementById('captureInput');
            const charCount = document.getElementById('charCount');
            const captureBtn = document.getElementById('captureBtn');

            input.addEventListener('input', () => {
                charCount.textContent = input.value.length;
                captureBtn.disabled = input.value.trim().length === 0;
            });

            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && e.metaKey) {
                    e.preventDefault();
                    if (!captureBtn.disabled) captureEntry();
                }
            });

            const searchInput = document.getElementById('searchInput');
            searchInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    searchEntries();
                }
            });
        }

        async function captureEntry() {
            const input = document.getElementById('captureInput');
            const content = input.value.trim();
            if (!content) return;

            const btn = document.getElementById('captureBtn');
            btn.disabled = true;
            btn.textContent = 'Capturing...';

            try {
                const res = await fetch(`${API}/execute_task`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        tool_name: 'spark_file',
                        action: 'add_entry',
                        params: { content }
                    })
                });
                const data = await res.json();

                if (data.status === 'success') {
                    showToast('Spark captured!', 'success');
                    input.value = '';
                    document.getElementById('charCount').textContent = '0';
                    loadRecent();
                } else {
                    showToast(data.message || 'Failed to capture', 'error');
                }
            } catch (e) {
                showToast('Error: ' + e.message, 'error');
            }

            btn.disabled = false;
            btn.textContent = 'Capture Spark';
        }

        async function loadRecent() {
            const list = document.getElementById('entriesList');
            list.innerHTML = '<div class="loading">Loading sparks</div>';

            try {
                const res = await fetch(`${API}/execute_task`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        tool_name: 'spark_file',
                        action: 'recent',
                        params: { limit: 50 }
                    })
                });
                const data = await res.json();

                if (data.status === 'success') {
                    renderEntries(data.entries || [], false);
                    document.getElementById('entriesCount').textContent =
                        (data.entries?.length || 0) + ' sparks';
                } else {
                    list.innerHTML = `<div class="empty-state"><div class="icon">⚡</div><p>${data.message || 'Failed to load'}</p></div>`;
                }
            } catch (e) {
                list.innerHTML = `<div class="empty-state"><div class="icon">⚠️</div><p>Error: ${e.message}</p></div>`;
            }
        }

        async function searchEntries() {
            const query = document.getElementById('searchInput').value.trim();
            if (!query) {
                showToast('Enter a search query', 'error');
                return;
            }

            const list = document.getElementById('entriesList');
            list.innerHTML = '<div class="loading">Searching</div>';

            try {
                const res = await fetch(`${API}/execute_task`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        tool_name: 'spark_file',
                        action: 'search',
                        params: { query, limit: 20 }
                    })
                });
                const data = await res.json();

                if (data.status === 'success') {
                    searchResults = data.results || [];
                    document.getElementById('tabResults').style.display = 'inline-block';
                    showTab('results');
                    renderEntries(searchResults, true);
                    document.getElementById('entriesCount').textContent =
                        searchResults.length + ' matches';
                } else {
                    list.innerHTML = `<div class="empty-state"><div class="icon">🔍</div><p>${data.message || 'Search failed'}</p></div>`;
                }
            } catch (e) {
                list.innerHTML = `<div class="empty-state"><div class="icon">⚠️</div><p>Error: ${e.message}</p></div>`;
            }
        }

        function clearSearch() {
            document.getElementById('searchInput').value = '';
            document.getElementById('tabResults').style.display = 'none';
            searchResults = [];
            showTab('recent');
            loadRecent();
        }

        function showTab(tab) {
            currentTab = tab;
            document.getElementById('tabRecent').classList.toggle('active', tab === 'recent');
            document.getElementById('tabResults').classList.toggle('active', tab === 'results');

            if (tab === 'recent') {
                loadRecent();
            } else {
                renderEntries(searchResults, true);
                document.getElementById('entriesCount').textContent =
                    searchResults.length + ' matches';
            }
        }

        function renderEntries(entries, showSimilarity) {
            const list = document.getElementById('entriesList');

            if (!entries || entries.length === 0) {
                list.innerHTML = `
                    <div class="empty-state">
                        <div class="icon">⚡</div>
                        <p>No sparks yet. Capture your first idea above!</p>
                    </div>
                `;
                return;
            }

            list.innerHTML = entries.map(entry => {
                const date = new Date(entry.created_at);
                const timeStr = date.toLocaleDateString('en-US', {
                    month: 'short', day: 'numeric', year: 'numeric',
                    hour: 'numeric', minute: '2-digit'
                });

                return `
                    <div class="entry-card">
                        <div class="entry-content">${escapeHtml(entry.content)}</div>
                        <div class="entry-meta">
                            <span class="entry-time">${timeStr}</span>
                            ${showSimilarity && entry.similarity !== undefined ?
                                `<span class="entry-similarity">${Math.round(entry.similarity * 100)}% match</span>` :
                                `<span class="entry-id">#${entry.id}</span>`
                            }
                        </div>
                    </div>
                `;
            }).join('');
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function showToast(msg, type = 'info') {
            const toast = document.getElementById('toast');
            toast.textContent = msg;
            toast.className = 'toast show ' + type;
            setTimeout(() => toast.classList.remove('show'), 3000);
        }
    

