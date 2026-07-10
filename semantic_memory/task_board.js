
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


        const API_BASE = '';
        const QUEUE_FILES = ['claude_task_q1.json', 'claude_task_q2.json', 'claude_task_q3.json', 'claude_task_q4.json', 'claude_task_q5.json', 'claude_task_q6.json', 'claude_task_q7.json'];
        const RESULTS_FILE = 'claude_task_results.json';
        const STAGED_FILE = 'staged_tasks.json';

        let stagedTasks = [];
        let activeTasks = [];
        let recentTasks = [];
        let completingTasks = [];  // Tasks that just finished - show briefly before moving to done
        let previousActiveIds = new Set();  // Track IDs from last poll
        let runningTimers = {};
        let lastActiveHash = '';
        let lastRecentHash = '';
        let isExpanded = false;

        const presetLabels = { custom:'Custom', image:'Images', document:'Document', research:'Research', social:'Social', newsletter:'Newsletter', code:'Code', automation:'Automation', mockup:'Mockup' };
        const placeholders = {
            custom: "Write your custom task description...",
            image: "Enter topic for image generation\n\nExample: sunset landscapes, tech workspace, product mockups",
            document: "Enter document title and content\n\nExample: Q1 OKRs - sales targets and marketing initiatives",
            research: "Enter research topic\n\nExample: AI coordination infrastructure market analysis",
            social: "Enter post topic or theme\n\nExample: Thread on why SaaS is dead, LinkedIn post on AI automation",
            newsletter: "Enter newsletter subject or theme\n\nExample: Weekly update on OrchestrateOS progress",
            code: "Describe the coding task\n\nExample: Add webhook endpoint for Stripe payments",
            automation: "Describe trigger and action in plain English\n\nExample: When a new podcast is added to podcast_index.json, auto-rename the audio file",
            mockup: "Enter: Site name/brand, description, style preferences\n\nExample: TechFlow AI - SaaS dashboard for ML ops, dark theme, minimal"
        };
        const presetTemplates = {
            custom: (text, col) => text,
            image: (text, col) => `Generate image batch:\n- Topic: ${text}\n- Style: cinematic, 16:9 aspect ratio\n- Count: 5 images\n- Output: semantic_memory/images/`,
            document: (text, col) => `Create document via doc_editor:\n- Title: ${text}\n- Collection: ${col || 'Inbox'}\n- Use doc_editor.create_doc action`,
            research: (text, col) => `Deep research using deep_research tool:\n\n1. Generate 10-15 subqueries for topic: "${text}"\n   Include angles: statistics, challenges, case studies, market data, expert analysis, best practices\n\n2. Execute: deep_research.search with subqueries array\n\n3. Execute: deep_research.prepare_synthesis with top_n=30\n\n4. Read data/research_synthesis.json and write comprehensive report\n\n5. Create document via doc_editor.create_doc:\n   - Title: "Deep Research: ${text}"\n   - Collection: Inbox\n   - Content: Full research report with citations\n\nDO NOT skip any step. Use the actual deep_research tool actions.`,
            social: (text, col) => `Create social media content:\n- Topic: ${text}\n- Platforms: LinkedIn, Twitter/X\n- Style: Professional but conversational\n- Include: Hook, value, CTA\n- Output: Post draft in Outline doc`,
            newsletter: (text, col) => `Draft newsletter email:\n- Subject: ${text}\n- Audience: Subscribers\n- Tone: Personal, insightful\n- Sections: Opening hook, main content, CTA\n- Output: Draft in Outline doc for review`,
            code: (text, col) => `Development task:\n- Task: ${text}\n- Follow existing patterns in codebase\n- Test after implementation\n- Document any significant changes`,
            automation: (text, col) => `Add automation rule via automation_engine.add_rule:\n\nParse user request: "${text}"\n\nExtract:\n1. rule_key: snake_case identifier derived from the description\n2. trigger: { "file": "<data file to watch>", "type": "entry_added|file_changed|schedule" }\n3. action: { "tool": "<tool_name>", "action": "<action_name>", "params": { <relevant params with {placeholders}> } }\n\nCall automation_engine.add_rule with:\n- rule_key: the generated key\n- rule: { "trigger": {...}, "action": {...}, "enabled": true }\n\nCommon triggers:\n- file watch: {"file": "data/some_file.json", "type": "entry_added"}\n- schedule: {"type": "schedule", "cron": "0 9 * * *"}\n\nConfirm rule was added successfully.`,
            mockup: (text, col) => `Generate site mockup variations via claude_assistant.assign_mockup_batch:\n\nUser input: "${text}"\n\nParse the input to extract:\n- Site name/brand\n- Description/purpose\n- Style preferences\n\nCall claude_assistant.assign_mockup_batch with:\n- description: Include site name, purpose, and style extracted above\n- Output path MUST be: semantic_memory/mockups/\n\nEach mockup variation should:\n1. Generate complete HTML file with inline CSS\n2. Save to semantic_memory/mockups/{site_name}_v{N}.html\n3. Create 3-5 unique design variations\n4. Include responsive design\n5. Use professional UI patterns\n\nDO NOT save mockups anywhere except semantic_memory/mockups/`
        };
        const doneColors = [CONFIG.colors.color_6,CONFIG.colors.color_2,CONFIG.colors.color_7,CONFIG.colors.color_10,CONFIG.colors.color_0];

        // API helpers
        async function fetchJson(url) {
            try {
                const resp = await fetch(url + '?t=' + Date.now());
                if (!resp.ok) return null;
                return await resp.json();
            } catch { return null; }
        }

        async function executeTask(toolName, action, params) {
            try {
                const resp = await fetch('/execute_task', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ tool_name: toolName, action, params })
                });
                return await resp.json();
            } catch (e) {
                console.error('Execute error:', e);
                return { status: 'error', message: e.message };
            }
        }

        // Generate card title from description (fallback)
        function generateCardTitle(desc) {
            let title = desc
                .replace(/^(please |can you |i need you to |i want you to |go ahead and )/i, '')
                .replace(/^(build |create |make |draft |write |send |deploy |generate |set up |configure |research |update |fix )/i, '');
            title = title.charAt(0).toUpperCase() + title.slice(1);
            if (title.length > 40) {
                title = title.substring(0, 37).replace(/\s+\S*$/, '') + '...';
            }
            return title;
        }

        // Placeholders
        function updatePlaceholder() {
            const s = document.getElementById('presetSelect');
            const t = document.getElementById('taskTextarea');
            const c = document.getElementById('collectionSelect');
            t.placeholder = placeholders[s.value] || placeholders.custom;
            t.value = '';
            // Show collection dropdown only for document preset
            c.style.display = s.value === 'document' ? 'block' : 'none';
            t.focus();
        }

        function getInput() {
            const text = document.getElementById('taskTextarea').value.trim();
            const preset = document.getElementById('presetSelect').value;
            const collection = document.getElementById('collectionSelect').value;
            return { text, preset, label: presetLabels[preset], collection };
        }

        function clearInput() {
            document.getElementById('taskTextarea').value = '';
            document.getElementById('presetSelect').value = 'custom';
            document.getElementById('collectionSelect').value = 'Inbox';
            document.getElementById('collectionSelect').style.display = 'none';
            document.getElementById('taskTextarea').placeholder = placeholders.custom;
            document.getElementById('taskTextarea').focus();
        }

        // Staging
        function addToStaging() {
            const { text, preset, label, collection } = getInput();
            if (!text) { showToast('Type a task first'); return; }
            stagedTasks.push({ id: 'stg_' + Date.now(), text, preset, label, collection });
            clearInput();
            renderStaging();
            showToast('Task added to batch');
        }

        function removeStagedTask(id) {
            const el = document.querySelector(`[data-staged-id="${id}"]`);
            if (el) {
                el.classList.add('removing');
                setTimeout(async () => {
                    stagedTasks = stagedTasks.filter(t => t.id !== id);
                    renderStaging();
                    // Also clear backend file if removing backend tasks
                    if (id.startsWith('backend_')) {
                        await saveStagedToBackend();
                    }
                }, 200);
            }
        }

        async function saveStagedToBackend() {
            const backendTasks = stagedTasks.filter(t => t.fromBackend).map(t => ({
                description: t.text,
                preset: t.preset,
                staged_at: t.id.replace('backend_', '')
            }));
            try {
                await fetch(API_BASE + '/execute_task', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        tool_name: 'json_manager',
                        action: 'create_json_file',
                        params: { file: 'data/staged_tasks.json', data: backendTasks }
                    })
                });
            } catch (e) { console.error('Failed to save staged tasks:', e); }
        }

        function renderStaging() {
            const area = document.getElementById('stagingArea');
            const list = document.getElementById('stagedList');
            document.getElementById('stagedCount').textContent = stagedTasks.length;
            if (stagedTasks.length === 0) { area.classList.remove('has-items'); return; }
            area.classList.add('has-items');
            list.innerHTML = stagedTasks.map((t,i) => `
                <div class="staged-item" data-staged-id="${t.id}">
                    <div class="staged-num">${i+1}</div>
                    <div class="staged-text" onclick="editStagedTask('${t.id}')">${escapeHtml(t.text)}</div>
                    <span class="staged-preset-tag">${t.label}${t.preset === 'document' && t.collection ? ' → ' + t.collection : ''}</span>
                    <button class="staged-remove" onclick="removeStagedTask('${t.id}')">&#10005;</button>
                </div>`).join('');
        }



        // Edit staged task inline
        function editStagedTask(id) {
            const task = stagedTasks.find(t => t.id === id);
            if (!task) return;

            const item = document.querySelector(`.staged-item[data-staged-id="${id}"]`);
            if (!item || item.classList.contains('editing')) return;

            item.classList.add('editing');

            // Create textarea with full text
            const textarea = document.createElement('textarea');
            textarea.className = 'staged-edit-input';
            textarea.value = task.text;

            // Create action buttons
            const actions = document.createElement('div');
            actions.className = 'staged-edit-actions';
            actions.innerHTML = `
                <button class="btn-cancel-edit" onclick="cancelStagedEdit('${id}')">Cancel</button>
                <button class="btn-save-edit" onclick="saveStagedEdit('${id}')">Save</button>
            `;

            // Insert after preset tag
            const presetTag = item.querySelector('.staged-preset-tag');
            presetTag.insertAdjacentElement('afterend', actions);
            presetTag.insertAdjacentElement('afterend', textarea);

            // Focus and select
            textarea.focus();
            textarea.select();

            // Keyboard handlers
            textarea.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') {
                    e.preventDefault();
                    cancelStagedEdit(id);
                } else if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                    e.preventDefault();
                    saveStagedEdit(id);
                }
            });
        }

        async function saveStagedEdit(id) {
            const item = document.querySelector(`.staged-item[data-staged-id="${id}"]`);
            if (!item) return;

            const textarea = item.querySelector('.staged-edit-input');
            if (!textarea) return;

            const newText = textarea.value.trim();
            if (!newText) {
                showToast('Task cannot be empty');
                return;
            }

            // Update in array
            const task = stagedTasks.find(t => t.id === id);
            if (task) {
                task.text = newText;
                await saveStagedToFile();
            }

            // Re-render
            renderStaging();
            showToast('Task updated');
        }

        function cancelStagedEdit(id) {
            // Simply re-render to restore original state
            renderStaging();
        }

        // Apply preset template to text
        function applyTemplate(text, preset, collection) {
            const template = presetTemplates[preset];
            return template ? template(text, collection) : text;
        }

        // Execute
        async function executeNow() {
            const { text, preset, collection } = getInput();
            if (!text) { showToast('Type a task first'); return; }

            const description = applyTemplate(text, preset, collection);
            showToast('Submitting task...');
            const result = await executeTask('claude_assistant', 'assign_task', {
                description: description,
                auto_execute: true
            });

            if (result.status === 'success' || result.status === 'queued') {
                clearInput();
                showToast('Task submitted');
                setTimeout(pollActiveTasks, 500);
            } else {
                showToast('Error: ' + (result.message || 'Unknown'));
            }
        }

        async function executeAll() {
            if (stagedTasks.length === 0) return;

            const { text, preset, label, collection } = getInput();
            if (text) {
                stagedTasks.push({ id: 'stg_' + Date.now(), text, preset, label, collection });
            }

            const tasks = stagedTasks.map(t => ({ description: applyTemplate(t.text, t.preset, t.collection) }));

            showToast('Submitting ' + tasks.length + ' tasks...');
            const result = await executeTask('claude_assistant', 'batch_assign_tasks', {
                tasks,
                auto_execute: true
            });

            if (result.status === 'success') {
                stagedTasks = [];
                clearInput();
                renderStaging();
                showToast(tasks.length + ' tasks queued');
                setTimeout(pollActiveTasks, 500);
            } else {
                showToast('Error: ' + (result.message || 'Unknown'));
            }
        }

        // Polling
        async function pollActiveTasks() {
            const allTasks = [];

            // Fetch results FIRST so we can skip tasks that are already done
            const resultsData = await fetchJson('/data-nocache/' + RESULTS_FILE);

            for (const qf of QUEUE_FILES) {
                const data = await fetchJson('/data-nocache/' + qf);
                if (data && data.tasks) {
                    for (const [taskId, taskData] of Object.entries(data.tasks)) {
                        const status = taskData.status || 'queued';
                        if (status === 'queued' || status === 'in_progress') {
                            // Skip if results already shows this task as done/error/cancelled
                            if (resultsData && resultsData.results && resultsData.results[taskId]) {
                                const resultStatus = resultsData.results[taskId].status;
                                if (resultStatus === 'done' || resultStatus === 'error') continue;
                            }
                            allTasks.push({
                                id: taskId,
                                status: status,
                                description: taskData.description || '',
                                card_title: taskData.card_title || generateCardTitle(taskData.description || taskId),
                                created_at: taskData.created_at,
                                started_at: taskData.started_at,
                                processing_started_at: taskData.processing_started_at,
                                spawned_via: taskData.spawned_via || null
                            });
                        }
                    }
                }
            }

            // Check for tasks that just disappeared (completed)
            const currentIds = new Set(allTasks.map(t => t.id));
            const completingIds = new Set(completingTasks.map(t => t.id));

            for (const prevId of previousActiveIds) {
                if (!currentIds.has(prevId) && !completingIds.has(prevId)) {
                    // Task vanished - check if it completed (resultsData already fetched above)
                    if (resultsData && resultsData.results && resultsData.results[prevId]) {
                        const result = resultsData.results[prevId];
                        // Add to completing tasks with card info
                        completingTasks.push({
                            id: prevId,
                            status: 'completing',
                            card_title: result.card_title || generateCardTitle(result.description || prevId),
                            card_stat: result.card_stat || 'done',
                            execution_time: result.execution_time_seconds
                        });
                        // Remove after 2.5 seconds (shows completion animation)
                        setTimeout(() => {
                            completingTasks = completingTasks.filter(t => t.id !== prevId);
                            renderActive();
                            pollRecentTasks();  // Refresh recent to show the completed task
                        }, 2500);
                    }
                }
            }

            // Update previous IDs for next poll
            previousActiveIds = currentIds;

            // Sort: running first, then by created_at
            allTasks.sort((a, b) => {
                if (a.status === 'in_progress' && b.status !== 'in_progress') return -1;
                if (b.status === 'in_progress' && a.status !== 'in_progress') return 1;
                return (a.created_at || '') > (b.created_at || '') ? 1 : -1;
            });

            // Only re-render if data changed (include completing tasks in hash)
            const newHash = JSON.stringify(allTasks.map(t => t.id + t.status)) + JSON.stringify(completingTasks.map(t => t.id));
            if (newHash !== lastActiveHash) {
                lastActiveHash = newHash;
                activeTasks = allTasks;
                renderActive();
            } else {
                // Just update timers without full re-render
                activeTasks = allTasks;
                startTimers();
            }
        }

        async function pollRecentTasks() {
            const data = await fetchJson('/data-nocache/' + RESULTS_FILE);
            if (!data || !data.results) {
                recentTasks = [];
                renderRecent();
                return;
            }

            const tasks = Object.entries(data.results)
                .map(([taskId, r]) => ({
                    id: taskId,
                    status: r.status,
                    description: r.description || '',
                    card_title: r.card_title || generateCardTitle(r.description || taskId),
                    card_stat: r.card_stat || (r.status === 'done' ? 'completed' : 'error'),
                    completed_at: r.completed_at,
                    execution_time: r.execution_time_seconds,
                    actions_taken: r.actions_taken,
                    output_summary: r.output_summary,
                    errors: r.errors
                }))
                .filter(t => t.status === 'done' || t.status === 'error')
                .sort((a, b) => (b.completed_at || '') > (a.completed_at || '') ? 1 : -1);

            // Only re-render if data changed
            const newTasks = tasks.slice(0, 20);
            const newHash = JSON.stringify(newTasks.map(t => t.id));
            if (newHash !== lastRecentHash) {
                lastRecentHash = newHash;
                recentTasks = newTasks;
                renderRecent();
            }
        }

        // Render
        function renderActive() {
            const section = document.getElementById('activeSection');
            const track = document.getElementById('activeTrack');
            const totalActive = activeTasks.length + completingTasks.length;
            document.getElementById('activeCountBadge').textContent = totalActive;

            if (totalActive === 0) {
                section.classList.add('hidden');
                return;
            }
            section.classList.remove('hidden');

            let queuePos = 0;

            // Render completing tasks first (green checkmark animation)
            const completingHtml = completingTasks.map(t => {
                const timeStr = t.execution_time ? formatDuration(t.execution_time) : '';
                return `<div class="task-card completing" data-card-id="${t.id}" style="animation: pulse-green 0.5s ease-out">
                    <div class="card-top-row">
                        <svg class="card-icon" viewBox="0 0 34 34" fill="none"><rect width="34" height="34" rx="8" fill=CONFIG.colors.rgb_0/><path d="M11 17l4 4 8-8" stroke=CONFIG.colors.color_6 stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
                        <span class="status-badge" style="background:rgba(16,185,129,0.15);color:#10B981">✓ ${timeStr}</span>
                    </div>
                    <div class="card-stat" style="color:#10B981">${escapeHtml(t.card_stat)}</div>
                    <div class="card-title">${escapeHtml(t.card_title)}</div>
                </div>`;
            }).join('');

            // Render active tasks
            const activeHtml = activeTasks.map((t, i) => {
                const isRunning = t.status === 'in_progress';
                if (!isRunning) queuePos++;

                const elapsed = isRunning && t.processing_started_at ? getElapsed(t.processing_started_at) : 0;

                if (isRunning) {
                    return `<div class="task-card running" data-card-id="${t.id}">
                        <div class="card-top-row">
                            <svg class="card-icon" viewBox="0 0 34 34" fill="none"><rect width="34" height="34" rx="8" fill=CONFIG.colors.rgb_2/><path d="M17 11v6l4 2" stroke=CONFIG.colors.color_10 stroke-width="2" stroke-linecap="round"/><circle cx="17" cy="17" r="6.5" stroke=CONFIG.colors.color_10 stroke-width="1.5"/></svg>
                            <span class="status-badge running"><span class="mini-spinner"></span><span class="elapsed-time">${formatTime(elapsed)}</span>${t.spawned_via === 'fallback' ? ' <span style="font-size:9px;background:rgba(228,67,50,0.2);color:#E44332;padding:2px 5px;border-radius:4px;margin-left:4px">FALLBACK</span>' : ''}</span>
                        </div>
                        <div class="card-stat">running</div>
                        <div class="card-title">${escapeHtml(t.card_title)}</div>
                        <button class="card-plus" onclick="openModal('active','${t.id}')">+</button>
                        <div class="progress-bar"><div class="progress-fill"></div></div>
                    </div>`;
                } else {
                    return `<div class="task-card queued" data-card-id="${t.id}">
                        <div class="card-top-row">
                            <svg class="card-icon" viewBox="0 0 34 34" fill="none"><rect width="34" height="34" rx="8" fill=CONFIG.colors.rgb_4/><circle cx="17" cy="17" r="6" stroke=CONFIG.colors.color_5 stroke-width="1.5" stroke-dasharray="3 3"/></svg>
                            <span class="status-badge queued">#${queuePos}</span>
                        </div>
                        <div class="card-stat">queued</div>
                        <div class="card-title">${escapeHtml(t.card_title)}</div>
                        <button class="card-plus" onclick="openModal('active','${t.id}')">+</button>
                    </div>`;
                }
            }).join('');

            track.innerHTML = completingHtml + activeHtml;
            updateRowNav('active', totalActive);
            startTimers();
        }

        function renderRecent() {
            const track = document.getElementById('recentTrack');
            const badge = document.getElementById('recentCountBadge');
            badge.textContent = recentTasks.length;
            document.getElementById('allCount').textContent = recentTasks.length > 0 ? `(${recentTasks.length})` : '';

            if (recentTasks.length === 0) {
                track.innerHTML = '<div class="empty-state"><div class="empty-state-icon">&#128203;</div><div class="empty-state-text">No completed tasks yet</div></div>';
                return;
            }

            track.innerHTML = recentTasks.slice(0, 5).map((t, i) => {
                const color = doneColors[i % doneColors.length];
                const timeStr = t.execution_time ? formatDuration(t.execution_time) : '';
                const isError = t.status === 'error';

                return `<div class="task-card done" data-card-id="${t.id}">
                    <div class="card-top-row">
                        <svg class="card-icon" viewBox="0 0 34 34" fill="none"><rect width="34" height="34" rx="8" fill="${color}1F"/><path d="${isError ? 'M12 12l10 10M22 12l-10 10' : 'M11 17l4 4 8-8'}" stroke="${color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
                        <span class="status-badge done">${isError ? '!' : '&#10003;'} ${timeStr}</span>
                    </div>
                    <div class="card-stat" style="color:${color}">${escapeHtml(t.card_stat)}</div>
                    <div class="card-title">${escapeHtml(t.card_title)}</div>
                    <button class="card-plus" onclick="openModal('recent','${t.id}')">+</button>
                </div>`;
            }).join('');

            updateRowNav('recent', Math.min(recentTasks.length, 5));

            // Also refresh expanded grid if it's showing
            if (isExpanded) {
                renderExpandedGrid();
                document.getElementById('seeAllLink').innerHTML = 'Collapse <span class="count" id="allCount">(' + recentTasks.length + ')</span>';
            }
        }

        // Timers
        function startTimers() {
            // Clear old timers
            Object.keys(runningTimers).forEach(id => {
                if (!activeTasks.find(t => t.id === id && t.status === 'in_progress')) {
                    clearInterval(runningTimers[id]);
                    delete runningTimers[id];
                }
            });

            // Start new timers
            activeTasks.filter(t => t.status === 'in_progress').forEach(t => {
                if (!runningTimers[t.id] && t.processing_started_at) {
                    runningTimers[t.id] = setInterval(() => {
                        const el = document.querySelector(`[data-card-id="${t.id}"] .elapsed-time`);
                        if (el) {
                            el.textContent = formatTime(getElapsed(t.processing_started_at));
                        }
                    }, 1000);
                }
            });
        }

        function getElapsed(isoTime) {
            if (!isoTime) return 0;
            const start = new Date(isoTime);
            return Math.floor((Date.now() - start.getTime()) / 1000);
        }

        function formatTime(secs) {
            const m = Math.floor(secs / 60);
            const s = secs % 60;
            return m > 0 ? `${m}m ${s}s` : `${s}s`;
        }

        function formatDuration(secs) {
            if (secs < 60) return Math.round(secs) + 's';
            const m = Math.floor(secs / 60);
            const s = Math.round(secs % 60);
            return `${m}m ${s}s`;
        }

        // Row navigation
        const rowSlide = { active: 0, recent: 0 };

        function updateRowNav(row, total) {
            const max = Math.max(0, total - 3);
            rowSlide[row] = Math.min(rowSlide[row], max);
            document.getElementById(row + 'Prev').classList.toggle('disabled', rowSlide[row] === 0);
            document.getElementById(row + 'Next').classList.toggle('disabled', rowSlide[row] >= max || total <= 3);
            if (row === 'active') {
                const s = rowSlide[row] + 1, e = Math.min(rowSlide[row] + 3, total);
                document.getElementById('activePage').textContent = total > 3 ? `${s}-${e} of ${total}` : '';
            }
        }

        function slideRow(row, dir) {
            const track = document.getElementById(row + 'Track');
            if (!track.children.length) return;
            const total = track.children.length;
            const max = Math.max(0, total - 3);
            rowSlide[row] = Math.max(0, Math.min(max, rowSlide[row] + dir));
            const w = track.children[0].offsetWidth + 12;
            track.style.transform = `translateX(-${rowSlide[row] * w}px)`;
            updateRowNav(row, total);
        }

        // Modal
        function openModal(source, id) {
            let task;
            if (source === 'active') task = activeTasks.find(t => t.id === id);
            else task = recentTasks.find(t => t.id === id);
            if (!task) return;

            const isActive = source === 'active';
            const badge = document.getElementById('modalBadge');
            const title = document.getElementById('modalTitle');
            const content = document.getElementById('modalContent');

            if (isActive) {
                const isRunning = task.status === 'in_progress';
                badge.textContent = isRunning ? 'Running' : 'Queued';
                badge.className = 'modal-status-badge ' + (isRunning ? 'running' : 'queued');
                title.textContent = task.card_title;
                content.innerHTML = `
                    <div class="modal-section-label">Original task</div>
                    <div class="modal-body">${escapeHtml(task.description)}</div>
                    <div class="modal-divider"></div>
                    <div class="modal-meta" style="justify-content: space-between; align-items: center;">
                        <span>Status: <strong>${task.status}</strong></span>
                        <button onclick="cancelTask('${task.id}')" style="padding: 8px 18px; background: rgba(228,67,50,0.12); color: #E44332; border: 1px solid rgba(228,67,50,0.3); border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; font-family: inherit;">Cancel Task</button>
                    </div>`;
            } else {
                const isError = task.status === 'error';
                badge.textContent = isError ? 'Error' : 'Completed';
                badge.className = 'modal-status-badge ' + (isError ? 'queued' : 'done');
                title.textContent = task.card_title;

                let detail = '';
                if (task.actions_taken) {
                    detail = Array.isArray(task.actions_taken)
                        ? task.actions_taken.join('\n')
                        : task.actions_taken;
                } else if (task.output_summary) {
                    detail = task.output_summary;
                } else if (task.errors) {
                    detail = 'Error: ' + task.errors;
                }

                content.innerHTML = `
                    <div class="modal-section-label">What happened</div>
                    <div class="modal-body">${escapeHtml(detail).replace(/\n/g, '<br>')}</div>
                    <div class="modal-divider"></div>
                    <div class="modal-section-label">Original task</div>
                    <div class="modal-body" style="color:#999">${escapeHtml(task.description)}</div>
                    <div class="modal-divider"></div>
                    <div class="modal-meta">
                        <span>Duration: <strong>${task.execution_time ? formatDuration(task.execution_time) : '-'}</strong></span>
                    </div>`;
            }

            document.getElementById('modalOverlay').classList.add('active');
            document.body.style.overflow = 'hidden';
        }

        function closeModal(e) {
            if (e && e.target !== e.currentTarget) return;
            document.getElementById('modalOverlay').classList.remove('active');
            document.body.style.overflow = '';
        }

        async function cancelTask(taskId) {
            const result = await executeTask('claude_assistant', 'cancel_task', { task_id: taskId });
            if (result.status === 'success') {
                document.getElementById('modalOverlay').classList.remove('active');
                document.body.style.overflow = '';
                showToast('Task cancelled');
                pollActiveTasks();
            } else {
                showToast('Cancel failed: ' + (result.message || 'Unknown'));
            }
        }

        // Toast
        function showToast(msg) {
            const t = document.getElementById('toast');
            t.textContent = msg;
            t.classList.add('show');
            setTimeout(() => t.classList.remove('show'), 2000);
        }

        // Helpers
        function escapeHtml(str) {
            if (!str) return '';
            return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }

        // Keyboard shortcuts
        document.addEventListener('keydown', e => {
            if (e.key === 'Escape') closeModal();
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && !e.shiftKey) {
                e.preventDefault();
                stagedTasks.length > 0 ? executeAll() : executeNow();
            }
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && e.shiftKey) {
                e.preventDefault();
                addToStaging();
            }
        });

        // Poll staged tasks from backend
        let lastStagedHash = '';
        async function pollStagedTasks() {
            const data = await fetchJson('/data-nocache/' + STAGED_FILE);
            if (!data || !Array.isArray(data)) return;

            const newHash = JSON.stringify(data);
            if (newHash === lastStagedHash) return;
            lastStagedHash = newHash;

            // Replace backend tasks, keep local-only tasks
            const localOnly = stagedTasks.filter(t => !t.fromBackend);
            const backendTasks = data.map((t, i) => ({
                id: 'backend_' + t.staged_at,
                text: t.description,
                preset: t.preset || 'custom',
                label: presetLabels[t.preset] || 'Custom',
                fromBackend: true
            }));
            stagedTasks = [...backendTasks, ...localOnly];
            renderStaging();
        }

        // All Results toggle
        function toggleAllResults(e) {
            e.preventDefault();
            const grid = document.getElementById('expandedGrid');
            const link = document.getElementById('seeAllLink');
            const rowWindow = document.querySelector('#recentSection .row-window');

            isExpanded = !isExpanded;

            if (isExpanded) {
                // Hide the 5-card row, show expanded grid
                rowWindow.style.display = 'none';
                grid.style.display = 'grid';
                link.classList.add('expanded');
                link.innerHTML = 'Collapse <span class="count" id="allCount">(' + recentTasks.length + ')</span>';
                renderExpandedGrid();
            } else {
                // Show the 5-card row, hide expanded grid
                rowWindow.style.display = 'block';
                grid.style.display = 'none';
                link.classList.remove('expanded');
                link.innerHTML = 'See all <span class="count" id="allCount">(' + recentTasks.length + ')</span>';
            }
        }

        function renderExpandedGrid() {
            const grid = document.getElementById('expandedGrid');
            if (recentTasks.length === 0) {
                grid.innerHTML = '<div style="grid-column:1/-1;color:#666;padding:20px 0;text-align:center">No completed tasks yet</div>';
                return;
            }

            grid.innerHTML = recentTasks.map((t, i) => {
                const color = doneColors[i % doneColors.length];
                const timeStr = t.execution_time ? formatDuration(t.execution_time) : '';
                const isError = t.status === 'error';

                return `<div class="task-card done" data-card-id="${t.id}">
                    <div class="card-top-row">
                        <svg class="card-icon" viewBox="0 0 34 34" fill="none"><rect width="34" height="34" rx="8" fill="${color}1F"/><path d="${isError ? 'M12 12l10 10M22 12l-10 10' : 'M11 17l4 4 8-8'}" stroke="${color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
                        <span class="status-badge done">${isError ? '!' : '&#10003;'} ${timeStr}</span>
                    </div>
                    <div class="card-stat" style="color:${color}">${escapeHtml(t.card_stat)}</div>
                    <div class="card-title">${escapeHtml(t.card_title)}</div>
                    <button class="card-plus" onclick="openModal('recent','${t.id}')">+</button>
                </div>`;
            }).join('');
        }

        // Init
        async function init() {
            await Promise.all([pollActiveTasks(), pollRecentTasks(), pollStagedTasks()]);

            // Poll active tasks every 500ms (fast enough to catch running state)
            setInterval(pollActiveTasks, 500);
            // Poll recent tasks every 5s
            setInterval(pollRecentTasks, 5000);
            // Poll staged tasks every 3s
            setInterval(pollStagedTasks, 3000);
        }

        init();

        // Global keyboard shortcuts
        const shortcuts = {
            '1': 'task_board.html',
            '2': 'doc_editor.html',
            '3': 'bullet_journal.html',
            '4': 'calendar_dashboard.html',
            '5': 'inbox_dashboard.html',
            '6': 'crm_dashboard.html',
            '0': 'command_center.html'
        };
        document.addEventListener('keydown', (e) => {
            if ((e.metaKey || e.ctrlKey) && shortcuts[e.key]) {
                e.preventDefault();
                window.location.href = shortcuts[e.key];
            }
        });

        // Speech recognition
        let recognition = null;
        let isRecording = false;

        function initSpeechRecognition() {
            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            if (!SpeechRecognition) {
                document.getElementById('micBtn').style.display = 'none';
                return;
            }
            recognition = new SpeechRecognition();
            recognition.continuous = true;
            recognition.interimResults = true;
            recognition.lang = 'en-US';

            recognition.onresult = (event) => {
                const textarea = document.getElementById('taskTextarea');
                let finalTranscript = '';

                for (let i = event.resultIndex; i < event.results.length; i++) {
                    const transcript = event.results[i][0].transcript;
                    if (event.results[i].isFinal) {
                        finalTranscript += transcript;
                    }
                }

                if (finalTranscript) {
                    textarea.value = (textarea.value + ' ' + finalTranscript).trim();
                }
            };

            recognition.onerror = (event) => {
                console.error('Speech error:', event.error);
                stopRecording();
            };

            recognition.onend = () => {
                if (isRecording) {
                    recognition.start();
                }
            };
        }

        function toggleMic() {
            if (isRecording) {
                stopRecording();
            } else {
                startRecording();
            }
        }

        function startRecording() {
            if (!recognition) initSpeechRecognition();
            if (!recognition) return;

            isRecording = true;
            document.getElementById('micBtn').classList.add('recording');
            document.getElementById('micBtn').textContent = '⏹️';
            recognition.start();
        }

        function stopRecording() {
            isRecording = false;
            document.getElementById('micBtn').classList.remove('recording');
            document.getElementById('micBtn').textContent = '🎤';
            if (recognition) recognition.stop();
        }

        // Init speech recognition on load
        initSpeechRecognition();
    

