
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


        const dropZone = document.getElementById('dropZone');
        const fileInput = document.getElementById('fileInput');
        const selectedFile = document.getElementById('selectedFile');
        const fileIcon = document.getElementById('fileIcon');
        const fileName = document.getElementById('fileName');
        const fileSize = document.getElementById('fileSize');
        const fileRemove = document.getElementById('fileRemove');
        const convertBtn = document.getElementById('convertBtn');
        const progressContainer = document.getElementById('progressContainer');
        const progressBar = document.getElementById('progressBar');
        const progressStatus = document.getElementById('progressStatus');
        const progressPercent = document.getElementById('progressPercent');
        const resultsList = document.getElementById('resultsList');
        const youtubeUrl = document.getElementById('youtubeUrl');
        const youtubeBtn = document.getElementById('youtubeBtn');
        const imageOperation = document.getElementById('imageOperation');
        const resizeGroup = document.getElementById('resizeGroup');

        let currentFile = null;
        let currentTab = 'video';
        let results = [];

        // File type detection
        function getFileType(file) {
            const ext = file.name.split('.').pop().toLowerCase();
            const videoExts = ['mp4', 'mov', 'avi', 'mkv', 'webm', 'flv', 'wmv'];
            const imageExts = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'tiff'];
            const audioExts = ['mp3', 'wav', 'flac', 'aac', 'ogg', 'm4a'];
            const docExts = ['pdf', 'docx', 'txt', 'md', 'csv', 'json'];

            if (videoExts.includes(ext)) return 'video';
            if (imageExts.includes(ext)) return 'image';
            if (audioExts.includes(ext)) return 'audio';
            if (docExts.includes(ext)) return 'document';
            return 'unknown';
        }

        function getFileIcon(type) {
            const icons = { video: '🎬', image: '🖼️', audio: '🎵', document: '📄', unknown: '📁' };
            return icons[type] || '📁';
        }

        function formatSize(bytes) {
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
            return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
        }

        // Drop zone events
        dropZone.addEventListener('click', () => fileInput.click());

        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });

        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('dragover');
        });

        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            const files = e.dataTransfer.files;
            if (files.length > 0) handleFile(files[0]);
        });

        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) handleFile(e.target.files[0]);
        });

        function handleFile(file) {
            currentFile = file;
            const type = getFileType(file);

            fileIcon.textContent = getFileIcon(type);
            fileName.textContent = file.name;
            fileSize.textContent = formatSize(file.size);
            selectedFile.classList.add('visible');
            convertBtn.disabled = false;

            // Auto-select appropriate tab
            if (type === 'video' || type === 'audio') selectTab('video');
            else if (type === 'image') selectTab('image');
            else if (type === 'document') selectTab('document');
        }

        fileRemove.addEventListener('click', () => {
            currentFile = null;
            selectedFile.classList.remove('visible');
            convertBtn.disabled = true;
            fileInput.value = '';
        });

        // Tab switching
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', () => selectTab(btn.dataset.tab));
        });

        function selectTab(tab) {
            currentTab = tab;
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelector(`[data-tab="${tab}"]`).classList.add('active');
            document.querySelectorAll('.options-panel').forEach(p => p.classList.remove('active'));
            document.getElementById(`${tab}Options`).classList.add('active');
        }

        // Image operation toggle
        imageOperation.addEventListener('change', () => {
            resizeGroup.style.display = imageOperation.value === 'resize' ? 'block' : 'none';
        });

        // Convert button
        convertBtn.addEventListener('click', async () => {
            if (!currentFile) return;

            convertBtn.disabled = true;
            progressContainer.classList.add('visible');
            progressBar.style.width = '0%';
            progressStatus.textContent = 'Uploading...';
            progressPercent.textContent = '0%';

            // Simulate progress (actual conversion is server-side)
            let progress = 0;
            const progressInterval = setInterval(() => {
                progress += Math.random() * 15;
                if (progress > 90) progress = 90;
                progressBar.style.width = progress + '%';
                progressPercent.textContent = Math.round(progress) + '%';
                if (progress > 30) progressStatus.textContent = 'Processing...';
                if (progress > 60) progressStatus.textContent = 'Converting...';
            }, 500);

            try {
                const action = getConversionAction();
                const params = getConversionParams();

                const response = await fetch('/execute_task', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        tool_name: 'media_manager',
                        action: action,
                        params: params
                    })
                });

                const result = await response.json();

                clearInterval(progressInterval);
                progressBar.style.width = '100%';
                progressPercent.textContent = '100%';
                progressStatus.textContent = 'Complete!';

                addResult(action, result.status === 'success', result.message || 'Conversion complete');
                showToast(result.status === 'success', result.message || 'Conversion complete');

            } catch (err) {
                clearInterval(progressInterval);
                progressStatus.textContent = 'Error';
                addResult('convert', false, err.message);
                showToast(false, 'Conversion failed: ' + err.message);
            }

            setTimeout(() => {
                progressContainer.classList.remove('visible');
                convertBtn.disabled = false;
            }, 2000);
        });

        function getConversionAction() {
            if (currentTab === 'video') return 'convert_media';
            if (currentTab === 'image') {
                const op = imageOperation.value;
                if (op === 'resize') return 'resize_image';
                if (op === 'compress') return 'compress_image';
                if (op === 'rembg') return 'remove_background';
            }
            if (currentTab === 'document') return 'convert_file';
            return 'convert_media';
        }

        function getConversionParams() {
            const params = { filename: currentFile.name };

            if (currentTab === 'video') {
                params.format = document.getElementById('videoFormat').value;
            } else if (currentTab === 'image') {
                if (imageOperation.value === 'resize') {
                    params.width = document.getElementById('imageWidth').value;
                    params.height = document.getElementById('imageHeight').value;
                }
            } else if (currentTab === 'document') {
                const ext = currentFile.name.split('.').pop().toLowerCase();
                params.from_format = ext;
                params.to_format = document.getElementById('documentFormat').value;
            }

            return params;
        }

        // YouTube download
        youtubeBtn.addEventListener('click', async () => {
            const url = youtubeUrl.value.trim();
            if (!url) return;

            youtubeBtn.disabled = true;
            youtubeBtn.innerHTML = '<span class="spinner"></span>';

            try {
                const response = await fetch('/execute_task', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        tool_name: 'media_manager',
                        action: 'download_youtube',
                        params: { url: url }
                    })
                });

                const result = await response.json();
                addResult('download_youtube', result.status === 'success', result.message);
                showToast(result.status === 'success', result.message);

            } catch (err) {
                addResult('download_youtube', false, err.message);
                showToast(false, 'Download failed');
            }

            youtubeBtn.disabled = false;
            youtubeBtn.textContent = 'Download';
            youtubeUrl.value = '';
        });

        // Results
        function addResult(action, success, message) {
            const actionNames = {
                'convert_media': 'Video Convert',
                'resize_image': 'Image Resize',
                'compress_image': 'Image Compress',
                'remove_background': 'Background Remove',
                'convert_file': 'Document Convert',
                'download_youtube': 'YouTube Download'
            };

            const result = {
                action: actionNames[action] || action,
                success: success,
                message: message,
                time: new Date().toLocaleTimeString()
            };

            results.unshift(result);
            if (results.length > 10) results.pop();

            renderResults();
        }

        function renderResults() {
            if (results.length === 0) {
                resultsList.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-state-icon">📋</div>
                        <div>No recent conversions</div>
                    </div>
                `;
                return;
            }

            resultsList.innerHTML = results.map(r => `
                <div class="result-item">
                    <div class="result-icon ${r.success ? 'success' : 'error'}">
                        ${r.success ? '✓' : '✕'}
                    </div>
                    <div class="result-details">
                        <div class="result-action">${r.action}</div>
                        <div class="result-message">${r.message}</div>
                    </div>
                    <div class="result-time">${r.time}</div>
                </div>
            `).join('');
        }

        // Toast
        function showToast(success, message) {
            const toast = document.getElementById('toast');
            const toastIcon = document.getElementById('toastIcon');
            const toastMessage = document.getElementById('toastMessage');

            toast.className = 'toast visible ' + (success ? 'success' : 'error');
            toastIcon.textContent = success ? '✓' : '✕';
            toastMessage.textContent = message;

            setTimeout(() => {
                toast.classList.remove('visible');
            }, 4000);
        }
    

