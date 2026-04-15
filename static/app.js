// ComicPacker Web Interface - Client-side JavaScript

// Configuration
const DEFAULT_PATH_KEY = 'comicpacker_default_path';

// State management
let currentPath = '.';
let selectedFolder = null;
let selectedFolderAnalysis = null;

// DOM elements
const fileList = document.getElementById('file-list');
const currentPathInput = document.getElementById('current-path');
const selectedFolderDisplay = document.getElementById('selected-folder-display');
const firstFileDisplay = document.getElementById('first-file-display');
const namingSourceDisplay = document.getElementById('naming-source-display');
const conversionForm = document.getElementById('conversion-form');
const jobList = document.getElementById('job-list');
const startBtn = document.getElementById('start-btn');
const clearHistoryBtn = document.getElementById('clear-history-btn');
const comicNameInput = document.getElementById('comic-name');
const comicNameHelp = document.getElementById('comic-name-help');
const outputInput = document.getElementById('output');
const outputNamePreview = document.getElementById('output-name-preview');
const outputPreviewHelp = document.getElementById('output-preview-help');

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
    updateOutputPreview();
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

function sanitizePathComponent(value) {
    return (value || '')
        .replace(/[<>:"/\\|?*]+/g, ' ')
        .replace(/\s+/g, ' ')
        .trim()
        .replace(/[ ._-]+$/g, '');
}

function getCurrentComicName() {
    return (comicNameInput.value || '').trim();
}

function setOutputValue(value, autoManaged = true) {
    outputInput.value = value;
    outputInput.dataset.autoManaged = autoManaged ? 'true' : 'false';
}

function formatNamingSource(data) {
    if (!data || !data.first_file_name) {
        return '未找到漫画文件，请手动填写漫画名';
    }

    const sourceLabel = {
        filename: '已从首个文件名自动提取',
        folder: '文件名仅包含 Vol，已从文件夹名推断',
        unknown: '暂时无法可靠推断'
    }[data.naming_source] || '暂时无法可靠推断';

    const confidenceLabel = {
        high: '高',
        medium: '中',
        low: '低'
    }[data.naming_confidence] || '低';

    return `${sourceLabel}（置信度${confidenceLabel}）`;
}

function updateOutputFolderSuggestion(force = false) {
    const canAutoUpdate = force || outputInput.dataset.autoManaged !== 'false' || !outputInput.value.trim();
    if (!canAutoUpdate) {
        return;
    }

    const comicName = sanitizePathComponent(getCurrentComicName());

    if (comicName) {
        setOutputValue(`./output/${comicName}`, true);
        return;
    }

    if (selectedFolderAnalysis?.suggested_output_dir) {
        setOutputValue(selectedFolderAnalysis.suggested_output_dir, true);
        return;
    }

    setOutputValue('./output', true);
}

function updateOutputPreview() {
    const previewVolume = selectedFolderAnalysis?.sample_volume || '01';
    const comicName = getCurrentComicName();
    const batchPreviewBase = comicName || '漫画名';
    const previewText = modeSelect.value === 'batch'
        ? `${batchPreviewBase}_CH-001_to_CH-010`
        : (comicName
            ? `${comicName} Vol.${previewVolume}`
            : (selectedFolderAnalysis?.output_preview || `漫画名 Vol.${previewVolume}`));

    outputNamePreview.textContent = previewText;

    if (selectedFolderAnalysis?.first_file_name) {
        outputPreviewHelp.textContent = `源文件示例：${selectedFolderAnalysis.first_file_name}`;
    } else {
        outputPreviewHelp.textContent = '预览格式：漫画名 Vol.01';
    }
}

function applyFolderAnalysis(data) {
    selectedFolderAnalysis = data;
    firstFileDisplay.textContent = data.first_file_name || '未找到漫画文件';
    namingSourceDisplay.textContent = formatNamingSource(data);

    comicNameInput.value = data.comic_name || '';

    if (data.naming_source === 'filename') {
        comicNameHelp.textContent = '已从首个文件名提取漫画名；如果你想统一输出名，可以直接修改这里。';
    } else if (data.naming_source === 'folder') {
        comicNameHelp.textContent = '首个文件只有 Vol 编号，漫画名来自文件夹推断；开始转换前建议确认一次。';
    } else {
        comicNameHelp.textContent = '未能稳定识别漫画名，请手动填写，输出预览会同步更新。';
    }

    updateOutputPreview();
    updateOutputFolderSuggestion(true);
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

        updateOutputPreview();
    });

    // MOBI conversion checkbox
    convertToMobiCheckbox.addEventListener('change', (e) => {
        if (e.target.checked) {
            kindleProfileGroup.style.display = 'block';
        } else {
            kindleProfileGroup.style.display = 'none';
        }
    });

    comicNameInput.addEventListener('input', () => {
        updateOutputPreview();
        updateOutputFolderSuggestion();
    });

    outputInput.addEventListener('input', () => {
        outputInput.dataset.autoManaged = 'false';
    });

    // Form submission
    conversionForm.addEventListener('submit', (e) => {
        e.preventDefault();
        startConversion();
    });

    // Clear history button
    clearHistoryBtn.addEventListener('click', clearJobHistory);
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
                    selectFolder(item.path);
                }
            }
        });

        fileList.appendChild(fileItem);
    });
}

// Select folder
async function selectFolder(path) {
    selectedFolder = path;
    selectedFolderDisplay.textContent = path;
    selectedFolderAnalysis = null;
    firstFileDisplay.textContent = '读取中...';
    namingSourceDisplay.textContent = '正在分析文件夹内容...';
    outputInput.dataset.autoManaged = 'true';
    updateOutputPreview();

    // 自动检测文件类型并切换模式
    await detectAndSwitchMode(path);
}

// Detect folder contents and switch mode automatically
async function detectAndSwitchMode(folderPath) {
    try {
        const response = await fetch('/api/detect-mode', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ path: folderPath })
        });

        if (!response.ok) {
            console.error('Failed to detect mode');
            return;
        }

        const data = await response.json();
        const recommendedMode = data.recommended_mode;
        applyFolderAnalysis(data);

        // 切换到推荐的模式
        modeSelect.value = recommendedMode;

        // 触发 change 事件以更新相关UI
        const changeEvent = new Event('change');
        modeSelect.dispatchEvent(changeEvent);

        // 显示通知
        if (data.cbz_count > 0) {
            showNotification(`✓ 检测到 ${data.cbz_count} 个CBZ文件，已切换到CBZ模式`, 'info');
        } else if (data.zip_count > 0) {
            showNotification(`✓ 检测到 ${data.zip_count} 个ZIP文件，已切换到按书打包模式`, 'info');
        } else if (data.total_comic_files > 0) {
            showNotification(`✓ 已读取 ${data.total_comic_files} 个漫画文件`, 'info');
        }

        // 检测到Vol开头的文件时提醒用户确认漫画名
        if (data.has_vol_files) {
            showNotification(`💡 检测到 ${data.vol_files_count} 个仅含 Vol 编号的文件，请确认漫画输出名`, 'warning');
        }

    } catch (error) {
        console.error('Error detecting mode:', error);
        firstFileDisplay.textContent = '读取失败';
        namingSourceDisplay.textContent = '自动分析失败，请手动填写漫画名';
    }
}

// Start conversion
async function startConversion() {
    if (!selectedFolder) {
        alert('请先选择一个文件夹');
        return;
    }

    // Gather form data
    const formData = new FormData(conversionForm);
    const comicName = getCurrentComicName();
    const outputFolder = (formData.get('output') || './output').trim() || './output';

    const params = {
        folder: selectedFolder,
        mode: formData.get('mode'),
        prefix: comicName,
        comic_name: comicName,
        output: outputFolder,
        convert_to_mobi: convertToMobiCheckbox.checked,
        kindle_profile: formData.get('kindle_profile') || 'KPW5'
    };

    // Add batch_size only for batch mode
    if (params.mode === 'batch') {
        params.batch_size = parseInt(formData.get('batch_size'));
    }

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

        // Show success notification
        showNotification(`✓ 任务已提交: ${data.job_id.substring(0, 8)}`, 'success');

        // Refresh job list to show new job
        loadJobs();

    } catch (error) {
        console.error('Error starting conversion:', error);
        alert('启动转换失败: ' + error.message);
    }
}

// Cancel job
async function cancelJob(jobId) {
    // 添加二次确认
    if (!confirm('确定要取消这个任务吗？')) {
        return;
    }

    try {
        const response = await fetch(`/api/jobs/${jobId}/cancel`, {
            method: 'POST'
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to cancel job');
        }

        showNotification('✓ 任务取消请求已发送', 'success');

        // Refresh job list
        setTimeout(() => loadJobs(), 1000);

    } catch (error) {
        console.error('Error cancelling job:', error);
        alert('取消任务失败: ' + error.message);
    }
}

// Delete job
async function deleteJob(jobId) {
    try {
        const response = await fetch(`/api/jobs/${jobId}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to delete job');
        }

        showNotification('✓ 任务已删除', 'success');

        // Refresh job list
        loadJobs();

    } catch (error) {
        console.error('Error deleting job:', error);
        alert('删除任务失败: ' + error.message);
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

// Clear job history
async function clearJobHistory() {
    if (!confirm('确定要清除所有任务历史记录吗？')) {
        return;
    }

    try {
        const response = await fetch('/api/jobs/clear', {
            method: 'POST'
        });

        if (!response.ok) {
            throw new Error('Failed to clear job history');
        }

        // Reload job list
        loadJobs();
    } catch (error) {
        console.error('Error clearing job history:', error);
        alert('清除历史记录失败: ' + error.message);
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
            'pending': '⏳ 等待中',
            'running': '▶️ 运行中',
            'completed': '✅ 已完成',
            'failed': '❌ 失败',
            'cancelled': '⚠️ 已取消'
        }[job.status] || job.status;

        const createdTime = new Date(job.created_time).toLocaleString('zh-CN');
        const mode = job.parameters.mode;
        const folder = job.parameters.folder;

        // 获取进度信息
        const progress = job.progress || {};
        const progressPercentage = progress.percentage || 0;
        const progressMessage = progress.message || '';
        const progressInfo = progress.current && progress.total
            ? `${progress.current}/${progress.total}`
            : '';

        // 确定显示哪个按钮
        const isActive = job.status === 'pending' || job.status === 'running';
        const actionButton = isActive
            ? `<button class="job-action-btn cancel-btn" onclick="cancelJob('${job.id}')">🛑 取消</button>`
            : `<button class="job-action-btn delete-btn" onclick="deleteJob('${job.id}')">🗑️ 删除</button>`;

        return `
            <div class="job-item ${statusClass}">
                <div class="job-header">
                    <div class="job-id">${job.id.substring(0, 8)}</div>
                    <div class="job-status ${statusClass}">${statusText}</div>
                    ${actionButton}
                </div>
                <div class="job-details">
                    <div><strong>模式:</strong> ${mode}</div>
                    <div><strong>文件夹:</strong> ${folder}</div>
                    <div><strong>创建时间:</strong> ${createdTime}</div>
                    ${job.status === 'running' ? `
                        <div class="job-progress-info">
                            <div class="job-progress-bar-container">
                                <div class="job-progress-bar" style="width: ${progressPercentage}%"></div>
                            </div>
                            <div class="job-progress-text">
                                <span>${progressPercentage}%</span>
                                ${progressInfo ? `<span class="job-progress-count">${progressInfo}</span>` : ''}
                            </div>
                            ${progressMessage ? `<div class="job-progress-message">${progressMessage}</div>` : ''}
                        </div>
                    ` : ''}
                    ${job.status === 'completed' && progressInfo ? `<div><strong>处理数量:</strong> ${progressInfo}</div>` : ''}
                    ${job.error ? `<div style="color: var(--accent-error);"><strong>错误:</strong> ${job.error}</div>` : ''}
                </div>
            </div>
        `;
    }).join('');
}

// Load and update system stats
async function loadSystemStats() {
    try {
        const response = await fetch('/api/system-stats');
        if (!response.ok) {
            throw new Error('Failed to load system stats');
        }

        const data = await response.json();

        // Update CPU usage
        const cpuUsage = document.getElementById('cpu-usage');
        if (cpuUsage) {
            cpuUsage.textContent = `${data.cpu_percent}%`;
            // Change color based on usage
            if (data.cpu_percent > 80) {
                cpuUsage.style.color = 'var(--accent-error)';
            } else if (data.cpu_percent > 50) {
                cpuUsage.style.color = 'var(--accent-warning)';
            } else {
                cpuUsage.style.color = 'var(--accent-success)';
            }
        }

        // Update memory usage
        const memoryUsage = document.getElementById('memory-usage');
        if (memoryUsage) {
            memoryUsage.textContent = `${data.memory_percent}% (${data.memory_used_gb}/${data.memory_total_gb}GB)`;
            // Change color based on usage
            if (data.memory_percent > 80) {
                memoryUsage.style.color = 'var(--accent-error)';
            } else if (data.memory_percent > 50) {
                memoryUsage.style.color = 'var(--accent-warning)';
            } else {
                memoryUsage.style.color = 'var(--accent-success)';
            }
        }

    } catch (error) {
        console.error('Error loading system stats:', error);
    }
}

// Auto-refresh job list every 5 seconds
setInterval(() => {
    loadJobs();
}, 5000);

// Load and update console output
async function loadConsoleOutput() {
    try {
        const response = await fetch('/api/console-output');
        if (!response.ok) {
            throw new Error('Failed to load console output');
        }

        const data = await response.json();
        const consoleOutput = document.getElementById('console-output');

        if (consoleOutput) {
            if (data.output && data.output.length > 0) {
                consoleOutput.innerHTML = data.output
                    .map(line => `<div class="console-line">${line}</div>`)
                    .join('');
            } else {
                consoleOutput.innerHTML = '<div class="console-line">等待任务输出...</div>';
            }
        }

    } catch (error) {
        console.error('Error loading console output:', error);
    }
}

// Auto-refresh system stats every 1 second
setInterval(() => {
    loadSystemStats();
}, 1000);

// Auto-refresh console output every 1 second
setInterval(() => {
    loadConsoleOutput();
}, 1000);

// Load system stats and console output on page load
loadSystemStats();
loadConsoleOutput();
