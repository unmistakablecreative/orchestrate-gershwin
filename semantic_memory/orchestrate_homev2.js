// OrchestrateOS Home v2 - Command Center Logic
// ALL actions queue tasks via claude_assistant.create_task
// Output cards ONLY show when tasks are COMPLETED

let CONFIG = null;
let currentAction = null;
let seenTaskIds = new Set();
// Guest collection filtering - null = show all (Srini's view), string = filter to that collection
const GUEST_COLLECTION = document.documentElement.dataset.guestCollection || null;
// Source string (lowercase) used in context.source for SSE filtering — matches shruti_task_board pattern
const GUEST_SOURCE = GUEST_COLLECTION ? GUEST_COLLECTION.toLowerCase() : null;
// SSE event source for task updates (replaces polling)
let progressAnimationInterval = null;
let currentProgressPercent = 0;
let targetProgressPercent = 0;
let activeTaskCount = 0;

// Icon mapping
const ICONS = {
    doc_icon: '📄',
    slides_icon: '📊',
    mockup_icon: '🎨',
    task_icon: '⚡',
    default: '🔧'
};

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    await loadConfig();
    renderActionIcons();
    setupModal();
    setupSidebar();
    startProgressPolling();
    loadSeenTaskIds();
});

// Load config from JSON file
async function loadConfig() {
    try {
        const response = await fetch('orchestrate_homev2_config.json');
        CONFIG = await response.json();
        applyColors();
    } catch (error) {
        console.error('Failed to load config:', error);
        CONFIG = getDefaultConfig();
    }
}

// Apply colors from config
function applyColors() {
    if (!CONFIG.colors) return;
    const root = document.documentElement;
    if (CONFIG.colors.background) root.style.setProperty('--bg-color', CONFIG.colors.background);
    if (CONFIG.colors.card) root.style.setProperty('--card-color', CONFIG.colors.card);
    if (CONFIG.colors.accent) root.style.setProperty('--accent-color', CONFIG.colors.accent);
    if (CONFIG.colors.progressBar) root.style.setProperty('--progress-gradient', CONFIG.colors.progressBar);
}

// Get default config as fallback
function getDefaultConfig() {
    return {
        actionIcons: [
            { id: 'create_doc', label: 'Create Doc', icon: 'doc_icon', description: 'Create a document', inputField: { placeholder: 'Describe...', submitLabel: 'Create' } },
            { id: 'assign_task', label: 'Assign Task', icon: 'task_icon', description: 'Queue a task', inputField: { placeholder: 'What to do?', submitLabel: 'Assign' } }
        ],
        customActionsEnabled: true,
        progressBar: { enabled: true },
        outputSection: { enabled: true }
    };
}

// Render action icons grid
function renderActionIcons() {
    const grid = document.getElementById('actionGrid');
    if (!grid) return;

    grid.innerHTML = '';

    CONFIG.actionIcons.forEach(action => {
        const card = document.createElement('div');
        card.className = 'action-card';
        card.onclick = () => openModal(action);
        card.innerHTML = `
            <div class="action-icon">${ICONS[action.icon] || ICONS.default}</div>
            <div class="action-label">${action.label}</div>
            <div class="action-description">${action.description}</div>
        `;
        grid.appendChild(card);
    });

    // Add custom action button if enabled
    if (CONFIG.customActionsEnabled) {
        const addBtn = document.createElement('button');
        addBtn.className = 'add-action-btn';
        addBtn.onclick = openCustomActionModal;
        addBtn.innerHTML = `
            <div class="icon">+</div>
            <div>Add Custom Action</div>
        `;
        grid.appendChild(addBtn);
    }
}

// Sidebar functionality
function setupSidebar() {
    // Setup navigation
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', () => {
            const view = item.dataset.view;
            const src = item.dataset.src;
            navigateToView(view, src, item);
        });
    });

    // Keyboard shortcuts for navigation
    document.addEventListener('keydown', (e) => {
        // Only handle if not in input/textarea
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

        const shortcuts = {
            'h': 'home',
            't': 'tasks',
            'd': 'docs',
            'i': 'images',
            'm': 'mockups',
            'b': 'brain'
        };

        const view = shortcuts[e.key.toLowerCase()];
        if (view) {
            const navItem = document.querySelector(`.nav-item[data-view="${view}"]`);
            if (navItem) {
                navItem.click();
            }
        }
    });
}

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    sidebar.classList.toggle('collapsed');
}

function navigateToView(view, src, navItem) {
    // Update active state
    document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
    navItem.classList.add('active');

    const homeView = document.getElementById('homeView');
    const viewFrame = document.getElementById('viewFrame');

    if (view === 'home') {
        // Show home view
        homeView.classList.add('active');
        viewFrame.classList.remove('active');
        viewFrame.src = '';
        // Hide back button when returning to home
        const backBtn = document.getElementById('backToHome');
        if (backBtn) backBtn.style.display = 'none';
    } else if (src) {
        // Load in iframe
        homeView.classList.remove('active');
        viewFrame.classList.add('active');
        viewFrame.src = src;
    }
}

// Load content in iframe (for output cards)
function loadInIframe(url) {
    const homeView = document.getElementById('homeView');
    const viewFrame = document.getElementById('viewFrame');

    // Hide home view, show iframe
    homeView.classList.remove('active');
    viewFrame.classList.add('active');
    viewFrame.src = url;

    // Clear sidebar active state (output is not a nav item)
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
    });

    // Show back button
    showBackButton();
}

// Show floating back button when viewing outputs
function showBackButton() {
    let backBtn = document.getElementById('backToHome');
    if (!backBtn) {
        backBtn = document.createElement('button');
        backBtn.id = 'backToHome';
        backBtn.className = 'back-to-home-btn';
        backBtn.innerHTML = '← Back to Home';
        backBtn.onclick = () => {
            document.querySelector('.nav-item[data-view="home"]').click();
        };
        document.body.appendChild(backBtn);
    }
    backBtn.style.display = 'block';
}

// Modal system
function setupModal() {
    const overlay = document.getElementById('modalOverlay');
    if (!overlay) return;

    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeModal();
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeModal();
    });
}

function openModal(action) {
    currentAction = action;
    const overlay = document.getElementById('modalOverlay');
    const modalIcon = document.getElementById('modalIcon');
    const modalTitle = document.getElementById('modalTitle');
    const modalInput = document.getElementById('modalInput');
    const submitBtn = document.getElementById('submitBtn');
    const variationsField = document.getElementById('variationsField');
    const variationsInput = document.getElementById('variationsInput');

    modalIcon.textContent = ICONS[action.icon] || ICONS.default;
    modalTitle.textContent = action.label;
    modalInput.placeholder = action.inputField.placeholder;
    modalInput.value = '';
    submitBtn.textContent = action.inputField.submitLabel;
    submitBtn.disabled = false;

    // Show variations field for mockup actions
    if (action.showVariations) {
        variationsField.style.display = 'block';
        variationsInput.value = action.defaultVariations || 3;
    } else {
        variationsField.style.display = 'none';
    }

    overlay.classList.add('active');
    modalInput.focus();
}

function closeModal() {
    const overlay = document.getElementById('modalOverlay');
    overlay.classList.remove('active');
    currentAction = null;

    // Hide variations field
    const variationsField = document.getElementById('variationsField');
    if (variationsField) variationsField.style.display = 'none';
}

// Execute action - ALL actions queue via claude_assistant.create_task
async function executeAction() {
    if (!currentAction) return;

    const input = document.getElementById('modalInput').value.trim();
    if (!input) return;

    const submitBtn = document.getElementById('submitBtn');
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<div class="spinner"></div>';

    try {
        // Build task description based on action type
        let taskDescription = buildTaskDescription(currentAction, input);

        // GUEST MODE: Force collection via description instruction (matches shruti_task_board pattern)
        if (GUEST_COLLECTION) {
            taskDescription += `\n\nIMPORTANT: Any documents created in this task must use the "${GUEST_COLLECTION}" collection.`;
        }

        // Queue via claude_assistant.create_task - ALWAYS
        const payload = {
            tool_name: 'claude_assistant',
            action: 'assign_task',
            params: {
                description: taskDescription,
                priority: 'normal',
                ...(GUEST_SOURCE && { context: { source: GUEST_SOURCE } })
            },
            ...(GUEST_COLLECTION && { sandbox: GUEST_COLLECTION.toLowerCase() })
        };

        const response = await fetch('https://app.orchestrateos.io/execute_task', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const result = await response.json();

        if (result.status === 'success') {
            // Task queued successfully - do NOT add output card yet
            // Output card will appear when polling detects completion
            showQueuedFeedback();
        } else {
            submitBtn.textContent = 'Error - Retry';
            submitBtn.disabled = false;
            return;
        }

        closeModal();
    } catch (error) {
        console.error('Action failed:', error);
        submitBtn.textContent = 'Error - Retry';
        submitBtn.disabled = false;
    }
}

// Build task description for the autonomous agent
function buildTaskDescription(action, input) {
    const actionId = action.id;

    if (actionId === 'create_doc') {
        return `Create a document about: ${input}`;
    } else if (actionId === 'design_slides') {
        return `Design a slide deck titled "${input}". Use "${input}" as the deck title when calling slide_designer_premium.create_deck.`;
    } else if (actionId === 'design_mockup') {
        const variationsInput = document.getElementById('variationsInput');
        const variations = parseInt(variationsInput?.value) || 3;
        return `Generate ${variations} mockup variations: ${input}`;
    } else if (actionId === 'assign_task') {
        // Generic task - just use the input directly
        return input;
    } else {
        // Fallback for custom actions
        return `${action.label}: ${input}`;
    }
}

// Show visual feedback that task was queued - start progress at 5%
function showQueuedFeedback() {
    const fill = document.getElementById('progressFill');
    if (fill) {
        // Reset to starting state
        currentProgressPercent = 5;
        fill.style.width = '5%';
        fill.classList.add('animating');

        // Yellow pulse briefly then start green progress
        fill.style.background = 'linear-gradient(90deg, #eab308, #ca8a04)';
        fill.style.boxShadow = '0 0 20px rgba(234, 179, 8, 0.5)';
        setTimeout(() => {
            fill.style.background = '';
            fill.style.boxShadow = '';
            // Start progress animation
            targetProgressPercent = 85;
            startProgressAnimation();
        }, 500);
    }

    // Update count immediately
    const count = document.getElementById('progressCount');
    if (count) {
        count.textContent = '1 task in progress';
    }
}

// SSE-based task updates - no polling, server pushes updates
let eventSource = null;

function startProgressPolling() {
    if (!CONFIG.progressBar?.enabled) return;

    updateProgressDisplay();
    connectSSE();
}

function connectSSE() {
    // Close any existing connection
    if (eventSource) {
        eventSource.close();
    }

    // Connect to SSE endpoint
    eventSource = new EventSource('https://app.orchestrateos.io/api/task-updates');

    eventSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);

            if (data.type === 'heartbeat') {
                // Heartbeat - connection is alive, no action needed
                return;
            }

            if (data.type === 'task_update' && data.tasks) {
                handleTaskUpdate(data.tasks);
            }
        } catch (error) {
            console.error('SSE message parse error:', error);
        }
    };

    eventSource.onerror = (error) => {
        console.error('SSE connection error:', error);
        // Reconnect after 5 seconds
        eventSource.close();
        setTimeout(connectSSE, 5000);
    };
}

function handleTaskUpdate(tasks) {
    const activeTasks = tasks.active || [];
    let recentTasks = tasks.recent || [];

    // Filter by guest source if set (guest pages only see their own outputs)
    if (GUEST_SOURCE) {
        recentTasks = recentTasks.filter(t =>
            t.source === GUEST_SOURCE
        );
    }

    const inProgressCount = activeTasks.length;
    const completedTasks = recentTasks.filter(t => t.status === 'done');
    const total = inProgressCount + completedTasks.length;
    const completed = completedTasks.length;

    // Update progress bar
    updateProgressBar(completed, total, inProgressCount > 0, inProgressCount);

    // Add output cards for newly completed tasks (limit to 5 most recent)
    // Only show cards for tasks with actual output links (docs, slides, mockups)
    const recentCompleted = completedTasks.slice(0, 5);
    recentCompleted.forEach(async task => {
        if (!seenTaskIds.has(task.task_id)) {
            seenTaskIds.add(task.task_id);
            saveSeenTaskIds();

            let outputLink = extractOutputLink(task);

            // Resolve deck_id lookup to actual file path
            if (outputLink && outputLink.startsWith('_deck_id_lookup_:')) {
                const deckId = outputLink.replace('_deck_id_lookup_:', '');
                try {
                    const idxResp = await fetch('https://app.orchestrateos.io/execute_task', {
                        method: 'POST', headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({tool_name: 'files', action: 'read_file_text', params: {filename: 'data/slide_decks/deck_index.json'}})
                    });
                    const idxResult = await idxResp.json();
                    const decks = Array.isArray(idxResult.data) ? idxResult.data : [];
                    const deck = decks.find(d => d.id === deckId);
                    if (deck?.file) outputLink = `slides/${deck.file}`;
                    else outputLink = null;
                } catch(e) { outputLink = null; }
            }

            // Only create cards for tasks with actual outputs (not code edits, generic tasks)
            if (outputLink) {
                // Fetch actual output title (doc title, deck title, mockup title)
                const title = await fetchOutputTitle(task, outputLink);
                addOutputCard({
                    title: title,
                    icon: getIconFromDescription(task.description),
                    link: outputLink,
                    type: 'visual',
                    timestamp: task.completed_at || new Date().toISOString()
                });
            }
        }
    });
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (eventSource) {
        eventSource.close();
    }
});

// Determine output type from task description
function determineOutputTypeFromDescription(description) {
    if (!description) return 'silent';
    const desc = description.toLowerCase();

    if (desc.includes('document') || desc.includes('doc')) return 'visual';
    if (desc.includes('slide') || desc.includes('deck')) return 'visual';
    if (desc.includes('mockup') || desc.includes('design')) return 'visual';
    if (desc.includes('image') || desc.includes('graphic')) return 'visual';

    return 'navigation';
}

// Get icon from task description
function getIconFromDescription(description) {
    if (!description) return 'task_icon';
    const desc = description.toLowerCase();

    if (desc.includes('document') || desc.includes('doc')) return 'doc_icon';
    if (desc.includes('slide') || desc.includes('deck')) return 'slides_icon';
    if (desc.includes('mockup') || desc.includes('design')) return 'mockup_icon';

    return 'task_icon';
}

function updateProgressBar(completed, total, hasActiveTask = false, newActiveCount = 0) {
    const fill = document.getElementById('progressFill');
    const count = document.getElementById('progressCount');

    if (fill) {
        if (hasActiveTask) {
            fill.classList.add('animating');

            // If new task started, reset to 5%
            if (newActiveCount > activeTaskCount) {
                currentProgressPercent = 5;
                fill.style.width = '5%';
            }
            activeTaskCount = newActiveCount;

            // Target is 85% max while in progress (never looks complete until done)
            targetProgressPercent = 85;

            // Start gradual progress animation if not already running
            if (!progressAnimationInterval) {
                startProgressAnimation();
            }
        } else {
            // No active tasks - stop animation and show final state
            stopProgressAnimation();
            fill.classList.remove('animating');
            activeTaskCount = 0;

            if (total > 0) {
                const percent = Math.round((completed / total) * 100);
                fill.style.width = `${percent}%`;
                currentProgressPercent = percent;
            } else {
                fill.style.width = '0%';
                currentProgressPercent = 0;
            }
        }
    }

    if (count) {
        if (hasActiveTask) {
            const inProgress = newActiveCount;
            count.textContent = `${inProgress} task${inProgress !== 1 ? 's' : ''} in progress`;
        } else {
            count.textContent = `${completed} / ${total} tasks`;
        }
    }
}

// Gradually animate progress while task is running
function startProgressAnimation() {
    if (progressAnimationInterval) return;

    progressAnimationInterval = setInterval(() => {
        const fill = document.getElementById('progressFill');
        if (!fill) return;

        // Gradually increase towards target, slowing down as we approach
        if (currentProgressPercent < targetProgressPercent) {
            // Faster at start, slower near end (easing)
            const remaining = targetProgressPercent - currentProgressPercent;
            const increment = Math.max(0.5, remaining * 0.08);
            currentProgressPercent = Math.min(currentProgressPercent + increment, targetProgressPercent);
            fill.style.width = `${currentProgressPercent}%`;
        }
    }, 200);
}

function stopProgressAnimation() {
    if (progressAnimationInterval) {
        clearInterval(progressAnimationInterval);
        progressAnimationInterval = null;
    }
}

function updateProgressDisplay() {
    updateProgressBar(0, 0);
    // Initial state - SSE will push updates
}

// Output cards - ONLY for completed tasks
function addOutputCard(output) {
    const grid = document.getElementById('outputGrid');
    const emptyState = document.getElementById('emptyState');

    if (emptyState) emptyState.style.display = 'none';

    const card = document.createElement('div');
    card.className = 'output-card';
    card.style.cursor = 'pointer';
    card.onclick = (e) => {
        e.preventDefault();
        if (output.link) {
            loadInIframe(output.link);
        }
    };

    const timeAgo = formatTimeAgo(output.timestamp);

    card.innerHTML = `
        <div class="output-icon">${ICONS[output.icon] || ICONS.default}</div>
        <div class="output-info">
            <div class="output-card-title">${output.title}</div>
            <div class="output-meta">${timeAgo}</div>
        </div>
        <div class="output-arrow">→</div>
    `;

    // Insert at top
    grid.insertBefore(card, grid.firstChild);

    // Limit to 5 most recent outputs
    const outputCards = grid.querySelectorAll('.output-card');
    if (outputCards.length > 5) {
        for (let i = 5; i < outputCards.length; i++) {
            outputCards[i].remove();
        }
    }
}

// Fetch actual output title based on output type
async function fetchOutputTitle(task, outputLink) {
    // card_title set at completion time — use it directly if available
    if (task.card_title) return task.card_title;
    // actions_taken can be array or string - normalize to string for regex matching
    const actionsTaken = Array.isArray(task.actions_taken)
        ? task.actions_taken.join(' ')
        : (task.actions_taken || '');

    try {
        // Check for doc_id - fetch from docs tool
        const docMatch = actionsTaken.match(/doc_[a-f0-9]{8}/);
        if (docMatch) {
            const response = await fetch('https://app.orchestrateos.io/execute_task', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    tool_name: 'docs',
                    action: 'read_doc',
                    params: { doc_id: docMatch[0] }
                })
            });
            const result = await response.json();
            if (result.status === 'success' && result.doc?.title) {
                return result.doc.title;
            }
        }

        // Check for slide deck - read from deck_index.json
        // First try matching from actions_taken, then fall back to outputLink parameter
        let slideFilename = null;
        const slidePathMatch = actionsTaken.match(/(?:semantic_memory\/)?slides\/([^\s\]\"]+\.html)/);
        if (slidePathMatch) {
            slideFilename = slidePathMatch[1];
        } else if (outputLink && outputLink.includes('slides/')) {
            // Extract filename from outputLink (e.g., "slides/my_deck.html" -> "my_deck.html")
            const match = outputLink.match(/slides\/([^\/]+\.html)/);
            if (match) slideFilename = match[1];
        }

        if (slideFilename) {
            const response = await fetch('https://app.orchestrateos.io/execute_task', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    tool_name: 'files',
                    action: 'read_file_text',
                    params: { filename: 'data/slide_decks/deck_index.json' }
                })
            });
            const result = await response.json();
            if (result.status === 'success' && result.content) {
                const decks = JSON.parse(result.content);
                const deck = decks.find(d => d.file === slideFilename || d.filename === slideFilename);
                if (deck?.title) return deck.title;
            }
        }

        // Check for mockup - fetch HTML and extract <title> tag directly
        // This is idiot-proof: no dependency on agents logging correctly
        if (outputLink && outputLink.includes('mockups/')) {
            try {
                const mockupUrl = outputLink.startsWith('http') ? outputLink : `mockups/${outputLink.split('mockups/').pop()}`;
                const htmlResponse = await fetch(mockupUrl);
                if (htmlResponse.ok) {
                    const html = await htmlResponse.text();
                    const titleMatch = html.match(/<title>([^<]+)<\/title>/i);
                    if (titleMatch && titleMatch[1] && titleMatch[1].trim()) {
                        return titleMatch[1].trim();
                    }
                }
            } catch (e) {
                console.warn('Failed to fetch mockup HTML for title:', e);
            }
        }
    } catch (error) {
        console.error('Failed to fetch output title:', error);
    }

    // Fallback to task description
    return task.description?.slice(0, 60) || 'Completed Task';
}

// Extract actual output link from task result
function extractOutputLink(task) {
    // actions_taken can be array or string - normalize to string for regex matching
    const actionsTaken = Array.isArray(task.actions_taken)
        ? task.actions_taken.join(' ')
        : (task.actions_taken || '');

    // Look for doc_id patterns (e.g., doc_abc123)
    const docMatch = actionsTaken.match(/doc_[a-f0-9]{8}/);
    if (docMatch) {
        // Use ?id= parameter (doc_editor.js expects 'id', not 'doc')
        return `doc_editor_v4.html?id=${docMatch[0]}`;
    }

    // Look for rendered slide deck paths in semantic_memory/slides/
    // Pattern: semantic_memory/slides/some_deck.html or slides/some_deck.html
    const slidePathMatch = actionsTaken.match(/(?:semantic_memory\/)?slides\/([^\s\]\"]+\.html)/);
    if (slidePathMatch) {
        return `slides/${slidePathMatch[1]}`;
    }

    // Look for deck_id pattern — agent logged deck_id but not full path
    const deckIdMatch = actionsTaken.match(/deck_[a-f0-9]{8}/);
    if (deckIdMatch) {
        return `_deck_id_lookup_:${deckIdMatch[0]}`;
    }

    // Look for mockup paths - link directly to the mockup file
    // Pattern 1: mockups/filename.html (full path)
    const mockupMatch = actionsTaken.match(/mockups\/([^\s\]\"]+\.html)/);
    if (mockupMatch) {
        return `mockups/${mockupMatch[1]}`;
    }
    // Pattern 2: "filename.html mockup" (common agent output format)
    const mockupAltMatch = actionsTaken.match(/([a-z0-9_-]+\.html)\s+mockup/i);
    if (mockupAltMatch) {
        return `mockups/${mockupAltMatch[1]}`;
    }
    // Pattern 3: If task description mentions mockup and actions contain a standalone HTML filename
    // This catches agents that write "Created filename.html" without full path
    const isMockupTask = (task.description || '').toLowerCase().includes('mockup');
    if (isMockupTask) {
        // Match HTML filenames that are NOT doc_editor, slide, or other system files
        const htmlFileMatch = actionsTaken.match(/\b([a-z][a-z0-9_-]+(?:_landing|_mockup|_page|_hero|_site)?\.html)\b/i);
        if (htmlFileMatch && !htmlFileMatch[1].includes('doc_editor') && !htmlFileMatch[1].includes('gallery')) {
            return `mockups/${htmlFileMatch[1]}`;
        }
    }

    // Check description for doc_id references
    const descDocMatch = (task.description || '').match(/doc_[a-f0-9]{8}/);
    if (descDocMatch) {
        return `doc_editor_v4.html?id=${descDocMatch[0]}`;
    }

    return null;
}

// Persist seen task IDs to avoid duplicates
function loadSeenTaskIds() {
    try {
        const saved = localStorage.getItem('orchestrate_seen_tasks');
        if (saved) {
            const ids = JSON.parse(saved);
            seenTaskIds = new Set(ids);
        }
    } catch (error) {
        console.error('Failed to load seen task IDs:', error);
    }
}

function saveSeenTaskIds() {
    try {
        const ids = Array.from(seenTaskIds).slice(-100); // Keep last 100
        localStorage.setItem('orchestrate_seen_tasks', JSON.stringify(ids));
    } catch (error) {
        console.error('Failed to save seen task IDs:', error);
    }
}

function clearOutputs() {
    const grid = document.getElementById('outputGrid');
    const emptyState = document.getElementById('emptyState');
    grid.innerHTML = '';
    if (emptyState) {
        grid.appendChild(emptyState);
        emptyState.style.display = 'block';
    }
    // Also clear seen tasks so they can reappear
    seenTaskIds.clear();
    localStorage.removeItem('orchestrate_seen_tasks');
}

// Custom action modal
function openCustomActionModal() {
    const overlay = document.getElementById('customActionOverlay');
    if (overlay) overlay.classList.add('active');
}

function closeCustomActionModal() {
    const overlay = document.getElementById('customActionOverlay');
    if (overlay) overlay.classList.remove('active');
}

async function saveCustomAction() {
    const label = document.getElementById('customLabel').value.trim();
    const placeholder = document.getElementById('customPlaceholder').value.trim();

    if (!label) return;

    // Custom actions also queue via create_task, not direct execution
    const newAction = {
        id: `custom_${Date.now()}`,
        label: label,
        icon: 'default',
        description: `Custom action: ${label}`,
        inputField: {
            placeholder: placeholder || 'Enter input...',
            submitLabel: 'Execute'
        }
    };

    CONFIG.actionIcons.push(newAction);
    renderActionIcons();
    closeCustomActionModal();

    // Persist to server
    try {
        await fetch('https://app.orchestrateos.io/execute_task', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                tool_name: 'files',
                action: 'write_json',
                params: {
                    filename: 'semantic_memory/orchestrate_homev2_config.json',
                    data: CONFIG
                }
            })
        });
    } catch (error) {
        console.error('Failed to persist custom action:', error);
    }
}

// Utility functions
function formatTimeAgo(timestamp) {
    if (!timestamp) return 'Just now';

    const now = new Date();
    const then = new Date(timestamp);
    const diff = Math.floor((now - then) / 1000);

    if (diff < 60) return 'Just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
}

// Keyboard shortcuts for action icons
document.addEventListener('keydown', (e) => {
    // Cmd/Ctrl + number to trigger action
    if ((e.metaKey || e.ctrlKey) && e.key >= '1' && e.key <= '4') {
        const index = parseInt(e.key) - 1;
        if (CONFIG.actionIcons[index]) {
            e.preventDefault();
            openModal(CONFIG.actionIcons[index]);
        }
    }
});
