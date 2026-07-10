// Config-driven architecture - load configuration
let CONFIG = {};
async function loadConfig() {
    try {
        const response = await fetch('./orchestrate_home_config.json');
        CONFIG = await response.json();
        console.log('[Config] Loaded:', Object.keys(CONFIG));
        // Render sidebar from config after loading
        if (CONFIG.sidebar && CONFIG.icons) {
            renderSidebar();
        }
    } catch (e) {
        console.warn('[Config] Failed to load, using defaults:', e);
        CONFIG = {};
    }
}

// Render sidebar from config
function renderSidebar() {
    const navSection = document.querySelector('.nav-section');
    if (!navSection || !CONFIG.sidebar) return;

    // Clear existing nav items (but keep shortcuts button and custom links section)
    const shortcutsBtn = navSection.querySelector('.shortcuts-btn');
    const addLinkBtn = navSection.querySelector('#add-link-btn');
    const customLinksContainer = navSection.querySelector('#custom-links-container');

    // Build new nav items HTML
    let navHtml = '';
    CONFIG.sidebar.forEach((item, idx) => {
        const icon = CONFIG.icons[item.icon] || '';
        const shortcutAttr = item.shortcut ? `data-shortcut="${item.shortcut}"` : '';
        const srcAttr = item.src ? `data-src="${item.src}"` : '';
        const unlockAttr = item.requires_unlock ? `data-requires-unlock="${item.requires_unlock}"` : '';
        const activeClass = idx === 0 ? ' active' : '';

        navHtml += `
            <div class="nav-item${activeClass}" data-view="${item.id}" ${srcAttr} ${shortcutAttr} ${unlockAttr}>
                ${icon}
                <span>${item.label}</span>
            </div>
        `;

        if (item.divider_after) {
            navHtml += '<div class="nav-divider"></div>';
        }
    });

    // Add final divider before custom links
    navHtml += '<div class="nav-divider"></div>';

    // Rebuild nav section
    navSection.innerHTML = navHtml;

    // Re-add custom links container
    const newCustomLinksContainer = document.createElement('div');
    newCustomLinksContainer.id = 'custom-links-container';
    navSection.appendChild(newCustomLinksContainer);

    // Re-add "Add Link" button
    navSection.innerHTML += `
        <div class="nav-item add-link-btn" id="add-link-btn" title="Add custom link">
            <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/>
                <line x1="12" y1="8" x2="12" y2="16"/>
                <line x1="8" y1="12" x2="16" y2="12"/>
            </svg>
            <span>Add Link</span>
        </div>
        <div class="nav-divider"></div>
        <button class="shortcuts-btn" id="shortcuts-btn">
            <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="2" y="4" width="20" height="16" rx="2"/>
                <path d="M6 8h.01M10 8h.01M14 8h.01M18 8h.01M8 12h.01M12 12h.01M16 12h.01M6 16h12"/>
            </svg>
            <span>Keyboard Shortcuts</span>
        </button>
    `;

    // Update keyboard shortcuts from config
    updateKeyboardShortcuts();

    console.log('[Config] Sidebar rendered with', CONFIG.sidebar.length, 'items');
}

// Build keyboard shortcuts map from config
function updateKeyboardShortcuts() {
    window.configShortcuts = {};
    if (CONFIG.sidebar) {
        CONFIG.sidebar.forEach(item => {
            if (item.shortcut) {
                window.configShortcuts[item.shortcut.toLowerCase()] = item.id;
            }
        });
    }
    console.log('[Config] Shortcuts registered:', Object.keys(window.configShortcuts));
}

// State
let currentView = 'home';
let contentFrame, homeView, statusText, sidebar, collapseBtn, shortcutsBtn, shortcutsModal, modalClose;

// Custom links state
let editingLinkId = null;

function getCustomLinks() {
    const links = localStorage.getItem('gershwin-custom-links');
    return links ? JSON.parse(links) : [];
}

function saveCustomLinks(links) {
    localStorage.setItem('gershwin-custom-links', JSON.stringify(links));
}

function generateLinkId() {
    return 'link-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function isExternalUrl(url) {
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
        return false;
    }
    try {
        const linkHost = new URL(url).hostname;
        const currentHost = window.location.hostname;
        return linkHost !== currentHost;
    } catch (e) {
        return true;
    }
}

function renderCustomLinks() {
    const customLinksContainer = document.getElementById('custom-links-container');
    if (!customLinksContainer) return;

    const links = getCustomLinks();
    customLinksContainer.innerHTML = '';

    links.forEach(link => {
        const div = document.createElement('div');
        const isExternal = link.url.startsWith('http://') || link.url.startsWith('https://');
        div.className = `nav-item custom-link${link.locked ? ' locked' : ''}${isExternal ? ' external-link' : ''}`;
        div.dataset.view = link.id;
        div.dataset.src = link.url;
        div.dataset.external = isExternal ? 'true' : 'false';
        div.innerHTML = `
            <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                ${isExternal
                    ? '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>'
                    : '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>'}
            </svg>
            <span>${escapeHtml(link.name)}${isExternal ? ' <small style="opacity:0.5;font-size:10px;">↗</small>' : ''}</span>
            <div class="link-actions">
                <button class="link-action-btn edit-btn" title="Edit" data-id="${link.id}">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                    </svg>
                </button>
                <button class="link-action-btn lock-btn" title="${link.locked ? 'Unlock' : 'Lock'}" data-id="${link.id}">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        ${link.locked
                            ? '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>'
                            : '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 9.9-1"/>'}
                    </svg>
                </button>
                <button class="link-action-btn delete-btn" title="Remove" data-id="${link.id}" ${link.locked ? 'disabled style="opacity:0.3;cursor:not-allowed;"' : ''}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="3 6 5 6 21 6"/>
                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                    </svg>
                </button>
            </div>
        `;

        div.addEventListener('click', (e) => {
            if (!e.target.closest('.link-actions')) {
                navigateToCustomLink(link);
            }
        });

        customLinksContainer.appendChild(div);
    });

    // Add event listeners for action buttons
    customLinksContainer.querySelectorAll('.edit-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            openEditModal(btn.dataset.id);
        });
    });

    customLinksContainer.querySelectorAll('.lock-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleLock(btn.dataset.id);
        });
    });

    customLinksContainer.querySelectorAll('.delete-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (!btn.disabled) {
                deleteLink(btn.dataset.id);
            }
        });
    });
}

function navigateToCustomLink(link) {
    if (isExternalUrl(link.url)) {
        window.open(link.url, '_blank');
        statusText.textContent = `Opened ${link.name} in new tab`;
        return;
    }

    document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
    const navItem = document.querySelector(`[data-view="${link.id}"]`);
    if (navItem) navItem.classList.add('active');

    currentView = link.id;
    window.location.hash = link.id;

    homeView.style.display = 'none';
    contentFrame.style.display = 'block';
    contentFrame.src = link.url;
    statusText.textContent = `Loading ${link.name}...`;

    contentFrame.onload = () => {
        statusText.textContent = link.name;
    };
}

function openAddModal() {
    const addLinkModal = document.getElementById('add-link-modal');
    const linkModalTitle = document.getElementById('link-modal-title');
    const linkSaveBtn = document.getElementById('link-save');
    const linkNameInput = document.getElementById('link-name');
    const linkUrlInput = document.getElementById('link-url');

    editingLinkId = null;
    linkModalTitle.textContent = 'Add Custom Link';
    linkSaveBtn.textContent = 'Add Link';
    linkNameInput.value = '';
    linkUrlInput.value = '';
    addLinkModal.classList.add('active');
    linkNameInput.focus();
}

function openEditModal(linkId) {
    const links = getCustomLinks();
    const link = links.find(l => l.id === linkId);
    if (!link) return;

    const addLinkModal = document.getElementById('add-link-modal');
    const linkModalTitle = document.getElementById('link-modal-title');
    const linkSaveBtn = document.getElementById('link-save');
    const linkNameInput = document.getElementById('link-name');
    const linkUrlInput = document.getElementById('link-url');

    editingLinkId = linkId;
    linkModalTitle.textContent = 'Edit Link';
    linkSaveBtn.textContent = 'Save Changes';
    linkNameInput.value = link.name;
    linkUrlInput.value = link.url;
    addLinkModal.classList.add('active');
    linkNameInput.focus();
}

function closeAddModal() {
    const addLinkModal = document.getElementById('add-link-modal');
    addLinkModal.classList.remove('active');
    editingLinkId = null;
}

function toggleLock(linkId) {
    const links = getCustomLinks();
    const link = links.find(l => l.id === linkId);
    if (link) {
        link.locked = !link.locked;
        saveCustomLinks(links);
        renderCustomLinks();
    }
}

function deleteLink(linkId) {
    let links = getCustomLinks();
    links = links.filter(l => l.id !== linkId);
    saveCustomLinks(links);
    renderCustomLinks();

    if (currentView === linkId) {
        navigateTo('home');
    }
}

function handleInitialRoute() {
    const hash = window.location.hash.slice(1);
    if (hash && document.querySelector(`[data-view="${hash}"]`)) {
        navigateTo(hash);
    }
}

// Navigation function
function navigateTo(view) {
    const navItem = document.querySelector(`[data-view="${view}"]`);
    if (!navItem) {
        // Check custom links
        const links = getCustomLinks();
        const customLink = links.find(l => l.id === view);
        if (customLink) {
            navigateToCustomLink(customLink);
            return;
        }
        return;
    }

    // Gate Tasks - require claude_assistant to be unlocked
    // Check localStorage first for persisted unlock state
    if (localStorage.getItem('claudeAssistantUnlocked') === 'true') {
        window.claudeAssistantUnlocked = true;
    }
    if (view === 'tasks' && window.claudeAssistantUnlocked === false) {
        showTasksLockedModal();
        return;
    }

    // Update active state
    document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
    navItem.classList.add('active');
    currentView = view;

    // Update URL hash
    window.location.hash = view;

    // Show appropriate content
    if (view === 'home') {
        // Check user state and gate home view based on unlock status
        // checkUserState is defined in HTML script tag and sets window.claudeAssistantUnlocked
        if (typeof checkUserState === 'function') {
            checkUserState().then(() => {
                if (window.claudeAssistantUnlocked === false) {
                    // Show app store instead of home when locked
                    if (typeof showAppStoreAsHome === 'function') {
                        showAppStoreAsHome();
                    }
                } else {
                    // Show normal home view
                    homeView.style.display = 'flex';
                    contentFrame.style.display = 'none';
                    statusText.textContent = 'Home';
                }
            });
        } else {
            // Fallback if checkUserState not available
            homeView.style.display = 'flex';
            contentFrame.style.display = 'none';
            statusText.textContent = 'Home';
        }
    } else {
        const src = navItem.dataset.src;
        if (src) {
            homeView.style.display = 'none';
            contentFrame.style.display = 'block';
            contentFrame.src = src;
            statusText.textContent = `Loading ${navItem.querySelector('span').textContent}...`;

            contentFrame.onload = () => {
                statusText.textContent = navItem.querySelector('span').textContent;
            };
        }
    }
}

// Make navigateTo globally accessible
window.navigateTo = navigateTo;

// Listen for postMessage events from child frames (e.g., app_store.html badge clicks)
window.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'open_url') {
        const url = event.data.url.replace(/^\//, '');
        navigateTo(url);
    }
});

function attachNavListeners() {
    document.querySelectorAll('.nav-item').forEach(item => {
        if (!item.classList.contains('add-link-btn')) {
            item.addEventListener('click', () => {
                navigateTo(item.dataset.view);
            });
        }
    });

    // Re-attach add link button listener
    const addLinkBtn = document.getElementById('add-link-btn');
    if (addLinkBtn) {
        addLinkBtn.addEventListener('click', openAddModal);
    }

    // Re-attach shortcuts button listener
    const shortcutsBtn = document.getElementById('shortcuts-btn');
    const shortcutsModal = document.getElementById('shortcuts-modal');
    if (shortcutsBtn && shortcutsModal) {
        shortcutsBtn.addEventListener('click', () => {
            shortcutsModal.classList.add('active');
        });
    }
}

// Initialize app after DOM and config are ready
function initApp() {
    contentFrame = document.getElementById('content-frame');
    homeView = document.getElementById('home-view');
    statusText = document.getElementById('status-text');
    sidebar = document.getElementById('sidebar');
    collapseBtn = document.getElementById('collapse-btn');
    shortcutsBtn = document.getElementById('shortcuts-btn');
    shortcutsModal = document.getElementById('shortcuts-modal');
    modalClose = document.getElementById('modal-close');

    // Sidebar collapse toggle
    if (collapseBtn) {
        collapseBtn.addEventListener('click', () => {
            sidebar.classList.toggle('collapsed');
            localStorage.setItem('gershwinSidebarCollapsed', sidebar.classList.contains('collapsed'));
        });
    }

    // Restore sidebar state
    if (localStorage.getItem('gershwinSidebarCollapsed') === 'true') {
        sidebar.classList.add('collapsed');
    }

    // Shortcuts modal
    if (shortcutsBtn && shortcutsModal) {
        shortcutsBtn.addEventListener('click', () => {
            shortcutsModal.classList.add('active');
        });
    }

    if (modalClose) {
        modalClose.addEventListener('click', () => {
            shortcutsModal.classList.remove('active');
        });
    }

    if (shortcutsModal) {
        shortcutsModal.addEventListener('click', (e) => {
            if (e.target === shortcutsModal) {
                shortcutsModal.classList.remove('active');
            }
        });
    }

    // Keyboard shortcuts (use config-driven shortcuts)
    document.addEventListener('keydown', (e) => {
        // Close modal on Escape
        if (e.key === 'Escape' && shortcutsModal && shortcutsModal.classList.contains('active')) {
            shortcutsModal.classList.remove('active');
            return;
        }

        // Only handle Cmd/Ctrl + key
        if (!e.metaKey && !e.ctrlKey) return;

        const shortcuts = window.configShortcuts || {
            'h': 'home',
            't': 'tasks',
            'd': 'docs',
            'l': 'slides',
            'e': 'sheets',
            'o': 'todo',
            's': 'spark',
            'm': 'media',
            'a': 'appstore'
        };

        const view = shortcuts[e.key.toLowerCase()];
        if (view) {
            e.preventDefault();
            navigateTo(view);
        }
    });

    // Handle browser back/forward
    window.addEventListener('hashchange', () => {
        const hash = window.location.hash.slice(1) || 'home';
        if (hash !== currentView) {
            navigateTo(hash);
        }
    });

    // Attach nav listeners
    attachNavListeners();

    // Initialize custom links
    renderCustomLinks();

    // Add link modal form setup
    const addLinkModal = document.getElementById('add-link-modal');
    const addLinkForm = document.getElementById('add-link-form');
    const linkModalClose = document.getElementById('link-modal-close');
    const linkCancel = document.getElementById('link-cancel');

    if (linkModalClose) {
        linkModalClose.addEventListener('click', closeAddModal);
    }
    if (linkCancel) {
        linkCancel.addEventListener('click', closeAddModal);
    }
    if (addLinkModal) {
        addLinkModal.addEventListener('click', (e) => {
            if (e.target === addLinkModal) {
                closeAddModal();
            }
        });
    }
    if (addLinkForm) {
        addLinkForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const linkNameInput = document.getElementById('link-name');
            const linkUrlInput = document.getElementById('link-url');
            const name = linkNameInput.value.trim();
            let url = linkUrlInput.value.trim();

            if (!name || !url) return;

            if (!url.startsWith('http://') && !url.startsWith('https://')) {
                url = 'https://' + url;
            }

            const links = getCustomLinks();

            if (editingLinkId) {
                const link = links.find(l => l.id === editingLinkId);
                if (link) {
                    link.name = name;
                    link.url = url;
                }
            } else {
                links.push({
                    id: generateLinkId(),
                    name: name,
                    url: url,
                    locked: false
                });
            }

            saveCustomLinks(links);
            renderCustomLinks();
            closeAddModal();
        });
    }

    // Handle initial route
    handleInitialRoute();
}

// Load config on DOMContentLoaded, then init app
document.addEventListener('DOMContentLoaded', async () => {
    await loadConfig();
    initApp();
});
