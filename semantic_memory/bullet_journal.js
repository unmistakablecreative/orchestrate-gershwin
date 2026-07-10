
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


        const TRUNCATE_THRESHOLD = 120;
        let allEntries = [];
        let currentFilter = 'all';
        let currentCollection = null;

        async function loadData() {
            try {
                const response = await fetch('/data-nocache/bullet_journal.json');
                const data = await response.json();

                allEntries = Object.entries(data.entries || {}).map(([id, entry]) => ({
                    id,
                    ...entry
                })).sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));

                updateStats();
                renderCollectionDropdown();
                renderEntries();
            } catch (err) {
                console.error('Failed to load data:', err);
                document.getElementById('entriesGrid').innerHTML = '<div class="empty-state"><h3>Could not load entries</h3><p>Check that bullet_journal.json exists</p></div>';
            }
        }

        function updateStats() {
            const tasks = allEntries.filter(e => e.type === 'task');
            const events = allEntries.filter(e => e.type === 'event');
            const notes = allEntries.filter(e => e.type === 'note');

            document.getElementById('taskCount').textContent = tasks.length;
            document.getElementById('eventCount').textContent = events.length;
            document.getElementById('noteCount').textContent = notes.length;
        }

        function renderCollectionDropdown() {
            const select = document.getElementById('collectionSelect');
            const collections = [...new Set(allEntries.map(e => e.collection || 'uncategorized'))].sort();

            select.innerHTML = '<option value="">All Collections</option>' +
                collections.map(col =>
                    '<option value="' + col + '"' + (currentCollection === col ? ' selected' : '') + '>' + col + '</option>'
                ).join('');

            select.onchange = function() {
                currentCollection = this.value || null;
                renderEntries();
            };
        }

        function renderEntries() {
            const grid = document.getElementById('entriesGrid');

            let filtered = allEntries;

            // Apply collection filter first (if active)
            if (currentCollection) {
                filtered = filtered.filter(e => (e.collection || 'uncategorized') === currentCollection);
                // When collection is active, exclude done items unless done filter is selected
                if (currentFilter !== 'done') {
                    filtered = filtered.filter(e => e.status !== 'done');
                }
            } else {
                // No collection filter - apply type filters
                if (currentFilter === 'done') {
                    // Show only done items
                    filtered = allEntries.filter(e => e.status === 'done');
                } else if (currentFilter === 'task' || currentFilter === 'event' || currentFilter === 'note') {
                    // Show type but exclude done
                    filtered = allEntries.filter(e => e.type === currentFilter && e.status !== 'done');
                } else {
                    // 'all' - exclude done items by default
                    filtered = allEntries.filter(e => e.status !== 'done');
                }
            }

            if (filtered.length === 0) {
                grid.innerHTML = '<div class="empty-state"><h3>No entries found</h3><p>Click + to add your first entry</p></div>';
                return;
            }

            grid.innerHTML = filtered.map(entry => {
                const content = entry.content || '';
                const needsTruncate = content.length > TRUNCATE_THRESHOLD;
                const date = formatDate(entry.timestamp);
                const statusClass = entry.status === 'done' ? 'done' : '';

                return '<div class="card ' + entry.type + '">' +
                    '<div class="card-type">' + entry.type + '</div>' +
                    '<div class="card-content' + (needsTruncate ? ' truncated' : '') + '">' + escapeHtml(content) + '</div>' +
                    (needsTruncate ? '<div class="show-more" onclick="toggleExpand(this)">Show more</div>' : '') +
                    '<div class="card-footer">' +
                        '<span class="card-date">' + date + '</span>' +
                        '<div>' +
                            '<span class="card-collection">' + (entry.collection || 'uncategorized') + '</span>' +
                            '<span class="card-status ' + statusClass + '">' + (entry.status || 'raw') + '</span>' +
                        '</div>' +
                    '</div>' +
                '</div>';
            }).join('');
        }

        function toggleExpand(btn) {
            const content = btn.previousElementSibling;
            if (content.classList.contains('truncated')) {
                content.classList.remove('truncated');
                content.classList.add('expanded');
                btn.textContent = 'Show less';
            } else {
                content.classList.remove('expanded');
                content.classList.add('truncated');
                btn.textContent = 'Show more';
            }
        }

        function formatDate(timestamp) {
            if (!timestamp) return '';
            const d = new Date(timestamp);
            return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        document.querySelectorAll('.filter').forEach(filter => {
            filter.addEventListener('click', () => {
                document.querySelectorAll('.filter').forEach(f => f.classList.remove('active'));
                filter.classList.add('active');
                currentFilter = filter.dataset.filter;
                renderEntries();
            });
        });

        function openModal() {
            document.getElementById('addModal').classList.add('active');
            document.getElementById('entryContent').focus();
        }

        function closeModal() {
            document.getElementById('addModal').classList.remove('active');
            document.getElementById('entryType').value = 'task';
            document.getElementById('entryContent').value = '';
            document.getElementById('entryCollection').value = '';
        }

        async function saveEntry() {
            const type = document.getElementById('entryType').value;
            const content = document.getElementById('entryContent').value.trim();
            const collection = document.getElementById('entryCollection').value.trim() || 'uncategorized';

            if (!content) {
                alert('Please enter some content');
                return;
            }

            try {
                const response = await fetch('/execute_task', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        tool_name: 'bullet_journal',
                        action: 'add_entry',
                        params: { type, content, collection }
                    })
                });

                const result = await response.json();
                if (result.status === 'success') {
                    closeModal();
                    loadData();
                } else {
                    alert('Failed to save: ' + (result.message || result.error || 'Unknown error'));
                }
            } catch (err) {
                alert('Failed to save entry: ' + err.message);
            }
        }

        document.getElementById('addModal').addEventListener('click', (e) => {
            if (e.target.id === 'addModal') closeModal();
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') closeModal();
            if (e.key === 'n' && !document.querySelector('.modal.active') && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
                e.preventDefault();
                openModal();
            }
        });

        loadData();
    
        // Global keyboard shortcuts (Cmd+0 to return home)
        const shortcuts = { '0': 'command_center.html', '1': 'task_board.html', '2': 'doc_editor.html', '3': 'bullet_journal.html', '4': 'calendar_dashboard.html', '5': 'inbox_dashboard.html', '6': 'crm_dashboard.html' };
        document.addEventListener('keydown', (e) => { if ((e.metaKey || e.ctrlKey) && shortcuts[e.key]) { e.preventDefault(); window.location.href = shortcuts[e.key]; } });
    

