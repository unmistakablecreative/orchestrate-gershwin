
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


        const API_BASE = 'https://app.orchestrateos.io/execute_task';
        let currentDirectory = null;
        let expandedFileId = null;

        async function executeTask(toolName, action, params = {}) {
            try {
                const resp = await fetch(API_BASE, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ tool_name: toolName, action, params })
                });
                return await resp.json();
            } catch (e) {
                console.error('API Error:', e);
                return { status: 'error', message: e.message };
            }
        }

        function formatBytes(bytes) {
            if (!bytes || bytes === 0) return '—';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
        }

        function formatDate(dateStr) {
            if (!dateStr) return '—';
            const d = new Date(dateStr);
            if (isNaN(d)) return dateStr;
            return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
        }

        function getRankClass(rank) {
            if (!rank) return '';
            const r = rank.toLowerCase();
            if (r.includes('high') || r.includes('critical') || r === 'a') return 'rank-high';
            if (r.includes('medium') || r === 'b') return 'rank-medium';
            return 'rank-low';
        }

        async function loadDirectories() {
            const tree = document.getElementById('directoryTree');
            const result = await executeTask('files_db', 'list_directory', {});

            if (result.status === 'error') {
                tree.innerHTML = `<div class="empty-state">Failed to load directories</div>`;
                return;
            }

            const dirs = result.directories || result.data || [];
            if (dirs.length === 0) {
                tree.innerHTML = `<div class="empty-state">No directories found</div>`;
                return;
            }

            tree.innerHTML = `
                <div class="dir-item active" data-dir="">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
                    </svg>
                    All Files
                </div>
                ${dirs.map(d => `
                    <div class="dir-item" data-dir="${d.parent_dir || d}">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                        </svg>
                        ${d.parent_dir || d}
                    </div>
                `).join('')}
            `;

            tree.querySelectorAll('.dir-item').forEach(item => {
                item.addEventListener('click', () => {
                    tree.querySelectorAll('.dir-item').forEach(i => i.classList.remove('active'));
                    item.classList.add('active');
                    currentDirectory = item.dataset.dir || null;
                    document.getElementById('currentPath').textContent = currentDirectory || 'All Files';
                    loadFiles(currentDirectory);
                });
            });
        }

        async function loadFiles(directory = null) {
            const tbody = document.getElementById('filesBody');
            tbody.innerHTML = `<tr><td colspan="6"><div class="loading"><div class="loading-spinner"></div>Loading files...</div></td></tr>`;

            const params = directory ? { directory } : {};
            const result = await executeTask('files_db', 'list_directory', params);

            if (result.status === 'error') {
                tbody.innerHTML = `<tr><td colspan="6"><div class="empty-state">Failed to load files</div></td></tr>`;
                return;
            }

            const files = result.files || result.data || [];
            renderFiles(files);
        }

        async function searchFiles(query) {
            if (!query || query.length < 2) {
                loadFiles(currentDirectory);
                return;
            }

            const tbody = document.getElementById('filesBody');
            tbody.innerHTML = `<tr><td colspan="6"><div class="loading"><div class="loading-spinner"></div>Searching...</div></td></tr>`;

            const result = await executeTask('files_db', 'search_files_fts', { query });

            if (result.status === 'error') {
                tbody.innerHTML = `<tr><td colspan="6"><div class="empty-state">Search failed</div></td></tr>`;
                return;
            }

            const files = result.files || result.data || result.results || [];
            renderFiles(files);
        }

        function renderFiles(files) {
            const tbody = document.getElementById('filesBody');
            const countEl = document.getElementById('fileCount');

            countEl.textContent = `${files.length} file${files.length !== 1 ? 's' : ''}`;

            if (files.length === 0) {
                tbody.innerHTML = `<tr><td colspan="6"><div class="empty-state">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>
                        <polyline points="14 2 14 8 20 8"/>
                    </svg>
                    No files found
                </div></td></tr>`;
                return;
            }

            tbody.innerHTML = files.map((f, i) => `
                <tr data-file-id="${f.id || i}" onclick="toggleDetails(this, ${JSON.stringify(f).replace(/"/g, '&quot;')})">
                    <td>
                        <div class="filename-cell">
                            <span class="file-icon">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>
                                    <polyline points="14 2 14 8 20 8"/>
                                </svg>
                            </span>
                            ${f.filename || '—'}
                        </div>
                    </td>
                    <td><span class="ext-badge">${f.extension || '—'}</span></td>
                    <td class="size-cell">${formatBytes(f.size_bytes)}</td>
                    <td class="date-cell">${formatDate(f.modified_at)}</td>
                    <td>${f.purpose || '—'}</td>
                    <td class="rank-cell">
                        ${f.file_rank ? `<span class="rank-badge ${getRankClass(f.file_rank)}">${f.file_rank}</span>` : '—'}
                    </td>
                </tr>
                <tr class="expanded-details" id="details-${f.id || i}">
                    <td colspan="6">
                        <div class="detail-grid">
                            <div class="detail-item">
                                <div class="detail-label">Full Path</div>
                                <div class="detail-value">${f.path || f.parent_dir ? (f.parent_dir + '/' + f.filename) : f.filename}</div>
                            </div>
                            <div class="detail-item">
                                <div class="detail-label">Size (bytes)</div>
                                <div class="detail-value">${f.size_bytes || 0}</div>
                            </div>
                            <div class="detail-item">
                                <div class="detail-label">Last Modified</div>
                                <div class="detail-value">${f.modified_at || '—'}</div>
                            </div>
                            <div class="detail-item">
                                <div class="detail-label">Extension</div>
                                <div class="detail-value">${f.extension || '—'}</div>
                            </div>
                            <div class="detail-item">
                                <div class="detail-label">Purpose</div>
                                <div class="detail-value">${f.purpose || 'Not specified'}</div>
                            </div>
                            <div class="detail-item">
                                <div class="detail-label">File Rank</div>
                                <div class="detail-value">${f.file_rank || 'Unranked'}</div>
                            </div>
                        </div>
                    </td>
                </tr>
            `).join('');
        }

        function toggleDetails(row, file) {
            const fileId = row.dataset.fileId;
            const detailsRow = document.getElementById(`details-${fileId}`);

            // Collapse previously expanded
            document.querySelectorAll('.expanded-details.show').forEach(el => {
                if (el.id !== `details-${fileId}`) {
                    el.classList.remove('show');
                    el.previousElementSibling.classList.remove('expanded');
                }
            });

            // Toggle current
            const isExpanded = detailsRow.classList.contains('show');
            detailsRow.classList.toggle('show');
            row.classList.toggle('expanded');

            // Optionally fetch full file details
            if (!isExpanded && file.id) {
                fetchFileDetails(file.id, detailsRow);
            }
        }

        async function fetchFileDetails(fileId, detailsRow) {
            const result = await executeTask('files_db', 'get_file', { file_id: fileId });
            if (result.status === 'success' && result.file) {
                const f = result.file;
                const grid = detailsRow.querySelector('.detail-grid');
                if (grid) {
                    grid.innerHTML = `
                        <div class="detail-item">
                            <div class="detail-label">Full Path</div>
                            <div class="detail-value">${f.path || f.parent_dir ? (f.parent_dir + '/' + f.filename) : f.filename}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">Size (bytes)</div>
                            <div class="detail-value">${f.size_bytes || 0}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">Last Modified</div>
                            <div class="detail-value">${f.modified_at || '—'}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">Extension</div>
                            <div class="detail-value">${f.extension || '—'}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">Purpose</div>
                            <div class="detail-value">${f.purpose || 'Not specified'}</div>
                        </div>
                        <div class="detail-item">
                            <div class="detail-label">File Rank</div>
                            <div class="detail-value">${f.file_rank || 'Unranked'}</div>
                        </div>
                    `;
                }
            }
        }

        // Search debounce
        let searchTimeout;
        document.getElementById('searchInput').addEventListener('input', (e) => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                searchFiles(e.target.value.trim());
            }, 300);
        });

        // Init
        document.addEventListener('DOMContentLoaded', () => {
            loadDirectories();
            loadFiles();
        });
    

