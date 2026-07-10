
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


        let currentDeck = null;
        let currentDeckData = null;
        let currentSlide = null;
        let currentSlideIndex = 0;
        let slides = [];
        let layouts = [];
        let icons = {};
        let themes = {};
        let zoomLevel = 100;
        let saveTimeout = null;
        let activeIconSlot = null;
        let allDecks = [];
        let isPresentMode = false;

        const layoutPreviews = {
            title_hero: { class: 'lp-title-hero', html: '<div class="lp-headline"></div><div class="lp-subtitle"></div>' },
            title_with_image: { class: 'lp-image-full', html: '<div class="lp-image"></div>' },
            split_content: { class: 'lp-split', html: '<div class="lp-left"><div class="lp-text-block"></div><div class="lp-text-block"></div></div><div class="lp-right"><div class="lp-image-block"></div></div>' },
            split_content_reverse: { class: 'lp-split', html: '<div class="lp-left"><div class="lp-image-block"></div></div><div class="lp-right"><div class="lp-text-block"></div><div class="lp-text-block"></div></div>' },
            three_column: { class: 'lp-three-col', html: '<div class="lp-col"><div class="lp-icon"></div><div class="lp-title"></div></div><div class="lp-col"><div class="lp-icon"></div><div class="lp-title"></div></div><div class="lp-col"><div class="lp-icon"></div><div class="lp-title"></div></div>' },
            four_grid: { class: 'lp-three-col', html: '<div class="lp-col"><div class="lp-icon"></div></div><div class="lp-col"><div class="lp-icon"></div></div><div class="lp-col"><div class="lp-icon"></div></div><div class="lp-col"><div class="lp-icon"></div></div>' },
            big_number: { class: 'lp-big-number', html: '<div class="lp-number">99</div><div class="lp-label"></div>' },
            stats_row: { class: 'lp-stats', html: '<div class="lp-stat"><div class="lp-stat-num">10</div></div><div class="lp-stat"><div class="lp-stat-num">25</div></div><div class="lp-stat"><div class="lp-stat-num">50</div></div>' },
            quote: { class: 'lp-quote', html: '<div class="lp-quote-mark">"</div><div class="lp-quote-line"></div><div class="lp-quote-line"></div>' },
            text_only: { class: 'lp-bullets', html: '<div class="lp-title-line"></div><div class="lp-bullet"><div class="lp-bullet-text" style="width:100%"></div></div>' },
            bullet_list: { class: 'lp-bullets', html: '<div class="lp-title-line"></div><div class="lp-bullet"><div class="lp-bullet-dot"></div><div class="lp-bullet-text"></div></div><div class="lp-bullet"><div class="lp-bullet-dot"></div><div class="lp-bullet-text"></div></div>' },
            numbered_steps: { class: 'lp-bullets', html: '<div class="lp-title-line"></div><div class="lp-bullet"><div class="lp-bullet-dot" style="border-radius:0"></div><div class="lp-bullet-text"></div></div>' },
            timeline_horizontal: { class: 'lp-stats', html: '<div class="lp-stat"><div class="lp-stat-label" style="width:8px;height:8px;border-radius:50%"></div></div><div style="flex:1;height:2px;background:var(--border)"></div><div class="lp-stat"><div class="lp-stat-label" style="width:8px;height:8px;border-radius:50%"></div></div>' },
            image_full: { class: 'lp-image-full', html: '<div class="lp-image"></div>' },
            image_gallery: { class: 'lp-three-col', html: '<div class="lp-col" style="background:var(--accent);opacity:0.2;border-radius:2px"></div><div class="lp-col" style="background:var(--accent);opacity:0.2;border-radius:2px"></div><div class="lp-col" style="background:var(--accent);opacity:0.2;border-radius:2px"></div>' },
            chart_single: { class: 'lp-split', html: '<div class="lp-left"><div class="lp-text-block"></div></div><div class="lp-right"><div class="lp-image-block" style="background:var(--accent);opacity:0.3"></div></div>' },
            comparison_table: { class: 'lp-three-col', html: '<div class="lp-col" style="border-right:1px solid var(--border)"><div class="lp-title"></div></div><div class="lp-col" style="border-right:1px solid var(--border)"><div class="lp-title"></div></div><div class="lp-col"><div class="lp-title"></div></div>' },
            team_grid: { class: 'lp-three-col', html: '<div class="lp-col"><div class="lp-icon" style="border-radius:50%;width:16px;height:16px"></div><div class="lp-title"></div></div><div class="lp-col"><div class="lp-icon" style="border-radius:50%"></div><div class="lp-title"></div></div>' },
            logo_grid: { class: 'lp-three-col', html: '<div class="lp-col"><div class="lp-icon"></div></div><div class="lp-col"><div class="lp-icon"></div></div><div class="lp-col"><div class="lp-icon"></div></div>' },
            cta_closing: { class: 'lp-title-hero', html: '<div class="lp-headline"></div><div class="lp-subtitle"></div><div style="width:40px;height:12px;background:var(--accent);border-radius:2px;margin-top:8px"></div>' },
            section_divider: { class: 'lp-big-number', html: '<div class="lp-number" style="font-size:16px">01</div><div class="lp-label" style="width:60px"></div>' },
            headline: { class: 'lp-title-hero', html: '<div class="lp-headline"></div>' },
            section_break: { class: 'lp-big-number', html: '<div class="lp-label" style="width:80px;height:8px"></div>' },
            agenda: { class: 'lp-bullets', html: '<div class="lp-title-line"></div><div class="lp-bullet"><div class="lp-bullet-dot" style="background:var(--text-muted)"></div><div class="lp-bullet-text"></div></div>' },
            icon_list: { class: 'lp-three-col', html: '<div class="lp-col" style="flex-direction:row;gap:4px"><div class="lp-icon"></div><div style="flex:1"><div class="lp-title"></div></div></div>' },
            video_embed: { class: 'lp-image-full', html: '<div class="lp-image" style="display:flex;align-items:center;justify-content:center"><div style="width:20px;height:20px;border:2px solid var(--text-muted);border-radius:50%"></div></div>' }
        };

        // Layouts that should be centered
        const centeredLayouts = ['title_hero', 'headline', 'quote', 'big_number', 'section_break', 'section_divider', 'cta_closing'];

        document.addEventListener('DOMContentLoaded', async () => {
            await loadLayouts();
            await loadIcons();
            await loadThemes();
            await loadDecks();
            renderLayoutGrid();
        });

        // Keyboard navigation
        document.addEventListener('keydown', (e) => {
            if (isPresentMode) {
                if (e.key === 'Escape') exitPresent();
                else if (e.key === 'ArrowRight' || e.key === ' ') nextSlide();
                else if (e.key === 'ArrowLeft') prevSlide();
                return;
            }
            // Only nav when not editing
            if (document.activeElement.contentEditable !== 'true' && currentDeck) {
                if (e.key === 'ArrowRight') nextSlide();
                else if (e.key === 'ArrowLeft') prevSlide();
            }
        });

        async function apiCall(toolName, action, params = {}) {
            const response = await fetch('/execute_task', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tool_name: toolName, action: action, params: params })
            });
            return response.json();
        }

        async function loadLayouts() {
            try {
                const response = await fetch('/data/slide_designer_layouts.json');
                const data = await response.json();
                layouts = data.layouts || [];
            } catch (e) { layouts = []; }
        }

        async function loadIcons() {
            try {
                const response = await fetch('/data/lucide_icons.json');
                if (!response.ok) { console.error('loadIcons failed:', response.status); icons = {}; return; }
                const data = await response.json();
                icons = data.icons || data || {};
                console.log('Icons loaded:', Object.keys(icons).length, 'icons');
            } catch (e) { console.error('loadIcons error:', e); icons = {}; }
        }

        async function loadThemes() {
            try {
                const response = await fetch('/data/slide_themes.json');
                if (!response.ok) { console.error('loadThemes failed:', response.status); themes = {}; return; }
                const data = await response.json();
                themes = data.themes || {};
                console.log('Themes loaded:', Object.keys(themes).length, 'themes');
            } catch (e) { console.error('loadThemes error:', e); themes = {}; }
        }

        async function loadDecks() {
            const result = await apiCall('slide_designer', 'list_decks', {});
            if (result.status === 'success' && result.decks) {
                allDecks = result.decks;
                renderDeckGrid();
            }
        }

        function renderDeckGrid() {
            const container = document.getElementById('deckGrid');
            if (allDecks.length === 0) {
                container.innerHTML = '<div style="grid-column: span 3; text-align: center; padding: 80px 20px; color: var(--text-muted);"><div style="font-size: 64px; margin-bottom: 16px; opacity: 0.3;">Slides</div><div style="font-size: 16px;">Create your first deck to get started</div></div>';
                return;
            }
            container.innerHTML = allDecks.map(deck => {
                const slideCount = deck.slide_count || 0;
                const lastEdited = deck.updated_at ? formatDate(deck.updated_at) : 'Just now';
                return `<div class="deck-card-home" onclick="openDeck('${deck.id}')">
                    <button class="deck-card-delete" onclick="event.stopPropagation(); deleteDeck('${deck.id}', '${escapeHtml(deck.title)}')" title="Delete deck">&times;</button>
                    <div class="deck-card-thumbnail">${slideCount > 0 ? slideCount : 'Slides'}</div>
                    <div class="deck-card-info">
                        <div class="deck-card-title-home">${escapeHtml(deck.title)}</div>
                        <div class="deck-card-meta">
                            <span>${slideCount} slide${slideCount !== 1 ? 's' : ''}</span>
                            <span>${lastEdited}</span>
                        </div>
                    </div>
                </div>`;
            }).join('');
        }

        function formatDate(dateStr) {
            if (!dateStr) return 'Just now';
            const d = new Date(dateStr);
            const now = new Date();
            const diff = now - d;
            if (diff < 60000) return 'Just now';
            if (diff < 3600000) return Math.floor(diff / 60000) + 'm ago';
            if (diff < 86400000) return Math.floor(diff / 3600000) + 'h ago';
            return d.toLocaleDateString();
        }

        async function openDeck(deckId) {
            currentDeck = deckId;
            const result = await apiCall('slide_designer', 'get_deck', { deck_id: deckId });
            if (result.status === 'success') {
                currentDeckData = result.deck;
                slides = (result.deck && result.deck.slides) ? result.deck.slides : [];

                // Apply theme
                const themeName = result.deck.theme || 'dark_pro';
                // Update theme selector to match deck theme
                const themeSelector = document.getElementById('themeSelector');
                if (themeSelector) themeSelector.value = themeName;
                // Ensure themes are loaded before applying
                if (Object.keys(themes).length === 0) {
                    await loadThemes();
                }
                applyTheme(themeName);

                // Switch to deck view
                document.getElementById('homeView').classList.remove('active');
                document.getElementById('deckView').classList.add('active');
                document.getElementById('backBtn').classList.add('visible');
                document.getElementById('headerTitle').textContent = result.deck.title || 'Untitled Deck';
                document.getElementById('exportBtn').style.display = 'flex';
                document.getElementById('presentBtn').style.display = 'flex';
                document.getElementById('themeSelector').style.display = 'block';
                document.getElementById('fontPairingSelector').style.display = 'block';
                
                // Apply saved font pairing
                const fontPairing = result.deck.font_pairing || 'classic';
                document.getElementById('fontPairingSelector').value = fontPairing;
                applyFontPairing(fontPairing);

                renderSlideList();
                if (slides.length > 0) {
                    currentSlideIndex = 0;
                    selectSlide(slides[0].id);
                } else {
                    showEmptyState();
                }
                updateNavArrows();
            }
        }

        function applyTheme(themeName) {
            const theme = themes[themeName] || themes['dark_pro'];
            if (!theme) return;

            const root = document.documentElement;
            const canvas = document.getElementById('slideCanvas');
            const presentSlide = document.getElementById('presentSlide');

            if (theme.css_vars) {
                Object.entries(theme.css_vars).forEach(([key, value]) => {
                    root.style.setProperty(key, value);
                });
                if (canvas) {
                    Object.entries(theme.css_vars).forEach(([key, value]) => {
                        canvas.style.setProperty(key, value);
                    });
                    canvas.style.background = theme.css_vars['--theme-bg'] || CONFIG.colors.color_1;
                }
                if (presentSlide) {
                    Object.entries(theme.css_vars).forEach(([key, value]) => {
                        presentSlide.style.setProperty(key, value);
                    });
                    presentSlide.style.background = theme.css_vars['--theme-bg'] || CONFIG.colors.color_1;
                }
            }
            if (isPresentMode) {
                renderPresentSlide();
            } else if (currentSlide) {
                renderSlideCanvas();
            }
        }

        function goToHome() {
            currentDeck = null;
            currentDeckData = null;
            currentSlide = null;
            slides = [];

            document.getElementById('deckView').classList.remove('active');
            document.getElementById('homeView').classList.add('active');
            document.getElementById('backBtn').classList.remove('visible');
            document.getElementById('headerTitle').innerHTML = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"></rect><line x1="8" y1="21" x2="16" y2="21"></line><line x1="12" y1="17" x2="12" y2="21"></line></svg> Slide Designer';
            document.getElementById('exportBtn').style.display = 'none';
            document.getElementById('presentBtn').style.display = 'none';
            document.getElementById('fontPairingSelector').style.display = 'none';
            document.getElementById('themeSelector').style.display = 'none';

            loadDecks();
        }

        function openNewDeckModal() {
            document.getElementById('newDeckModal').classList.add('active');
            document.getElementById('newDeckTitle').value = '';
            document.getElementById('newDeckTitle').focus();
        }

        function closeNewDeckModal() {
            document.getElementById('newDeckModal').classList.remove('active');
        }

        async function confirmNewDeck() {
            const title = document.getElementById('newDeckTitle').value.trim();
            if (!title) return;
            closeNewDeckModal();
            const result = await apiCall('slide_designer', 'create_deck', { title: title });
            if (result.status === 'success') {
                await loadDecks();
                await openDeck(result.deck_id);
                showToast('Deck created', 'success');
            }
        }

        function renderSlideList() {
            const container = document.getElementById('slideList');
            if (slides.length === 0) {
                container.innerHTML = '<div style="padding: 20px; text-align: center; color: var(--text-muted); font-size: 12px;">No slides yet</div>';
                return;
            }
            container.innerHTML = slides.map((slide, idx) => {
                const isActive = currentSlide && currentSlide.id === slide.id;
                const thumbnailContent = renderSlideForThumbnail(slide);
                return `<div class="slide-thumbnail ${isActive ? 'active' : ''}" data-id="${slide.id}" onclick="selectSlide('${slide.id}')">
                    <div class="slide-thumbnail-preview">
                        <div class="slide-thumbnail-content">${thumbnailContent}</div>
                    </div>
                    <div class="slide-thumbnail-label">
                        <span class="slide-number">${idx + 1}</span>
                        <div class="slide-actions">
                            <button class="slide-action-btn delete" onclick="event.stopPropagation(); deleteSlide('${slide.id}')" title="Delete">×</button>
                        </div>
                    </div>
                </div>`;
            }).join('');
            initSortable();
        }
        
        let sortableInstance = null;
        function initSortable() {
            const container = document.getElementById('slideList');
            if (sortableInstance) sortableInstance.destroy();
            sortableInstance = new Sortable(container, {
                animation: 150,
                ghostClass: 'slide-thumbnail-ghost',
                onEnd: async function(evt) {
                    const oldIndex = evt.oldIndex;
                    const newIndex = evt.newIndex;
                    if (oldIndex === newIndex) return;
                    // Reorder slides array
                    const movedSlide = slides.splice(oldIndex, 1)[0];
                    slides.splice(newIndex, 0, movedSlide);
                    // Update currentSlideIndex
                    if (currentSlide) {
                        currentSlideIndex = slides.findIndex(s => s.id === currentSlide.id);
                    }
                    // Save new order to backend
                    const slideIds = slides.map(s => s.id);
                    await apiCall('slide_designer', 'reorder_slides', { deck_id: currentDeck, slide_ids: slideIds });
                    renderSlideList();
                    updateNavArrows();
                }
            });
        }

        function renderSlideForThumbnail(slide) {
            const layout = slide.layout_type;
            const content = slide.content || {};
            const isCentered = centeredLayouts.includes(layout);
            let html = `<div class="slide-content ${isCentered ? 'centered' : ''}">`;

            // Simplified rendering for thumbnails
            if (layout === 'title_hero') {
                html += `<div class="slide-headline">${escapeHtml(content.headline || 'Headline')}</div>
                    <div class="slide-subtitle">${escapeHtml(content.subtitle || 'Subtitle')}</div>`;
            } else if (layout === 'big_number') {
                html += `<div class="slide-big-number">${escapeHtml(content.number || '0')}</div>
                    <div class="slide-stat-label">${escapeHtml(content.label || 'Label')}</div>`;
            } else if (layout === 'quote') {
                html += `<div class="slide-quote">${escapeHtml(content.quote_text || 'Quote')}</div>`;
            } else {
                html += `<div class="slide-section-title">${escapeHtml(content.title || content.header || layout)}</div>`;
            }

            html += '</div>';
            return html;
        }

        async function selectSlide(slideId) {
            const idx = slides.findIndex(s => s.id === slideId);
            if (idx < 0) return;
            currentSlideIndex = idx;
            currentSlide = slides[idx];
            renderSlideList();
            renderSlideCanvas();
            document.getElementById('slideInfo').textContent = `Slide ${idx + 1} of ${slides.length}`;
            updateNavArrows();
        }

        function updateNavArrows() {
            const prevBtn = document.getElementById('prevSlideBtn');
            const nextBtn = document.getElementById('nextSlideBtn');
            prevBtn.classList.toggle('disabled', currentSlideIndex <= 0);
            nextBtn.classList.toggle('disabled', currentSlideIndex >= slides.length - 1);
        }

        function prevSlide() {
            if (currentSlideIndex > 0) {
                currentSlideIndex--;
                if (isPresentMode) {
                    renderPresentSlide();
                } else {
                    selectSlide(slides[currentSlideIndex].id);
                }
            }
        }

        function nextSlide() {
            if (currentSlideIndex < slides.length - 1) {
                currentSlideIndex++;
                if (isPresentMode) {
                    renderPresentSlide();
                } else {
                    selectSlide(slides[currentSlideIndex].id);
                }
            }
        }

        function showEmptyState() {
            document.getElementById('emptyState').style.display = 'flex';
            document.getElementById('slideContent').style.display = 'none';
            document.getElementById('slideInfo').textContent = '';
        }

        function renderSlideCanvas() {
            if (!currentSlide) { showEmptyState(); return; }
            document.getElementById('emptyState').style.display = 'none';
            const content = document.getElementById('slideContent');
            content.style.display = 'block';
            const layout = currentSlide.layout_type;
            const slideContent = currentSlide.content || {};
            const isCentered = centeredLayouts.includes(layout);
            let html = `<div class="slide-content ${isCentered ? 'centered' : ''}">`;

            if (layout === 'title_hero') {
                html += '<div class="slide-headline" contenteditable="true" data-field="headline" data-placeholder="Click to edit headline" onblur="saveField(this)">' + escapeHtml(slideContent.headline || '') + '</div>' +
                    '<div class="slide-subtitle" contenteditable="true" data-field="subtitle" data-placeholder="Click to edit subtitle" onblur="saveField(this)">' + escapeHtml(slideContent.subtitle || '') + '</div>';
            } else if (layout === 'headline') {
                html += '<div class="slide-headline" contenteditable="true" data-field="headline" data-placeholder="Click to edit headline" onblur="saveField(this)">' + escapeHtml(slideContent.headline || '') + '</div>';
            } else if (layout === 'big_number') {
                html += '<div class="slide-big-number" contenteditable="true" data-field="number" data-placeholder="99" onblur="saveField(this)">' + escapeHtml(slideContent.number || '') + '</div>' +
                    '<div class="slide-stat-label" contenteditable="true" data-field="label" data-placeholder="Click to edit label" onblur="saveField(this)">' + escapeHtml(slideContent.label || '') + '</div>' +
                    '<div class="slide-body" style="text-align:center; margin-top:24px;" contenteditable="true" data-field="context" data-placeholder="Add context..." onblur="saveField(this)">' + escapeHtml(slideContent.context || '') + '</div>';
            } else if (layout === 'quote') {
                html += '<div style="max-width:800px;">' +
                    '<div class="slide-quote" contenteditable="true" data-field="quote_text" data-placeholder="Click to enter quote..." onblur="saveField(this)">' + escapeHtml(slideContent.quote_text || '') + '</div>' +
                    '<div class="slide-author" contenteditable="true" data-field="author_name" data-placeholder="Author Name" onblur="saveField(this)">' + escapeHtml(slideContent.author_name || '') + '</div>' +
                    '<div class="slide-author" style="font-size:14px; opacity:0.7;" contenteditable="true" data-field="author_title" data-placeholder="Title / Company" onblur="saveField(this)">' + escapeHtml(slideContent.author_title || '') + '</div>' +
                '</div>';
            } else if (layout === 'section_break' || layout === 'section_divider') {
                html += '<div style="font-size:72px; font-weight:800; color:var(--theme-accent); opacity:0.3;" contenteditable="true" data-field="section_number" data-placeholder="01" onblur="saveField(this)">' + escapeHtml(slideContent.section_number || '') + '</div>' +
                    '<div class="slide-headline" style="font-size:36px;" contenteditable="true" data-field="section_title" data-placeholder="Section Title" onblur="saveField(this)">' + escapeHtml(slideContent.section_title || '') + '</div>';
            } else if (layout === 'cta_closing') {
                html += '<div class="slide-headline" contenteditable="true" data-field="headline" data-placeholder="Call to Action" onblur="saveField(this)">' + escapeHtml(slideContent.headline || '') + '</div>' +
                    '<div class="slide-subtitle" contenteditable="true" data-field="subtext" data-placeholder="Supporting text..." onblur="saveField(this)">' + escapeHtml(slideContent.subtext || '') + '</div>' +
                    '<div style="margin-top:32px; padding:12px 32px; background:var(--theme-accent); border-radius:8px; cursor:pointer;" contenteditable="true" data-field="cta_button" data-placeholder="Get Started" onblur="saveField(this)">' + escapeHtml(slideContent.cta_button || '') + '</div>' +
                    '<div class="slide-author" style="margin-top:24px;" contenteditable="true" data-field="contact_info" data-placeholder="contact@example.com" onblur="saveField(this)">' + escapeHtml(slideContent.contact_info || '') + '</div>';
            } else if (layout === 'text_only') {
                html += '<div class="slide-section-title" contenteditable="true" data-field="title" data-placeholder="Click to edit title" onblur="saveField(this)">' + escapeHtml(slideContent.title || '') + '</div>' +
                    '<div class="slide-body" style="flex:1; margin-top:24px;" contenteditable="true" data-field="body" data-placeholder="Click to edit body text..." onblur="saveField(this)">' + escapeHtml(slideContent.body || '') + '</div>';
            } else if (layout === 'bullet_list') {
                const bullets = slideContent.bullets || ['Click to edit', 'Add more bullets', 'Press Enter for new line'];
                html += '<div class="slide-section-title" contenteditable="true" data-field="title" data-placeholder="Click to edit title" onblur="saveField(this)">' + escapeHtml(slideContent.title || '') + '</div>' +
                    '<ul class="slide-bullets" id="bulletList">';
                bullets.forEach((b, i) => {
                    html += '<li contenteditable="true" data-field="bullets" data-index="' + i + '" onblur="saveBullet(this)" onkeydown="handleBulletKey(event, this)">' + escapeHtml(b) + '</li>';
                });
                html += '</ul>';
            } else if (layout === 'stats_row') {
                const stats = slideContent.stats || [{number: '100', label: 'Stat 1'}, {number: '50', label: 'Stat 2'}, {number: '25', label: 'Stat 3'}];
                html += '<div class="slide-section-title" style="text-align:center;" contenteditable="true" data-field="header" data-placeholder="Click to edit header" onblur="saveField(this)">' + escapeHtml(slideContent.header || '') + '</div>' +
                    '<div class="slide-stats-row">';
                stats.forEach((s, i) => {
                    html += '<div class="slide-stat-item">' +
                        '<div class="slide-stat-number" contenteditable="true" data-field="stats.' + i + '.number" data-placeholder="0" onblur="saveNestedField(this)">' + escapeHtml(s.number || '') + '</div>' +
                        '<div class="slide-stat-label" contenteditable="true" data-field="stats.' + i + '.label" data-placeholder="Label" onblur="saveNestedField(this)">' + escapeHtml(s.label || '') + '</div>' +
                    '</div>';
                });
                html += '</div>';
            } else if (layout === 'three_column') {
                html += '<div class="slide-section-title" style="text-align:center;" contenteditable="true" data-field="header" data-placeholder="Click to edit header" onblur="saveField(this)">' + escapeHtml(slideContent.header || '') + '</div>' +
                    '<div class="slide-grid-3">';
                [1,2,3].forEach(i => {
                    html += '<div class="slide-grid-item">' +
                        '<div class="slide-item-icon icon-slot" data-field="col' + i + '_icon" onclick="openIconPicker(\'col' + i + '_icon\')" oncontextmenu="event.preventDefault(); openIconColorSwatches(this, event)">' + renderIcon(slideContent['col'+i+'_icon']) + '</div>' +
                        '<div class="slide-item-title" contenteditable="true" data-field="col' + i + '_title" data-placeholder="Title ' + i + '" onblur="saveField(this)">' + escapeHtml(slideContent['col'+i+'_title'] || '') + '</div>' +
                        '<div class="slide-item-body" contenteditable="true" data-field="col' + i + '_body" data-placeholder="Description..." onblur="saveField(this)">' + escapeHtml(slideContent['col'+i+'_body'] || '') + '</div>' +
                    '</div>';
                });
                html += '</div>';
            } else if (layout === 'four_grid') {
                html += '<div class="slide-section-title" style="text-align:center;" contenteditable="true" data-field="header" data-placeholder="Click to edit header" onblur="saveField(this)">' + escapeHtml(slideContent.header || '') + '</div>' +
                    '<div class="slide-grid-4">';
                [1,2,3,4].forEach(i => {
                    html += '<div class="slide-grid-item">' +
                        '<div class="slide-item-icon icon-slot" data-field="cell' + i + '_icon" onclick="openIconPicker(\'cell' + i + '_icon\')" oncontextmenu="event.preventDefault(); openIconColorSwatches(this, event)">' + renderIcon(slideContent['cell'+i+'_icon']) + '</div>' +
                        '<div class="slide-item-title" contenteditable="true" data-field="cell' + i + '_title" data-placeholder="Title ' + i + '" onblur="saveField(this)">' + escapeHtml(slideContent['cell'+i+'_title'] || '') + '</div>' +
                        '<div class="slide-item-body" contenteditable="true" data-field="cell' + i + '_body" data-placeholder="Description..." onblur="saveField(this)">' + escapeHtml(slideContent['cell'+i+'_body'] || '') + '</div>' +
                    '</div>';
                });
                html += '</div>';
            } else if (layout === 'split_content') {
                html += '<div class="slide-split">' +
                    '<div class="slide-split-content">' +
                        '<div class="slide-section-title" contenteditable="true" data-field="left_title" data-placeholder="Click to edit title" onblur="saveField(this)">' + escapeHtml(slideContent.left_title || '') + '</div>' +
                        '<div class="slide-body" style="margin-top:16px;" contenteditable="true" data-field="left_body" data-placeholder="Click to edit body..." onblur="saveField(this)">' + escapeHtml(slideContent.left_body || '') + '</div>' +
                    '</div>' +
                    '<div class="slide-split-image"><span>Image placeholder</span></div>' +
                '</div>';
            } else if (layout === 'split_content_reverse') {
                html += '<div class="slide-split">' +
                    '<div class="slide-split-image"><span>Image placeholder</span></div>' +
                    '<div class="slide-split-content">' +
                        '<div class="slide-section-title" contenteditable="true" data-field="right_title" data-placeholder="Click to edit title" onblur="saveField(this)">' + escapeHtml(slideContent.right_title || '') + '</div>' +
                        '<div class="slide-body" style="margin-top:16px;" contenteditable="true" data-field="right_body" data-placeholder="Click to edit body..." onblur="saveField(this)">' + escapeHtml(slideContent.right_body || '') + '</div>' +
                    '</div>' +
                '</div>';
            } else if (layout === 'icon_list') {
                html += '<div class="slide-section-title" contenteditable="true" data-field="title" data-placeholder="Click to edit title" onblur="saveField(this)">' + escapeHtml(slideContent.title || '') + '</div>' +
                    '<div style="display:flex; flex-direction:column; gap:24px; margin-top:32px;">';
                [1,2,3,4].forEach(i => {
                    html += '<div style="display:flex; align-items:flex-start; gap:16px;">' +
                        '<div class="slide-item-icon icon-slot" style="flex-shrink:0;" data-field="item' + i + '_icon" onclick="openIconPicker(\'item' + i + '_icon\')" oncontextmenu="event.preventDefault(); openIconColorSwatches(this, event)">' + renderIcon(slideContent['item'+i+'_icon']) + '</div>' +
                        '<div style="flex:1;">' +
                            '<div class="slide-item-title" style="text-align:left;" contenteditable="true" data-field="item' + i + '_title" data-placeholder="Item ' + i + ' title" onblur="saveField(this)">' + escapeHtml(slideContent['item'+i+'_title'] || '') + '</div>' +
                            '<div class="slide-item-body" style="text-align:left;" contenteditable="true" data-field="item' + i + '_body" data-placeholder="Description..." onblur="saveField(this)">' + escapeHtml(slideContent['item'+i+'_body'] || '') + '</div>' +
                        '</div>' +
                    '</div>';
                });
                html += '</div>';
            } else if (layout === 'comparison_table') {
                const rows = slideContent.rows || [{left: 'Item A', right: 'Item B'}, {left: 'Feature 1', right: 'Feature 2'}];
                html += '<div class="slide-section-title" style="text-align:center;" contenteditable="true" data-field="header" data-placeholder="Comparison" onblur="saveField(this)">' + escapeHtml(slideContent.header || '') + '</div>' +
                    '<table style="width:100%; margin-top:32px; border-collapse:collapse;">';
                rows.forEach((r, i) => {
                    html += '<tr>' +
                        '<td style="padding:16px; border:1px solid var(--theme-accent); width:50%;" contenteditable="true" data-field="rows.' + i + '.left" onblur="saveNestedField(this)">' + escapeHtml(r.left || '') + '</td>' +
                        '<td style="padding:16px; border:1px solid var(--theme-accent); width:50%;" contenteditable="true" data-field="rows.' + i + '.right" onblur="saveNestedField(this)">' + escapeHtml(r.right || '') + '</td>' +
                    '</tr>';
                });
                html += '</table>';
            } else if (layout === 'agenda') {
                const items = slideContent.agenda_items || ['Agenda item 1', 'Agenda item 2', 'Agenda item 3'];
                html += '<div class="slide-section-title" style="text-align:center;" contenteditable="true" data-field="title" data-placeholder="Agenda" onblur="saveField(this)">' + escapeHtml(slideContent.title || '') + '</div>' +
                    '<div style="margin-top:32px; display:flex; flex-direction:column; gap:16px;">';
                items.forEach((item, i) => {
                    html += '<div style="display:flex; align-items:center; gap:16px; padding:16px; background:rgba(255,255,255,0.05); border-radius:8px;">' +
                        '<div style="width:32px; height:32px; background:var(--theme-accent); border-radius:50%; display:flex; align-items:center; justify-content:center; font-weight:600;">' + (i+1) + '</div>' +
                        '<div contenteditable="true" data-field="agenda_items" data-index="' + i + '" style="flex:1; font-size:18px;" onblur="saveBullet(this)">' + escapeHtml(item) + '</div>' +
                    '</div>';
                });
                html += '</div>';
            } else if (layout === 'logo_grid') {
                html += '<div class="slide-section-title" style="text-align:center;" contenteditable="true" data-field="header" data-placeholder="Our Partners" onblur="saveField(this)">' + escapeHtml(slideContent.header || '') + '</div>' +
                    '<div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:32px; margin-top:48px;">';
                [1,2,3,4,5,6,7,8].forEach(i => {
                    html += '<div class="icon-slot" style="aspect-ratio:3/2; background:rgba(255,255,255,0.05); border-radius:8px; display:flex; align-items:center; justify-content:center; cursor:pointer;" data-field="logo' + i + '" onclick="openIconPicker(\'logo' + i + '\')" oncontextmenu="event.preventDefault(); openIconColorSwatches(this, event)">' + 
                        (slideContent['logo'+i] ? renderIcon(slideContent['logo'+i]) : '<span style="color:var(--text-muted);">Logo ' + i + '</span>') + '</div>';
                });
                html += '</div>';
            } else if (layout === 'image_full') {
                html += '<div style="position:absolute; top:0; left:0; right:0; bottom:0; display:flex; align-items:center; justify-content:center; background:rgba(255,255,255,0.05);">' +
                    '<div style="text-align:center; color:var(--text-muted);">' +
                        '<div style="font-size:48px; margin-bottom:16px;">🖼</div>' +
                        '<div contenteditable="true" data-field="caption" data-placeholder="Click to add caption" onblur="saveField(this)">' + escapeHtml(slideContent.caption || '') + '</div>' +
                    '</div>' +
                '</div>';
            } else if (layout === 'image_gallery') {
                html += '<div class="slide-section-title" style="text-align:center;" contenteditable="true" data-field="header" data-placeholder="Gallery" onblur="saveField(this)">' + escapeHtml(slideContent.header || '') + '</div>' +
                    '<div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:16px; margin-top:32px;">';
                [1,2,3,4,5,6].forEach(i => {
                    html += '<div style="aspect-ratio:4/3; background:rgba(255,255,255,0.05); border-radius:8px; display:flex; align-items:center; justify-content:center;">' +
                        '<span style="color:var(--text-muted);">Image ' + i + '</span></div>';
                });
                html += '</div>';
            } else if (layout === 'horizontal_line') {
                html += '<div class="slide-section-title" style="text-align:center;" contenteditable="true" data-field="title" data-placeholder="Click to edit title" onblur="saveField(this)">' + escapeHtml(slideContent.title || '') + '</div>' +
                    '<hr style="border:none; height:2px; background:var(--theme-accent); margin:32px 0;">' +
                    '<div class="slide-body" style="text-align:center;" contenteditable="true" data-field="body" data-placeholder="Content below the line..." onblur="saveField(this)">' + escapeHtml(slideContent.body || '') + '</div>';
            } else if (layout === 'title_with_image') {
                html += '<div style="position:absolute; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.5); display:flex; flex-direction:column; align-items:center; justify-content:center;">' +
                    '<div class="slide-headline" contenteditable="true" data-field="headline" data-placeholder="Click to edit headline" onblur="saveField(this)">' + escapeHtml(slideContent.headline || '') + '</div>' +
                    '<div class="slide-subtitle" contenteditable="true" data-field="subtitle" data-placeholder="Click to edit subtitle" onblur="saveField(this)">' + escapeHtml(slideContent.subtitle || '') + '</div>' +
                '</div>';
            } else if (layout === 'numbered_steps') {
                const steps = slideContent.steps || ['Step 1', 'Step 2', 'Step 3'];
                html += '<div class="slide-section-title" contenteditable="true" data-field="title" data-placeholder="Click to edit title" onblur="saveField(this)">' + escapeHtml(slideContent.title || '') + '</div>' +
                    '<div style="margin-top:32px; display:flex; flex-direction:column; gap:20px;">';
                steps.forEach((step, i) => {
                    html += '<div style="display:flex; align-items:flex-start; gap:16px;">' +
                        '<div style="width:40px; height:40px; background:var(--theme-accent); border-radius:50%; display:flex; align-items:center; justify-content:center; font-weight:700; font-size:18px; flex-shrink:0;">' + (i+1) + '</div>' +
                        '<div contenteditable="true" data-field="steps" data-index="' + i + '" style="flex:1; font-size:18px; padding-top:8px;" onblur="saveBullet(this)">' + escapeHtml(step) + '</div>' +
                    '</div>';
                });
                html += '</div>';
            } else if (layout === 'timeline_horizontal') {
                html += '<div class="slide-section-title" style="text-align:center;" contenteditable="true" data-field="title" data-placeholder="Timeline Title" onblur="saveField(this)">' + escapeHtml(slideContent.title || '') + '</div>' +
                    '<div style="margin-top:48px; position:relative;">' +
                        '<div style="position:absolute; top:20px; left:10%; right:10%; height:3px; background:var(--theme-accent);"></div>' +
                        '<div style="display:flex; justify-content:space-between; padding:0 5%;">';
                [1,2,3,4,5].forEach(i => {
                    html += '<div style="text-align:center; position:relative;">' +
                        '<div style="width:16px; height:16px; background:var(--theme-accent); border-radius:50%; margin:12px auto 16px;"></div>' +
                        '<div style="font-weight:600; margin-bottom:8px;" contenteditable="true" data-field="point' + i + '_label" data-placeholder="Point ' + i + '" onblur="saveField(this)">' + escapeHtml(slideContent['point'+i+'_label'] || '') + '</div>' +
                        '<div style="font-size:14px; color:var(--theme-text-secondary); max-width:150px;" contenteditable="true" data-field="point' + i + '_body" data-placeholder="Description" onblur="saveField(this)">' + escapeHtml(slideContent['point'+i+'_body'] || '') + '</div>' +
                    '</div>';
                });
                html += '</div></div>';
            } else if (layout === 'chart_single') {
                html += '<div class="slide-section-title" style="text-align:center;" contenteditable="true" data-field="title" data-placeholder="Chart Title" onblur="saveField(this)">' + escapeHtml(slideContent.title || '') + '</div>' +
                    '<div style="flex:1; display:flex; align-items:center; justify-content:center; margin:24px 0;">' +
                        '<div style="width:80%; height:300px; background:rgba(255,255,255,0.05); border-radius:8px; display:flex; align-items:center; justify-content:center; color:var(--text-muted);">[Chart Placeholder]</div>' +
                    '</div>' +
                    '<div class="slide-body" style="text-align:center;" contenteditable="true" data-field="insights" data-placeholder="Key insights..." onblur="saveField(this)">' + escapeHtml(slideContent.insights || '') + '</div>';
            } else if (layout === 'team_grid') {
                html += '<div class="slide-section-title" style="text-align:center;" contenteditable="true" data-field="title" data-placeholder="Our Team" onblur="saveField(this)">' + escapeHtml(slideContent.title || '') + '</div>' +
                    '<div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:32px; margin-top:40px;">';
                [1,2,3,4].forEach(i => {
                    html += '<div style="text-align:center;">' +
                        '<div style="width:120px; height:120px; background:rgba(255,255,255,0.1); border-radius:50%; margin:0 auto 16px; display:flex; align-items:center; justify-content:center; color:var(--text-muted);">Photo ' + i + '</div>' +
                        '<div style="font-weight:600; font-size:16px;" contenteditable="true" data-field="member' + i + '_name" data-placeholder="Name" onblur="saveField(this)">' + escapeHtml(slideContent['member'+i+'_name'] || '') + '</div>' +
                        '<div style="font-size:14px; color:var(--theme-text-secondary);" contenteditable="true" data-field="member' + i + '_title" data-placeholder="Title" onblur="saveField(this)">' + escapeHtml(slideContent['member'+i+'_title'] || '') + '</div>' +
                    '</div>';
                });
                html += '</div>';
            } else if (layout === 'video_embed') {
                html += '<div class="slide-section-title" style="text-align:center;" contenteditable="true" data-field="title" data-placeholder="Video Title" onblur="saveField(this)">' + escapeHtml(slideContent.title || '') + '</div>' +
                    '<div style="flex:1; display:flex; align-items:center; justify-content:center; margin:24px 0;">' +
                        '<div style="width:80%; aspect-ratio:16/9; background:rgba(255,255,255,0.05); border-radius:8px; display:flex; flex-direction:column; align-items:center; justify-content:center; color:var(--text-muted);">' +
                            '<div style="font-size:48px; margin-bottom:16px;">▶</div>' +
                            '<div>Video Placeholder</div>' +
                        '</div>' +
                    '</div>';
            } else {
                // Default fallback
                html += '<div class="slide-section-title" contenteditable="true" data-field="title" data-placeholder="Click to edit title" onblur="saveField(this)">' + escapeHtml(slideContent.title || '') + '</div>' +
                    '<div class="slide-body" style="margin-top:24px; text-align:center;" contenteditable="true" data-field="body" data-placeholder="Click to edit content..." onblur="saveField(this)">' + escapeHtml(slideContent.body || '') + '</div>';
            }
            html += '</div>';
            content.innerHTML = html;
            
            // Apply saved text styles and colors
            applySavedStyles();
        }
        
        function applySavedStyles() {
            if (!currentSlide || !currentSlide.content) return;
            
            // Find all contenteditable elements and apply saved styles/colors
            document.querySelectorAll('[contenteditable="true"][data-field]').forEach(function(el) {
                const field = el.dataset.field;
                
                // Apply text styles
                const styleKey = field + '_style';
                if (currentSlide.content[styleKey]) {
                    const styles = currentSlide.content[styleKey].split(',');
                    styles.forEach(function(style) {
                        if (style) el.classList.add('text-style-' + style);
                    });
                }
                
                // Apply text color
                const colorKey = field + '_color';
                if (currentSlide.content[colorKey]) {
                    el.style.color = currentSlide.content[colorKey];
                }
            });
            
            // Apply icon colors
            document.querySelectorAll('.icon-slot[data-field]').forEach(function(el) {
                const field = el.dataset.field;
                const colorKey = field + '_color';
                if (currentSlide.content[colorKey]) {
                    const svg = el.querySelector('svg');
                    if (svg) {
                        svg.style.stroke = currentSlide.content[colorKey];
                        svg.style.color = currentSlide.content[colorKey];
                    }
                }
            });
        }

        function renderIcon(iconName) {
            if (!iconName) {
                return '<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="opacity:0.3"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="9" x2="15" y2="15"/><line x1="15" y1="9" x2="9" y2="15"/></svg>';
            }
            // If icons object is empty, fetch synchronously as fallback
            if (Object.keys(icons).length === 0) {
                try {
                    const xhr = new XMLHttpRequest();
                    xhr.open('GET', '/data/lucide_icons.json', false); // synchronous
                    xhr.send();
                    if (xhr.status === 200) {
                        const data = JSON.parse(xhr.responseText);
                        icons = data.icons || data || {};
                    }
                } catch (e) { console.error('Sync icon fetch failed:', e); }
            }
            if (!icons[iconName]) {
                return '<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="opacity:0.3"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="9" x2="15" y2="15"/><line x1="15" y1="9" x2="9" y2="15"/></svg>';
            }
            return '<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + icons[iconName] + '</svg>';
        }

        function escapeHtml(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        async function saveField(element) {
            const field = element.dataset.field;
            const value = element.textContent.trim();
            if (!currentSlide) return;
            if (!currentSlide.content) currentSlide.content = {};
            currentSlide.content[field] = value;
            showSaving();
            clearTimeout(saveTimeout);
            saveTimeout = setTimeout(function() { saveSlide(); }, 500);
        }

        async function saveNestedField(element) {
            const field = element.dataset.field;
            const value = element.textContent.trim();
            if (!currentSlide) return;
            const parts = field.split('.');
            if (!currentSlide.content) currentSlide.content = {};
            if (parts[0] === 'stats') {
                if (!currentSlide.content.stats) currentSlide.content.stats = [{}, {}, {}, {}];
                const idx = parseInt(parts[1]);
                const prop = parts[2];
                currentSlide.content.stats[idx][prop] = value;
            }
            showSaving();
            clearTimeout(saveTimeout);
            saveTimeout = setTimeout(function() { saveSlide(); }, 500);
        }

        async function saveBullet(element) {
            const idx = parseInt(element.dataset.index);
            const value = element.textContent.trim();
            if (!currentSlide) return;
            if (!currentSlide.content) currentSlide.content = {};
            if (!currentSlide.content.bullets) currentSlide.content.bullets = [];
            currentSlide.content.bullets[idx] = value;
            showSaving();
            clearTimeout(saveTimeout);
            saveTimeout = setTimeout(function() { saveSlide(); }, 500);
        }

        function handleBulletKey(event, element) {
            if (event.key === 'Enter') {
                event.preventDefault();
                const idx = parseInt(element.dataset.index);
                if (!currentSlide.content.bullets) currentSlide.content.bullets = [];
                currentSlide.content.bullets.splice(idx + 1, 0, '');
                saveSlide().then(function() {
                    renderSlideCanvas();
                    setTimeout(function() {
                        const newBullet = document.querySelector('[data-field="bullets"][data-index="' + (idx + 1) + '"]');
                        if (newBullet) newBullet.focus();
                    }, 50);
                });
            } else if (event.key === 'Backspace' && element.textContent === '') {
                event.preventDefault();
                const idx = parseInt(element.dataset.index);
                if (currentSlide.content.bullets && currentSlide.content.bullets.length > 1) {
                    currentSlide.content.bullets.splice(idx, 1);
                    saveSlide().then(function() {
                        renderSlideCanvas();
                        setTimeout(function() {
                            const prevIdx = Math.max(0, idx - 1);
                            const prevBullet = document.querySelector('[data-field="bullets"][data-index="' + prevIdx + '"]');
                            if (prevBullet) prevBullet.focus();
                        }, 50);
                    });
                }
            }
        }

        async function saveSlide() {
            if (!currentSlide || !currentDeck) return;
            const result = await apiCall('slide_designer', 'update_slide', { slide_id: currentSlide.id, content: currentSlide.content });
            hideSaving();
            renderSlideList(); // Update thumbnails
            if (result.status !== 'success') showToast('Failed to save', 'error');
        }

        function showSaving() { document.getElementById('savingIndicator').classList.add('active'); }
        function hideSaving() { document.getElementById('savingIndicator').classList.remove('active'); }

        function openLayoutPicker() {
            if (!currentDeck) { showToast('Select or create a deck first', 'error'); return; }
            document.getElementById('layoutPickerModal').classList.add('active');
        }

        function closeLayoutPicker() { document.getElementById('layoutPickerModal').classList.remove('active'); }

        function renderLayoutGrid() {
            const container = document.getElementById('layoutGrid');
            container.innerHTML = layouts.map(function(layout) {
                const preview = layoutPreviews[layout.id] || layoutPreviews.title_hero;
                return '<div class="layout-card" onclick="createSlide(\'' + layout.id + '\')"><div class="layout-preview ' + preview.class + '"><div class="layout-preview-content">' + preview.html + '</div></div><div class="layout-name">' + layout.name + '</div></div>';
            }).join('');
        }

        async function createSlide(layoutId) {
            closeLayoutPicker();
            const layout = layouts.find(function(l) { return l.id === layoutId; });
            if (!layout) return;
            const content = {};
            if (layout.slots) {
                layout.slots.forEach(function(slot) {
                    if (slot.type === 'text') content[slot.id] = '';
                    else if (slot.type === 'icon') content[slot.id] = 'star';
                });
            }
            const result = await apiCall('slide_designer', 'add_slide', { deck_id: currentDeck, layout_type: layoutId, content: content, index: slides.length });
            if (result.status === 'success') {
                // Reload deck to get updated slides
                const deckResult = await apiCall('slide_designer', 'get_deck', { deck_id: currentDeck });
                if (deckResult.status === 'success') {
                    slides = (deckResult.deck && deckResult.deck.slides) ? deckResult.deck.slides : [];
                    renderSlideList();
                    if (result.slide_id) selectSlide(result.slide_id);
                }
                showToast('Slide created', 'success');
            } else showToast('Failed to create slide', 'error');
        }

        async function deleteSlide(slideId) {
            if (!confirm('Delete this slide?')) return;
            const result = await apiCall('slide_designer', 'delete_slide', { slide_id: slideId });
            if (result.status === 'success') {
                // Reload deck
                const deckResult = await apiCall('slide_designer', 'get_deck', { deck_id: currentDeck });
                if (deckResult.status === 'success') {
                    slides = (deckResult.deck && deckResult.deck.slides) ? deckResult.deck.slides : [];
                    renderSlideList();
                    if (slides.length > 0) {
                        currentSlideIndex = Math.min(currentSlideIndex, slides.length - 1);
                        selectSlide(slides[currentSlideIndex].id);
                    } else {
                        currentSlide = null;
                        showEmptyState();
                    }
                }
                showToast('Slide deleted', 'success');
            }
        }

        async function deleteDeck(deckId, deckTitle) {
            if (!confirm('Delete deck "' + deckTitle + '" and all its slides?')) return;
            const result = await apiCall('slide_designer', 'delete_deck', { deck_id: deckId });
            if (result.status === 'success') {
                showToast('Deck deleted', 'success');
                loadDecks();
            } else {
                showToast(result.message || 'Failed to delete deck', 'error');
            }
        }

        function openIconPicker(fieldName) {
            activeIconSlot = fieldName;
            document.getElementById('iconSearch').value = '';
            renderIconGrid('');
            document.getElementById('iconPickerModal').classList.add('active');
        }

        function closeIconPicker() {
            document.getElementById('iconPickerModal').classList.remove('active');
            activeIconSlot = null;
        }

        function filterIcons(query) { renderIconGrid(query.toLowerCase()); }

        function renderIconGrid(filter) {
            const container = document.getElementById('iconGrid');
            const iconNames = Object.keys(icons).filter(function(name) {
                return !name.startsWith('_') && name !== 'semantic_mapping' && (!filter || name.includes(filter));
            }).slice(0, 100);
            container.innerHTML = iconNames.map(function(name) {
                return '<div class="icon-option" onclick="selectIcon(\'' + name + '\')" title="' + name + '"><svg viewBox="0 0 24 24">' + icons[name] + '</svg></div>';
            }).join('');
        }

        async function selectIcon(iconName) {
            if (!activeIconSlot || !currentSlide) return;
            if (!currentSlide.content) currentSlide.content = {};
            currentSlide.content[activeIconSlot] = iconName;
            closeIconPicker();
            await saveSlide();
            // Fully re-render the canvas to ensure icon renders correctly
            renderSlideCanvas();
            showToast('Icon updated', 'success');
        }

        function zoomIn() { zoomLevel = Math.min(150, zoomLevel + 10); updateZoom(); }
        function zoomOut() { zoomLevel = Math.max(50, zoomLevel - 10); updateZoom(); }
        function updateZoom() {
            document.getElementById('zoomLevel').textContent = zoomLevel + '%';
            document.getElementById('slideCanvas').style.transform = 'scale(' + (zoomLevel / 100) + ')';
        }

        // Present Mode
        function startPresent() {
            if (slides.length === 0) { showToast('No slides to present', 'error'); return; }
            isPresentMode = true;
            currentSlideIndex = 0;
            document.getElementById('presentMode').classList.add('active');
            const counter = document.getElementById('presentCounter');
            if (counter) counter.textContent = `1 / ${slides.length}`;
            renderPresentSlide();
        }

        function exitPresent() {
            isPresentMode = false;
            document.getElementById('presentMode').classList.remove('active');
        }

        function renderPresentSlide() {
            if (!isPresentMode || slides.length === 0) return;
            const slide = slides[currentSlideIndex];
            const container = document.getElementById('presentSlide');
            const counter = document.getElementById('presentCounter');
            if (counter) counter.textContent = `${currentSlideIndex + 1} / ${slides.length}`;

            const layout = slide.layout_type;
            const content = slide.content || {};
            const isCentered = centeredLayouts.includes(layout);

            // Apply theme vars to present slide container
            if (container) {
                const themeSelector = document.getElementById('themeSelector');
                const themeName = themeSelector ? themeSelector.value : 'dark_pro';
                const theme = themes[themeName] || themes['dark_pro'];
                if (theme && theme.css_vars) {
                    Object.entries(theme.css_vars).forEach(([key, value]) => {
                        container.style.setProperty(key, value);
                    });
                    container.style.background = theme.css_vars['--theme-bg'] || CONFIG.colors.color_1;
                }
            }

            // Full rendering — same as editor but without contenteditable
            let html = `<div class="slide-content ${isCentered ? 'centered' : ''}" style="pointer-events:none; width:100%; height:100%; padding:48px; display:flex; flex-direction:column; color:var(--theme-text);">`;

            if (layout === 'title_hero') {
                html += `<div class="slide-headline">${escapeHtml(content.headline || '')}</div>
                    <div class="slide-subtitle">${escapeHtml(content.subtitle || '')}</div>`;
            } else if (layout === 'headline') {
                html += `<div class="slide-headline">${escapeHtml(content.headline || '')}</div>`;
            } else if (layout === 'big_number') {
                html += `<div class="slide-big-number">${escapeHtml(content.number || '')}</div>
                    <div class="slide-stat-label">${escapeHtml(content.label || '')}</div>`;
            } else if (layout === 'quote') {
                html += `<div style="max-width:800px;">
                    <div class="slide-quote">${escapeHtml(content.quote_text || '')}</div>
                    <div class="slide-author">${escapeHtml(content.author_name || '')}</div>
                    <div class="slide-author" style="font-size:14px;opacity:0.7;">${escapeHtml(content.author_title || '')}</div>
                </div>`;
            } else if (layout === 'bullet_list') {
                const bullets = content.bullets || [];
                html += `<div class="slide-section-title">${escapeHtml(content.title || '')}</div>
                    <ul class="slide-bullets">${bullets.map(b => `<li>${escapeHtml(b)}</li>`).join('')}</ul>`;
            } else if (layout === 'stats_row') {
                const stats = content.stats || [];
                html += `<div class="slide-section-title" style="text-align:center;">${escapeHtml(content.header || '')}</div>
                    <div class="slide-stats-row">${stats.map(s => `<div class="slide-stat-item">
                        <div class="slide-stat-number">${escapeHtml(s.number || '')}</div>
                        <div class="slide-stat-label">${escapeHtml(s.label || '')}</div>
                    </div>`).join('')}</div>`;
            } else if (layout === 'three_column') {
                html += `<div class="slide-section-title" style="text-align:center;">${escapeHtml(content.header || '')}</div>
                    <div class="slide-grid-3">${[1,2,3].map(i => `<div class="slide-grid-item">
                        <div class="slide-item-icon">${renderIcon(content['col'+i+'_icon'])}</div>
                        <div class="slide-item-title">${escapeHtml(content['col'+i+'_title'] || '')}</div>
                        <div class="slide-item-body">${escapeHtml(content['col'+i+'_body'] || '')}</div>
                    </div>`).join('')}</div>`;
            } else if (layout === 'four_grid') {
                html += `<div class="slide-section-title" style="text-align:center;">${escapeHtml(content.header || '')}</div>
                    <div class="slide-grid-4">${[1,2,3,4].map(i => `<div class="slide-grid-item">
                        <div class="slide-item-icon">${renderIcon(content['cell'+i+'_icon'])}</div>
                        <div class="slide-item-title">${escapeHtml(content['cell'+i+'_title'] || '')}</div>
                        <div class="slide-item-body">${escapeHtml(content['cell'+i+'_body'] || '')}</div>
                    </div>`).join('')}</div>`;
            } else if (layout === 'split_content') {
                html += `<div class="slide-split">
                    <div class="slide-split-content">
                        <div class="slide-section-title">${escapeHtml(content.left_title || '')}</div>
                        <div class="slide-body" style="margin-top:16px;">${escapeHtml(content.left_body || '')}</div>
                    </div>
                    <div class="slide-split-image"><span style="color:var(--theme-text-secondary)">Image</span></div>
                </div>`;
            } else if (layout === 'text_only') {
                html += `<div class="slide-section-title">${escapeHtml(content.title || '')}</div>
                    <div class="slide-body" style="flex:1;margin-top:24px;">${escapeHtml(content.body || '')}</div>`;
            } else if (layout === 'agenda') {
                const items = content.agenda_items || [];
                html += `<div class="slide-section-title" style="text-align:center;">${escapeHtml(content.title || 'Agenda')}</div>
                    <div style="margin-top:32px;display:flex;flex-direction:column;gap:16px;">
                    ${items.map((item, i) => `<div style="display:flex;align-items:center;gap:16px;padding:16px;background:rgba(255,255,255,0.05);border-radius:8px;">
                        <div style="width:32px;height:32px;background:var(--theme-accent);border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:600;">${i+1}</div>
                        <div style="font-size:18px;">${escapeHtml(item)}</div>
                    </div>`).join('')}</div>`;
            } else if (layout === 'section_break' || layout === 'section_divider') {
                html += `<div style="font-size:72px;font-weight:800;color:var(--theme-accent);opacity:0.3;">${escapeHtml(content.section_number || '')}</div>
                    <div class="slide-headline" style="font-size:36px;">${escapeHtml(content.section_title || '')}</div>`;
            } else if (layout === 'cta_closing') {
                html += `<div class="slide-headline">${escapeHtml(content.headline || '')}</div>
                    <div class="slide-subtitle">${escapeHtml(content.subtext || '')}</div>
                    <div style="margin-top:32px;padding:12px 32px;background:var(--theme-accent);border-radius:8px;display:inline-block;">${escapeHtml(content.cta_button || '')}</div>`;
            } else {
                html += `<div class="slide-section-title">${escapeHtml(content.title || content.header || content.headline || '')}</div>
                    <div class="slide-body" style="margin-top:24px;">${escapeHtml(content.body || '')}</div>`;
            }

            html += '</div>';
            container.innerHTML = html;
        }

        async function exportDeck() {
            if (!currentDeck) { showToast('No deck selected', 'error'); return; }
            const result = await apiCall('slide_designer', 'export_html', { deck_id: currentDeck });
            if (result.status === 'success') showToast('Deck exported to ' + result.output_path, 'success');
            else showToast('Export failed', 'error');
        }

        function showToast(message, type) {
            type = type || 'success';
            const toast = document.getElementById('toast');
            const toastMessage = document.getElementById('toastMessage');
            toastMessage.textContent = message;
            toast.className = 'toast ' + type + ' show';
            setTimeout(function() { toast.classList.remove('show'); }, 3000);
        }

        // ==========================================
        // FONT PAIRING FUNCTIONALITY
        // ==========================================
        let currentFontPairing = 'classic';

        function applyFontPairing(pairing) {
            currentFontPairing = pairing;
            const canvas = document.getElementById('slideCanvas');
            const presentSlide = document.getElementById('presentSlide');
            
            // Remove all font classes
            ['font-classic', 'font-editorial', 'font-technical', 'font-humanist'].forEach(cls => {
                canvas.classList.remove(cls);
                if (presentSlide) presentSlide.classList.remove(cls);
                document.documentElement.classList.remove(cls);
            });
            
            // Add the new font class
            canvas.classList.add('font-' + pairing);
            if (presentSlide) presentSlide.classList.add('font-' + pairing);
            document.documentElement.classList.add('font-' + pairing);
            
            // Save to backend if we have a deck open
            if (currentDeck) {
                saveFontPairing(pairing);
            }
        }

        async function saveFontPairing(pairing) {
            const result = await apiCall('slide_designer', 'update_deck', { 
                deck_id: currentDeck, 
                font_pairing: pairing 
            });
            if (result.status === 'success') {
                showToast('Font pairing saved', 'success');
            }
        }

        // ==========================================
        // FLOATING TEXT TOOLBAR FUNCTIONALITY
        // ==========================================
        let activeTextCell = null;

        // Show toolbar when text cell is clicked
        document.addEventListener('focusin', function(e) {
            if (e.target.contentEditable === 'true' && e.target.dataset.field) {
                activeTextCell = e.target;
                showTextToolbar(e.target);
            }
        });

        // Hide toolbar on blur (with delay to allow button clicks)
        document.addEventListener('focusout', function(e) {
            if (e.target.contentEditable === 'true') {
                setTimeout(function() {
                    if (!document.getElementById('textToolbar').contains(document.activeElement)) {
                        hideTextToolbar();
                    }
                }, 150);
            }
        });

        function showTextToolbar(element) {
            const toolbar = document.getElementById('textToolbar');
            const rect = element.getBoundingClientRect();
            
            // Position above the element
            toolbar.style.left = rect.left + 'px';
            toolbar.style.top = (rect.top - 50) + 'px';
            toolbar.classList.add('visible');
            
            // Update button states based on current styles
            updateToolbarButtonStates(element);
        }

        function hideTextToolbar() {
            document.getElementById('textToolbar').classList.remove('visible');
            hideColorSwatches();
        }

        function updateToolbarButtonStates(element) {
            const boldBtn = document.getElementById('boldBtn');
            const italicBtn = document.getElementById('italicBtn');
            
            if (element.classList.contains('text-style-bold')) {
                boldBtn.classList.add('active');
            } else {
                boldBtn.classList.remove('active');
            }
            
            if (element.classList.contains('text-style-italic')) {
                italicBtn.classList.add('active');
            } else {
                italicBtn.classList.remove('active');
            }
        }

        function applyTextStyle(style) {
            if (!activeTextCell) return;
            
            // Remove existing style classes
            activeTextCell.classList.remove('text-style-heading', 'text-style-subheading', 'text-style-body');
            
            // Add the new style class
            activeTextCell.classList.add('text-style-' + style);
            
            // Save the style to the slide content
            saveTextStyle(activeTextCell, style);
        }

        function toggleTextStyle(style) {
            if (!activeTextCell) return;
            
            const className = 'text-style-' + style;
            if (activeTextCell.classList.contains(className)) {
                activeTextCell.classList.remove(className);
            } else {
                activeTextCell.classList.add(className);
            }
            
            // Update button state
            updateToolbarButtonStates(activeTextCell);
            
            // Save the style
            saveTextStyle(activeTextCell, null);
        }

        async function saveTextStyle(element, style) {
            if (!currentSlide || !element.dataset.field) return;
            
            // Get current styles as array
            const styles = [];
            if (element.classList.contains('text-style-heading')) styles.push('heading');
            else if (element.classList.contains('text-style-subheading')) styles.push('subheading');
            else if (element.classList.contains('text-style-body')) styles.push('body');
            if (element.classList.contains('text-style-bold')) styles.push('bold');
            if (element.classList.contains('text-style-italic')) styles.push('italic');
            
            // Store styles in content
            const field = element.dataset.field;
            if (!currentSlide.content) currentSlide.content = {};
            currentSlide.content[field + '_style'] = styles.join(',');
            
            // Save slide
            await saveSlide();
        }

        // ==========================================
        // COLOR SWATCHES FUNCTIONALITY
        // ==========================================
        let colorSwatchTarget = null;
        let colorSwatchType = null; // 'text' or 'icon'

        function openTextColorSwatches() {
            colorSwatchTarget = activeTextCell;
            colorSwatchType = 'text';
            
            const popup = document.getElementById('textColorSwatches');
            const toolbar = document.getElementById('textToolbar');
            const rect = toolbar.getBoundingClientRect();
            
            // Get theme colors
            const root = getComputedStyle(document.documentElement);
            const colors = [
                { name: 'Primary', color: root.getPropertyValue('--theme-text').trim() || CONFIG.colors.color_2 },
                { name: 'Secondary', color: root.getPropertyValue('--theme-text-secondary').trim() || CONFIG.colors.color_0 },
                { name: 'Accent', color: root.getPropertyValue('--theme-accent').trim() || CONFIG.colors.color_3 }
            ];
            
            renderColorSwatches(popup, colors);
            popup.style.left = rect.left + 'px';
            popup.style.top = (rect.bottom + 8) + 'px';
            popup.classList.add('visible');
        }

        function openIconColorSwatches(iconElement, event) {
            event.stopPropagation();
            colorSwatchTarget = iconElement;
            colorSwatchType = 'icon';
            
            const popup = document.getElementById('iconColorSwatches');
            const rect = iconElement.getBoundingClientRect();
            
            // Get theme colors - 5 swatches for icons
            const root = getComputedStyle(document.documentElement);
            const accent = root.getPropertyValue('--theme-accent').trim() || CONFIG.colors.color_3;
            const text = root.getPropertyValue('--theme-text').trim() || CONFIG.colors.color_2;
            const secondary = root.getPropertyValue('--theme-text-secondary').trim() || CONFIG.colors.color_0;
            const bg = root.getPropertyValue('--theme-bg').trim() || CONFIG.colors.color_1;
            const surface = root.getPropertyValue('--theme-surface').trim() || CONFIG.colors.color_4;
            
            const colors = [
                { name: 'Accent', color: accent },
                { name: 'Text', color: text },
                { name: 'Secondary', color: secondary },
                { name: 'Surface', color: surface },
                { name: 'Background', color: bg }
            ];
            
            renderColorSwatches(popup, colors);
            popup.style.left = rect.left + 'px';
            popup.style.top = (rect.bottom + 8) + 'px';
            popup.classList.add('visible');
        }

        function renderColorSwatches(popup, colors) {
            popup.innerHTML = colors.map(c => 
                '<div class="color-swatch" style="background:' + c.color + ';" ' +
                'onclick="applyColor(\'' + c.color + '\')" title="' + c.name + '"></div>'
            ).join('');
        }

        function applyColor(color) {
            if (!colorSwatchTarget) return;
            
            if (colorSwatchType === 'text') {
                colorSwatchTarget.style.color = color;
                // Save to slide content
                if (currentSlide && colorSwatchTarget.dataset.field) {
                    const field = colorSwatchTarget.dataset.field;
                    if (!currentSlide.content) currentSlide.content = {};
                    currentSlide.content[field + '_color'] = color;
                    saveSlide();
                }
            } else if (colorSwatchType === 'icon') {
                // Color the SVG
                const svg = colorSwatchTarget.querySelector('svg');
                if (svg) {
                    svg.style.stroke = color;
                    svg.style.color = color;
                }
                // Save to slide content
                if (currentSlide && colorSwatchTarget.dataset.field) {
                    const field = colorSwatchTarget.dataset.field;
                    if (!currentSlide.content) currentSlide.content = {};
                    currentSlide.content[field + '_color'] = color;
                    saveSlide();
                }
            }
            
            hideColorSwatches();
            showToast('Color applied', 'success');
        }

        function hideColorSwatches() {
            document.getElementById('textColorSwatches').classList.remove('visible');
            document.getElementById('iconColorSwatches').classList.remove('visible');
        }

        // Hide color swatches when clicking outside
        document.addEventListener('click', function(e) {
            const textPopup = document.getElementById('textColorSwatches');
            const iconPopup = document.getElementById('iconColorSwatches');
            if (!textPopup.contains(e.target) && !iconPopup.contains(e.target) && 
                !e.target.classList.contains('text-toolbar-btn') && !e.target.classList.contains('icon-slot')) {
                hideColorSwatches();
            }
        });
    

