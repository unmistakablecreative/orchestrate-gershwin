// Global navigation shortcuts for OrchestrateOS
// Injected by jarvis.py middleware into all HTML responses
const NAV_SHORTCUTS = {
    '0': '/command',
    '1': '/tasks',
    '2': '/editor',
    '3': '/crm',
    '4': '/mockups',
    '5': '/images'
};

document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && NAV_SHORTCUTS[e.key]) {
        e.preventDefault();
        window.location.href = NAV_SHORTCUTS[e.key];
    }
});
