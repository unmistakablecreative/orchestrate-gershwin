
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


        // State
        let tables = [];
        let currentTable = null;
        let currentColumns = [];
        let currentRows = [];
        let selectedRowId = null;
        let searchQuery = '';
        let searchDebounceTimer = null;
        let sortState = { column: null, direction: null }; // 'asc', 'desc', or null
        let currentView = 'grid'; // 'grid' or 'list'

        const TAG_COLORS = ['green', 'yellow', 'red', 'blue', 'purple', 'pink'];

        // API helper
        async function api(action, params = {}) {
            const response = await fetch('/execute_task', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    tool_name: 'sheets_tool',
                    action: action,
                    params: params
                })
            });
            return response.json();
        }

        // Toast
        function showToast(message) {
            const toast = document.getElementById('toast');
            toast.textContent = message;
            toast.classList.add('show');
            setTimeout(() => toast.classList.remove('show'), 3000);
        }

        // Load tables
        async function loadTables() {
            const result = await api('list_tables');
            if (result.status === 'success') {
                tables = result.tables || [];
                renderTableList();
                if (tables.length > 0 && !currentTable) {
                    selectTable(tables[0].table_name);
                } else if (tables.length === 0) {
                    renderEmptyState();
                }
            }
        }

        // Render table list in sidebar
        function renderTableList() {
            const list = document.getElementById('tableList');
            list.innerHTML = tables.map(t => `
                <div class="table-item ${t.table_name === currentTable ? 'active' : ''}"
                     onclick="selectTable('${t.table_name}')">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="3" y="3" width="18" height="18" rx="2"/>
                        <path d="M3 9h18M9 21V9"/>
                    </svg>
                    ${t.display_name || t.table_name}
                </div>
            `).join('');
        }

        // Select table
        async function selectTable(tableName) {
            currentTable = tableName;
            renderTableList();

            const table = tables.find(t => t.table_name === tableName);
            if (table) {
                currentColumns = table.columns || [];
                await loadRows();
            }
        }

        // Load rows
        async function loadRows() {
            if (!currentTable) return;

            const result = await api('query', { table: currentTable });
            if (result.status === 'success') {
                currentRows = result.rows || [];
                renderGrid();
            }
        }

        // Render empty state
        function renderEmptyState() {
            const grid = document.getElementById('dataGrid');
            grid.innerHTML = `
                <div class="empty-state">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="3" y="3" width="18" height="18" rx="2"/>
                        <path d="M3 9h18M9 21V9"/>
                    </svg>
                    <p>No tables yet</p>
                    <button class="btn-primary" onclick="showCreateTableModal()">Create your first table</button>
                </div>
            `;
        }

        // Render grid
        function renderGrid() {
            const grid = document.getElementById('dataGrid');

            if (currentView === 'list') {
                renderListView(grid);
                return;
            }

            if (currentView === 'calendar') {
                renderCalendarView(grid);
                return;
            }

            const colCount = currentColumns.length + 2; // +1 for row number, +1 for add column button

            // Set grid template - include add column button width
            const colWidths = ['40px', ...currentColumns.map(c =>
                c.type === 'text' || c.type === 'long_text' || c.type === 'url' ? '200px' : '140px'
            ), '40px'];
            grid.style.gridTemplateColumns = colWidths.join(' ');

            // Header
            let html = '<div class="grid-header">';
            html += '<div class="header-cell">#</div>';
            currentColumns.forEach(col => {
                let sortIndicator = '';
                if (sortState.column === col.name) {
                    if (sortState.direction === 'asc') {
                        sortIndicator = ' <span style="margin-left:auto;font-size:10px;">▲</span>';
                    } else if (sortState.direction === 'desc') {
                        sortIndicator = ' <span style="margin-left:auto;font-size:10px;">▼</span>';
                    }
                }
                html += `<div class="header-cell" style="cursor:pointer;" onclick="toggleColumnSort('${col.name}')" ondblclick="editColumnName(event, '${col.name}')">
                    ${getTypeIcon(col.type)}
                    <span class="header-text">${col.display_name || col.name}</span>${sortIndicator}
                    <div class="resize-handle"></div>
                </div>`;
            });
            // Add column button at end of header
            html += `<div class="header-cell-add" onclick="showAddColumnModal()" title="Add column">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <line x1="12" y1="5" x2="12" y2="19"/>
                    <line x1="5" y1="12" x2="19" y2="12"/>
                </svg>
            </div>`;
            html += '</div>';

            // Rows - use filtered/sorted display rows
            const displayRows = getDisplayRows();
            displayRows.forEach((row, idx) => {
                html += `<div class="grid-row" data-row-id="${row._id}">`;
                html += `<div class="grid-cell">
                    <span class="row-number">${idx + 1}</span>
                    <span class="row-expand" onclick="showContextMenu(event, '${row._id}')">⤢</span>
                </div>`;

                currentColumns.forEach(col => {
                    const value = row[col.name];
                    html += `<div class="grid-cell">${renderCell(col, value, row._id)}</div>`;
                });
                // Empty cell for add column column
                html += '<div class="grid-cell" style="background:#fafafa;"></div>';
                html += '</div>';
            });

            // Add row - spans all columns including add column button
            html += `<div class="add-row-cell" style="grid-column: 1 / ${colCount + 1};" onclick="addRow()">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <line x1="12" y1="5" x2="12" y2="19"/>
                    <line x1="5" y1="12" x2="19" y2="12"/>
                </svg>
                Add row
            </div>`;

            grid.innerHTML = html;
        }

        // Switch between grid and list views
        function switchView(view) {
            currentView = view;
            document.getElementById('gridViewTab').classList.toggle('active', view === 'grid');
            document.getElementById('calendarViewTab').classList.toggle('active', view === 'calendar');
            document.getElementById('listViewTab').classList.toggle('active', view === 'list');
            renderGrid();
        }

        // Render list view as cards
        function renderListView(grid) {
            grid.style.gridTemplateColumns = '1fr'; // Reset grid columns for list view
            const displayRows = getDisplayRows();

            let html = '<div class="list-view-container" style="display:flex;flex-wrap:wrap;gap:16px;padding:16px;">';

            displayRows.forEach((row, idx) => {
                html += `<div class="list-card" data-row-id="${row._id}" style="
                    flex: 0 0 calc(50% - 8px);
                    background: var(--toolbar-bg);
                    border: 1px solid var(--border-color);
                    border-radius: 8px;
                    padding: 16px;
                    box-sizing: border-box;
                ">`;
                html += `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid var(--border-color);">
                    <span style="font-weight:600;color:var(--text-secondary);">#${idx + 1}</span>
                    <span class="row-expand" onclick="showContextMenu(event, '${row._id}')" style="cursor:pointer;">⤢</span>
                </div>`;

                currentColumns.forEach(col => {
                    const value = row[col.name];
                    const displayValue = value != null ? value : '';
                    html += `<div style="margin-bottom:8px;">
                        <div style="font-size:11px;color:var(--text-muted);margin-bottom:2px;">${col.display_name || col.name}</div>
                        <div style="color:var(--text-primary);">${renderCellValue(col, displayValue)}</div>
                    </div>`;
                });

                html += '</div>';
            });

            html += '</div>';
            grid.innerHTML = html;
        }

        // Render calendar view
        function renderCalendarView(grid) {
            grid.style.gridTemplateColumns = '1fr';

            // Find date column
            const dateCol = currentColumns.find(c => c.type === 'date');
            const titleCol = currentColumns.find(c => c.type === 'text') || currentColumns[0];

            if (!dateCol) {
                grid.innerHTML = `<div style="padding:48px;text-align:center;color:var(--text-secondary);">
                    <p style="font-size:16px;">No date column found.</p>
                    <p style="font-size:13px;">Add a Date column to this table to use Calendar view.</p>
                </div>`;
                return;
            }

            // Get current month/year from calendarState or default to today
            if (!window.calendarState) window.calendarState = { year: new Date().getFullYear(), month: new Date().getMonth() };
            const { year, month } = window.calendarState;

            const monthNames = ['January','February','March','April','May','June','July','August','September','October','November','December'];
            const dayNames = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];

            // Build map of date string → rows
            const rowsByDate = {};
            const displayRows = getDisplayRows();
            displayRows.forEach(row => {
                const val = row[dateCol.name];
                if (!val) return;
                const d = new Date(val);
                if (isNaN(d)) return;
                const key = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
                if (!rowsByDate[key]) rowsByDate[key] = [];
                rowsByDate[key].push(row);
            });

            // First day of month and total days
            const firstDay = new Date(year, month, 1).getDay();
            const daysInMonth = new Date(year, month + 1, 0).getDate();
            const today = new Date();
            const todayKey = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;

            let html = `<div style="padding:16px;">
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">
                    <button onclick="calendarNav(-1)" style="padding:6px 12px;border:1px solid var(--border-color);border-radius:4px;background:white;cursor:pointer;font-size:13px;">&#8592; Prev</button>
                    <span style="font-size:16px;font-weight:600;color:var(--text-primary);">${monthNames[month]} ${year}</span>
                    <button onclick="calendarNav(1)" style="padding:6px 12px;border:1px solid var(--border-color);border-radius:4px;background:white;cursor:pointer;font-size:13px;">Next &#8594;</button>
                </div>
                <div style="display:grid;grid-template-columns:repeat(7,1fr);gap:1px;background:var(--border-color);border:1px solid var(--border-color);border-radius:6px;overflow:hidden;">`;

            // Day name headers
            dayNames.forEach(d => {
                html += `<div style="background:var(--sidebar-bg);padding:8px;text-align:center;font-size:11px;font-weight:600;color:var(--text-secondary);">${d}</div>`;
            });

            // Empty cells before first day
            for (let i = 0; i < firstDay; i++) {
                html += `<div style="background:white;min-height:80px;padding:4px;"></div>`;
            }

            // Day cells
            for (let day = 1; day <= daysInMonth; day++) {
                const dateKey = `${year}-${String(month+1).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
                const isToday = dateKey === todayKey;
                const rows = rowsByDate[dateKey] || [];

                html += `<div style="background:white;min-height:80px;padding:4px;${isToday ? 'background:#e8f0fe;' : ''}">
                    <div style="font-size:12px;font-weight:${isToday ? '700' : '400'};color:${isToday ? 'var(--airtable-blue)' : 'var(--text-primary)'};margin-bottom:4px;">${day}</div>`;

                rows.forEach(row => {
                    const title = titleCol ? (row[titleCol.name] || '—') : row._id;
                    html += `<div style="background:var(--airtable-blue);color:white;font-size:11px;padding:2px 5px;border-radius:3px;margin-bottom:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${escapeHtml(String(title))}">${escapeHtml(String(title))}</div>`;
                });

                html += `</div>`;
            }

            html += `</div></div>`;
            grid.innerHTML = html;
        }

        function calendarNav(direction) {
            if (!window.calendarState) window.calendarState = { year: new Date().getFullYear(), month: new Date().getMonth() };
            window.calendarState.month += direction;
            if (window.calendarState.month > 11) { window.calendarState.month = 0; window.calendarState.year++; }
            if (window.calendarState.month < 0) { window.calendarState.month = 11; window.calendarState.year--; }
            renderGrid();
        }
        function renderCellValue(col, value) {
            if (value == null || value === '') return '<span style="color:var(--text-muted);">-</span>';

            if (col.type === 'boolean') {
                return value ? '✓ Yes' : '✗ No';
            }
            if (col.type === 'select' && col.options) {
                const opt = col.options.find(o => o.value === value);
                if (opt) {
                    const colorVar = `var(--${opt.color || 'blue'}-tag)`;
                    return `<span style="background:${colorVar};padding:2px 8px;border-radius:4px;font-size:12px;">${opt.label || value}</span>`;
                }
            }
            if (col.type === 'url' && value) {
                return `<a href="${value}" target="_blank" style="color:var(--airtable-blue);text-decoration:none;">${value}</a>`;
            }
            if (col.type === 'date' && value) {
                return new Date(value).toLocaleDateString();
            }
            return String(value);
        }

        // Get type icon
        function getTypeIcon(type) {
            const icons = {
                text: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 7V4h16v3M9 20h6M12 4v16"/></svg>',
                number: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 17l6-6-6-6M12 19h8"/></svg>',
                date: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>',
                boolean: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>',
                select: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>',
                url: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/></svg>',
                email: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"/><path d="M16 8v5a3 3 0 006 0v-1a10 10 0 10-3.92 7.94"/></svg>',
                long_text: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="17" y1="10" x2="3" y2="10"/><line x1="21" y1="6" x2="3" y2="6"/><line x1="21" y1="14" x2="3" y2="14"/><line x1="17" y1="18" x2="3" y2="18"/></svg>',
                multi_select: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>'
            };
            return icons[type] || icons.text;
        }

        // Render cell by type
        function renderCell(col, value, rowId) {
            switch (col.type) {
                case 'number':
                    return `<input type="number" class="cell-number" value="${value || ''}"
                            onblur="saveCell('${rowId}', '${col.name}', this.value)">`;

                case 'date':
                    return `<input type="date" class="cell-date" value="${value || ''}"
                            onchange="saveCell('${rowId}', '${col.name}', this.value)">`;

                case 'boolean':
                    return `<div class="cell-checkbox ${value ? 'checked' : ''}"
                            onclick="toggleCheckbox(this, '${rowId}', '${col.name}')"></div>`;

                case 'select':
                    if (!value) return `<span class="select-pill" style="background:#eee;color:#666"
                                        onclick="showSelectDropdown(event, '${rowId}', '${col.name}', '${JSON.stringify(col.options || []).replace(/'/g, "\\'")}')">—</span>`;
                    const colorIdx = (col.options || []).indexOf(value) % TAG_COLORS.length;
                    const color = TAG_COLORS[colorIdx >= 0 ? colorIdx : 0];
                    return `<span class="select-pill ${color}"
                            onclick="showSelectDropdown(event, '${rowId}', '${col.name}', '${JSON.stringify(col.options || []).replace(/'/g, "\\'")}')">
                            ${value}</span>`;

                case 'url':
                    if (!value) {
                        return `<input type="url" class="cell-url-input" value="" placeholder="https://..."
                                onblur="saveCell('${rowId}', '${col.name}', this.value)">`;
                    }
                    return `<a href="${escapeHtml(value)}" target="_blank" class="cell-url"
                            onclick="event.stopPropagation()"
                            ondblclick="editUrlCell(event, '${rowId}', '${col.name}', '${escapeHtml(value)}')">${escapeHtml(value)}</a>`;

                case 'email':
                    if (!value) {
                        return `<input type="email" class="cell-email-input" value="" placeholder="email@example.com"
                                onblur="saveCell('${rowId}', '${col.name}', this.value)">`;
                    }
                    return `<a href="mailto:${escapeHtml(value)}" class="cell-email"
                            onclick="event.stopPropagation()"
                            ondblclick="editEmailCell(event, '${rowId}', '${col.name}', '${escapeHtml(value)}')">${escapeHtml(value)}</a>`;

                case 'long_text':
                    const escapedValue = escapeHtml(value || '');
                    return `<div class="cell-longtext-container">
                                <textarea class="cell-longtext"
                                    onblur="saveCell('${rowId}', '${col.name}', this.value)"
                                    oninput="autoResizeTextarea(this)">${escapedValue}</textarea>
                            </div>`;

                case 'multi_select':
                    const selectedValues = parseMultiSelectValue(value);
                    const options = col.options || [];
                    const optionsJson = JSON.stringify(options).replace(/'/g, "\\'");

                    if (selectedValues.length === 0) {
                        return `<div class="multi-select-container"
                                onclick="showMultiSelectDropdown(event, '${rowId}', '${col.name}', '${optionsJson}', [])">
                                <span style="color:var(--text-muted)">Select...</span>
                            </div>`;
                    }

                    let pills = '';
                    selectedValues.forEach((val, idx) => {
                        const optIdx = options.indexOf(val);
                        const pillColor = TAG_COLORS[optIdx >= 0 ? optIdx % TAG_COLORS.length : idx % TAG_COLORS.length];
                        pills += `<span class="multi-select-pill ${pillColor}">${escapeHtml(val)}</span>`;
                    });

                    const selectedJson = JSON.stringify(selectedValues).replace(/'/g, "\\'");
                    return `<div class="multi-select-container"
                            onclick="showMultiSelectDropdown(event, '${rowId}', '${col.name}', '${optionsJson}', '${selectedJson}')">
                            ${pills}
                        </div>`;

                default: // text
                    return `<input type="text" class="cell-text" value="${escapeHtml(value || '')}"
                            onblur="saveCell('${rowId}', '${col.name}', this.value)">`;
            }
        }

        // Helper to escape HTML in values
        function escapeHtml(str) {
            if (!str) return '';
            return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
        }

        // Parse multi-select value (can be JSON array or comma-separated string)
        function parseMultiSelectValue(value) {
            if (!value) return [];
            if (Array.isArray(value)) return value;
            try {
                const parsed = JSON.parse(value);
                if (Array.isArray(parsed)) return parsed;
            } catch (e) {}
            // Fallback: comma-separated
            return String(value).split(',').map(s => s.trim()).filter(s => s);
        }

        // Auto-resize textarea for long_text
        function autoResizeTextarea(el) {
            el.style.height = 'auto';
            el.style.height = Math.min(el.scrollHeight, 200) + 'px';
        }

        // Edit URL cell (double-click to edit)
        function editUrlCell(event, rowId, colName, currentValue) {
            event.preventDefault();
            event.stopPropagation();
            const cell = event.target.parentElement;
            cell.innerHTML = `<input type="url" class="cell-url-input" value="${currentValue}"
                            onblur="saveCell('${rowId}', '${colName}', this.value);"
                            onkeydown="if(event.key==='Enter'){this.blur();}">`;
            cell.querySelector('input').focus();
        }

        // Edit email cell (double-click to edit)
        function editEmailCell(event, rowId, colName, currentValue) {
            event.preventDefault();
            event.stopPropagation();
            const cell = event.target.parentElement;
            cell.innerHTML = `<input type="email" class="cell-email-input" value="${currentValue}"
                            onblur="saveCell('${rowId}', '${colName}', this.value);"
                            onkeydown="if(event.key==='Enter'){this.blur();}">`;
            cell.querySelector('input').focus();
        }

        // Multi-select dropdown
        let activeMultiSelectDropdown = null;

        function showMultiSelectDropdown(event, rowId, colName, optionsJson, selectedJson) {
            event.stopPropagation();
            hideMultiSelectDropdown();

            const options = JSON.parse(optionsJson);
            const selected = typeof selectedJson === 'string' ? JSON.parse(selectedJson) : selectedJson;
            const rect = event.currentTarget.getBoundingClientRect();

            const dropdown = document.createElement('div');
            dropdown.className = 'multi-select-dropdown';
            dropdown.style.top = rect.bottom + 4 + 'px';
            dropdown.style.left = rect.left + 'px';
            dropdown.onclick = (e) => e.stopPropagation();

            options.forEach((opt, idx) => {
                const isSelected = selected.includes(opt);
                const colorClass = TAG_COLORS[idx % TAG_COLORS.length];
                dropdown.innerHTML += `
                    <div class="multi-select-option">
                        <input type="checkbox" ${isSelected ? 'checked' : ''}
                               onchange="toggleMultiSelectOption('${rowId}', '${colName}', '${optionsJson}', '${opt}')">
                        <span class="multi-select-pill ${colorClass}">${opt}</span>
                    </div>
                `;
            });

            document.body.appendChild(dropdown);
            activeMultiSelectDropdown = dropdown;
        }

        function hideMultiSelectDropdown() {
            if (activeMultiSelectDropdown) {
                activeMultiSelectDropdown.remove();
                activeMultiSelectDropdown = null;
            }
        }

        async function toggleMultiSelectOption(rowId, colName, optionsJson, toggledOption) {
            const row = currentRows.find(r => r._id == rowId);
            if (!row) return;

            let currentSelected = parseMultiSelectValue(row[colName]);

            if (currentSelected.includes(toggledOption)) {
                currentSelected = currentSelected.filter(v => v !== toggledOption);
            } else {
                currentSelected.push(toggledOption);
            }

            await saveCell(rowId, colName, JSON.stringify(currentSelected));
        }

        document.addEventListener('click', hideMultiSelectDropdown);

        // Save cell
        async function saveCell(rowId, colName, value) {
            const data = {};
            data[colName] = value;
            const result = await api('update_row', { table: currentTable, id: rowId, data: data });
            if (result.status === 'success') {
                // Update in-memory row so sort/filter state survives
                const row = currentRows.find(r => r._id == rowId);
                if (row) row[colName] = value;
                renderGrid();
            }
        }

        // Toggle checkbox
        async function toggleCheckbox(el, rowId, colName) {
            const isChecked = el.classList.toggle('checked');
            await saveCell(rowId, colName, isChecked);
        }

        // Select dropdown
        let activeDropdown = null;

        function showSelectDropdown(event, rowId, colName, optionsJson) {
            event.stopPropagation();
            hideSelectDropdown();

            const options = JSON.parse(optionsJson);
            const rect = event.target.getBoundingClientRect();

            const dropdown = document.createElement('div');
            dropdown.className = 'select-dropdown';
            dropdown.style.top = rect.bottom + 4 + 'px';
            dropdown.style.left = rect.left + 'px';

            options.forEach((opt, idx) => {
                const colorClass = TAG_COLORS[idx % TAG_COLORS.length];
                dropdown.innerHTML += `
                    <div class="select-option" onclick="selectOption('${rowId}', '${colName}', '${opt}')">
                        <span class="select-pill ${colorClass}">${opt}</span>
                    </div>
                `;
            });

            document.body.appendChild(dropdown);
            activeDropdown = dropdown;
        }

        function hideSelectDropdown() {
            if (activeDropdown) {
                activeDropdown.remove();
                activeDropdown = null;
            }
        }

        async function selectOption(rowId, colName, value) {
            hideSelectDropdown();
            await saveCell(rowId, colName, value);
            await loadRows();
        }

        document.addEventListener('click', hideSelectDropdown);

        // Add row
        async function addRow() {
            // Build default data based on column types
            const data = {};
            currentColumns.forEach(col => {
                if (col.type === 'number') {
                    data[col.name] = 0;
                } else if (col.type === 'boolean') {
                    data[col.name] = 0;
                } else if (col.type === 'select') {
                    data[col.name] = (col.options && col.options.length > 0) ? col.options[0] : '';
                } else {
                    // text, date, or default
                    data[col.name] = '';
                }
            });
            const result = await api('add_row', { table: currentTable, data: data });
            if (result.status === 'success') {
                await loadRows();
            }
        }

        // Context menu
        function showContextMenu(event, rowId) {
            event.stopPropagation();
            selectedRowId = rowId;
            const menu = document.getElementById('contextMenu');
            menu.style.top = event.clientY + 'px';
            menu.style.left = event.clientX + 'px';
            menu.classList.add('show');
        }

        document.addEventListener('click', () => {
            document.getElementById('contextMenu').classList.remove('show');
        });

        function expandRow() {
            showToast('Row detail view coming soon.');
            document.getElementById('contextMenu').classList.remove('show');
        }

        function deleteRow() {
            document.getElementById('contextMenu').classList.remove('show');
            document.getElementById('deleteModal').classList.remove('hidden');
        }

        function hideDeleteModal() {
            document.getElementById('deleteModal').classList.add('hidden');
            selectedRowId = null;
        }

        async function confirmDelete() {
            if (selectedRowId) {
                await api('delete_row', { table: currentTable, id: selectedRowId });
                hideDeleteModal();
                await loadRows();
                showToast('Row deleted');
            }
        }

        // Create table modal
        function showCreateTableModal() {
            document.getElementById('createTableModal').classList.remove('hidden');
            document.getElementById('newTableName').value = '';
            document.getElementById('columnList').innerHTML = `
                <div class="column-item">
                    <input type="text" value="Name" placeholder="Column name">
                    <select onchange="toggleOptionsInput(this)">
                        <option value="text">Text</option>
                        <option value="number">Number</option>
                        <option value="date">Date</option>
                        <option value="boolean">Checkbox</option>
                        <option value="select">Select</option>
                        <option value="url">URL</option>
                        <option value="email">Email</option>
                        <option value="long_text">Long Text</option>
                        <option value="multi_select">Multi-Select</option>
                    </select>
                    <button class="remove-btn" onclick="removeColumn(this)">&times;</button>
                </div>
            `;
        }

        function hideCreateTableModal() {
            document.getElementById('createTableModal').classList.add('hidden');
        }

        function addColumn() {
            const list = document.getElementById('columnList');
            const item = document.createElement('div');
            item.className = 'column-item';
            item.innerHTML = `
                <input type="text" placeholder="Column name">
                <select onchange="toggleOptionsInput(this)">
                    <option value="text">Text</option>
                    <option value="number">Number</option>
                    <option value="date">Date</option>
                    <option value="boolean">Checkbox</option>
                    <option value="select">Select</option>
                    <option value="url">URL</option>
                    <option value="email">Email</option>
                    <option value="long_text">Long Text</option>
                    <option value="multi_select">Multi-Select</option>
                </select>
                <button class="remove-btn" onclick="removeColumn(this)">&times;</button>
            `;
            list.appendChild(item);
        }

        function removeColumn(btn) {
            const items = document.querySelectorAll('.column-item');
            if (items.length > 1) {
                btn.closest('.column-item').remove();
            }
        }

        async function createTable() {
            const name = document.getElementById('newTableName').value.trim();
            if (!name) {
                showToast('Please enter a table name');
                return;
            }

            const columnItems = document.querySelectorAll('.column-item');
            const columns = [];
            columnItems.forEach(item => {
                const colName = item.querySelector('input[type="text"]').value.trim();
                const colType = item.querySelector('select').value;
                const optionsInput = item.querySelector('.col-options-input');

                if (colName) {
                    const colDef = { name: colName, type: colType };
                    // Include options for select/multi_select
                    if ((colType === 'select' || colType === 'multi_select') && optionsInput) {
                        const optionsStr = optionsInput.value.trim();
                        if (optionsStr) {
                            colDef.options = optionsStr.split(',').map(s => s.trim()).filter(s => s);
                        }
                    }
                    columns.push(colDef);
                }
            });

            if (columns.length === 0) {
                showToast('Please add at least one column');
                return;
            }

            const result = await api('create_table', { name: name, columns: columns });
            if (result.status === 'success') {
                hideCreateTableModal();
                await loadTables();
                selectTable(result.table_name);
                showToast('Table created');
            } else {
                showToast(result.message || 'Error creating table');
            }
        }

        // Export CSV
        async function exportCSV() {
            if (!currentTable) return;
            const result = await api('export_csv', { table: currentTable });
            if (result.status === 'success' && result.file_path) {
                showToast(`CSV exported to: ${result.file_path}`);
            }
        }

        // Add Column Modal
        function showAddColumnModal() {
            if (!currentTable) {
                showToast('Please select a table first');
                return;
            }
            document.getElementById('addColumnModal').classList.remove('hidden');
            document.getElementById('addColName').value = '';
            document.getElementById('addColType').value = 'text';
            document.getElementById('addColOptions').value = '';
            document.getElementById('addColOptionsGroup').classList.remove('show');
        }

        function hideAddColumnModal() {
            document.getElementById('addColumnModal').classList.add('hidden');
        }

        function toggleAddColOptionsInput() {
            const type = document.getElementById('addColType').value;
            const optionsGroup = document.getElementById('addColOptionsGroup');
            if (type === 'select' || type === 'multi_select') {
                optionsGroup.classList.add('show');
            } else {
                optionsGroup.classList.remove('show');
            }
        }

        // Toggle options input in create table modal column items
        function toggleOptionsInput(selectEl) {
            const colItem = selectEl.closest('.column-item');
            const type = selectEl.value;
            // Check if options input already exists
            let optionsInput = colItem.querySelector('.col-options-input');
            if (type === 'select' || type === 'multi_select') {
                if (!optionsInput) {
                    optionsInput = document.createElement('input');
                    optionsInput.type = 'text';
                    optionsInput.className = 'col-options-input';
                    optionsInput.placeholder = 'Options (comma-sep)';
                    optionsInput.style.cssText = 'flex: 1; padding: 6px 8px; border: 1px solid var(--border-color); border-radius: 4px; font-size: 12px; margin-left: 4px;';
                    colItem.insertBefore(optionsInput, colItem.querySelector('.remove-btn'));
                }
            } else if (optionsInput) {
                optionsInput.remove();
            }
        }

        async function addColumnToTable() {
            const nameInput = document.getElementById('addColName');
            const typeSelect = document.getElementById('addColType');
            const optionsInput = document.getElementById('addColOptions');

            // Ensure elements exist before reading values
            if (!nameInput || !typeSelect) {
                showToast('Error: form elements not found');
                return;
            }

            const name = nameInput.value.trim();
            const type = typeSelect.value;
            const optionsStr = optionsInput ? optionsInput.value.trim() : '';

            if (!name) {
                showToast('Column name required');
                nameInput.focus();
                return;
            }

            const columnDef = { name: name, type: type };

            // Parse options for select/multi_select
            if ((type === 'select' || type === 'multi_select') && optionsStr) {
                columnDef.options = optionsStr.split(',').map(s => s.trim()).filter(s => s);
            }

            const result = await api('add_column', {
                table: currentTable,
                name: name,
                type: type,
                options: columnDef.options || []
            });

            if (result.status === 'success') {
                hideAddColumnModal();
                showToast('Column added');
                // Reload tables to get updated schema, then reload rows
                await loadTables();
                await selectTable(currentTable);
            } else {
                showToast(result.message || 'Error adding column');
            }
        }

        // Search handler with debounce
        // Filter state
        let filterState = { column: '', condition: 'contains', value: '' };

        function toggleFilterPanel() {
            const panel = document.getElementById('filterPanel');
            const isVisible = panel.style.display === 'flex';
            panel.style.display = isVisible ? 'none' : 'flex';
            if (!isVisible) populatePanelColumns();
        }

        function toggleSortPanel() {
            const panel = document.getElementById('sortPanel');
            const isVisible = panel.style.display === 'flex';
            panel.style.display = isVisible ? 'none' : 'flex';
            if (!isVisible) populatePanelColumns();
        }

        function populatePanelColumns() {
            const filterCol = document.getElementById('filterColumn');
            const sortCol = document.getElementById('sortColumn');
            if (filterCol) {
                filterCol.innerHTML = '<option value="">All columns</option>' +
                    currentColumns.map(c => `<option value="${c.name}">${c.display_name || c.name}</option>`).join('');
            }
            if (sortCol) {
                sortCol.innerHTML = '<option value="">None</option>' +
                    currentColumns.map(c => `<option value="${c.name}">${c.display_name || c.name}</option>`).join('');
            }
        }

        function applyFilter() {
            filterState.column = document.getElementById('filterColumn').value;
            filterState.condition = document.getElementById('filterCondition').value;
            filterState.value = document.getElementById('filterValue').value.toLowerCase().trim();
            renderGrid();
        }

        function clearFilter() {
            filterState = { column: '', condition: 'contains', value: '' };
            document.getElementById('filterColumn').value = '';
            document.getElementById('filterValue').value = '';
            renderGrid();
        }

        function applySortPanel() {
            const col = document.getElementById('sortColumn').value;
            const dir = document.getElementById('sortDirection').value;
            if (col) {
                sortState.column = col;
                sortState.direction = dir;
            } else {
                sortState.column = null;
                sortState.direction = null;
            }
            renderGrid();
        }

        function clearSort() {
            sortState = { column: null, direction: null };
            document.getElementById('sortColumn').value = '';
            renderGrid();
        }

        function handleSearch(query) {
            clearTimeout(searchDebounceTimer);
            searchDebounceTimer = setTimeout(() => {
                searchQuery = query.toLowerCase().trim();
                renderGrid();
            }, 200);
        }

        // Get filtered and sorted rows
        function getDisplayRows() {
            let rows = [...currentRows];

            // Apply search filter
            if (searchQuery) {
                rows = rows.filter(row => {
                    return currentColumns.some(col => {
                        const val = row[col.name];
                        if (val == null) return false;
                        return String(val).toLowerCase().includes(searchQuery);
                    });
                });
            }

            // Apply panel filter
            if (filterState.value || filterState.condition === 'is_empty' || filterState.condition === 'not_empty') {
                rows = rows.filter(row => {
                    const cols = filterState.column ? [currentColumns.find(c => c.name === filterState.column)].filter(Boolean) : currentColumns;
                    return cols.some(col => {
                        const val = row[col.name];
                        const str = val == null ? '' : String(val).toLowerCase();
                        if (filterState.condition === 'contains') return str.includes(filterState.value);
                        if (filterState.condition === 'equals') return str === filterState.value;
                        if (filterState.condition === 'is_empty') return str === '';
                        if (filterState.condition === 'not_empty') return str !== '';
                        return true;
                    });
                });
            }

            // Apply sort
            if (sortState.column && sortState.direction) {
                const col = currentColumns.find(c => c.name === sortState.column);
                if (col) {
                    rows.sort((a, b) => {
                        let valA = a[col.name];
                        let valB = b[col.name];

                        // Handle nulls - null values go last
                        if (valA == null && valB == null) return 0;
                        if (valA == null) return 1;
                        if (valB == null) return -1;

                        let cmp = 0;
                        if (col.type === 'number') {
                            cmp = Number(valA) - Number(valB);
                        } else if (col.type === 'date') {
                            const dateA = new Date(valA);
                            const dateB = new Date(valB);
                            cmp = dateA - dateB;
                        } else if (col.type === 'boolean') {
                            // false (0) before true (1) in ascending
                            cmp = (valA ? 1 : 0) - (valB ? 1 : 0);
                        } else {
                            // text, select, url, email, long_text, multi_select
                            cmp = String(valA).localeCompare(String(valB));
                        }

                        return sortState.direction === 'desc' ? -cmp : cmp;
                    });
                }
            }

            return rows;
        }

        // Column sort click handler
        function toggleColumnSort(colName) {
            if (sortState.column === colName) {
                // Cycle: asc -> desc -> clear
                if (sortState.direction === 'asc') {
                    sortState.direction = 'desc';
                } else if (sortState.direction === 'desc') {
                    sortState.column = null;
                    sortState.direction = null;
                }
            } else {
                sortState.column = colName;
                sortState.direction = 'asc';
            }
            renderGrid();
        }

        // Edit column name on double-click
        function editColumnName(event, colName) {
            event.stopPropagation();
            const headerCell = event.currentTarget;
            const textSpan = headerCell.querySelector('.header-text');
            if (!textSpan) return;

            const currentName = textSpan.textContent;
            const input = document.createElement('input');
            input.type = 'text';
            input.value = currentName;
            input.className = 'header-edit-input';
            input.style.cssText = 'width:100%;font-size:13px;font-weight:500;border:1px solid var(--airtable-blue);border-radius:4px;padding:2px 6px;outline:none;';

            input.onblur = () => saveColumnName(colName, input.value, textSpan, input);
            input.onkeydown = (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    input.blur();
                } else if (e.key === 'Escape') {
                    textSpan.textContent = currentName;
                    input.replaceWith(textSpan);
                }
            };

            textSpan.replaceWith(input);
            input.focus();
            input.select();
        }

        async function saveColumnName(colName, newName, originalSpan, input) {
            const col = currentColumns.find(c => c.name === colName);
            const oldName = col ? (col.display_name || col.name) : colName;

            if (newName.trim() === '' || newName === oldName) {
                originalSpan.textContent = oldName;
                input.replaceWith(originalSpan);
                return;
            }

            const result = await api('update_column_name', {
                table: currentTable,
                column: colName,
                display_name: newName.trim()
            });

            if (result.status === 'success') {
                if (col) col.display_name = newName.trim();
                showToast('Column renamed');
                renderGrid();
            } else {
                showToast('Failed to rename column: ' + (result.message || 'Unknown error'));
                originalSpan.textContent = oldName;
                input.replaceWith(originalSpan);
            }
        }

        // Init
        loadTables();
    

