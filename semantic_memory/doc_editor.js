// Config loaded from doc_editor_config.json
        let editorConfig = null;

        // ========== SWIFT BRIDGE ABSTRACTION ==========
        // Detect if running inside Swift WebView (SWIFT_MODE injected at document start)
        const isSwiftMode = () => window.SWIFT_MODE === true;

        // Post message to Swift bridge
        function swiftPost(action, data = {}) {
            if (window.webkit?.messageHandlers?.swiftBridge) {
                window.webkit.messageHandlers.swiftBridge.postMessage({ action, ...data });
            }
        }

        // Swift callback receivers - Swift calls these after bridge operations
        window.swiftLoadDoc = function(jsonStr) {
            try {
                const doc = JSON.parse(jsonStr);
                document.body.classList.remove('timeline-mode');
                currentDocId = doc.id;
                docContentCache.set(doc.id, doc);
                document.getElementById('docTitle').value = doc.title || '';
                document.getElementById('docContent').innerHTML = doc.content || '';
                setCollection(doc.collection || 'Notes');
                lastKnownUpdatedAt = doc.updated_at;
                document.getElementById('docMeta').innerHTML = `
                    <span>Created ${formatDate(doc.created_at)}</span>
                    <span>Updated ${formatDate(doc.updated_at)}</span>
                `;
                document.getElementById('editorContainer').style.display = 'block';
                document.getElementById('emptyState').style.display = 'none';
                document.getElementById('deleteBtn').style.display = 'block';
                document.getElementById('queueTaskBtn').style.display = 'block';
                document.getElementById('copyDocIdBtn').style.display = 'block';
                document.getElementById('downloadPdfBtn').style.display = 'block';
                document.getElementById('markDeployedBtn').style.display = 'block';
                document.getElementById('docNavBtns').style.display = 'flex';
                updateNavButtons();
                renderDocList();
                loadBacklinks(doc.id);
                attachDocLinkHandlers();
                initCollapsibleHeaders();
            } catch (e) {
                console.error('swiftLoadDoc parse error:', e);
            }
        };

        window.swiftListDocs = function(jsonStr) {
            try {
                docs = JSON.parse(jsonStr);
                allDocsCache = docs;  // Populate cache for timeline view
                updateCollectionFilter();
                renderDocList();
                renderTimeline();  // Render timeline now that docs are loaded
            } catch (e) {
                console.error('swiftListDocs parse error:', e);
            }
        };

        window.swiftSaveComplete = function(result) {
            pendingSave = false;
            document.getElementById('saveStatus').textContent = 'Saved';
            document.getElementById('saveStatus').className = 'save-status saved';
            // In Swift mode, just call listDocs to refresh the sidebar
            if (isSwiftMode()) {
                swiftPost('listDocs');
            }
        };

        window.swiftTaskResult = function(jsonStr) {
            try {
                const result = JSON.parse(jsonStr);
                console.log('Swift task result:', result);
                // Handle specific task results as needed
            } catch (e) {
                console.error('swiftTaskResult parse error:', e);
            }
        };

        window.swiftDeleteComplete = function() {
            currentDocId = null;
            document.getElementById('editorContainer').style.display = 'none';
            document.getElementById('emptyState').style.display = 'flex';
            document.getElementById('deleteBtn').style.display = 'none';
            document.getElementById('queueTaskBtn').style.display = 'none';
            document.getElementById('copyDocIdBtn').style.display = 'none';
            document.getElementById('downloadPdfBtn').style.display = 'none';
            document.getElementById('markDeployedBtn').style.display = 'none';
            // listDocs is called automatically by Swift after delete
        };
        // ========== END SWIFT BRIDGE ==========

        let currentDocId = null;
        let currentDisplayedDocs = []; // Track currently displayed docs for navigation
        let saveTimeout = null;
        let pendingSave = false; // Prevent auto-refresh from overwriting unsaved edits
        let docs = [];
        let docOpenedFromCollection = null; // Track collection context when opening doc
        let navDocsLocked = false; // Lock nav list while viewing a doc from timeline
        let isPollingRefresh = false; // Flag for background polling - prevents disturbing active doc
        // Collections loaded from doc_editor_config.json by loadEditorConfig()
        let defaultCollections = [];
        let EXCLUDED_COLLECTIONS = [];
        const docContent = document.getElementById('docContent');
        let savedSelection = null; // Saved before toolbar mousedown clears it
        let docContentCache = new Map(); // Cache full doc content to avoid redundant fetches

        // Load config from external JSON file
        async function loadEditorConfig() {
            // In Swift mode, config is injected via SWIFT_EDITOR_CONFIG
            if (isSwiftMode() && window.SWIFT_EDITOR_CONFIG) {
                editorConfig = window.SWIFT_EDITOR_CONFIG;
                applyEditorConfig();
                console.log('Editor config loaded from Swift injection');
                return;
            }
            try {
                const response = await fetch('/semantic_memory/doc_editor_config.json?_=' + Date.now());
                if (!response.ok) throw new Error('Config file not found');
                editorConfig = await response.json();

                // Apply collections from config
                if (editorConfig.collections) {
                    if (editorConfig.collections.defaultCollections) {
                        defaultCollections = editorConfig.collections.defaultCollections;
                    }
                    if (editorConfig.collections.excludedCollections) {
                        EXCLUDED_COLLECTIONS = editorConfig.collections.excludedCollections;
                    }
                }

                // Apply slash menu items from config
                if (editorConfig.slashMenuItems && Array.isArray(editorConfig.slashMenuItems)) {
                    SlashMenu.commands = editorConfig.slashMenuItems.map(item => ({
                        cmd: item.cmd,
                        alias: item.alias,
                        label: item.label,
                        icon: item.icon,
                        action: item.action === 'executeTask' 
                            ? () => executeTaskSlashCommand(item)
                            : getActionFunction(item.action)
                    }));
                    // Update backwards compatibility reference
                    slashCommands.length = 0;
                    slashCommands.push(...SlashMenu.commands);
                }

                // Render toolbar from config
                renderToolbarFromConfig();
                
                console.log('Editor config loaded successfully');
            } catch (e) {
                console.warn('Failed to load editor config, using defaults:', e);
            }
        }

        // Helper to apply editor config (used by both fetch and Swift injection paths)
        function applyEditorConfig() {
            if (!editorConfig) return;
            // Apply collections from config
            if (editorConfig.collections) {
                if (editorConfig.collections.defaultCollections) {
                    defaultCollections = editorConfig.collections.defaultCollections;
                }
                if (editorConfig.collections.excludedCollections) {
                    EXCLUDED_COLLECTIONS = editorConfig.collections.excludedCollections;
                }
            }
            // Apply slash menu items from config
            if (editorConfig.slashMenuItems && Array.isArray(editorConfig.slashMenuItems)) {
                SlashMenu.commands = editorConfig.slashMenuItems.map(item => ({
                    cmd: item.cmd,
                    alias: item.alias,
                    label: item.label,
                    icon: item.icon,
                    action: getActionFunction(item.action)
                }));
                slashCommands.length = 0;
                slashCommands.push(...SlashMenu.commands);
            }
            renderToolbarFromConfig();
        }

        // Map action strings from config to actual functions
        function getActionFunction(actionName) {
            const actionMap = {
                'formatH1': () => format('h1'),
                'formatH2': () => format('h2'),
                'formatH3': () => format('h3'),
                'insertCodeBlock': () => insertCodeBlock(),
                'insertTable': () => insertTable(),
                'formatUL': () => format('ul'),
                'formatOL': () => format('ol'),
                'formatQuote': () => format('quote'),
                'formatHR': () => format('hr'),
            'formatP': () => format('p'),
            'formatStrikethrough': () => format('strikethrough'),
            'respondToDoc': () => respondToDoc(),
            'summarizeVideo': () => summarizeVideo(),
            'runViralityAnalysis': () => runViralityAnalysis(),
            'generateLinkedinPosts': () => generateLinkedinPosts(),
            'generateTwitterKnowledge': () => generateTwitterKnowledge(),
            'approveSocial': () => approveSocial(),
            'factCheck': () => factCheck(),
            'consolidateDoc': () => consolidateDoc()
            };
            // Generic handler: if action not in map, check if it's a tool.action execute_task call
            // Config entry needs: action: "executeTask", tool: "tool_name", taskAction: "action_name", params: {}
            if (!actionMap[actionName]) {
                return () => console.warn('Unknown action:', actionName);
            }
            return actionMap[actionName];
        }

        // Generic execute_task slash command handler
        // Config entry format: { cmd: "foo", label: "Foo", action: "executeTask", tool: "claude_assistant", taskAction: "assign_task", params: { description: "..." } }
        function executeTaskSlashCommand(item) {
            if (!item || !item.tool || !item.taskAction) {
                console.warn('executeTaskSlashCommand: missing tool or taskAction in config');
                return;
            }
            fetch('/execute_task', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    tool_name: item.tool,
                    action: item.taskAction,
                    params: item.params || {}
                })
            })
            .then(res => res.json())
            .then(() => {
                const toast = document.createElement('div');
                toast.textContent = item.toast || '✅ Done';
                toast.style.cssText = 'position:fixed;bottom:20px;right:20px;background:#6366f1;color:white;padding:12px 20px;border-radius:8px;z-index:10000;font-size:14px;';
                document.body.appendChild(toast);
                setTimeout(() => toast.remove(), 2500);
            })
            .catch(err => console.error('executeTaskSlashCommand failed:', err));
        }

        // Render toolbar buttons from config
        function renderToolbarFromConfig() {
            if (!editorConfig || !editorConfig.toolbarButtons) return;
            const toolbar = document.getElementById('floatingToolbar');
            if (!toolbar) return;
            
            // Clear existing buttons and rebuild from config
            toolbar.innerHTML = editorConfig.toolbarButtons.map(btn => {
                const actionFn = getToolbarAction(btn.action);
                return `<button class="toolbar-btn" onmousedown="event.preventDefault();if(window.getSelection().rangeCount){savedSelection=window.getSelection().getRangeAt(0).cloneRange();}${actionFn}" title="${btn.tooltip || btn.label}">${btn.icon}</button>`;
            }).join('');
        }

        // Map toolbar action strings to onclick handlers
        function getToolbarAction(actionName) {
            const actionMap = {
                'bold': "format('bold')",
                'italic': "format('italic')",
                'strikethrough': "format('strikethrough')",
                'inlineCode': "format('code')",
                'insertLink': "format('link')",
                'formatH1': "format('h1')",
                'formatH2': "format('h2')",
                'formatH3': "format('h3')",
                'formatH4': "format('h4')",
                'formatQuote': "format('quote')",
                'formatUL': "format('ul')",
                'formatOL': "format('ol')",
                'formatHR': "format('hr')",
                'formatP': "format('p')",
                'showImageModal': "showImageModal()"
            };
            return actionMap[actionName] || "console.warn('Unknown toolbar action')";
        }

        // Get keyboard shortcut action from config
        function getKeyboardShortcutAction(shortcutKey) {
            if (!editorConfig || !editorConfig.keyboardShortcuts) return null;
            return editorConfig.keyboardShortcuts[shortcutKey];
        }

        // Get polling interval from config with fallback
        function getPollingInterval(intervalName, defaultValue) {
            if (!editorConfig || !editorConfig.pollingIntervals) return defaultValue;
            return editorConfig.pollingIntervals[intervalName] || defaultValue;
        }


        // BLOCK DETECTION HELPER
        // Use this everywhere block detection happens in the editor
        function getEditableBlock(node) {
            let el = node.nodeType === 3 ? node.parentElement : node;
            // If el is docContent itself (cursor at end of doc with no block), return last child
            if (el === docContent) {
                return docContent.lastElementChild || null;
            }
            while (el && el !== docContent) {
                if (el.parentElement === docContent) return el;
                el = el.parentElement;
            }
            return null;
        }


        // === SlashMenu Object ===
        // Self-contained slash command menu. All slash menu logic lives here.
        const SlashMenu = {
            visible: false,
            filterText: '',
            selectedIndex: 0,
            savedRange: null,
            commands: [], // Populated from doc_editor_config.json by loadEditorConfig()
            
            show(x, y) {
                const menu = document.getElementById('slashMenu');
                menu.style.left = x + 'px';
                menu.style.top = y + 'px';
                menu.classList.add('visible');
                this.visible = true;
                this.selectedIndex = 0;
                this.render('');
            },
            
            hide() {
                const menu = document.getElementById('slashMenu');
                menu.classList.remove('visible');
                this.visible = false;
                this.filterText = '';
                this.savedRange = null;
            },
            
            render(filter) {
                const menu = document.getElementById('slashMenu');
                const filterLower = filter.toLowerCase();
                
                const filtered = this.commands.filter(c => 
                    c.cmd.includes(filterLower) || 
                    (c.alias && c.alias.includes(filterLower)) ||
                    c.label.toLowerCase().includes(filterLower)
                );

                if (filtered.length === 0) {
                    menu.innerHTML = '<div class="slash-menu-item" style="color: var(--text-muted); pointer-events: none;">No matches</div>';
                    menu.filteredCommands = [];
                    return;
                }

                menu.innerHTML = filtered.map((c, i) => `
                    <div class="slash-menu-item${i === this.selectedIndex ? ' selected' : ''}" data-index="${i}">
                        <span class="slash-menu-item-icon">${c.icon}</span>
                        <span class="slash-menu-item-label">${c.label}</span>
                        <span class="slash-menu-item-shortcut">/${c.cmd}</span>
                    </div>
                `).join('');

                menu.filteredCommands = filtered;
            },
            
            select(index) {
                const menu = document.getElementById('slashMenu');
                const filtered = menu.filteredCommands || this.commands;
                if (index >= 0 && index < filtered.length) {
                    const cmd = filtered[index];
                    
                    if (this.savedRange) {
                        const sel = window.getSelection();
                        sel.removeAllRanges();
                        sel.addRange(this.savedRange);
                        
                        const range = sel.getRangeAt(0);
                        // Calculate offset with bounds checking to prevent IndexSizeError
                        const node = range.startContainer;
                        const maxOffset = node.nodeType === 3 ? node.length : node.childNodes.length;
                        let newOffset = range.startOffset - this.filterText.length - 1;
                        newOffset = Math.max(0, Math.min(newOffset, maxOffset));
                        range.setStart(node, newOffset);
                        range.deleteContents();
                    }
                    
                    this.hide();
                    cmd.action();
                    scheduleAutoSave();
                }
            },
            
            handleKey(e) {
                if (!this.visible) return false;
                
                if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    const menu = document.getElementById('slashMenu');
                    const filtered = menu.filteredCommands || this.commands;
                    this.selectedIndex = Math.min(this.selectedIndex + 1, filtered.length - 1);
                    this.render(this.filterText);
                    return true;
                }
                if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    this.selectedIndex = Math.max(this.selectedIndex - 1, 0);
                    this.render(this.filterText);
                    return true;
                }
                if (e.key === 'Enter') {
                    e.preventDefault();
                    this.select(this.selectedIndex);
                    return true;
                }
                if (e.key === 'Escape') {
                    e.preventDefault();
                    this.hide();
                    return true;
                }
                if (e.key === 'Backspace') {
                    if (this.filterText.length > 0) {
                        this.filterText = this.filterText.slice(0, -1);
                        setTimeout(() => {
                            this.selectedIndex = 0;
                            this.render(this.filterText);
                        }, 0);
                    } else {
                        this.hide();
                    }
                    return true;
                }
                return false;
            },
            
            handleInput(e) {
                if (this.visible && e.inputType === 'insertText' && e.data) {
                    this.filterText += e.data;
                    this.selectedIndex = 0;
                    this.render(this.filterText);
                    
                    const sel = window.getSelection();
                    if (sel.rangeCount > 0) {
                        this.savedRange = sel.getRangeAt(0).cloneRange();
                    }
                }
            }
        };
        
        // Backwards compatibility for onclick handlers
        function showSlashMenu(x, y) { SlashMenu.show(x, y); }
        function hideSlashMenu() { SlashMenu.hide(); }
        function renderSlashMenu(f) { SlashMenu.render(f); }
        function selectSlashCommand(i) { SlashMenu.select(i); }
        
        // Keep slashCommands reference for menu click handler
        const slashCommands = SlashMenu.commands;


        // === QuickSearch Object ===
        // Self-contained quick search modal (Cmd+K). All quick search logic lives here.
        const QuickSearch = {
            selectedIndex: 0,
            results: [],
            
            open() {
                const modal = document.getElementById('quickSearchModal');
                const input = document.getElementById('quickSearchInput');
                modal.classList.add('active');
                input.value = '';
                this.selectedIndex = 0;
                this.results = [];
                this.filter();
                input.focus();
            },
            
            close() {
                document.getElementById('quickSearchModal').classList.remove('active');
            },
            
            filter() {
                const query = document.getElementById('quickSearchInput').value.toLowerCase().trim();
                const container = document.getElementById('quickSearchResults');

                let results = allDocsCache || [];
                
                if (query) {
                    results = results.filter(doc => 
                        (doc.title || '').toLowerCase().includes(query) ||
                        (doc.collection || '').toLowerCase().includes(query)
                    );
                }

                results = results.slice().sort((a, b) => 
                    new Date(b.updated_at || 0) - new Date(a.updated_at || 0)
                ).slice(0, 15);

                this.results = results;
                this.selectedIndex = 0;

                if (results.length === 0) {
                    container.innerHTML = '<div class="quick-search-empty">No documents found</div>';
                    return;
                }

                container.innerHTML = results.map((doc, i) => `
                    <div class="quick-search-item ${i === 0 ? 'selected' : ''}" 
                         data-doc-id="${doc.id}" 
                         onclick="selectQuickSearchDoc('${doc.id}')">
                        <div class="quick-search-item-title">${doc.title || 'Untitled'}</div>
                        <div class="quick-search-item-collection">${doc.collection || 'Notes'}</div>
                    </div>
                `).join('');
            },
            
            handleKey(e) {
                if (e.key === 'Escape') {
                    this.close();
                    return true;
                }
                
                if (e.key === 'Enter' && this.results.length > 0) {
                    e.preventDefault();
                    const selectedDoc = this.results[this.selectedIndex];
                    if (selectedDoc) {
                        selectQuickSearchDoc(selectedDoc.id);
                    }
                    return true;
                }
                
                if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    this.selectedIndex = Math.min(this.selectedIndex + 1, this.results.length - 1);
                    this.updateSelection();
                    return true;
                }
                
                if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    this.selectedIndex = Math.max(this.selectedIndex - 1, 0);
                    this.updateSelection();
                    return true;
                }
                return false;
            },
            
            updateSelection() {
                const items = document.querySelectorAll('.quick-search-item');
                items.forEach((item, i) => {
                    item.classList.toggle('selected', i === this.selectedIndex);
                });
                const selected = items[this.selectedIndex];
                if (selected) selected.scrollIntoView({ block: 'nearest' });
            }
        };
        
        // Backwards compatibility for external calls
        function openQuickSearch() { QuickSearch.open(); }
        function closeQuickSearch() { QuickSearch.close(); }
        function filterQuickSearch() { QuickSearch.filter(); }
        function handleQuickSearchKey(e) { return QuickSearch.handleKey(e); }
        function updateQuickSearchSelection() { QuickSearch.updateSelection(); }
        function selectQuickSearchDoc(docId) {
            QuickSearch.close();
            openDocFromTimeline(docId);
        }


        // === DistractionFree Object ===
        // Self-contained distraction-free writing mode. All DF logic lives here.
        const DistractionFree = {
            active: false,
            sessionStart: null,
            sessionStartWords: 0,
            
            countWords(text) {
                return text.trim().split(/\s+/).filter(w => w.length > 0).length;
            },
            
            enter() {
                if (!currentDocId) return;
                
                this.sessionStart = Date.now();
                const dc = document.getElementById('docContent');
                this.sessionStartWords = this.countWords(dc.innerText || '');
                
                document.body.classList.add('distraction-free');
                this.active = true;
                
                localStorage.setItem('docEditorDistractionFree', 'true');
                dc.focus();
            },
            
            exit() {
                document.body.classList.remove('distraction-free');
                localStorage.setItem('docEditorDistractionFree', 'false');
                
                if (this.sessionStart) {
                    this.showStats();
                }
                
                this.sessionStart = null;
                this.sessionStartWords = 0;
                this.active = false;
            },
            
            showStats() {
                const dc = document.getElementById('docContent');
                const endWordCount = this.countWords(dc.innerText || '');
                const wordsWritten = endWordCount - this.sessionStartWords;
                const elapsedMs = Date.now() - this.sessionStart;
                const elapsedMin = elapsedMs / 60000;
                const wpm = elapsedMin > 0 ? Math.round(wordsWritten / elapsedMin) : 0;
                
                let timeStr;
                if (elapsedMin < 1) {
                    timeStr = Math.round(elapsedMs / 1000) + 's';
                } else if (elapsedMin < 60) {
                    timeStr = Math.round(elapsedMin) + 'm';
                } else {
                    const hours = Math.floor(elapsedMin / 60);
                    const mins = Math.round(elapsedMin % 60);
                    timeStr = hours + 'h ' + mins + 'm';
                }
                
                const toast = document.getElementById('dfSessionToast');
                toast.innerHTML = `
                    <span class="stat"><span class="stat-value">${wordsWritten >= 0 ? '+' : ''}${wordsWritten}</span> <span class="stat-label">words</span></span>
                    <span class="stat"><span class="stat-value">${timeStr}</span> <span class="stat-label">session</span></span>
                    <span class="stat"><span class="stat-value">${wpm}</span> <span class="stat-label">wpm</span></span>
                `;
                toast.classList.add('visible');
                
                setTimeout(() => {
                    toast.classList.remove('visible');
                }, 4000);
            },
            
            toggle() {
                if (document.body.classList.contains('distraction-free')) {
                    this.exit();
                } else {
                    this.enter();
                }
            }
        };
        
        // Backwards compatibility for onclick and other references
        function toggleDistractionFree() { DistractionFree.toggle(); }
        function enterDistractionFree() { DistractionFree.enter(); }
        function exitDistractionFree() { DistractionFree.exit(); }
        function showSessionStats() { DistractionFree.showStats(); }
        function countWords(text) { return DistractionFree.countWords(text); }


        // MASTER KEYDOWN HANDLER
        // ALL keyboard shortcuts live here. DO NOT add another document.addEventListener keydown anywhere.
        // To add a new shortcut: add a case to the priority chain below.
        // Uses capture phase for Cmd+Arrow to intercept before contenteditable
        document.addEventListener('keydown', function(e) {
            // Priority 1: SlashMenu active -> delegate
            if (SlashMenu.visible) {
                if (SlashMenu.handleKey(e)) return;
            }
            
            // Priority 2: QuickSearch active -> delegate
            const quickSearchModal = document.getElementById('quickSearchModal');
            if (quickSearchModal && quickSearchModal.classList.contains('active')) {
                if (QuickSearch.handleKey(e)) return;
            }
            
            // Priority 3: Cmd+Shift+D -> distraction-free toggle
            if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === 'd') {
                e.preventDefault();
                DistractionFree.toggle();
                return;
            }
            
            // Priority 4: Cmd+Shift+K -> queue task modal (K for tasK, avoids Chrome Cmd+Shift+T)
            if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === 'k') {
                e.preventDefault();
                if (currentDocId) {
                    showQueueTaskModal(currentDocId, document.getElementById('docTitle').value);
                }
                return;
            }

            // Priority 4.5: Cmd+Shift+<key> -> formatting shortcuts from config
            if ((e.metaKey || e.ctrlKey) && e.shiftKey && editorConfig && editorConfig.keyboardShortcuts) {
                const shortcutKey = 'CmdShift' + e.key.toUpperCase();
                const actionName = editorConfig.keyboardShortcuts[shortcutKey];
                if (actionName) {
                    e.preventDefault();
                    const actionFn = getActionFunction(actionName);
                    if (actionFn) {
                        actionFn();
                        scheduleAutoSave();
                    }
                    return;
                }
            }

            // Priority 4.6: Cmd+Shift+H -> toggle yellow highlight
            if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === 'h') {
                e.preventDefault();
                const selection = window.getSelection();
                if (selection && selection.rangeCount > 0 && !selection.isCollapsed) {
                    const range = selection.getRangeAt(0);
                    const container = range.commonAncestorContainer;
                    const parentEl = container.nodeType === 3 ? container.parentElement : container;
                    const existingMark = parentEl.closest('mark.orch-highlight');
                    if (existingMark) {
                        // Unwrap existing highlight
                        const frag = document.createDocumentFragment();
                        while (existingMark.firstChild) frag.appendChild(existingMark.firstChild);
                        existingMark.parentNode.replaceChild(frag, existingMark);
                    } else {
                        try {
                            const mark = document.createElement('mark');
                            mark.className = 'orch-highlight';
                            mark.style.cssText = 'background-color:#ffeb3b;color:#000000;border-radius:2px;padding:0 2px;';
                            range.surroundContents(mark);
                        } catch(err) {
                            // Selection spans multiple elements - do nothing
                        }
                    }
                    scheduleAutoSave();
                }
                return;
            }

            // Priority 5: Cmd+ArrowUp/Down -> doc navigation
            if ((e.metaKey || e.ctrlKey) && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
                if (currentDocId && currentDisplayedDocs.length > 0) {
                    e.preventDefault();
                    e.stopPropagation();
                    saveDoc();
                    navigateDoc(e.key === 'ArrowUp' ? -1 : 1);
                }
                return;
            }
            
            // Priority 6: Escape -> context chain
            if (e.key === 'Escape') {
                // Distraction-free first
                if (document.body.classList.contains('distraction-free')) {
                    DistractionFree.exit();
                    return;
                }
                // Quick search modal
                if (quickSearchModal && quickSearchModal.classList.contains('active')) {
                    QuickSearch.close();
                    return;
                }
                // Mockup batch modal
                const mockupBatchModal = document.getElementById('mockupBatchModal');
                if (mockupBatchModal && mockupBatchModal.style.display !== 'none') {
                    closeMockupBatchModal();
                    return;
                }
                // Timeline filter modal
                if (document.getElementById('timelineFilterModal').classList.contains('active')) {
                    closeTimelineFilterModal();
                    return;
                }
                // Viewing a doc -> return to timeline
                if (currentDocId) {
                    exitFocusMode();
                    if (docOpenedFromCollection) {
                        collectionFilter = docOpenedFromCollection;
                    }
                    setView('timeline');
                    renderTimeline();
                    docOpenedFromCollection = null;
                    currentDocId = null;
                    navDocsLocked = false;
                    return;
                }
                // In timeline with filters -> clear them
                if (collectionFilter || timelineSearchQuery) {
                    clearTimelineFilters();
                    return;
                }
                // Otherwise ensure timeline view
                setView('timeline');
                return;
            }
            
            // Priority 7: Cmd+0-6 -> page navigation (from config)
            if ((e.metaKey || e.ctrlKey) && editorConfig && editorConfig.keyboardShortcuts) {
                const shortcutKey = 'Cmd' + e.key;
                const target = editorConfig.keyboardShortcuts[shortcutKey];
                if (target && target.endsWith('.html')) {
                    e.preventDefault();
                    window.location.href = target;
                    return;
                }
            }
            
            // Priority 8: Cmd+S/N/B/I/K -> editor shortcuts
            if (e.metaKey || e.ctrlKey) {
                if (e.key === 's') { e.preventDefault(); saveDoc(); return; }
                if (e.shiftKey && e.key.toLowerCase() === 'e') { e.preventDefault(); newDoc(); return; }
                if (e.key === 'b') { e.preventDefault(); document.execCommand('bold'); scheduleAutoSave(); return; }
                if (e.key === 'i') { e.preventDefault(); document.execCommand('italic'); scheduleAutoSave(); return; }
                if (e.key === 'k') { e.preventDefault(); QuickSearch.open(); return; }
                if (e.key === 'z' && !e.shiftKey) { e.preventDefault(); document.execCommand('undo'); return; }
                if (e.key === 'z' && e.shiftKey) { e.preventDefault(); document.execCommand('redo'); return; }
            }
        }, true); // capture phase



        // Load docs
        async function loadDocList() {
            // In Swift mode, request docs via bridge - Swift will call swiftListDocs callback
            if (isSwiftMode()) {
                swiftPost('listDocs');
                return;
            }
            try {
                const res = await fetch('/docs/list?_=' + Date.now());
                const data = await res.json();
                docs = data.docs || [];
                updateCollectionFilter();
                renderDocList();
            } catch (e) {
                console.error('Failed to load docs:', e);
            }
        }

        function updateCollectionFilter() {
            const filter = document.getElementById('collectionFilter');
            const collections = new Set(defaultCollections);
            docs.forEach(d => { if (d.collection) collections.add(d.collection); });
            filter.innerHTML = '<option value="">All Collections</option>' +
                Array.from(collections).sort().map(c => `<option value="${c}">${c}</option>`).join('');
        }

        // Debounce timer for API search
        let searchDebounceTimer = null;

        function filterDocs() {
            const search = document.getElementById('searchBox').value.trim();
            const collection = document.getElementById('collectionFilter').value;
            const sort = document.getElementById('sortSelect').value;

            // If search query exists, use API search (debounced)
            if (search.length >= 2) {
                clearTimeout(searchDebounceTimer);
                searchDebounceTimer = setTimeout(() => {
                    performAPISearch(search, collection, sort);
                }, 300);
                return;
            }

            // No search query - do client-side filtering only
            let filtered = docs.filter(d => {
                const matchCollection = !collection || d.collection === collection;
                return matchCollection;
            });

            filtered.sort((a, b) => {
                if (sort === 'title') return (a.title || '').localeCompare(b.title || '');
                if (sort === 'created') return new Date(b.created_at || 0) - new Date(a.created_at || 0);
                return new Date(b.updated_at || 0) - new Date(a.updated_at || 0);
            });

            renderDocList(filtered);
        }

        async function performAPISearch(query, collection, sort) {
            // In Swift mode, use executeTask bridge for search
            if (isSwiftMode()) {
                // For Swift mode, fall back to client-side filtering since executeTask is async
                const term = query.toLowerCase();
                let filtered = docs.filter(d => 
                    d.title.toLowerCase().includes(term) || 
                    (d.collection && d.collection.toLowerCase().includes(term))
                );
                if (collection) {
                    filtered = filtered.filter(d => d.collection === collection);
                }
                filtered.sort((a, b) => {
                    if (sort === 'title') return (a.title || '').localeCompare(b.title || '');
                    if (sort === 'created') return new Date(b.created_at || 0) - new Date(a.created_at || 0);
                    return new Date(b.updated_at || 0) - new Date(a.updated_at || 0);
                });
                renderDocList(filtered);
                return;
            }
            try {
                const params = { query: query, max_results: 50 };
                if (collection) params.collection = collection;

                const response = await fetch('/execute_task', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        tool_name: 'docs',
                        action: 'search_docs',
                        params: params
                    })
                });
                const result = await response.json();

                if (result.status === 'success' && result.docs) {
                    // Map API results to match docs array format
                    let filtered = result.docs.map(d => ({
                        id: d.id,
                        title: d.title,
                        collection: d.collection,
                        updated_at: d.updated_at,
                        created_at: d.created_at || d.updated_at,
                        word_count: d.word_count,
                        score: d.score
                    }));

                    // Sort by relevance (score) by default for searches, or by user preference
                    if (sort === 'title') {
                        filtered.sort((a, b) => (a.title || '').localeCompare(b.title || ''));
                    } else if (sort === 'created') {
                        filtered.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));
                    } else if (sort === 'updated') {
                        filtered.sort((a, b) => new Date(b.updated_at || 0) - new Date(a.updated_at || 0));
                    }
                    // Default: keep API's relevance ordering (by score)

                    renderDocList(filtered);
                } else {
                    console.error('Search failed:', result);
                    renderDocList([]);
                }
            } catch (e) {
                console.error('Search API error:', e);
                renderDocList([]);
            }
        }

        // Filter Modal Functions
        let activeCollection = '';

        function openFilterModal() {
            populateCollectionPills();
            document.getElementById('modalSearchBox').value = document.getElementById('searchBox').value;
            document.getElementById('filterModal').classList.add('active');
            document.getElementById('modalSearchBox').focus();
        }

        function closeFilterModal() {
            document.getElementById('filterModal').classList.remove('active');
            updateFilterButtonState();
        }

        function populateCollectionPills() {
            const collections = [...new Set(docs.map(d => d.collection).filter(Boolean))].sort();
            const container = document.getElementById('collectionPills');
            container.innerHTML = collections.map(c =>
                `<button class="collection-pill ${activeCollection === c ? 'active' : ''}" onclick="selectCollection('${c}')">${c}</button>`
            ).join('');
        }

        function selectCollection(collection) {
            if (activeCollection === collection) {
                activeCollection = '';
            } else {
                activeCollection = collection;
            }
            document.getElementById('collectionFilter').value = activeCollection;
            populateCollectionPills();
            filterDocs();
        }

        function applyModalFilter() {
            const modalSearch = document.getElementById('modalSearchBox').value;
            document.getElementById('searchBox').value = modalSearch;
            filterDocs();
        }

        function clearFilters() {
            activeCollection = '';
            document.getElementById('collectionFilter').value = '';
            document.getElementById('modalSearchBox').value = '';
            document.getElementById('searchBox').value = '';
            populateCollectionPills();
            filterDocs();
            updateFilterButtonState();
        }

        function updateFilterButtonState() {
            const btn = document.getElementById('filterBtn');
            const hasFilter = activeCollection || document.getElementById('searchBox').value;
            btn.classList.toggle('has-filter', !!hasFilter);
        }

        function getTimelineDotClass(dateStr) {
            if (!dateStr) return 'old';
            const diff = Date.now() - new Date(dateStr).getTime();
            if (diff < 3600000) return 'recent';
            if (diff < 86400000) return '';
            return 'old';
        }

        const DOC_LIST_PAGE_SIZE = 100;
        let docListRenderedCount = 0;
        let docListSource = [];

        function renderDocListPage(append = false) {
            const list = document.getElementById('docList');
            const nextBatch = docListSource.slice(docListRenderedCount, docListRenderedCount + DOC_LIST_PAGE_SIZE);
            if (nextBatch.length === 0) return;
            const html = nextBatch.map(doc => `
                <div class="doc-list-item ${doc.id === currentDocId ? 'active' : ''}" onclick="loadDoc('${doc.id}')">
                    <div class="doc-list-item-title">
                        <span class="timeline-dot ${getTimelineDotClass(doc.updated_at)}"></span>
                        ${doc.title || 'Untitled'}
                    </div>
                    <div class="doc-list-item-meta">
                        <span class="doc-collection-tag">${doc.collection || 'Notes'}</span>
                        <span class="doc-time">${formatDate(doc.updated_at)}</span>
                    </div>
                </div>
            `).join('');
            if (append) {
                list.insertAdjacentHTML('beforeend', html);
            } else {
                list.innerHTML = html;
            }
            docListRenderedCount += nextBatch.length;
        }

        function renderDocList(filteredDocs = null) {
            const list = document.getElementById('docList');
            const docsToRender = filteredDocs || docs;
            if (!navDocsLocked) {
                currentDisplayedDocs = docsToRender;
            }
            updateNavButtons();

            if (docsToRender.length === 0) {
                list.innerHTML = '<div style="padding: 20px; color: var(--text-muted); text-align: center;">No documents</div>';
                return;
            }

            docListSource = docsToRender;
            docListRenderedCount = 0;
            renderDocListPage(false);

            // Attach scroll listener once
            if (!list._scrollListenerAttached) {
                list.addEventListener('scroll', () => {
                    if (list.scrollTop + list.clientHeight >= list.scrollHeight - 100) {
                        renderDocListPage(true);
                    }
                });
                list._scrollListenerAttached = true;
            }
        }

        async function loadDoc(docId) {
            // In Swift mode, request doc via bridge - Swift will call swiftLoadDoc callback
            if (isSwiftMode()) {
                swiftPost('loadDoc', { docId: docId });
                return;
            }
            try {
                // Check cache first - use cached doc if updated_at matches
                const cachedMeta = allDocsCache.find(d => d.id === docId);
                const cached = docContentCache.get(docId);
                if (cached && cachedMeta && cached.updated_at === cachedMeta.updated_at) {
                    currentDocId = docId;
                    const doc = cached;
                    document.getElementById('docTitle').value = doc.title || '';
                    document.getElementById('docContent').innerHTML = doc.content || '';
                    setCollection(doc.collection || 'Notes');
                    lastKnownUpdatedAt = doc.updated_at;
                    document.getElementById('docMeta').innerHTML = `
                        <span>Created ${formatDate(doc.created_at)}</span>
                        <span>Updated ${formatDate(doc.updated_at)}</span>
                    `;
                    document.getElementById('editorContainer').style.display = 'block';
                    document.getElementById('emptyState').style.display = 'none';
                    document.getElementById('deleteBtn').style.display = 'block';
                    document.getElementById('queueTaskBtn').style.display = 'block';
                    document.getElementById('copyDocIdBtn').style.display = 'block';
                    document.getElementById('downloadPdfBtn').style.display = 'block';
                    document.getElementById('markDeployedBtn').style.display = 'block';
                    document.getElementById('docNavBtns').style.display = 'flex';
                    updateNavButtons();
                    renderDocList();
                    loadBacklinks(docId);
                    attachDocLinkHandlers();
                    initCollapsibleHeaders();
                    return;
                }
                
                const res = await fetch(`/docs/get/${docId}`);
                const data = await res.json();
                if (data.status === 'success') {
                    currentDocId = docId;
                    const doc = data.doc;
                    docContentCache.set(docId, doc); // Cache the fetched doc
                    document.getElementById('docTitle').value = doc.title || '';
                    document.getElementById('docContent').innerHTML = doc.content || '';
                    setCollection(doc.collection || 'Notes');
                    lastKnownUpdatedAt = doc.updated_at; // Track for auto-refresh
                    document.getElementById('docMeta').innerHTML = `
                        <span>Created ${formatDate(doc.created_at)}</span>
                        <span>Updated ${formatDate(doc.updated_at)}</span>
                    `;
                    document.getElementById('editorContainer').style.display = 'block';
                    document.getElementById('emptyState').style.display = 'none';
                    document.getElementById('deleteBtn').style.display = 'block';
            document.getElementById('queueTaskBtn').style.display = 'block';
                    document.getElementById('copyDocIdBtn').style.display = 'block';
                    document.getElementById('downloadPdfBtn').style.display = 'block';
                    document.getElementById('markDeployedBtn').style.display = 'block';
                    document.getElementById('docNavBtns').style.display = 'flex';
                    updateNavButtons();
                    renderDocList();
                    loadBacklinks(docId);
                    attachDocLinkHandlers(); // Re-attach click handlers to doc-links
                    initCollapsibleHeaders(); // Add collapse chevrons to headers
                }
            } catch (e) {
                console.error('Failed to load doc:', e);
            }
        }

        function handleWikiLink(el) {
            const title = el.getAttribute('data-title');
            const doc = allDocsCache.find(d => d.title.toLowerCase() === title.toLowerCase());
            if (doc) {
                loadDoc(doc.id);
            } else {
                console.log('Wiki link target not found:', title);
            }
        }

        function newDoc() {
            currentDocId = null;
            lastKnownUpdatedAt = null; // Reset for new doc
            document.getElementById('docTitle').value = '';
            document.getElementById('docContent').innerHTML = '';
            setCollection('Notes');
            document.getElementById('docMeta').innerHTML = '<span>New document</span>';
            document.getElementById('editorContainer').style.display = 'block';
            document.getElementById('emptyState').style.display = 'none';
            document.getElementById('deleteBtn').style.display = 'none';
        document.getElementById('queueTaskBtn').style.display = 'none';
                    document.getElementById('copyDocIdBtn').style.display = 'none';
            document.getElementById('downloadPdfBtn').style.display = 'none';
            document.getElementById('markDeployedBtn').style.display = 'none';
            document.getElementById('docNavBtns').style.display = 'none';
            document.getElementById('docTitle').focus();
            renderDocList();
        }


        // ===== DOC NAVIGATION =====
        function updateNavButtons() {
            const prevBtn = document.getElementById('prevDocBtn');
            const nextBtn = document.getElementById('nextDocBtn');
            if (!prevBtn || !nextBtn || !currentDocId) return;

            const currentIndex = currentDisplayedDocs.findIndex(d => d.id === currentDocId);
            prevBtn.disabled = currentIndex <= 0;
            nextBtn.disabled = currentIndex >= currentDisplayedDocs.length - 1 || currentIndex === -1;
        }

        function navigateDoc(direction) {
            if (!currentDocId || currentDisplayedDocs.length === 0) return;

            const currentIndex = currentDisplayedDocs.findIndex(d => d.id === currentDocId);
            if (currentIndex === -1) return;

            const newIndex = currentIndex + direction;
            if (newIndex < 0 || newIndex >= currentDisplayedDocs.length) return;

            const newDoc = currentDisplayedDocs[newIndex];
            loadDoc(newDoc.id);
        }

        // ===== BIDIRECTIONAL LINKING =====
        let mentionSearchTerm = '';
        let mentionStartPos = null;
        let selectedMentionIndex = 0;

        async function fetchAllDocs() {
            // In Swift mode, use the docs array already populated by swiftListDocs
            if (isSwiftMode()) {
                allDocsCache = docs || [];
                return;
            }
            try {
                const res = await fetch('/docs/list');
                const data = await res.json();
                if (data.status === 'success') {
                    allDocsCache = data.docs || [];
                }
            } catch (e) {
                console.error('Failed to fetch docs for linking:', e);
            }
        }

        async function loadBacklinks(docId) {
            const section = document.getElementById('backlinksSection');
            const list = document.getElementById('backlinksList');
            
            // In Swift mode, hide backlinks section (not critical for core functionality)
            if (isSwiftMode()) {
                section.style.display = 'none';
                return;
            }
            
            try {
                const res = await fetch(`/docs/backlinks/${docId}`);
                const data = await res.json();
                
                if (data.status === 'success' && data.backlinks && data.backlinks.length > 0) {
                    list.innerHTML = data.backlinks.map(bl => 
                        `<div class="backlink-item" onclick="loadDoc('${bl.doc_id}')">${bl.title}</div>`
                    ).join('');
                    section.style.display = 'block';
                } else {
                    section.style.display = 'none';
                }
            } catch (e) {
                console.error('Failed to load backlinks:', e);
                section.style.display = 'none';
            }
        }

        async function createDocLink(targetDocId, targetTitle) {
            if (!currentDocId) {
                // Save current doc first
                await saveDoc();
                if (!currentDocId) return; // Still no doc id
            }
            
            // In Swift mode, skip link creation (not critical for core functionality)
            if (isSwiftMode()) {
                console.log('Swift mode: link creation skipped');
                return;
            }
            
            try {
                const res = await fetch('/docs/link', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        source_doc_id: currentDocId,
                        target_doc_id: targetDocId
                    })
                });
                const data = await res.json();
                if (data.status === 'success') {
                    console.log('Link created:', currentDocId, '->', targetDocId);
                }
            } catch (e) {
                console.error('Failed to create link:', e);
            }
        }

        async function createDocFromMention(title) {
            // Convert to Title Case for the doc title
            const titleCased = title.split(' ').map(word => 
                word.charAt(0).toUpperCase() + word.slice(1)
            ).join(' ');
            
            // In Swift mode, doc creation from mention is not supported (needs sync return)
            if (isSwiftMode()) {
                console.log('Swift mode: creating doc from mention not supported');
                return null;
            }
            
            try {
                const res = await fetch('/docs/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        title: titleCased,
                        content: '',
                        collection: 'Inbox'
                    })
                });
                const data = await res.json();
                if (data.status === 'success') {
                    // Refresh docs cache
                    await fetchAllDocs();
                    return { id: data.doc_id, title: titleCased };
                }
            } catch (e) {
                console.error('Failed to create doc from mention:', e);
            }
            return null;
        }

        function showMentionDropdown(x, y) {
            const dropdown = document.getElementById('mentionDropdown');
            dropdown.style.left = x + 'px';
            dropdown.style.top = y + 'px';
            dropdown.classList.add('visible');
        }

        function hideMentionDropdown() {
            const dropdown = document.getElementById('mentionDropdown');
            dropdown.classList.remove('visible');
            mentionSearchTerm = '';
            mentionStartPos = null;
            selectedMentionIndex = 0;
        }

        function filterDocsForMention(search) {
            const term = search.toLowerCase();
            let filtered = allDocsCache.filter(d => 
                d.id !== currentDocId && 
                d.title.toLowerCase().includes(term)
            ).slice(0, 5);
            
            // Add "Create new" option if search term exists
            if (term.length > 0) {
                filtered.push({ id: '__create__', title: search, isCreate: true });
            }
            
            return filtered;
        }

        function renderMentionDropdown(docs) {
            const dropdown = document.getElementById('mentionDropdown');
            if (docs.length === 0) {
                dropdown.innerHTML = '<div class="mention-item" style="color: var(--text-muted);">No docs found</div>';
                return;
            }
            
            dropdown.innerHTML = docs.map((doc, i) => {
                if (doc.isCreate) {
                    return `<div class="mention-item mention-create ${i === selectedMentionIndex ? 'selected' : ''}" 
                        data-id="__create__" data-title="${doc.title}">
                        + Create "${doc.title}"
                    </div>`;
                }
                return `<div class="mention-item ${i === selectedMentionIndex ? 'selected' : ''}" 
                    data-id="${doc.id}" data-title="${doc.title}">
                    ${doc.title}
                    <span class="collection-tag">${doc.collection || ''}</span>
                </div>`;
            }).join('');
        }

async function insertDocLink(docId, title) {
            // Re-entry guard to prevent multiple executions (Bug 2 fix)
            if (insertDocLink._inserting) return;
            insertDocLink._inserting = true;

            try {
                const docContent = document.getElementById('docContent');
                const selection = window.getSelection();

                if (!selection.rangeCount) {
                    insertDocLink._inserting = false;
                    return;
                }

                // Delete the @searchTerm
                const range = selection.getRangeAt(0);
                if (mentionStartPos !== null) {
                    // Bug 1 fix: Use textNode and mentionStartPos directly - no TreeWalker needed
                    const textNode = range.startContainer;
                    if (textNode.nodeType === Node.TEXT_NODE) {
                        const deleteRange = document.createRange();
                        deleteRange.setStart(textNode, mentionStartPos);
                        deleteRange.setEnd(range.startContainer, range.startOffset);
                        deleteRange.deleteContents();
                    }

                    // Check if @ is at start of sentence/list item - preserve capitalization if so
                    const shouldPreserveCase = (() => {
                        // Walk backwards from @ position to find preceding content
                        const textBefore = textNode.textContent.substring(0, mentionStartPos);
                        const trimmedBefore = textBefore.trimEnd();

                        // If @ is first content in this text node...
                        if (trimmedBefore.length === 0) {
                            // Check parent element - is this in a p or li?
                            let parent = textNode.parentElement;
                            while (parent && parent !== docContent) {
                                if (parent.tagName === 'P' || parent.tagName === 'LI') {
                                    // Check if there's any preceding sibling text
                                    let prevSibling = textNode.previousSibling;
                                    while (prevSibling) {
                                        if (prevSibling.nodeType === Node.TEXT_NODE && prevSibling.textContent.trim()) {
                                            // There's text before - check if it ends a sentence
                                            const prevText = prevSibling.textContent.trimEnd();
                                            return prevText.endsWith('.') || prevText.endsWith('!') || prevText.endsWith('?');
                                        }
                                        if (prevSibling.nodeType === Node.ELEMENT_NODE) {
                                            const prevElText = prevSibling.textContent.trimEnd();
                                            if (prevElText) {
                                                return prevElText.endsWith('.') || prevElText.endsWith('!') || prevElText.endsWith('?');
                                            }
                                        }
                                        prevSibling = prevSibling.previousSibling;
                                    }
                                    // No preceding text - @ is first content in p/li
                                    return true;
                                }
                                parent = parent.parentElement;
                            }
                            return false;
                        }

                        // @ has text before it in same node - check if preceded by sentence-ending punctuation
                        return trimmedBefore.endsWith('.') || trimmedBefore.endsWith('!') || trimmedBefore.endsWith('?');
                    })();

                    // Insert the link - lowercase unless at start of sentence/list
                    const displayText = shouldPreserveCase ? title : title.split(' ').map(word =>
                        word.charAt(0).toLowerCase() + word.slice(1)
                    ).join(' ');
                    const link = document.createElement('span');
                    link.className = 'doc-link';
                    link.setAttribute('data-doc-id', docId);
                    link.setAttribute('data-doc-title', title);
                    link.setAttribute('contenteditable', 'false');
                    link.textContent = displayText;
                    link.title = title; // Tooltip shows real title
                    link.onclick = () => loadDoc(docId);

                    // Insert a plain space after the link
                    const spacer = document.createTextNode(' ');

                    // Insert link, then spacer
                    range.insertNode(spacer);
                    range.insertNode(link);

                    // Position cursor after spacer
                    const newRange = document.createRange();
                    newRange.setStartAfter(spacer);
                    newRange.collapse(true);
                    selection.removeAllRanges();
                    selection.addRange(newRange);

                    // Force reset text color to white using execCommand
                    document.execCommand('foreColor', false, '#E8E8EC');
                }

                // Create the bidirectional link
                await createDocLink(docId, title);

                // Hide dropdown and schedule save
                hideMentionDropdown();
                scheduleAutoSave();
            } finally {
                insertDocLink._inserting = false;
            }
        }

        async function insertDocEmbed(docId, title) {
            // In Swift mode, embed is not supported (would need bridge callback)
            if (isSwiftMode()) {
                console.log('Swift mode: doc embed not supported, inserting link instead');
                await insertDocLink(docId, title);
                return;
            }
            // Fetch the doc content and insert it inline
            try {
                const res = await fetch(`/docs/get/${docId}`);
                const data = await res.json();
                
                if (data.status === 'success' && data.doc) {
                    // First delete the @mention text (same as link insertion)
                    const docContentEl = document.getElementById('docContent');
                    const selection = window.getSelection();
                    if (!selection.rangeCount) return;
                    
                    const range = selection.getRangeAt(0);
                    
                    // Find and delete @term
                    if (mentionStartPos !== null) {
                        const text = range.startContainer.textContent || '';
                        const atIdx = text.lastIndexOf('@');
                        if (atIdx !== -1) {
                            range.setStart(range.startContainer, atIdx);
                            range.deleteContents();
                        }
                    }
                    
                    // Build embed HTML
                    const embedContent = data.doc.content || '(empty document)';
                    const sourceLink = `<br><span style="font-size:12px;color:#666;">Source: <span class="doc-link" data-doc-id="${docId}" onclick="loadDoc('${docId}')" style="font-size:12px;">${title}</span></span>`;
                    
                    // Insert using execCommand
                    document.execCommand('insertHTML', false, embedContent + sourceLink + ' ');
                    
                    // Create backlink
                    if (currentDocId) {
                        await createDocLink(docId, title);
                    }
                    
                    hideMentionDropdown();
                    scheduleAutoSave();
                }
            } catch (e) {
                console.error('Failed to embed doc:', e);
            }
        }

        // Setup @ mention detection
        function setupMentionDetection() {
            const docContent = document.getElementById('docContent');
            
            // Intercept Writing Tools insertions via beforeinput — same cleanup as paste handler
            docContent.addEventListener('beforeinput', (e) => {
                if (e.inputType === 'insertFromPaste' || 
                    e.inputType === 'insertReplacementText' ||
                    e.inputType === 'insertFromDrop') {
                    // Let paste handler deal with insertFromPaste
                    if (e.inputType === 'insertFromPaste') return;
                    // For Writing Tools replacements, clean the incoming HTML
                    if (e.dataTransfer) {
                        const html = e.dataTransfer.getData('text/html');
                        if (html) {
                            e.preventDefault();
                            const temp = document.createElement('div');
                            temp.innerHTML = html;
                            temp.querySelectorAll('*').forEach(el => {
                                el.removeAttribute('style');
                                el.removeAttribute('color');
                                el.removeAttribute('size');
                                el.removeAttribute('face');
                            });
                            // Convert font tags to spans
                            temp.querySelectorAll('font').forEach(font => {
                                const span = document.createElement('span');
                                span.innerHTML = font.innerHTML;
                                font.replaceWith(span);
                            });
                            document.execCommand('insertHTML', false, temp.innerHTML);
                        }
                    }
                }
            });

            // Fallback MutationObserver for any Writing Tools insertions that bypass beforeinput
            const writingToolsObserver = new MutationObserver((mutations) => {
                let needsNormalize = false;
                for (const mutation of mutations) {
                    if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
                        for (const node of mutation.addedNodes) {
                            if (node.nodeType === Node.ELEMENT_NODE) {
                                // Check for unstyled spans or divs inserted by Writing Tools
                                if ((node.tagName === 'SPAN' || node.tagName === 'DIV') && 
                                    !node.className && 
                                    node.style.color && node.style.color !== '') {
                                    node.style.color = '';
                                    node.style.fontSize = '';
                                    node.style.fontFamily = '';
                                    needsNormalize = true;
                                }
                                // Normalize all child spans with inline color/font styles
                                node.querySelectorAll('span[style], font[color]').forEach(el => {
                                    el.style.color = '';
                                    el.style.fontSize = '';
                                    el.style.fontFamily = '';
                                    if (el.tagName === 'FONT') {
                                        el.removeAttribute('color');
                                        el.removeAttribute('size');
                                        el.removeAttribute('face');
                                    }
                                });
                            }
                        }
                    }
                }
            });
            writingToolsObserver.observe(docContent, { childList: true, subtree: true, attributes: true, attributeFilter: ['style', 'color', 'face', 'size'] });

            // Handle click on dropdown items
            document.getElementById('mentionDropdown').addEventListener('click', async (e) => {
                const item = e.target.closest('.mention-item');
                if (!item) return;
                
                const docId = item.getAttribute('data-id');
                const title = item.getAttribute('data-title');
                
                if (docId === '__create__') {
                    const newDoc = await createDocFromMention(title);
                    if (newDoc) {
                        await insertDocLink(newDoc.id, newDoc.title);
                    }
                } else {
                    await insertDocLink(docId, title);
                }
            });
            
            // Hide dropdown when clicking outside
            document.addEventListener('click', (e) => {
                if (!e.target.closest('.mention-dropdown') && !e.target.closest('.doc-content')) {
                    hideMentionDropdown();
                }
            });
        }

        // Re-attach click handlers to all doc-links in content
        function attachDocLinkHandlers() {
            document.querySelectorAll('.doc-link[data-doc-id]').forEach(link => {
                link.onclick = () => loadDoc(link.getAttribute('data-doc-id'));
            });
        }

        // ===== COLLAPSIBLE HEADERS =====
        function initCollapsibleHeaders() {
            const docContent = document.getElementById('docContent');
            if (!docContent) return;

            // Reset any persisted display:none styles or collapsed-content classes
            docContent.querySelectorAll('[style*="display"]').forEach(el => {
                el.style.display = '';
            });
            docContent.querySelectorAll('.collapsed-content').forEach(el => {
                el.classList.remove('collapsed-content');
            });
            // Reset all chevrons to expanded state
            docContent.querySelectorAll('.collapse-chevron').forEach(chevron => {
                chevron.setAttribute('data-collapsed', 'false');
                chevron.innerHTML = '▼';
            });

            // Find all headers h1-h4 within docContent
            const headers = docContent.querySelectorAll('h1, h2, h3, h4');

            headers.forEach(header => {
                let chevron = header.querySelector('.collapse-chevron');

                // If no chevron exists, create one
                if (!chevron) {
                    chevron = document.createElement('span');
                    chevron.className = 'collapse-chevron';
                    chevron.innerHTML = '▼';
                    chevron.contentEditable = 'false'; // Prevent editing the chevron
                    chevron.setAttribute('data-collapsed', 'false');
                    header.insertBefore(chevron, header.firstChild);
                }

                // ALWAYS attach click handler (even to existing chevrons)
                // Use onclick to replace any stale handlers
                chevron.onclick = function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    toggleCollapse(header);
                };
            });
        }

        function toggleCollapse(header) {
            const chevron = header.querySelector('.collapse-chevron');
            if (!chevron) return;

            const isCollapsed = chevron.getAttribute('data-collapsed') === 'true';
            const headerLevel = parseInt(header.tagName.charAt(1)); // 1, 2, 3, or 4

            // Get all siblings after this header until next header of same or higher level
            let sibling = header.nextElementSibling;
            const elementsToToggle = [];

            while (sibling) {
                // Check if it's a header of same or higher level
                if (/^H[1-4]$/.test(sibling.tagName)) {
                    const siblingLevel = parseInt(sibling.tagName.charAt(1));
                    if (siblingLevel <= headerLevel) {
                        break; // Stop at same or higher level header
                    }
                }
                elementsToToggle.push(sibling);
                sibling = sibling.nextElementSibling;
            }

            // Toggle visibility using CSS classes for reliable state
            if (isCollapsed) {
                // Expand
                chevron.setAttribute('data-collapsed', 'false');
                chevron.innerHTML = '▼';
                chevron.style.transform = 'rotate(0deg)';
                elementsToToggle.forEach(el => {
                    el.classList.remove('collapsed-content');
                    el.style.display = ''; // Also clear any legacy inline styles
                });
            } else {
                // Collapse
                chevron.setAttribute('data-collapsed', 'true');
                chevron.innerHTML = '▶';
                chevron.style.transform = '';
                elementsToToggle.forEach(el => {
                    el.classList.add('collapsed-content');
                });
            }
        }
        // ===== END COLLAPSIBLE HEADERS =====

        // Initialize mention detection on page load
        document.addEventListener('DOMContentLoaded', () => {
            setupMentionDetection();
            fetchAllDocs();
        });
        // ===== END BIDIRECTIONAL LINKING =====

        function scheduleAutoSave() {
            document.getElementById('saveStatus').textContent = 'Editing...';
            document.getElementById('saveStatus').className = 'save-status';
            pendingSave = true;
            clearTimeout(saveTimeout);
            saveTimeout = setTimeout(saveDoc, 800);
        }

        async function saveDoc() {
            const title = document.getElementById('docTitle').value;
            // Clone content to clean collapse state before saving
            const docContentEl = document.getElementById('docContent');
            const clone = docContentEl.cloneNode(true);
            // Remove collapsed-content classes so content is visible on reload
            clone.querySelectorAll('.collapsed-content').forEach(el => {
                el.classList.remove('collapsed-content');
            });
            // Remove inline display styles from any collapsed elements
            clone.querySelectorAll('[style*="display"]').forEach(el => {
                el.style.display = '';
            });
            // Reset chevrons to expanded state in saved content
            clone.querySelectorAll('.collapse-chevron').forEach(chevron => {
                chevron.setAttribute('data-collapsed', 'false');
                chevron.innerHTML = '▼';
            });
            const content = clone.innerHTML;
            const collection = document.getElementById('collectionLabel').textContent;

            if (!title && !content) return;

            document.getElementById('saveStatus').textContent = 'Saving...';
            document.getElementById('saveStatus').className = 'save-status saving';

            // In Swift mode, save via bridge - Swift will call swiftSaveComplete callback
            if (isSwiftMode()) {
                swiftPost('saveDoc', {
                    id: currentDocId,
                    title: title || 'Untitled',
                    content: content,
                    collection: collection
                });
                return;
            }

            try {
                const res = await fetch('/docs/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        id: currentDocId,
                        title: title || 'Untitled',
                        content: content,
                        collection: collection
                    })
                });
                const data = await res.json();

                if (data.status === 'success') {
                    pendingSave = false;
                    if (!currentDocId) {
                        currentDocId = data.doc_id;
                        document.getElementById('deleteBtn').style.display = 'block';
            document.getElementById('queueTaskBtn').style.display = 'block';
                    document.getElementById('copyDocIdBtn').style.display = 'block';
                        document.getElementById('downloadPdfBtn').style.display = 'block';
                        document.getElementById('markDeployedBtn').style.display = 'block';
                    }
                    document.getElementById('saveStatus').textContent = 'Saved';
                    document.getElementById('saveStatus').className = 'save-status saved';
                    loadDocList();
                }
            } catch (e) {
                console.error('Failed to save:', e);
                document.getElementById('saveStatus').textContent = 'Save failed';
            }
        }

        async function deleteDoc() {
            if (!currentDocId) return;
            if (!confirm('Delete this document?')) return;
            
            // In Swift mode, delete via bridge - Swift will call swiftDeleteComplete and listDocs
            if (isSwiftMode()) {
                swiftPost('deleteDoc', { docId: currentDocId });
                // Clear UI immediately
                currentDocId = null;
                document.getElementById('editorContainer').style.display = 'none';
                document.getElementById('emptyState').style.display = 'flex';
                document.getElementById('deleteBtn').style.display = 'none';
                document.getElementById('queueTaskBtn').style.display = 'none';
                document.getElementById('copyDocIdBtn').style.display = 'none';
                document.getElementById('downloadPdfBtn').style.display = 'none';
                document.getElementById('markDeployedBtn').style.display = 'none';
                return;
            }
            try {
                const res = await fetch(`/docs/delete/${currentDocId}`, { method: 'DELETE' });
                const data = await res.json();
                if (data.status === 'success') {
                    currentDocId = null;
                    document.getElementById('editorContainer').style.display = 'none';
                    document.getElementById('emptyState').style.display = 'flex';
                    document.getElementById('deleteBtn').style.display = 'none';
                    document.getElementById('queueTaskBtn').style.display = 'none';
                    document.getElementById('copyDocIdBtn').style.display = 'none';
                    document.getElementById('downloadPdfBtn').style.display = 'none';
                    document.getElementById('markDeployedBtn').style.display = 'none';
                    loadDocList();
                } else {
                    console.error('Delete failed:', data.message || 'Unknown error');
                    alert('Failed to delete: ' + (data.message || 'Unknown error'));
                }
            } catch (e) {
                console.error('Failed to delete:', e);
                alert('Failed to delete document. Check console for details.');
            }
        }

        // Download PDF - renders doc content with white background
        function downloadPDF() {
            const title = document.getElementById('docTitle').value || 'document';
            const content = document.getElementById('docContent').cloneNode(true);
            
            // Create wrapper with white background for PDF
            const wrapper = document.createElement('div');
            wrapper.style.cssText = 'background: #fff; color: #000; padding: 40px; font-family: Montserrat, sans-serif; font-size: 14px; line-height: 1.6;';
            
            // Add title
            const titleEl = document.createElement('h1');
            titleEl.textContent = title;
            titleEl.style.cssText = 'font-size: 24px; margin-bottom: 24px; color: #000; font-weight: 700;';
            wrapper.appendChild(titleEl);
            
            // Fix all text colors to black for PDF
            content.querySelectorAll('*').forEach(el => {
                el.style.color = '#000';
            });
            wrapper.appendChild(content);
            
            // Generate PDF
            const opt = {
                margin: 0.5,
                filename: title.replace(/[^a-z0-9]/gi, '_').toLowerCase() + '.pdf',
                image: { type: 'jpeg', quality: 0.98 },
                html2canvas: { scale: 2, useCORS: true },
                jsPDF: { unit: 'in', format: 'letter', orientation: 'portrait' }
            };
            
            html2pdf().set(opt).from(wrapper).save();
        }

        // Mark doc as deployed - moves to Deployed collection
        async function markAsDeployed() {
            if (!currentDocId) return;
            // Set collection to Deployed and save
            setCollection('Deployed');
            await saveDoc();
            loadDocList();
        }

        // WYSIWYG Formatting - using manual DOM manipulation for reliability
        function format(type) {
            if (typeof event !== 'undefined' && event) event.preventDefault();
            const selection = window.getSelection();
            if (!selection.rangeCount) return;

            const range = selection.getRangeAt(0);
            savedSelection = null;

            switch(type) {
                case 'bold':
                    document.execCommand('bold', false, null);
                    break;
                case 'italic':
                    document.execCommand('italic', false, null);
                    break;
                case 'code':
                    const code = document.createElement('code');
                    code.appendChild(range.extractContents());
                    range.insertNode(code);
                    selection.removeAllRanges();
                    break;
                case 'link':
                    const url = prompt('Enter URL:');
                    if (url && url.trim()) {
                        const a = document.createElement('a');
                        a.href = url.trim();
                        a.target = '_blank';
                        a.appendChild(range.extractContents());
                        range.insertNode(a);
                        selection.removeAllRanges();
                        scheduleAutoSave();
                    }
                    break;
                case 'h1':
                    wrapInBlock('h1', range, selection);
                    break;
                case 'h2':
                    wrapInBlock('h2', range, selection);
                    break;
                case 'h3':
                    wrapInBlock('h3', range, selection);
                    break;
                case 'h4':
                    wrapInBlock('h4', range, selection);
                    break;
                case 'strikethrough':
                    document.execCommand('strikeThrough', false, null);
                    break;
                case 'hr':
                    const hr = document.createElement('hr');
                    range.deleteContents();
                    range.insertNode(hr);
                    // Move cursor after hr
                    const afterHr = document.createRange();
                    afterHr.setStartAfter(hr);
                    afterHr.collapse(true);
                    selection.removeAllRanges();
                    selection.addRange(afterHr);
                    break;
                case 'ul':
                case 'ol':
                    // Check if selection is inside a block element
                    let listContainer = range.commonAncestorContainer;
                    if (listContainer.nodeType === 3) listContainer = listContainer.parentNode;

                    // Find the parent block element
                    let blockParent = listContainer;
                    while (blockParent && blockParent !== docContent &&
                           !['P', 'DIV', 'H1', 'H2', 'H3', 'H4'].includes(blockParent.tagName)) {
                        blockParent = blockParent.parentNode;
                    }

                    const listTag = type === 'ol' ? 'ol' : 'ul';
                    const newList = document.createElement(listTag);
                    const li = document.createElement('li');

                    if (blockParent && blockParent !== docContent && ['P', 'DIV', 'H1', 'H2', 'H3', 'H4'].includes(blockParent.tagName)) {
                        // Replace the entire block with a list containing its text
                        let text = blockParent.textContent || '';
                        // Strip leading dash/asterisk and whitespace
                        text = text.replace(/^[-*]\s*/, '');
                        li.textContent = text;
                        newList.appendChild(li);
                        blockParent.parentNode.replaceChild(newList, blockParent);
                    } else {
                        // Original behavior for selections not in a block
                        const fragment = range.extractContents();
                        // Strip leading dash and whitespace from text
                        if (fragment.firstChild && fragment.firstChild.nodeType === 3) {
                            fragment.firstChild.textContent = fragment.firstChild.textContent.replace(/^[-*]\s*/, '');
                        }
                        li.appendChild(fragment);
                        newList.appendChild(li);
                        range.insertNode(newList);
                    }
                    selection.removeAllRanges();
                    break;
                case 'p':
                    // Check if we are inside a list item
                    let liParent = range.commonAncestorContainer;
                    if (liParent.nodeType === 3) liParent = liParent.parentNode;
                    const listItem = liParent.closest('li');
                    if (listItem) {
                        const list = listItem.closest('ul') || listItem.closest('ol');
                        const p = document.createElement('p');
                        p.innerHTML = listItem.innerHTML;
                        list.parentNode.insertBefore(p, list);
                        listItem.remove();
                        if (list.children.length === 0) list.remove();
                        const newRange = document.createRange();
                        newRange.selectNodeContents(p);
                        newRange.collapse(false);
                        selection.removeAllRanges();
                        selection.addRange(newRange);
                    } else {
                        wrapInBlock('p', range, selection);
                    }
                    break;
                case 'quote':
                    const blockquote = document.createElement('blockquote');
                    blockquote.appendChild(range.extractContents());
                    range.insertNode(blockquote);
                    selection.removeAllRanges();
                    break;
            }
            document.getElementById('floatingToolbar').classList.remove('visible');
            scheduleAutoSave();
        }

        // Insert styled HR response trigger and fire Claude assistant task
        function respondToDoc() {
            if (!currentDocId) {
                alert('No document open');
                return;
            }
            
            const selection = window.getSelection();
            const docContent = document.getElementById('docContent');
            
            // Create styled HR for response trigger
            const hr = document.createElement('hr');
            hr.className = 'respond-trigger';
            hr.style.cssText = 'border: none; height: 3px; background: linear-gradient(90deg, #6366f1, #8b5cf6, #a855f7); margin: 20px 0; border-radius: 2px;';
            
            // Insert at cursor position or end of doc
            if (selection.rangeCount > 0) {
                const range = selection.getRangeAt(0);
                // Make sure we're inside docContent
                if (docContent.contains(range.commonAncestorContainer)) {
                    range.deleteContents();
                    range.insertNode(hr);
                    // Move cursor after hr
                    const afterHr = document.createRange();
                    afterHr.setStartAfter(hr);
                    afterHr.collapse(true);
                    selection.removeAllRanges();
                    selection.addRange(afterHr);
                } else {
                    docContent.appendChild(hr);
                }
            } else {
                docContent.appendChild(hr);
            }
            
            // Save the doc first
            scheduleAutoSave();
            
            // Get current doc title
            const docTitle = document.getElementById('docTitle').value || 'Untitled';
            
            // Fire Claude assistant task immediately (no modal)
            const taskDescription = `Read doc_id: ${currentDocId} titled ${docTitle} in full and write your response below the last HR in the document.`;
            
            fetch('/execute_task', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    tool_name: 'claude_assistant',
                    action: 'assign_task',
                    params: {
                        description: taskDescription
                    }
                })
            })
            .then(res => res.json())
            .then(data => {
                console.log('Claude task assigned:', data);
                // Show brief toast notification
                const toast = document.createElement('div');
                toast.textContent = 'Claude task queued';
                toast.style.cssText = 'position: fixed; bottom: 20px; right: 20px; background: #6366f1; color: white; padding: 12px 20px; border-radius: 8px; z-index: 10000; font-size: 14px;';
                document.body.appendChild(toast);
                setTimeout(() => toast.remove(), 2000);
            })
            .catch(err => {
                console.error('Failed to queue Claude task:', err);
                alert('Failed to queue Claude task');
            });
        }

        function generateLinkedinPosts() {
            const today = new Date().toLocaleDateString('en-US', { month: 'long', day: 'numeric' });
            const taskDescription = `Query permanent_notes collection filtered for AI coordination, agentic systems, orchestration infrastructure, and thought leadership. Exclude creator economy, social media platform commentary, generic productivity content. Generate 5-10 standalone LinkedIn posts from the filtered notes. Create a doc titled "LinkedIn Posts ${today}" in the Social collection. Format each post as a numbered section with the full post text ready to publish.`;
            queueSlashTask(taskDescription, '💼 Generating LinkedIn posts...');
        }

        function generateTwitterKnowledge() {
            const today = new Date().toLocaleDateString('en-US', { month: 'long', day: 'numeric' });
            const taskDescription = `Query the knowledge vault for book highlights and article highlights. Exclude anything authored by Srinivas Rao or Unmistakable Creative. Select 10-15 punchy standalone quotes suitable for Twitter. Create a doc titled "Twitter Knowledge ${today}" in the Social collection. Format each as: [Quote] - [Author], [Book/Article].`;
            queueSlashTask(taskDescription, '📚 Generating Twitter knowledge posts...');
        }

        function approveSocial() {
            if (!currentDocId) {
                alert('No document open');
                return;
            }
            const docTitle = document.getElementById('docTitle').value || '';
            const network = docTitle.toLowerCase().includes('twitter') ? 'twitter' : 'linkedin';
            const taskDescription = `Read doc_id: ${currentDocId} titled "${docTitle}". Parse all numbered posts from the doc. Insert each post into social.db with network=${network} and status=queued. Confirm how many posts were loaded.`;
            queueSlashTask(taskDescription, `✅ Loading posts to social.db as ${network}...`);
        }

        function factCheck() {
            if (!currentDocId) {
                alert('No document open');
                return;
            }
            const docTitle = document.getElementById('docTitle').value || 'Untitled';
            const today = new Date().toLocaleDateString('en-US', { month: 'long', day: 'numeric' });
            const taskDescription = `Read doc_id: ${currentDocId} titled "${docTitle}" in full. Extract all factual claims from the document. For each claim, search the web to verify accuracy. Create a new doc titled "${docTitle} - Fact Check ${today}" in the Blogs collection with the verification results. Format: each claim as an H2, the article claim quoted, verdict (ACCURATE/PARTIALLY ACCURATE/INACCURATE), supporting evidence with sources, and recommended corrections if needed. End with a summary section.`;
            queueSlashTask(taskDescription, '🔍 Fact check task queued...');
        }

        function consolidateDoc() {
            if (!currentDocId) {
                alert('No document open');
                return;
            }
            const docTitle = document.getElementById('docTitle').value || 'Untitled';
            const taskDescription = `Read doc_id: ${currentDocId} titled "${docTitle}" in full. Consolidate and clean up the document:
1. Remove duplicate content and redundant sections
2. Merge related ideas and sections
3. Remove outdated or irrelevant notes
4. Improve organization and flow
5. Clean up formatting inconsistencies
6. Keep the core ideas and valuable content intact

Overwrite the original doc with the cleaned version. Preserve the collection and title. Do not create a new doc - update the existing one in place.`;
            queueSlashTask(taskDescription, '🧹 Consolidation task queued...');
        }

        function queueSlashTask(description, toastMsg) {
            fetch('/execute_task', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    tool_name: 'claude_assistant',
                    action: 'assign_task',
                    params: { description }
                })
            })
            .then(res => res.json())
            .then(() => {
                const toast = document.createElement('div');
                toast.textContent = toastMsg;
                toast.style.cssText = 'position:fixed;bottom:20px;right:20px;background:#6366f1;color:white;padding:12px 20px;border-radius:8px;z-index:10000;font-size:14px;';
                document.body.appendChild(toast);
                setTimeout(() => toast.remove(), 2500);
            })
            .catch(err => console.error('Failed to queue task:', err));
        }

        // Summarize YouTube video - prompts for URL if not in slash command
        function summarizeVideo(providedUrl) {
            if (!currentDocId) {
                alert('No document open');
                return;
            }
            
            // If URL provided directly, queue immediately
            if (providedUrl && providedUrl.includes('youtube.com') || providedUrl && providedUrl.includes('youtu.be')) {
                queueVideoSummaryTask(providedUrl);
                return;
            }
            
            // Show inline prompt for URL
            showUrlPrompt('Paste YouTube URL:', (url) => {
                if (url && (url.includes('youtube.com') || url.includes('youtu.be'))) {
                    queueVideoSummaryTask(url);
                } else {
                    alert('Please enter a valid YouTube URL');
                }
            });
        }
        
        // Show inline prompt for URL input
        function showUrlPrompt(placeholder, callback) {
            // Create overlay
            const overlay = document.createElement('div');
            overlay.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 10000; display: flex; align-items: center; justify-content: center;';
            
            const promptBox = document.createElement('div');
            promptBox.style.cssText = 'background: var(--bg-card); padding: 24px; border-radius: 12px; min-width: 400px; box-shadow: 0 8px 32px rgba(0,0,0,0.3);';
            
            const label = document.createElement('div');
            label.textContent = placeholder;
            label.style.cssText = 'color: var(--text-muted); margin-bottom: 12px; font-size: 14px;';
            
            const input = document.createElement('input');
            input.type = 'text';
            input.placeholder = 'https://youtube.com/watch?v=...';
            input.style.cssText = 'width: 100%; padding: 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-page); color: var(--text); font-size: 14px; box-sizing: border-box;';
            
            const btnRow = document.createElement('div');
            btnRow.style.cssText = 'display: flex; gap: 8px; margin-top: 16px; justify-content: flex-end;';
            
            const cancelBtn = document.createElement('button');
            cancelBtn.textContent = 'Cancel';
            cancelBtn.style.cssText = 'padding: 8px 16px; border: 1px solid var(--border); border-radius: 6px; background: transparent; color: var(--text-muted); cursor: pointer;';
            cancelBtn.onclick = () => overlay.remove();
            
            const submitBtn = document.createElement('button');
            submitBtn.textContent = 'Summarize';
            submitBtn.style.cssText = 'padding: 8px 16px; border: none; border-radius: 6px; background: #6366f1; color: white; cursor: pointer;';
            submitBtn.onclick = () => {
                const url = input.value.trim();
                overlay.remove();
                callback(url);
            };
            
            input.onkeydown = (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    submitBtn.click();
                } else if (e.key === 'Escape') {
                    overlay.remove();
                }
            };
            
            btnRow.appendChild(cancelBtn);
            btnRow.appendChild(submitBtn);
            promptBox.appendChild(label);
            promptBox.appendChild(input);
            promptBox.appendChild(btnRow);
            overlay.appendChild(promptBox);
            document.body.appendChild(overlay);
            
            // Focus input after render
            setTimeout(() => input.focus(), 0);
        }
        
        // Queue the video summary task
        function queueVideoSummaryTask(url) {
            const taskDescription = `Transcribe and summarize this YouTube video: ${url}

Use media_manager to download/transcribe, then create a summary doc with:
- Video title and URL
- Key points (bullet list)
- Full transcript (collapsible section if long)

Write the summary to doc_id: ${currentDocId} below the last HR, or create a new doc if this one doesn't have an HR.`;
            
            fetch('/execute_task', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    tool_name: 'claude_assistant',
                    action: 'assign_task',
                    params: {
                        description: taskDescription
                    }
                })
            })
            .then(res => res.json())
            .then(data => {
                console.log('Video summary task queued:', data);
                const toast = document.createElement('div');
                toast.textContent = 'Video summary task queued';
                toast.style.cssText = 'position: fixed; bottom: 20px; right: 20px; background: #6366f1; color: white; padding: 12px 20px; border-radius: 8px; z-index: 10000; font-size: 14px;';
                document.body.appendChild(toast);
                setTimeout(() => toast.remove(), 2000);
            })
            .catch(err => {
                console.error('Failed to queue video summary task:', err);
                alert('Failed to queue video summary task');
            });
        }
        // Run virality analysis on current doc - creates analysis doc in Resources
        function runViralityAnalysis() {
            if (!currentDocId) {
                alert('No document open');
                return;
            }

            const docTitle = document.getElementById('docTitle').value || 'Untitled';

            // Queue Claude task to run full virality analysis workflow
            const taskDescription = `Run a STEPPS virality analysis on doc_id: ${currentDocId} titled "${docTitle}".

WORKFLOW:
1. Read data/virality_revision_config.json FIRST - this contains required constraints
2. Use liwc tool with action virality_analysis to analyze the doc
3. Create analysis doc in Resources collection with:
   - Title: "Virality Analysis - ${docTitle}"
   - STEPPS factor scores
   - Weakest factors identified
   - Sentence-level flags for targeted edits
4. Make ONE revision pass on the ORIGINAL doc (${currentDocId}):
   - Use flag_interpretations from config to guide HOW to fix each issue
   - DO NOT add emotion words, certainty words, or affect language to hit targets
   - Stay within +/-20% of original word count
   - DO NOT make multiple passes that compound changes
5. Update analysis doc with before/after comparison

CRITICAL: LIWC data is DIAGNOSTIC only. Flags tell you WHERE to improve. HOW to improve means strengthening substance, specificity, and stakes - not gaming linguistic markers. Do NOT optimize for scores.

Put final analysis doc in Resources collection, NOT Blogs.`;

            fetch('/execute_task', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    tool_name: 'claude_assistant',
                    action: 'assign_task',
                    params: {
                        description: taskDescription
                    }
                })
            })
            .then(res => res.json())
            .then(data => {
                console.log('Virality analysis task queued:', data);
                const toast = document.createElement('div');
                toast.textContent = 'Virality analysis queued';
                toast.style.cssText = 'position: fixed; bottom: 20px; right: 20px; background: #6366f1; color: white; padding: 12px 20px; border-radius: 8px; z-index: 10000; font-size: 14px;';
                document.body.appendChild(toast);
                setTimeout(() => toast.remove(), 2000);
            })
            .catch(err => {
                console.error('Failed to queue virality analysis task:', err);
                alert('Failed to queue virality analysis task');
            });
        }

        // Insert a code block at cursor position
        function insertCodeBlock() {
            const selection = window.getSelection();
            if (!selection.rangeCount) return;

            const range = selection.getRangeAt(0);

            // Create pre and code elements
            const pre = document.createElement('pre');
            const code = document.createElement('code');
            code.className = 'language-javascript';

            // If there's selected text, use it; otherwise placeholder
            const selectedText = selection.toString();
            code.textContent = selectedText || '// Enter code here';

            pre.appendChild(code);

            // Replace the current block with pre + p after, so pre is a direct child of docContent
            const currentBlock = getEditableBlock(range.startContainer) || docContent.lastElementChild;
            if (currentBlock && currentBlock.parentNode === docContent) {
                const p = document.createElement('p');
                p.innerHTML = '<br>';
                currentBlock.replaceWith(pre);
                pre.parentNode.insertBefore(p, pre.nextSibling);
            } else {
                // Force pre to be direct child of docContent to prevent nesting issues
                range.deleteContents();
                docContent.appendChild(pre);
                const p = document.createElement('p');
                p.innerHTML = '<br>';
                docContent.appendChild(p);
            }

            // Move cursor into the code block
            const newRange = document.createRange();
            newRange.selectNodeContents(code);
            selection.removeAllRanges();
            selection.addRange(newRange);

            scheduleAutoSave();
        }

        // Insert a 3x3 table at cursor position
        function insertTable() {
            const selection = window.getSelection();
            if (!selection.rangeCount) return;

            const range = selection.getRangeAt(0);

            // Create table with 3 rows and 3 columns
            const table = document.createElement('table');
            table.className = 'md-table';
            table.style.cssText = 'border-collapse:collapse;width:100%;margin:16px 0;';

            // Header row
            const thead = document.createElement('thead');
            const headerRow = document.createElement('tr');
            for (let i = 0; i < 3; i++) {
                const th = document.createElement('th');
                th.style.cssText = 'border:1px solid var(--border-color,#333);padding:8px 12px;text-align:left;background:var(--bg-tertiary,#1A1A1E);font-weight:600;';
                th.textContent = 'Header ' + (i + 1);
                headerRow.appendChild(th);
            }
            thead.appendChild(headerRow);
            table.appendChild(thead);

            // Body rows
            const tbody = document.createElement('tbody');
            for (let r = 0; r < 2; r++) {
                const row = document.createElement('tr');
                for (let c = 0; c < 3; c++) {
                    const td = document.createElement('td');
                    td.style.cssText = 'border:1px solid var(--border-color,#333);padding:8px 12px;text-align:left;';
                    td.textContent = 'Cell';
                    row.appendChild(td);
                }
                tbody.appendChild(row);
            }
            table.appendChild(tbody);

            // Insert the table
            range.deleteContents();
            range.insertNode(table);

            // Add a paragraph after for continued typing
            const p = document.createElement('p');
            p.innerHTML = '<br>';
            table.parentNode.insertBefore(p, table.nextSibling);

            selection.removeAllRanges();
            scheduleAutoSave();
        }

        function wrapInBlock(tag, range, selection) {
            const dc = document.getElementById('docContent');
            let container = range.commonAncestorContainer;
            if (container.nodeType === 3) container = container.parentNode;

            // Walk up to find direct child of docContent
            let blockEl = container;
            while (blockEl && blockEl.parentNode !== dc) {
                blockEl = blockEl.parentNode;
            }

            if (blockEl && blockEl.parentNode === dc) {
                // If blockEl is a DIV wrapper, look inside for the actual header
                const inner = blockEl.querySelector('h1,h2,h3,h4,h5,h6') || blockEl;
                const sourceEl = (blockEl.tagName === 'DIV' && inner !== blockEl) ? inner : blockEl;

                // Toggle: clicking same tag converts to paragraph
                const effectiveTag = (sourceEl.tagName.toLowerCase() === tag.toLowerCase()) ? 'p' : tag;

                const newEl = document.createElement(effectiveTag);
                if (['PRE', 'CODE'].includes(sourceEl.tagName)) {
                    newEl.textContent = sourceEl.textContent || '';
                } else {
                    let content = sourceEl.innerHTML;
                    content = content.replace(/<span[^>]*class="collapse-chevron"[^>]*>.*?<\/span>/gi, '');
                    newEl.innerHTML = content;
                }
                blockEl.parentNode.replaceChild(newEl, blockEl);
                const newRange = document.createRange();
                newRange.selectNodeContents(newEl);
                newRange.collapse(false);
                selection.removeAllRanges();
                selection.addRange(newRange);
            }
        }

        // Show toolbar on selection
        window.insertLinkAtSelection = function insertLinkAtSelection() {
            const selection = window.getSelection();
            if (!selection.rangeCount || selection.toString().trim() === '') return;
            const url = prompt('Enter URL:');
            if (!url || !url.trim()) return;
            const range = selection.getRangeAt(0);
            const a = document.createElement('a');
            a.href = url.trim();
            a.target = '_blank';
            a.appendChild(range.extractContents());
            range.insertNode(a);
            selection.removeAllRanges();
            scheduleAutoSave();
        }


        function checkSelection() {
            const selection = window.getSelection();
            const selectedText = selection.toString().trim();

            if (selectedText.length > 0 && docContent.contains(selection.anchorNode)) {
                const range = selection.getRangeAt(0);
                const rect = range.getBoundingClientRect();

                // Position toolbar above selection, centered
                const toolbarEl = document.getElementById('floatingToolbar');
                toolbarEl.style.left = `${rect.left + rect.width / 2}px`;
                toolbarEl.style.top = `${rect.top - 50}px`;
                toolbarEl.classList.add('visible');
            } else {
                document.getElementById('floatingToolbar').classList.remove('visible');
            }
        }

        // Focus mode - distraction free writing
        let focusTimeout = null;
        // Collection helper
        // Generate consistent color from string
        function stringToColor(str) {
            let hash = 0;
            for (let i = 0; i < str.length; i++) {
                hash = str.charCodeAt(i) + ((hash << 5) - hash);
            }
            const hue = Math.abs(hash % 360);
            return { hue, color: `hsl(${hue}, 70%, 65%)`, bg: `hsla(${hue}, 70%, 50%, 0.2)` };
        }

        function setCollection(name) {
            const label = document.getElementById('collectionLabel');
            label.textContent = name;
            const slug = name.toLowerCase().replace(/\s+/g, '-');
            label.className = 'collection-label ' + slug;
            // Apply dynamic color for custom collections
            const knownCollections = ['notes', 'projects', 'logs', 'inbox', 'resources', 'permanent-notes'];
            if (!knownCollections.includes(slug)) {
                const { color, bg } = stringToColor(name);
                label.style.color = color;
                label.style.background = bg;
            } else {
                label.style.color = '';
                label.style.background = '';
            }
        }

        // Hashtag collection detection
        const validCollections = ['notes', 'permanent notes', 'projects', 'logs', 'resources', 'inbox'];
        function detectHashtagCollection() {
            const content = document.getElementById('docContent').innerHTML;
            // Match #hashtag followed by space, &nbsp;, <br>, or newline
            const match = content.match(/#([a-zA-Z][a-zA-Z0-9-]*)(?:\s|&nbsp;|<br>|<br\/>|<br \/>)/i);
            if (match) {
                let collection = match[1].toLowerCase().replace(/-+/g, ' ');
                // Capitalize first letter of each word
                collection = collection.split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
                setCollection(collection);
                // Remove the hashtag from content
                document.getElementById('docContent').innerHTML = content.replace(match[0], '').trim();
                scheduleAutoSave();
            }
        }

        function enterFocusMode() {
            document.body.classList.add('focus-mode');
        }
        function exitFocusMode() {
            document.body.classList.remove('focus-mode');
        }


        function placeCaretIn(el, position = 'start', offset = null) {
            const range = document.createRange();
            const sel = window.getSelection();
            
            // Bounds check: clamp offset to valid range to prevent IndexSizeError
            function safeSetStart(node, off) {
                const maxLen = node.nodeType === 3 ? node.length : node.childNodes.length;
                const safeOffset = Math.max(0, Math.min(off, maxLen));
                range.setStart(node, safeOffset);
            }
            
            if (position === 'end') {
                // Find last text node or use element end
                const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null, false);
                let lastTextNode = null;
                while (walker.nextNode()) lastTextNode = walker.currentNode;
                if (lastTextNode) {
                    safeSetStart(lastTextNode, offset !== null ? offset : lastTextNode.length);
                    range.collapse(true);
                } else {
                    range.selectNodeContents(el);
                    range.collapse(false); // collapse to end
                }
            } else {
                if (el.firstChild && el.firstChild.nodeType === 3) {
                    safeSetStart(el.firstChild, offset !== null ? offset : 0);
                } else {
                    range.selectNodeContents(el);
                }
                range.collapse(true);
            }
            sel.removeAllRanges();
            sel.addRange(range);
            // Don't call focus() or scrollIntoView() - the caret placement is enough
            // and the element should already be visible since user was just typing there
        }

        // Strip formatting on paste - match Docs style
        // Special handling: force plain text in code blocks to prevent corruption
        docContent.addEventListener('paste', (e) => {
            e.preventDefault();
            const text = e.clipboardData.getData('text/plain');
            
            // Check if cursor is inside a code block
            const selection = window.getSelection();
            if (selection.rangeCount > 0) {
                const range = selection.getRangeAt(0);
                const container = range.startContainer.parentElement || range.startContainer;
                
                // If inside <pre> or <code>, force plain text paste
                if (container.closest('pre') || container.closest('code')) {
                    document.execCommand('insertText', false, text);
                    scheduleAutoSave();
                    return;
                }
            }
            
            // Normal paste: If user pasted HTML, preserve basic structure
            const html = e.clipboardData.getData('text/html');
            if (html) {
                // Create temp element to strip styles
                const temp = document.createElement('div');
                temp.innerHTML = html;
                // Remove all style attributes and class attributes
                temp.querySelectorAll('*').forEach(el => {
                    el.removeAttribute('style');
                    el.removeAttribute('class');
                    // Keep only structural elements
                    if (!['P','BR','DIV','UL','OL','LI','H1','H2','H3','H4','STRONG','B','EM','I','A','CODE','PRE','BLOCKQUOTE'].includes(el.tagName)) {
                        // Replace non-semantic elements with their text content
                        el.replaceWith(document.createTextNode(el.textContent));
                    }
                });
                document.execCommand('insertHTML', false, temp.innerHTML);
            } else {
                // Plain text paste
                document.execCommand('insertText', false, text);
            }
            scheduleAutoSave();
        });
        docContent.addEventListener('focus', () => {
            // Enter focus mode after brief delay when clicking in content
            clearTimeout(focusTimeout);
            focusTimeout = setTimeout(enterFocusMode, 500);
        });
        docContent.addEventListener('mouseup', () => setTimeout(checkSelection, 10));
        docContent.addEventListener('keyup', (e) => {
            if (e.shiftKey) setTimeout(checkSelection, 10);
            else document.getElementById('floatingToolbar').classList.remove('visible');
        });
        // Also check on selection change
        document.addEventListener('selectionchange', () => {
            if (docContent.contains(document.activeElement) || document.activeElement === docContent) {
                setTimeout(checkSelection, 10);
            }
        });
        // Click on sidebar item exits focus mode
        document.querySelector('.doc-list-sidebar').addEventListener('click', exitFocusMode);

        document.addEventListener('click', (e) => {
            const toolbarEl = document.getElementById('floatingToolbar');
            if (toolbarEl && !toolbarEl.contains(e.target) && e.target !== docContent) {
                toolbarEl.classList.remove('visible');
            }
        });

        function formatDate(dateStr) {
            if (!dateStr) return 'Unknown';
            const d = new Date(dateStr);
            const diff = Date.now() - d;
            if (diff < 60000) return 'just now';
            if (diff < 3600000) return `${Math.floor(diff/60000)}m ago`;
            if (diff < 86400000) return `${Math.floor(diff/3600000)}h ago`;
            if (diff < 604800000) return `${Math.floor(diff/86400000)}d ago`;
            return d.toLocaleDateString();
        }

        // Initialize: load config first, then doc list
        (async function initEditor() {
            await loadEditorConfig();
            await loadDocList();
            renderTimeline();
            
            // Doc content polling only (doc list no longer auto-refreshes)
            startDocContentPolling();
        })();

        // Check URL for doc ID param - auto-load if present
        (async function checkUrlForDoc() {
            // In Swift mode, load doc from injected SWIFT_DOC_ID
            if (isSwiftMode() && window.SWIFT_DOC_ID) {
                await new Promise(r => setTimeout(r, 150));
                swiftPost('loadDoc', { docId: window.SWIFT_DOC_ID });
                return;
            }
            const urlParams = new URLSearchParams(window.location.search);
            const docId = urlParams.get('id');
            if (docId) {
                // Wait a tick for allDocsCache to populate
                await new Promise(r => setTimeout(r, 100));
                openDocFromTimeline(docId);
            }
        })();

        // View toggle
        let currentView = 'timeline';
        let timelineSort = 'updated';
        let allDocsCache = [];

        function setView(view) {
            currentView = view;
            document.getElementById('sidebarViewBtn').classList.toggle('active', view === 'sidebar');
            document.getElementById('timelineViewBtn').classList.toggle('active', view === 'timeline');
            document.body.classList.toggle('timeline-mode', view === 'timeline');

            if (view === 'timeline') {
                renderTimeline();
                // Clear URL param when returning to timeline
                if (window.location.search) {
                    history.pushState({}, '', '/editor');
                }
            }
        }

        function setTimelineSort(sort) {
            timelineSort = sort;
            document.querySelectorAll('.sort-chip').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.sort === sort);
            });
            renderTimeline();
        }

        let collectionFilter = '';
        let statusFilter = '';

        function setCollectionFilter(collection) {
            collectionFilter = collection;
            renderTimeline();
            updateTimelineFilterBtn();
        }

        // Timeline Filter Modal Functions
        let timelineSearchQuery = '';

        function openTimelineFilterModal() {
            populateTimelineFilterPills();
            document.getElementById('timelineFilterSearch').value = timelineSearchQuery;
            document.getElementById('timelineFilterModal').classList.add('active');
            document.getElementById('timelineFilterSearch').focus();
        }

        function closeTimelineFilterModal() {
            document.getElementById('timelineFilterModal').classList.remove('active');
            updateTimelineFilterBtn();
        }


        function populateTimelineFilterPills() {
            // Collection dropdown
            const collections = [...new Set(allDocsCache.map(d => d.collection).filter(c => c && !EXCLUDED_COLLECTIONS.includes(c)))].sort();
            const collDropdown = document.getElementById('collectionDropdown');
            if (collDropdown) {
                const collOptions = ['<option value="">All Collections</option>'];
                collections.forEach(c => {
                    const selected = collectionFilter === c ? 'selected' : '';
                    collOptions.push(`<option value="${c}" ${selected}>${c}</option>`);
                });
                collDropdown.innerHTML = collOptions.join('');
            }

            // Status dropdown
            const statusDropdown = document.getElementById('statusDropdown');
            if (statusDropdown) {
                statusDropdown.value = statusFilter || 'any';
            }
        }

        function selectTimelineCollection(collection) {
            collectionFilter = collection;
            renderTimeline();
            updateTimelineFilterBtn();
        }

        function selectTimelineStatus(status) {
            statusFilter = status === 'any' ? '' : status;
            renderTimeline();
            updateTimelineFilterBtn();
        }

        function applyTimelineFilter() {
            timelineSearchQuery = document.getElementById('timelineFilterSearch').value;
            renderTimeline();
        }

        function clearTimelineFilters() {
            collectionFilter = '';
            statusFilter = '';
            timelineSearchQuery = '';
            document.getElementById('timelineFilterSearch').value = '';
            const collDropdown = document.getElementById('collectionDropdown');
            const statusDropdown = document.getElementById('statusDropdown');
            if (collDropdown) collDropdown.value = '';
            if (statusDropdown) statusDropdown.value = 'any';
            renderTimeline();
            updateTimelineFilterBtn();
        }

        function updateTimelineFilterBtn() {
            const btn = document.getElementById('timelineFilterBtn');
            if (btn) {
                const hasFilter = collectionFilter || statusFilter || timelineSearchQuery;
                btn.classList.toggle('has-filter', !!hasFilter);
            }
        }

        async function renderTimeline() {
            const container = document.getElementById('timelineCards');

            try {
                // Use allDocsCache directly; if empty, fetch once to populate
                if (allDocsCache.length === 0) {
                    if (isSwiftMode()) return;  // Wait for swiftListDocs callback
                    const res = await fetch('/docs/list');
                    const data = await res.json();
                    allDocsCache = data.docs || [];
                }

                // Exclude archived docs from timeline
                let docs = allDocsCache.filter(d => !EXCLUDED_COLLECTIONS.includes(d.collection));

                // Filter by collection
                if (collectionFilter) {
                    docs = docs.filter(d => d.collection === collectionFilter);
                }

                // Filter by status
                if (statusFilter) {
                    docs = docs.filter(d => d.status === statusFilter);
                }

                // Filter by search query
                if (timelineSearchQuery) {
                    const q = timelineSearchQuery.toLowerCase();
                    docs = docs.filter(d => d.title && d.title.toLowerCase().includes(q));
                }

                // Sort
                docs = [...docs].sort((a, b) => {
                    if (timelineSort === 'title') return (a.title || '').localeCompare(b.title || '');
                    if (timelineSort === 'created') return new Date(b.created_at || 0) - new Date(a.created_at || 0);
                    return new Date(b.updated_at || 0) - new Date(a.updated_at || 0);
                });

                // Store filtered docs for navigation when opening from timeline
                currentDisplayedDocs = docs;

                // Update timeline title with count
                const titleEl = document.querySelector('.timeline-title');
                if (titleEl) {
                    const countText = collectionFilter || statusFilter || timelineSearchQuery
                        ? `Documents · ${docs.length}`
                        : `Documents · ${docs.length}`;
                    titleEl.textContent = countText;
                }

                container.innerHTML = docs.map(doc => {
                    const wordCount = doc.word_count || 0;
                    const dateStr = formatDate(doc.updated_at);
                    return `
                        <div class="timeline-card" data-id="${doc.id}" onclick="openDocFromTimeline('${doc.id}')">
                            <div class="timeline-card-header">
                                <input type="checkbox" class="timeline-card-checkbox" 
                                    onclick="event.stopPropagation(); toggleDocSelection('${doc.id}', this)"
                                    ${selectedDocs.has(doc.id) ? 'checked' : ''}>
                                <div class="timeline-card-content-wrapper">
                                    <div class="timeline-card-title">${doc.title || 'Untitled'}</div>
                                    <div class="timeline-card-meta">
                                        <span class="collection-badge ${(doc.collection || '').toLowerCase().replace(/\s+/g, '-')}" style="${(() => { const c = doc.collection || ''; const known = ['notes','projects','logs','inbox','resources','permanent notes']; if (!known.includes(c.toLowerCase())) { const {color,bg} = stringToColor(c); return `color:${color};background:${bg}`; } return ''; })()}">${doc.collection || 'Notes'}</span>
                                        <span class="timeline-card-date">${dateStr}</span>
                                        <span class="timeline-card-stats">${wordCount.toLocaleString()} words</span>
                                        ${doc.status ? `<span class="status-badge ${doc.status}">${doc.status === 'in_progress' ? 'in progress' : doc.status === 'publication_ready' ? 'ready' : doc.status}</span>` : ''}
                                    </div>
                                </div>
                                <div class="card-actions">
                                    <button class="timeline-card-expand" onclick="event.stopPropagation(); toggleTimelineCard(this.closest('.timeline-card'))">+</button>
                                    <button class="timeline-card-delete" onclick="event.stopPropagation(); deleteDocFromTimeline('${doc.id}')" title="Delete">−</button>
                                </div>
                            </div>
                            <div class="timeline-card-metadata" onclick="event.stopPropagation()">
                                <div class="metadata-field">
                                    <div class="metadata-label">Description</div>
                                    <textarea class="metadata-textarea"
                                        placeholder="Add a short description..."
                                        data-doc-id="${doc.id}"
                                        data-field="description"
                                        onblur="saveMetadataField(this)">${doc.description || ''}</textarea>
                                </div>
                                <div class="metadata-field">
                                    <div class="metadata-label">Status</div>
                                    <div class="status-pills">
                                        <button class="status-pill ${doc.status === 'idea' ? 'active' : ''}" data-status="idea" onclick="setDocStatus('${doc.id}', 'idea', this)">Idea</button>
                                        <button class="status-pill ${doc.status === 'draft' ? 'active' : ''}" data-status="draft" onclick="setDocStatus('${doc.id}', 'draft', this)">Draft</button>
                                        <button class="status-pill ${doc.status === 'in_progress' ? 'active' : ''}" data-status="in_progress" onclick="setDocStatus('${doc.id}', 'in_progress', this)">In Progress</button>
                                        <button class="status-pill ${doc.status === 'publication_ready' ? 'active' : ''}" data-status="publication_ready" onclick="setDocStatus('${doc.id}', 'publication_ready', this)">Publication Ready</button>
                                        <button class="status-pill ${doc.status === 'published' ? 'active' : ''}" data-status="published" onclick="setDocStatus('${doc.id}', 'published', this)">Published</button>
                                    </div>
                                </div>
                                <div class="publication-section">
                                    <div class="publication-section-title">Publication Details</div>
                                    <div class="metadata-field">
                                        <div class="metadata-label">Campaign ID</div>
                                        <input type="text" class="metadata-input"
                                            placeholder="e.g. Q1-2026-launch"
                                            value="${doc.campaign_id || ''}"
                                            data-doc-id="${doc.id}"
                                            data-field="campaign_id"
                                            onblur="saveMetadataField(this)">
                                    </div>
                                    <div class="metadata-field">
                                        <div class="metadata-label">Published URL</div>
                                        <input type="text" class="metadata-input"
                                            placeholder="https://..."
                                            value="${doc.published_url || ''}"
                                            data-doc-id="${doc.id}"
                                            data-field="published_url"
                                            onblur="saveMetadataField(this)">
                                    </div>
                                </div>
                                <div class="metadata-btn-row">
                                    <button class="metadata-queue-btn" onclick="showQueueTaskModal('${doc.id}', '${doc.title.replace(/'/g, "\\'")}')">Queue Task</button>
                                    <button class="metadata-publish-btn" onclick="publishToMedium('${doc.id}')">
                                        <svg viewBox="0 0 1633 1000" fill="currentColor"><path d="M178.5 313.6c1.9-19.1-5.4-38-19.7-50.4L31.5 106.2V75h393.2l303.7 665.9L999.6 75H1375v31.3L1268 211c-9.3 7.1-14 18.4-12.2 29.7v746.9c-1.7 11.3 2.9 22.6 12.2 29.7l104.4 104.7v31.3H870.5v-31.3l108.1-105c10.6-10.6 10.6-13.8 10.6-30V365.5l-300.6 763.2h-40.6L310.3 365.5v511.5c-2.9 21.6 4.3 43.3 19.4 58.9l140.8 170.8v31.3H29.2v-31.3l140.8-170.8c15-15.6 21.7-37.5 18.5-58.9V313.6z"/></svg>
                                        Publish
                                    </button>
                                    <button class="metadata-delete-btn" onclick="deleteDocFromTimeline('${doc.id}')">Delete</button>
                                </div>
                            </div>
                        </div>
                    `;
                }).join('');

            } catch (e) {
                console.error('Failed to load timeline:', e);
                container.innerHTML = '<div style="color:#666;text-align:center;padding:40px;">Failed to load documents</div>';
            }
        }

        function toggleTimelineCard(card) {
            const wasExpanded = card.classList.contains('expanded');
            document.querySelectorAll('.timeline-card.expanded').forEach(c => c.classList.remove('expanded'));
            if (!wasExpanded) card.classList.add('expanded');
        }

        async function saveMetadataField(element) {
            const docId = element.dataset.docId;
            const field = element.dataset.field;
            const value = element.value;

            // Find the doc in cache and update it
            const doc = allDocsCache.find(d => d.id === docId);
            if (doc) doc[field] = value;

            // Save ONLY the specific field - server preserves other fields
            // DO NOT send content - cache doesn't have it, would wipe document!
            try {
                await fetch('/docs/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        id: docId,
                        [field]: value
                    })
                });
            } catch (e) {
                console.error('Failed to save metadata:', e);
            }
        }

        async function setDocStatus(docId, status, pill) {
            // Update UI immediately
            const pillContainer = pill.closest('.status-pills');
            pillContainer.querySelectorAll('.status-pill').forEach(p => p.classList.remove('active'));
            pill.classList.add('active');

            // Update cache
            const doc = allDocsCache.find(d => d.id === docId);
            if (doc) doc.status = status;

            // Save ONLY status field - server preserves other fields
            // DO NOT send content - cache doesn't have it, would wipe document!
            try {
                await fetch('/docs/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        id: docId,
                        status: status
                    })
                });
            } catch (e) {
                console.error('Failed to save status:', e);
            }
        }

        async function openDocFromTimeline(docId) {
            // Store collection context for Escape navigation
            docOpenedFromCollection = collectionFilter || null;
            // Lock the navigation order to the current timeline view
            // (currentDisplayedDocs is already set by loadTimeline)
            navDocsLocked = true;
            
            // Enter focus mode BEFORE switching view to prevent flicker
            enterFocusMode();
            setView('sidebar');
            await loadDoc(docId);
            document.getElementById('docContent').focus();
            // Update URL to include doc ID for shareability
            history.pushState({ docId: docId }, '', `/editor?id=${docId}`);
        }

        async function publishToMedium(docId) {
            const btn = event.target.closest('.metadata-publish-btn');
            const originalText = btn.innerHTML;
            btn.innerHTML = '<svg viewBox="0 0 24 24" fill="currentColor" style="width:16px;height:16px;animation:spin 1s linear infinite"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" fill="none" stroke-dasharray="30 70"/></svg> Publishing...';
            btn.disabled = true;

            try {
                const response = await fetch('/execute_task', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        tool_name: 'medium_publisher',
                        action: 'publish_from_doc_editor',
                        params: { doc_id: docId }
                    })
                });
                const result = await response.json();

                if (result.status === 'success') {
                    btn.innerHTML = '<svg viewBox="0 0 24 24" fill="currentColor" style="width:16px;height:16px"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg> Published!';
                    btn.style.borderColor = '#22c55e';
                    btn.style.color = '#22c55e';
                    if (result.url) {
                        setTimeout(() => window.open(result.url, '_blank'), 1000);
                    }
                } else {
                    throw new Error(result.message || 'Publish failed');
                }
            } catch (e) {
                alert('Publish failed: ' + e.message);
                btn.innerHTML = originalText;
                btn.disabled = false;
            }
        }

        async function deleteDocFromTimeline(docId) {
            if (!confirm('Delete this document?')) return;
            try {
                await fetch(`/docs/delete/${docId}`, { method: 'DELETE' });
                renderTimeline();
            } catch (e) {
                console.error('Failed to delete:', e);
            }
        }

        // Track selected docs for bulk delete
        let selectedDocs = new Set();

        function toggleDocSelection(docId, checkbox) {
            if (checkbox.checked) {
                selectedDocs.add(docId);
            } else {
                selectedDocs.delete(docId);
            }
            updateBulkDeleteBtn();
        }

        function updateBulkDeleteBtn() {
            const btn = document.getElementById('bulkDeleteBtn');
            const countEl = document.getElementById('selectedCount');
            if (selectedDocs.size > 0) {
                btn.classList.add('visible');
                countEl.textContent = `(${selectedDocs.size})`;
            } else {
                btn.classList.remove('visible');
            }
        }

        async function bulkDeleteSelected() {
            if (selectedDocs.size === 0) return;
            if (!confirm(`Delete ${selectedDocs.size} selected document(s)?`)) return;
            try {
                const res = await fetch('/docs/bulk-delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ doc_ids: Array.from(selectedDocs) })
                });
                const data = await res.json();
                if (data.status === 'success') {
                    selectedDocs.clear();
                    updateBulkDeleteBtn();
                    renderTimeline();
                } else {
                    alert('Error: ' + (data.message || 'Failed to delete'));
                }
            } catch (e) {
                console.error('Bulk delete failed:', e);
                alert('Failed to delete selected documents');
            }
        }

        function newDocFromTimeline() {
            enterFocusMode();
            setView('sidebar');
            newDoc();
            document.getElementById('docTitle').focus();
        }

        // Track current doc's last known update time
        let lastKnownUpdatedAt = null;

        // Auto-refresh doc content using config interval (starts after config loaded)
        function startDocContentPolling() {
            const interval = 30000;
            setInterval(async () => {
                const isEditing = document.activeElement === docContent || document.activeElement === document.getElementById('docTitle');

                // Refresh current doc if it was updated externally (skip if pending save)
                if (currentDocId && !isEditing && !pendingSave) {
                    try {
                        const resp = await fetch(`/docs/get/${currentDocId}`);
                        if (resp.ok) {
                            const data = await resp.json();
                            if (data.status === 'success' && data.doc) {
                                const doc = data.doc;
                                if (doc.updated_at && doc.updated_at !== lastKnownUpdatedAt) {
                                    console.log('Doc updated externally, refreshing...');
                                    lastKnownUpdatedAt = doc.updated_at;
                                    document.getElementById('docTitle').value = doc.title || '';
                                    docContent.innerHTML = doc.content || '';
                                    currentCollection = doc.collection || 'Notes';
                                    updateCollectionLabel();
                                    document.getElementById('docMeta').innerHTML = `
                                        <span>Created ${formatDate(doc.created_at)}</span>
                                        <span>Updated ${formatDate(doc.updated_at)}</span>
                                    `;
                                    // Also refresh timeline if visible
                                    if (currentView === 'timeline') {
                                        renderTimeline();
                                    }
                                }
                            }
                        }
                    } catch (e) {
                        // Ignore fetch errors during polling
                    }
                }
            }, interval);
        }

        
        // Theme Toggle
        function toggleTheme() {
            document.body.classList.toggle('light-mode');
            const isLight = document.body.classList.contains('light-mode');
            localStorage.setItem('docEditorTheme', isLight ? 'light' : 'dark');
        }
        
        // Load saved theme on startup
        (function() {
            const savedTheme = localStorage.getItem('docEditorTheme');
            if (savedTheme === 'light') {
                document.body.classList.add('light-mode');
            }
        })();

        // Initialize timeline view
        setView('timeline');
    
        // Global keyboard shortcuts now handled via config in MASTER KEYDOWN HANDLER
    

        // CONTENT EDITING HANDLER
        // Editing-specific keys only (Tab, Enter, Space markdown triggers).
        // DO NOT add global shortcuts here.
        docContent.addEventListener('keydown', async (e) => {
            const selection = window.getSelection();
            if (!selection.rangeCount) return;
            const range = selection.getRangeAt(0);
            let node = range.startContainer;
            
            // Get current block element using helper
            const block = getEditableBlock(node);
            
            // Priority 1: SlashMenu visible -> delegate to SlashMenu
            if (SlashMenu.visible) {
                if (SlashMenu.handleKey(e)) return;
            }
            
            // Priority 2: Mention dropdown visible -> handle navigation
            const dropdown = document.getElementById('mentionDropdown');
            if (dropdown && dropdown.classList.contains('visible')) {
                const items = dropdown.querySelectorAll('.mention-item');
                
                if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    selectedMentionIndex = Math.min(selectedMentionIndex + 1, items.length - 1);
                    renderMentionDropdown(filterDocsForMention(mentionSearchTerm));
                    return;
                }
                if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    selectedMentionIndex = Math.max(selectedMentionIndex - 1, 0);
                    renderMentionDropdown(filterDocsForMention(mentionSearchTerm));
                    return;
                }
                if (e.key === 'Enter' || e.key === 'Tab') {
                    e.preventDefault();
                    const selected = items[selectedMentionIndex];
                    if (selected) {
                        const docId = selected.getAttribute('data-id');
                        const title = selected.getAttribute('data-title');

                        if (docId === '__create__') {
                            const newDoc = await createDocFromMention(title);
                            if (newDoc) {
                                await insertDocLink(newDoc.id, newDoc.title);
                            }
                        } else if (e.shiftKey) {
                            await insertDocEmbed(docId, title);
                        } else {
                            await insertDocLink(docId, title);
                        }
                    }
                    return;
                }
                if (e.key === 'Escape') {
                    hideMentionDropdown();
                    return;
                }
            }
            
            // Priority 3: Tab in li -> indent/outdent
            if (e.key === 'Tab') {
                const li = node.closest ? node.closest('li') : null;
                if (li) {
                    e.preventDefault();
                    if (e.shiftKey) {
                        // Outdent
                        const parentUl = li.parentNode;
                        const grandparentLi = parentUl.parentNode.closest('li');
                        if (grandparentLi) {
                            grandparentLi.parentNode.insertBefore(li, grandparentLi.nextSibling);
                            if (parentUl.children.length === 0) parentUl.remove();
                        }
                    } else {
                        // Indent
                        const prevLi = li.previousElementSibling;
                        if (prevLi) {
                            let nestedUl = prevLi.querySelector('ul');
                            if (!nestedUl) {
                                nestedUl = document.createElement('ul');
                                prevLi.appendChild(nestedUl);
                            }
                            nestedUl.appendChild(li);
                        }
                    }
                    placeCaretIn(li);
                    scheduleAutoSave();
                    return;
                }
            }
            
            // Priority 4: Shift+Enter in li -> exit list
            if (e.key === 'Enter' && e.shiftKey) {
                const li = node.closest ? node.closest('li') : (node.parentNode && node.parentNode.closest ? node.parentNode.closest('li') : null);
                if (li) {
                    e.preventDefault();
                    const ul = li.closest('ul') || li.closest('ol');
                    const p = document.createElement('p');
                    p.innerHTML = '<br>';
                    ul.parentNode.insertBefore(p, ul.nextSibling);
                    placeCaretIn(p);
                    scheduleAutoSave();
                    return;
                }
                
                // Priority 4b: Shift+Enter in pre/code -> exit code block
                const codeNode = node.nodeType === 3 ? node.parentElement : node;
                const codeEl = codeNode ? codeNode.closest('pre, code') : null;
                if (codeEl) {
                    e.preventDefault();
                    const pre = codeEl.tagName === 'PRE' ? codeEl : codeEl.closest('pre');
                    if (pre) {
                        const p = document.createElement('p');
                        p.innerHTML = '<br>';
                        pre.parentNode.insertBefore(p, pre.nextSibling);
                        placeCaretIn(p);
                        scheduleAutoSave();
                    }
                    return;
                }
            }
            
            // Priority 5: Enter on empty li -> exit list
            if (e.key === 'Enter' && !e.shiftKey) {
                const li = node.closest ? node.closest('li') : (node.parentNode && node.parentNode.closest ? node.parentNode.closest('li') : null);
                if (li && li.textContent.trim() === '') {
                    e.preventDefault();
                    const ul = li.parentNode;
                    const p = document.createElement('p');
                    p.innerHTML = '<br>';
                    ul.parentNode.insertBefore(p, ul.nextSibling);
                    li.remove();
                    if (ul.children.length === 0) ul.remove();
                    placeCaretIn(p);
                    scheduleAutoSave();
                    return;
                }
                
                // Priority 5b: Enter in pre/code -> insert newline, or exit on empty last line
                const codeNode2 = node.nodeType === 3 ? node.parentElement : node;
                const codeEl = codeNode2 ? codeNode2.closest('pre, code') : null;
                if (codeEl) {
                    e.preventDefault();
                    const pre = codeEl.tagName === 'PRE' ? codeEl : codeEl.closest('pre');
                    const code = pre ? pre.querySelector('code') : codeEl;
                    const codeText = code ? code.textContent : '';
                    // If the last line is empty (user pressed Enter on a blank line), exit the code block
                    if (codeText.endsWith('\n\n') || (codeText.endsWith('\n') && codeText.length > 1)) {
                        // Trim the trailing newline from the code block
                        if (code && codeText.endsWith('\n')) {
                            code.textContent = codeText.slice(0, -1);
                        }
                        // Find or create a <p> after the pre
                        let nextP = pre ? pre.nextElementSibling : null;
                        if (!nextP || nextP.tagName !== 'P') {
                            nextP = document.createElement('p');
                            nextP.innerHTML = '<br>';
                            if (pre) pre.parentNode.insertBefore(nextP, pre.nextSibling);
                        }
                        placeCaretIn(nextP, 'start');
                        scheduleAutoSave();
                    } else {
                        document.execCommand('insertText', false, '\n');
                    }
                    return;
                }
            }
            
            // Priority 6: Space -> markdown trigger patterns
            if (e.key === ' ') {
                // If block is null, try one more approach before bailing
                let blockForMd = block;
                if (!blockForMd) {
                    const sel = window.getSelection();
                    if (sel.rangeCount) {
                        let el = sel.getRangeAt(0).startContainer;
                        el = el.nodeType === 3 ? el.parentElement : el;
                        while (el && el.parentElement !== docContent) el = el.parentElement;
                        if (el && el.parentElement === docContent) blockForMd = el;
                    }
                }
                if (!blockForMd) return;
                const text = (blockForMd.textContent || '').trimEnd();
                
                // Collection shortcut first
                const collectionShortcutMatch = text.match(/^#([a-zA-Z][a-zA-Z0-9-]*)$/);
                if (collectionShortcutMatch && !text.startsWith('##')) {
                    e.preventDefault();
                    let collectionName = collectionShortcutMatch[1].toLowerCase().replace(/-+/g, ' ');
                    collectionName = collectionName.split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
                    setCollection(collectionName);
                    blockForMd.innerHTML = '';
                    if (blockForMd.nodeType === 3) {
                        blockForMd.textContent = '';
                    }
                    scheduleAutoSave();
                    return;
                }
                
                // Markdown patterns
                const patterns = [
                    { match: /^#{4}\s*(.*)$/, tag: 'h4' },
                    { match: /^#{3}\s*(.*)$/, tag: 'h3' },
                    { match: /^#{2}\s*(.*)$/, tag: 'h2' },
                    { match: /^#\s*(.*)$/, tag: 'h1' },
                    { match: /^-(.*)$/, tag: 'ul' },
                    { match: /^\*(.*)$/, tag: 'ul' },
                    { match: /^1\.(.*)$/, tag: 'ol' },
                    { match: /^>(.*)$/, tag: 'blockquote' },
                    { match: /^---$/, tag: 'hr' },
                    { match: /^```$/, tag: 'pre' },
                ];
                
                for (const {match, tag} of patterns) {
                    const matchResult = text.match(match);
                    if (matchResult) {
                        e.preventDefault();
                        const remainingText = matchResult[1] ? matchResult[1].trim() : '';
                        
                        if (tag === 'ul' || tag === 'ol') {
                            const list = document.createElement(tag);
                            const li = document.createElement('li');
                            li.innerHTML = remainingText || '<br>';
                            list.appendChild(li);
                            blockForMd.nodeType === 3 ? blockForMd.replaceWith(list) : blockForMd.replaceWith(list);
                            placeCaretIn(li, remainingText ? 'end' : 'start');
                        } else if (tag === 'hr') {
                            const hr = document.createElement('hr');
                            const p = document.createElement('p');
                            p.innerHTML = '<br>';
                            blockForMd.nodeType === 3 ? blockForMd.replaceWith(hr) : blockForMd.replaceWith(hr);
                            hr.parentNode.insertBefore(p, hr.nextSibling);
                            placeCaretIn(p);
                        } else if (tag === 'pre') {
                            const pre = document.createElement('pre');
                            const code = document.createElement('code');
                            code.innerHTML = '<br>';
                            pre.appendChild(code);
                            blockForMd.nodeType === 3 ? blockForMd.replaceWith(pre) : blockForMd.replaceWith(pre);
                            placeCaretIn(code);
                        } else {
                            const el = document.createElement(tag);
                            let contentToKeep = remainingText;
                            if (!contentToKeep && blockForMd.innerHTML) {
                                const htmlContent = blockForMd.innerHTML;
                                const markerMatch = htmlContent.match(/^(?:#{1,4}|>)\s*/);
                                if (markerMatch) {
                                    contentToKeep = htmlContent.substring(markerMatch[0].length).trim();
                                }
                            }
                            el.innerHTML = contentToKeep || '<br>';
                            blockForMd.nodeType === 3 ? blockForMd.replaceWith(el) : blockForMd.replaceWith(el);
                            placeCaretIn(el, contentToKeep ? 'end' : 'start');
                        }
                        scheduleAutoSave();
                        return;
                    }
                }
            }
        });

// === CONSOLIDATED INPUT HANDLER ===
// All docContent input handling in ONE listener. DO NOT add another docContent.addEventListener('input', ...) anywhere.
// Handler responsibilities:
// 1. Writing Tools cleanup (capture phase logic for insertReplacementText/historyUndo)
// 2. @mention detection
// 3. Inline markdown conversion (bold, italic, inline code)
// 4. SlashMenu filter updates
// 5. Hashtag collection detection
// 6. Auto-save trigger
// 7. Focus mode entry
docContent.addEventListener('input', async function(e) {
    // Priority 1: Writing Tools cleanup (formerly capture-phase listener)
    if (e.inputType === 'insertReplacementText' || e.inputType === 'historyUndo') {
        docContent.querySelectorAll('[style*="color"], [style*="font-size"], [style*="font-family"], font[color], font[face], font[size]').forEach(el => {
            if (el.tagName === 'FONT') {
                const span = document.createElement('span');
                span.innerHTML = el.innerHTML;
                el.replaceWith(span);
            } else {
                el.style.color = '';
                el.style.fontSize = '';
                el.style.fontFamily = '';
                if (!el.getAttribute('style') || !el.getAttribute('style').trim()) el.removeAttribute('style');
            }
        });
        docContent.querySelectorAll('div:not([id]):not([class])').forEach(div => {
            const p = document.createElement('p');
            p.innerHTML = div.innerHTML;
            div.replaceWith(p);
        });
        docContent.querySelectorAll('br + br, p + br, br:first-child, br:last-child').forEach(br => {
            if (br.parentElement === docContent) br.remove();
        });
    }
    
    // Priority 2: SlashMenu filter update (if visible)
    if (SlashMenu.visible && e.inputType === 'insertText' && e.data) {
        SlashMenu.filterText += e.data;
        SlashMenu.selectedIndex = 0;
        renderSlashMenu(SlashMenu.filterText);
        const sel = window.getSelection();
        if (sel.rangeCount > 0) {
            SlashMenu.savedRange = sel.getRangeAt(0).cloneRange();
        }
    }
    
    // Priority 3: @mention detection
    const selection = window.getSelection();
    if (selection.rangeCount) {
        const range = selection.getRangeAt(0);
        const node = range.startContainer;
        
        if (node.nodeType === Node.TEXT_NODE) {
            const text = node.textContent;
            const cursorPos = range.startOffset;
            const beforeCursor = text.substring(0, cursorPos);
            const atIndex = beforeCursor.lastIndexOf('@');
            
            if (atIndex !== -1 && (atIndex === 0 || beforeCursor[atIndex - 1] === ' ' || beforeCursor[atIndex - 1] === '\n')) {
                mentionSearchTerm = beforeCursor.substring(atIndex + 1);
                mentionStartPos = atIndex;
                
                const tempRange = document.createRange();
                tempRange.setStart(node, atIndex);
                tempRange.setEnd(node, atIndex);
                const rect = tempRange.getBoundingClientRect();
                
                if (allDocsCache.length === 0) {
                    await fetchAllDocs();
                }
                
                const filtered = filterDocsForMention(mentionSearchTerm);
                selectedMentionIndex = 0;
                renderMentionDropdown(filtered);
                showMentionDropdown(rect.left, rect.bottom + 5);
            } else {
                hideMentionDropdown();
            }
        }
    }
    
    // Priority 4: Hashtag collection detection
    detectHashtagCollection();
    
    // Priority 5: Inline markdown conversion
    if (selection.rangeCount) {
        const node = selection.anchorNode;
        if (node && node.nodeType === 3) {
            const text = node.textContent;
            
            // Inline code: `code`
            const codeMatch = text.match(/`([^`]+)`/);
            if (codeMatch) {
                const before = text.substring(0, codeMatch.index);
                const code = document.createElement('code');
                code.textContent = codeMatch[1];
                const after = text.substring(codeMatch.index + codeMatch[0].length);
                
                const parent = node.parentNode;
                const frag = document.createDocumentFragment();
                if (before) frag.appendChild(document.createTextNode(before));
                frag.appendChild(code);
                if (after) frag.appendChild(document.createTextNode(after));
                parent.replaceChild(frag, node);
                
                const range = document.createRange();
                range.setStartAfter(code);
                range.collapse(true);
                selection.removeAllRanges();
                selection.addRange(range);
                scheduleAutoSave();
                enterFocusMode();
                return;
            }
            
            // Bold: **text**
            const boldMatch = text.match(/\*\*([^*]+)\*\*/);
            if (boldMatch) {
                const before = text.substring(0, boldMatch.index);
                const strong = document.createElement('strong');
                strong.textContent = boldMatch[1];
                const after = text.substring(boldMatch.index + boldMatch[0].length);
                
                const parent = node.parentNode;
                const frag = document.createDocumentFragment();
                if (before) frag.appendChild(document.createTextNode(before));
                frag.appendChild(strong);
                if (after) frag.appendChild(document.createTextNode(after));
                parent.replaceChild(frag, node);
                
                const range = document.createRange();
                range.setStartAfter(strong);
                range.collapse(true);
                selection.removeAllRanges();
                selection.addRange(range);
                scheduleAutoSave();
                enterFocusMode();
                return;
            }
            
            // Italic: *text* (but not **)
            const italicMatch = text.match(/(?<!\*)\*([^*]+)\*(?!\*)/);
            if (italicMatch) {
                const before = text.substring(0, italicMatch.index);
                const em = document.createElement('em');
                em.textContent = italicMatch[1];
                const after = text.substring(italicMatch.index + italicMatch[0].length);
                
                const parent = node.parentNode;
                const frag = document.createDocumentFragment();
                if (before) frag.appendChild(document.createTextNode(before));
                frag.appendChild(em);
                if (after) frag.appendChild(document.createTextNode(after));
                parent.replaceChild(frag, node);
                
                const range = document.createRange();
                range.setStartAfter(em);
                range.collapse(true);
                selection.removeAllRanges();
                selection.addRange(range);
                scheduleAutoSave();
                enterFocusMode();
                return;
            }
        }
    }
    
    // Priority 6: Auto-save trigger and focus mode (always runs)
    scheduleAutoSave();
    enterFocusMode();
});


        // Detect slash at beginning of line
        docContent.addEventListener('keyup', function(e) {
            if (e.key === '/' && !SlashMenu.visible) {
                const sel = window.getSelection();
                if (sel.rangeCount === 0) return;
                
                const range = sel.getRangeAt(0);
                const node = range.startContainer;
                const offset = range.startOffset;
                
                // Check if slash is at beginning of line or after newline
                if (node.nodeType === Node.TEXT_NODE) {
                    const textBefore = node.textContent.substring(0, offset);
                    const lastNewline = textBefore.lastIndexOf('\n');
                    const lineStart = lastNewline === -1 ? 0 : lastNewline + 1;
                    const textOnLine = textBefore.substring(lineStart);
                    
                    // Only show menu if / is at start of line (possibly with whitespace)
                    if (textOnLine.trim() === '/') {
                        SlashMenu.savedRange = range.cloneRange();
                        SlashMenu.filterText = '';
                        
                        // Get cursor position
                        const rect = range.getBoundingClientRect();
                        showSlashMenu(rect.left, rect.bottom + 5);
                    }
                }
            }
        });

        // Close slash menu on outside click
        document.addEventListener('click', (e) => {
            if (SlashMenu.visible && !e.target.closest('.slash-menu') && !e.target.closest('.doc-content')) {
                hideSlashMenu();
            }
        });



        // Image embed functions
        let savedImageSelection = null;

        function showImageModal() {
            // Save current selection
            const selection = window.getSelection();
            if (selection.rangeCount > 0) {
                savedImageSelection = selection.getRangeAt(0).cloneRange();
            }
            document.getElementById('imageModal').style.display = 'flex';
            document.getElementById('imageUrl').focus();
        }

        function hideImageModal() {
            document.getElementById('imageModal').style.display = 'none';
            document.getElementById('imageUrl').value = '';
            document.getElementById('imageAlt').value = '';
            savedImageSelection = null;
        }

        function insertImage() {
            const urlInput = document.getElementById('imageUrl').value.trim();
            const alt = document.getElementById('imageAlt').value.trim();
            
            if (!urlInput) {
                hideImageModal();
                return;
            }
            
            // Auto-expand filename to full URL
            let url = urlInput;
            if (!urlInput.startsWith('http://') && !urlInput.startsWith('https://') && !urlInput.startsWith('data:')) {
                url = 'https://app.orchestrateos.io/semantic_memory/public_images/' + urlInput;
            }
            
            const img = document.createElement('img');
            img.src = url;
            img.alt = alt;
            img.style.maxWidth = '100%';
            img.style.height = 'auto';
            
            const editor = document.getElementById('editor');
            const selection = window.getSelection();
            
            // Insert at saved selection or cursor position
            if (savedImageSelection) {
                selection.removeAllRanges();
                selection.addRange(savedImageSelection);
            }
            
            if (selection.rangeCount > 0) {
                const range = selection.getRangeAt(0);
                range.deleteContents();
                range.insertNode(img);
                
                // Move cursor after image
                range.setStartAfter(img);
                range.setEndAfter(img);
                selection.removeAllRanges();
                selection.addRange(range);
            } else {
                editor.appendChild(img);
            }

            hideImageModal();
            markDirty();
        }

        // Queue Task Modal functions
        function showQueueTaskModal(docId, docTitle) {
            document.getElementById('queueTaskDocId').value = docId;
            document.getElementById('queueTaskDocTitle').textContent = docTitle;
            document.getElementById('queueTaskDescription').value = '';
            document.getElementById('queueTaskModal').style.display = 'flex';
            document.getElementById('queueTaskDescription').focus();
        }

        function hideQueueTaskModal() {
            document.getElementById('queueTaskModal').style.display = 'none';
            document.getElementById('queueTaskDescription').value = '';
            document.getElementById('queueTaskDocId').value = '';
        }

        async function submitQueueTask() {
            const docId = document.getElementById('queueTaskDocId').value;
            const description = document.getElementById('queueTaskDescription').value.trim();
            
            if (!description) {
                alert('Please enter a task description');
                return;
            }

            // Close modal immediately - don't wait for server
            hideQueueTaskModal();
            const toast = document.createElement('div');
            toast.style.cssText = 'position:fixed;bottom:20px;right:20px;background:#22c55e;color:white;padding:12px 20px;border-radius:8px;z-index:10001;font-weight:500;';
            toast.textContent = 'Task queued successfully';
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), 3000);

            try {
                const docTitle = document.getElementById('queueTaskDocTitle').textContent;
                fetch("/execute_task", {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        tool_name: 'claude_assistant',
                        action: 'assign_task',
                        params: {
                            description: `[doc_id: ${docId}] ${description}`
                        }
                    })
                }).then(r => r.json()).then(result => {
                    if (result.status !== 'success') {
                        console.error('Queue task failed:', result.message);
                    }
                }).catch(e => console.error('Queue task error:', e));
            } catch (e) {
                console.error('Queue task error:', e);
            }
        }

        async function submitStageTask() {
            const docId = document.getElementById('queueTaskDocId').value;
            const description = document.getElementById('queueTaskDescription').value.trim();
            
            if (!description) {
                alert('Please enter a task description');
                return;
            }

            // Close modal immediately - don't wait for server
            hideQueueTaskModal();
            const toast = document.createElement('div');
            toast.style.cssText = 'position:fixed;bottom:20px;right:20px;background:#059669;color:white;padding:12px 20px;border-radius:8px;z-index:10001;font-weight:500;';
            toast.textContent = 'Task staged successfully';
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), 3000);

            try {
                const docTitle = document.getElementById('queueTaskDocTitle').textContent;
                fetch("/execute_task", {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        tool_name: 'claude_assistant',
                        action: 'stage_task',
                        params: {
                            description: `[doc_id: ${docId}] ${description}`
                        }
                    })
                }).then(r => r.json()).then(result => {
                    if (result.status !== 'success') {
                        console.error('Stage task failed:', result.message);
                    }
                }).catch(e => console.error('Stage task error:', e));
            } catch (e) {
                console.error('Stage task error:', e);
            }
        }


    

        function copyDocId() {
            if (!currentDocId) {
                const toast = document.createElement('div');
                toast.style.cssText = 'position:fixed;bottom:20px;right:20px;background:#EF4444;color:white;padding:12px 20px;border-radius:8px;z-index:10001;font-weight:500;';
                toast.textContent = 'No document selected';
                document.body.appendChild(toast);
                setTimeout(() => toast.remove(), 3000);
                return;
            }
            
            navigator.clipboard.writeText(currentDocId).then(() => {
                const toast = document.createElement('div');
                toast.style.cssText = 'position:fixed;bottom:20px;right:20px;background:#8B5CF6;color:white;padding:12px 20px;border-radius:8px;z-index:10001;font-weight:500;';
                toast.textContent = 'Doc ID copied: ' + currentDocId;
                document.body.appendChild(toast);
                setTimeout(() => toast.remove(), 3000);
            }).catch(err => {
                console.error('Failed to copy:', err);
            });
        }

        // Mockup Batch Modal Functions
        function openMockupBatchModal() {
            // Close the queue task modal if it's open
            hideQueueTaskModal();
            document.getElementById('mockupBatchModal').style.display = 'flex';
            document.getElementById('mockupBatchDesc').focus();
        }

        function closeMockupBatchModal(e) {
            if (e && e.target !== e.currentTarget) return;
            document.getElementById('mockupBatchModal').style.display = 'none';
            document.getElementById('mockupBatchDesc').value = '';
            document.getElementById('mockupBatchVariations').value = '4';
            document.getElementById('mockupBatchBaseName').value = '';
        }

        async function stageMockupBatch() {
            const description = document.getElementById('mockupBatchDesc').value.trim();
            const variations = parseInt(document.getElementById('mockupBatchVariations').value) || 4;
            const baseName = document.getElementById('mockupBatchBaseName').value.trim();

            if (!description) {
                alert('Please enter a mockup description');
                return;
            }

            const params = { description, variations };
            if (baseName) params.base_name = baseName;

            try {
                const response = await fetch("/execute_task", {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        tool_name: 'claude_assistant',
                        action: 'stage_mockup_batch',
                        params: params
                    })
                });

                const result = await response.json();
                if (result.status === 'success') {
                    closeMockupBatchModal();
                    const toast = document.createElement('div');
                    toast.style.cssText = 'position:fixed;bottom:20px;right:20px;background:#7C3AED;color:white;padding:12px 20px;border-radius:8px;z-index:10001;font-weight:500;';
                    toast.textContent = 'Staged ' + (result.staged_count || variations) + ' mockup variations';
                    document.body.appendChild(toast);
                    setTimeout(() => toast.remove(), 3000);
                } else {
                    alert('Failed to stage mockup batch: ' + (result.message || 'Unknown error'));
                }
            } catch (e) {
                console.error('Mockup batch stage error:', e);
                alert('Failed to stage mockup batch: ' + e.message);
            }
        }