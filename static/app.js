// ComicPacker Web Interface - Client-side JavaScript

// Configuration
const DEFAULT_PATH_KEY = 'comicpacker_default_path';

// State management
let currentPath = '.';
let selectedFolder = null;
let currentJobId = null;
let eventSource = null;

// DOM elements
const fileList = document.getElementById('file-list');
const currentPathInput = document.getElementById('current-path');
const selectedFolderDisplay = document.getElementById('selected-folder-display');
const conversionForm = document.getElementById('conversion-form');
const progressPanel = document.getElementById('progress-panel');
const progressBar = document.getElementById('progress-bar');
const progressText = document.getElementById('progress-text');
const progressStage = document.getElementById('progress-stage');
const progressMessage = document.getElementById('progress-message');
const progressLogs = document.getElementById('progress-logs');
const jobList = document.getElementById('job-list');
const startBtn = document.getElementById('start-btn');

// Settings elements
const setDefaultBtn = document.getElementById('set-default-btn');

// Mode-specific controls
const batchSizeGroup = document.getElementById('batch-size-group');
const batchSizeSlider = document.getElementById('batch-size');
const batchSizeValue = document.getElementById('batch-size-value');
const modeSelect = document.getElementById('mode');
const convertToMobiCheckbox = document.getElementById('convert-to-mobi');
const kindleProfileGroup = document.getElementById('kindle-profile-group');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    const startPath = getDefaultPath() || '.';
    loadDirectory(startPath);
    loadJobs();
    setupEventListeners();
});

// Settings management
function getDefaultPath() {
    return localStorage.getItem(DEFAULT_PATH_KEY);
}

function setCurrentAsDefault() {
    if (currentPath) {
        localStorage.setItem(DEFAULT_PATH_KEY, currentPath);
        showNotification(`✓ 已设置默认路径: ${currentPath}`, 'success');
    } else {
        showNotification('⚠ 当前路径无效', 'warning');
    }
}

function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    document.body.appendChild(notification);

    // Animate in
    setTimeout(() => notification.classList.add('show'), 10);

    // Remove after 3 seconds
    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// Event listeners
function setupEventListeners() {
    // Settings controls
    setDefaultBtn.addEventListener('click', setCurrentAsDefault);

    // File browser controls
    document.getElementById('parent-btn').addEventListener('click', () => {
        const parent = currentPathInput.dataset.parent;
        if (parent) {
            loadDirectory(parent);
        }
    });

    document.getElementById('refresh-btn').addEventListener('click', () => {
        loadDirectory(currentPath);
    });

    // Batch size slider
    batchSizeSlider.addEventListener('input', (e) => {
        batchSizeValue.textContent = e.target.value;
    });

    // Mode selection
    modeSelect.addEventListener('change', (e) => {
        if (e.target.value === 'batch') {
            batchSizeGroup.style.display = 'block';
        } else {
            batchSizeGroup.style.display = 'none';
        }
    });

    // MOBI conversion checkbox
    convertToMobiCheckbox.addEventListener('change', (e) => {
        if (e.target.checked) {
            kindleProfileGroup.style.display = 'block';
        } else {
            kindleProfileGroup.style.display = 'none';
        }
    });

    // Prefix input - auto update output folder
    const prefixInput = document.getElementById('prefix');
    const outputInput = document.getElementById('output');

    prefixInput.addEventListener('input', (e) => {
        const prefix = e.target.value.trim();
        if (prefix) {
            outputInput.value = `./output/${prefix}`;
        } else {
            outputInput.value = './output';
        }
    });

    // Form submission
    conversionForm.addEventListener('submit', (e) => {
        e.preventDefault();
        startConversion();
    });
}

// Load directory contents
async function loadDirectory(path) {
    fileList.innerHTML = '<div class="loading">加载中...</div>';

    try {
        const response = await fetch('/api/browse', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ path })
        });

        if (!response.ok) {
            throw new Error('Failed to load directory');
        }

        const data = await response.json();
        currentPath = data.path;
        currentPathInput.value = data.path;
        currentPathInput.dataset.parent = data.parent;

        renderFileList(data.items);
    } catch (error) {
        console.error('Error loading directory:', error);
        fileList.innerHTML = '<div class="loading">加载失败</div>';
    }
}

// Render file list
function renderFileList(items) {
    if (items.length === 0) {
        fileList.innerHTML = '<div class="empty-state">目录为空</div>';
        return;
    }

    fileList.innerHTML = '';

    items.forEach(item => {
        const fileItem = document.createElement('div');
        fileItem.className = 'file-item';

        const icon = item.is_dir ? '📁' : '📄';
        const fileCount = item.is_dir && item.file_count > 0
            ? `<div class="file-count">${item.file_count} 个文件</div>`
            : '';

        fileItem.innerHTML = `
            <div class="file-icon">${icon}</div>
            <div class="file-info">
                <div class="file-name">${item.name}</div>
                ${fileCount}
            </div>
        `;

        fileItem.addEventListener('click', () => {
            if (item.is_dir) {
                // Double-click to navigate, single-click to select
                if (fileItem.classList.contains('selected')) {
                    loadDirectory(item.path);
                } else {
                    // Clear previous selection
                    document.querySelectorAll('.file-item').forEach(el => {
                        el.classList.remove('selected');
                    });
                    fileItem.classList.add('selected');
                    selectedFolder = item.path;
                    selectedFolderDisplay.textContent = item.path;
                }
            }
        });

        fileList.appendChild(fileItem);
    });
}

// Start conversion
async function startConversion() {
    if (!selectedFolder) {
        alert('请先选择一个文件夹');
        return;
    }

    // Gather form data
    const formData = new FormData(conversionForm);
    const prefix = formData.get('prefix') || '';

    // 任务2: 如果设置了前缀，则输出文件夹使用前缀名称
    let outputFolder = formData.get('output') || './output';
    if (prefix) {
        outputFolder = `./output/${prefix}`;
    }

    const params = {
        folder: selectedFolder,
        mode: formData.get('mode'),
        prefix: prefix,
        output: outputFolder,
        convert_to_mobi: convertToMobiCheckbox.checked,  // 直接读取checkbox的checked属性
        kindle_profile: formData.get('kindle_profile') || 'KPW5'
    };

    // Add batch_size only for batch mode
    if (params.mode === 'batch') {
        params.batch_size = parseInt(formData.get('batch_size'));
    }

    console.log('发送转换请求:', params);  // 调试日志

    // Disable start button
    startBtn.disabled = true;
    startBtn.textContent = '⏳ 处理中...';

    try {
        const response = await fetch('/api/jobs', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(params)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to start conversion');
        }

        const data = await response.json();
        currentJobId = data.job_id;

        // Show progress panel
        progressPanel.style.display = 'block';
        progressPanel.scrollIntoView({ behavior: 'smooth' });

        // Start listening to progress
        listenToProgress(currentJobId);

    } catch (error) {
        console.error('Error starting conversion:', error);
        alert('启动转换失败: ' + error.message);
        startBtn.disabled = false;
        startBtn.textContent = '🚀 开始转换';
    }
}

// Listen to progress via SSE
function listenToProgress(jobId) {
    // Close existing connection
    if (eventSource) {
        eventSource.close();
    }

    eventSource = new EventSource(`/api/progress/${jobId}`);

    eventSource.onmessage = (event) => {
        const job = JSON.parse(event.data);
        updateProgress(job);

        // Close connection if job is completed or failed
        if (job.status === 'completed' || job.status === 'failed') {
            eventSource.close();
            startBtn.disabled = false;
            startBtn.textContent = '🚀 开始转换';
            loadJobs(); // Refresh job list
        }
    };

    eventSource.onerror = (error) => {
        console.error('SSE error:', error);
        eventSource.close();
        startBtn.disabled = false;
        startBtn.textContent = '🚀 开始转换';
    };
}

// Update progress display
function updateProgress(job) {
    const progress = job.progress;

    // Update progress bar
    progressBar.style.width = `${progress.percentage}%`;

    // Update progress text with book count if available
    let progressTextContent = `${progress.percentage}%`;
    if (progress.current !== undefined && progress.total !== undefined && progress.total > 0) {
        progressTextContent = `${progress.current}/${progress.total} (${progress.percentage}%)`;
    }
    progressText.textContent = progressTextContent;

    // Update stage and message
    progressStage.textContent = progress.stage;
    progressMessage.textContent = progress.message;

    // Update logs
    if (job.logs && job.logs.length > 0) {
        progressLogs.innerHTML = job.logs
            .map(log => `<div class="log-entry">${log}</div>`)
            .join('');
        progressLogs.scrollTop = progressLogs.scrollHeight;
    }

    // Show error if failed
    if (job.status === 'failed' && job.error) {
        progressStage.textContent = '❌ 转换失败';
        progressMessage.textContent = job.error;
        progressBar.style.background = 'linear-gradient(90deg, #ef4444, #dc2626)';
    } else if (job.status === 'completed') {
        progressStage.textContent = '✅ 转换完成';
        progressBar.style.background = 'linear-gradient(90deg, #10b981, #059669)';
    }
}

// Load job history
async function loadJobs() {
    try {
        const response = await fetch('/api/jobs');
        if (!response.ok) {
            throw new Error('Failed to load jobs');
        }

        const data = await response.json();
        renderJobList(data.jobs);
    } catch (error) {
        console.error('Error loading jobs:', error);
    }
}

// Render job list
function renderJobList(jobs) {
    if (jobs.length === 0) {
        jobList.innerHTML = '<div class="empty-state">暂无任务记录</div>';
        return;
    }

    // Sort by created time (newest first)
    jobs.sort((a, b) => new Date(b.created_time) - new Date(a.created_time));

    jobList.innerHTML = jobs.map(job => {
        const statusClass = job.status;
        const statusText = {
            'pending': '等待中',
            'running': '运行中',
            'completed': '已完成',
            'failed': '失败'
        }[job.status] || job.status;

        const createdTime = new Date(job.created_time).toLocaleString('zh-CN');
        const mode = job.parameters.mode;
        const folder = job.parameters.folder;

        return `
            <div class="job-item ${statusClass}">
                <div class="job-header">
                    <div class="job-id">${job.id.substring(0, 8)}</div>
                    <div class="job-status ${statusClass}">${statusText}</div>
                </div>
                <div class="job-details">
                    <div>模式: ${mode}</div>
                    <div>文件夹: ${folder}</div>
                    <div>创建时间: ${createdTime}</div>
                    ${job.error ? `<div style="color: var(--accent-error);">错误: ${job.error}</div>` : ''}
                </div>
            </div>
        `;
    }).join('');
}

// Auto-refresh job list every 10 seconds
setInterval(() => {
    if (!currentJobId || (eventSource && eventSource.readyState === EventSource.CLOSED)) {
        loadJobs();
    }
}, 10000);
