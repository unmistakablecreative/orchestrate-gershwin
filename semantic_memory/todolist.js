
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


        let tasks = [];
        let currentFilter = 'pending';
        const API = window.location.origin;

        document.addEventListener('DOMContentLoaded', loadTasks);

        async function loadTasks() {
            try {
                const showCompleted = currentFilter === 'all';
                const res = await fetch(`${API}/execute_task`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        tool_name: 'todolist',
                        action: 'list_tasks',
                        params: {show_completed: showCompleted}
                    })
                });
                const data = await res.json();
                if (data.status === 'success') {
                    tasks = data.tasks || [];
                    renderTasks();
                    updateStats();
                }
            } catch (e) {
                console.error('Failed to load tasks:', e);
                showToast('Failed to load tasks', 'error');
            }
        }

        async function addTask(e) {
            e.preventDefault();
            const input = document.getElementById('taskInput');
            const content = input.value.trim();
            if (!content) return;

            input.disabled = true;
            try {
                const res = await fetch(`${API}/execute_task`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        tool_name: 'todolist',
                        action: 'add_task',
                        params: {content}
                    })
                });
                const data = await res.json();
                if (data.status === 'success') {
                    input.value = '';
                    showToast('Task added', 'success');
                    await loadTasks();
                } else {
                    showToast(data.message || 'Failed to add task', 'error');
                }
            } catch (e) {
                showToast('Failed to add task', 'error');
            }
            input.disabled = false;
            input.focus();
        }

        async function toggleComplete(id, currentState) {
            if (currentState) return; // Already completed, don't uncomplete

            try {
                const res = await fetch(`${API}/execute_task`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        tool_name: 'todolist',
                        action: 'complete_task',
                        params: {id}
                    })
                });
                const data = await res.json();
                if (data.status === 'success') {
                    showToast('Task completed', 'success');
                    await loadTasks();
                }
            } catch (e) {
                showToast('Failed to complete task', 'error');
            }
        }

        async function deleteTask(id) {
            try {
                const res = await fetch(`${API}/execute_task`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        tool_name: 'todolist',
                        action: 'delete_task',
                        params: {id}
                    })
                });
                const data = await res.json();
                if (data.status === 'success') {
                    showToast('Task deleted', 'success');
                    await loadTasks();
                }
            } catch (e) {
                showToast('Failed to delete task', 'error');
            }
        }

        function setFilter(filter) {
            currentFilter = filter;
            document.querySelectorAll('.filter button').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.filter === filter);
            });
            loadTasks();
        }

        function renderTasks() {
            const list = document.getElementById('taskList');

            if (!tasks.length) {
                list.innerHTML = `
                    <div class="empty-state">
                        <div class="icon">&#10003;</div>
                        <div>${currentFilter === 'pending' ? 'All done! No pending tasks.' : 'No tasks yet. Add one above.'}</div>
                    </div>
                `;
                return;
            }

            list.innerHTML = tasks.map(task => {
                const date = new Date(task.created_at).toLocaleDateString('en-US', {
                    month: 'short', day: 'numeric'
                });
                return `
                <div class="task-item ${task.completed ? 'completed' : ''}">
                    <div class="checkbox ${task.completed ? 'checked' : ''}" onclick="toggleComplete(${task.id}, ${task.completed})"></div>
                    <div class="task-content">${escapeHtml(task.content)}</div>
                    <div class="task-date">${date}</div>
                    <button class="delete-btn" onclick="deleteTask(${task.id})">Delete</button>
                </div>
                `;
            }).join('');
        }

        async function updateStats() {
            // Fetch all tasks to get accurate stats
            try {
                const res = await fetch(`${API}/execute_task`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        tool_name: 'todolist',
                        action: 'list_tasks',
                        params: {show_completed: true}
                    })
                });
                const data = await res.json();
                if (data.status === 'success') {
                    const allTasks = data.tasks || [];
                    const pending = allTasks.filter(t => !t.completed).length;
                    const done = allTasks.filter(t => t.completed).length;
                    document.getElementById('pendingCount').textContent = pending;
                    document.getElementById('doneCount').textContent = done;
                }
            } catch (e) {
                console.error('Failed to update stats:', e);
            }
        }

        function escapeHtml(str) {
            const div = document.createElement('div');
            div.textContent = str;
            return div.innerHTML;
        }

        function showToast(msg, type = 'info') {
            const toast = document.getElementById('toast');
            toast.textContent = msg;
            toast.className = 'toast show ' + type;
            setTimeout(() => toast.classList.remove('show'), 3000);
        }
    

