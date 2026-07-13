// Gershwin Home v2 - Action Grid Logic
// Queues tasks via claude_assistant.assign_task to localhost:5004
// Modal system: click action card -> modal -> submit -> task queued

const GERSHWIN_API = '/execute_task';

const GERSHWIN_ACTIONS = [
    {
        id: 'create_doc',
        label: 'Create Doc',
        icon: '📄',
        description: 'Create a document about anything',
        placeholder: 'Describe what you want to write...',
        submitLabel: 'Create'
    },
    {
        id: 'design_slides',
        label: 'Design Slides',
        icon: '📊',
        description: 'Design a slide deck',
        placeholder: "What's the deck about?",
        submitLabel: 'Design'
    },
    {
        id: 'design_mockup',
        label: 'Design Mockups',
        icon: '🎨',
        description: 'Generate multiple mockup variations',
        placeholder: 'Describe the page you want to design...',
        submitLabel: 'Generate',
        showVariations: true
    },
    {
        id: 'assign_task',
        label: 'Assign Task',
        icon: '⚡',
        description: 'Queue a task for autonomous execution',
        placeholder: 'What do you want done?',
        submitLabel: 'Assign'
    }
];

let gershwinCurrentAction = null;
let gershwinProgressInterval = null;
let gershwinCurrentProgress = 0;
let gershwinTargetProgress = 0;

function initGershwinV2() {
    renderGershwinActionGrid();
    setupGershwinModal();
    setupGershwinProgressPolling();
}

function renderGershwinActionGrid() {
    const grid = document.getElementById('gershwin-action-grid');
    if (!grid) return;

    grid.innerHTML = GERSHWIN_ACTIONS.map(action => `
        <div class="gershwin-action-card" onclick="openGershwinModal('${action.id}')">
            <div class="gershwin-action-icon">${action.icon}</div>
            <div class="gershwin-action-label">${action.label}</div>
            <div class="gershwin-action-desc">${action.description}</div>
        </div>
    `).join('') + `
        <div class="gershwin-action-card gershwin-add-card" onclick="openGershwinCustomModal()">
            <div class="gershwin-action-icon">+</div>
            <div class="gershwin-action-label">Add Action</div>
        </div>
    `;
}

function setupGershwinModal() {
    const overlay = document.getElementById('gershwin-modal-overlay');
    if (!overlay) return;
    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) closeGershwinModal();
    });
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') closeGershwinModal();
    });
}

function openGershwinModal(actionId) {
    const action = GERSHWIN_ACTIONS.find(a => a.id === actionId);
    if (!action) return;
    gershwinCurrentAction = action;

    document.getElementById('gershwin-modal-icon').textContent = action.icon;
    document.getElementById('gershwin-modal-title').textContent = action.label;
    document.getElementById('gershwin-modal-input').placeholder = action.placeholder;
    document.getElementById('gershwin-modal-input').value = '';
    document.getElementById('gershwin-modal-submit').textContent = action.submitLabel;
    document.getElementById('gershwin-modal-submit').disabled = false;

    const variationsRow = document.getElementById('gershwin-variations-row');
    if (variationsRow) {
        variationsRow.style.display = action.showVariations ? 'block' : 'none';
    }

    document.getElementById('gershwin-modal-overlay').classList.add('active');
    document.getElementById('gershwin-modal-input').focus();
}

function closeGershwinModal() {
    const overlay = document.getElementById('gershwin-modal-overlay');
    if (overlay) overlay.classList.remove('active');
    gershwinCurrentAction = null;
}

function openGershwinCustomModal() {
    // For now just open assign_task modal
    openGershwinModal('assign_task');
}

async function submitGershwinAction() {
    if (!gershwinCurrentAction) return;
    const input = document.getElementById('gershwin-modal-input').value.trim();
    if (!input) return;

    const submitBtn = document.getElementById('gershwin-modal-submit');
    submitBtn.disabled = true;
    submitBtn.textContent = '...';

    try {
        const description = buildGershwinTaskDescription(gershwinCurrentAction, input);

        const response = await fetch(GERSHWIN_API, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                tool_name: 'claude_assistant',
                action: 'assign_task',
                params: { description: description }
            })
        });

        const result = await response.json();

        if (result.status === 'success' || result.status === 'queued') {
            closeGershwinModal();
            gershwinShowQueuedFeedback();
        } else {
            submitBtn.textContent = 'Error — Retry';
            submitBtn.disabled = false;
        }
    } catch (err) {
        console.error('Gershwin action failed:', err);
        submitBtn.textContent = 'Error — Retry';
        submitBtn.disabled = false;
    }
}

function buildGershwinTaskDescription(action, input) {
    if (action.id === 'create_doc') {
        return `Create a document about: ${input}`;
    } else if (action.id === 'design_slides') {
        return `Design a slide deck titled "${input}". Use "${input}" as the deck title when calling slide_designer_premium.create_deck.`;
    } else if (action.id === 'design_mockup') {
        const variationsInput = document.getElementById('gershwin-variations-input');
        const variations = parseInt(variationsInput?.value) || 3;
        return `Generate ${variations} mockup variations: ${input}`;
    } else if (action.id === 'assign_task') {
        return input;
    }
    return `${action.label}: ${input}`;
}

function gershwinShowQueuedFeedback() {
    const fill = document.getElementById('gershwin-progress-fill');
    const count = document.getElementById('gershwin-progress-count');
    if (fill) {
        gershwinCurrentProgress = 5;
        fill.style.width = '5%';
        gershwinTargetProgress = 85;
        startGershwinProgressAnimation();
    }
    if (count) count.textContent = '1 task in progress';
}

function setupGershwinProgressPolling() {
    updateGershwinProgress();
    setInterval(updateGershwinProgress, 5000);
}

async function updateGershwinProgress() {
    try {
        const resp = await fetch('/task_status');
        if (!resp.ok) return;
        const data = await resp.json();
        if (!data || data.status === 'error') return;

        const active = (data.active_tasks || []).length;
        const recent = (data.recent_results || []).filter(t => t.status === 'done' || t.status === 'error');
        const total = active + recent.length;
        const done = recent.length;

        const fill = document.getElementById('gershwin-progress-fill');
        const count = document.getElementById('gershwin-progress-count');

        if (fill) {
            if (active > 0) {
                fill.classList.add('animating');
                gershwinTargetProgress = 85;
                startGershwinProgressAnimation();
            } else {
                stopGershwinProgressAnimation();
                fill.classList.remove('animating');
                fill.style.width = total > 0 ? `${Math.round((done / total) * 100)}%` : '0%';
            }
        }
        if (count) {
            count.textContent = active > 0 ? `${active} task${active !== 1 ? 's' : ''} in progress` : `${done} / ${total} tasks`;
        }
    } catch (e) {}
}

function startGershwinProgressAnimation() {
    if (gershwinProgressInterval) return;
    gershwinProgressInterval = setInterval(() => {
        const fill = document.getElementById('gershwin-progress-fill');
        if (!fill) return;
        if (gershwinCurrentProgress < gershwinTargetProgress) {
            const remaining = gershwinTargetProgress - gershwinCurrentProgress;
            gershwinCurrentProgress = Math.min(gershwinCurrentProgress + Math.max(0.5, remaining * 0.08), gershwinTargetProgress);
            fill.style.width = `${gershwinCurrentProgress}%`;
        }
    }, 200);
}

function stopGershwinProgressAnimation() {
    if (gershwinProgressInterval) {
        clearInterval(gershwinProgressInterval);
        gershwinProgressInterval = null;
    }
}
