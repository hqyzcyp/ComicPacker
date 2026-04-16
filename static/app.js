// ComicPacker Web Interface - Client-side JavaScript

// Configuration
const ACTIVE_JOB_STATUSES = new Set(['pending', 'running']);
const FAST_CONSOLE_POLL_MS = 1000;
const IDLE_CONSOLE_POLL_MS = 4000;
const HIDDEN_CONSOLE_POLL_MS = 15000;
const JOB_LIST_POLL_MS = 5000;
const SYSTEM_STATS_POLL_MS = 1000;
const FALLBACK_BROWSE_ROOT = '/mnt';
const STAT_TONE_CLASSES = ['stat-value--good', 'stat-value--warn', 'stat-value--bad'];
const MODE_LABELS = {
    book: '按书打包',
    cbz: '按CBZ打包',
    batch: '按批次打包',
    pdf: 'PDF转换MOBI'
};

// State management
let currentPath = FALLBACK_BROWSE_ROOT;
let selectedFolder = null;
let selectedFolderAnalysis = null;
let latestConsoleOutput = [];
let lastConsoleSignature = '';
let consolePollTimer = null;
let consolePollInFlight = false;
let hasActiveJobs = false;
let lastFocusedElement = null;
let defaultComicFolder = FALLBACK_BROWSE_ROOT;
let defaultOutputFolder = `${FALLBACK_BROWSE_ROOT}/comic_output`;
let isSubmittingJob = false;

// DOM elements
const fileList = document.getElementById('file-list');
const currentPathInput = document.getElementById('current-path');
const selectedFolderDisplay = document.getElementById('selected-folder-display');
const firstFileDisplay = document.getElementById('first-file-display');
const conversionForm = document.getElementById('conversion-form');
const jobList = document.getElementById('job-list');
const startBtn = document.getElementById('start-btn');
const clearHistoryBtn = document.getElementById('clear-history-btn');
const comicNameInput = document.getElementById('comic-name');
const comicNameHelp = document.getElementById('comic-name-help');
const outputInput = document.getElementById('output');
const outputNamePreview = document.getElementById('output-name-preview');
const outputPreviewHelp = document.getElementById('output-preview-help');
const consoleOutputPanel = document.getElementById('console-output');
const expandConsoleBtn = document.getElementById('expand-console-btn');
const consoleModal = document.getElementById('console-modal');
const closeConsoleModalBtn = document.getElementById('close-console-modal-btn');
const consoleOutputModal = document.getElementById('console-output-modal');

// Settings elements
const setDefaultBtn = document.getElementById('set-default-btn');

// Mode-specific controls
const batchSizeGroup = document.getElementById('batch-size-group');
const batchSizeSlider = document.getElementById('batch-size');
const batchSizeValue = document.getElementById('batch-size-value');
const modeSelect = document.getElementById('mode');
const convertToMobiGroup = document.getElementById('convert-to-mobi-group');
const convertToMobiCheckbox = document.getElementById('convert-to-mobi');
const keepPdfGroup = document.getElementById('keep-pdf-group');
const keepPdfCheckbox = document.getElementById('keep-pdf');
const formatOptionsHelp = document.getElementById('format-options-help');
const kindleProfileGroup = document.getElementById('kindle-profile-group');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
    updateModeSpecificControls();
    renderConsoleOutputs([]);
    initializePage();
});

async function initializePage() {
    const config = await loadConfig();
    await loadDirectory(config.comic_folder || FALLBACK_BROWSE_ROOT);
    loadJobs();
}

async function loadConfig() {
    try {
        const data = await requestJson('/api/config');
        defaultComicFolder = data.comic_folder || FALLBACK_BROWSE_ROOT;
        defaultOutputFolder = data.output_folder || `${FALLBACK_BROWSE_ROOT}/comic_output`;
        setOutputValue(defaultOutputFolder, true);
        return data;
    } catch (error) {
        console.error('Error loading config:', error);
        setOutputValue(defaultOutputFolder, true);
        showNotification('⚠ 读取配置文件失败，已使用 /mnt 默认路径', 'warning');
        return {
            comic_folder: defaultComicFolder,
            output_folder: defaultOutputFolder
        };
    }
}

async function setCurrentAsDefault() {
    if (!currentPath) {
        showNotification('⚠ 当前路径无效', 'warning');
        return;
    }

    try {
        const data = await requestJson('/api/config/default-path', {
            method: 'POST',
            body: { path: currentPath }
        });

        defaultComicFolder = data.comic_folder || currentPath;
        defaultOutputFolder = data.output_folder || defaultOutputFolder;
        setOutputValue(defaultOutputFolder, true);
        showNotification(`✓ 已写入配置文件: ${defaultComicFolder}`, 'success');
    } catch (error) {
        console.error('Error saving default path:', error);
        showNotification(`⚠ 保存默认路径失败: ${error.message}`, 'warning');
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

async function readApiPayload(response) {
    const contentType = response.headers.get('content-type') || '';
    const rawText = await response.text();

    if (!rawText) {
        return {};
    }

    if (contentType.includes('application/json')) {
        return JSON.parse(rawText);
    }

    try {
        return JSON.parse(rawText);
    } catch (error) {
        const isHtml = rawText.trim().startsWith('<');
        return {
            error: isHtml
                ? `服务端返回了 HTML（HTTP ${response.status}），可能需要重启 Web 服务`
                : `服务端返回了无法解析的响应（HTTP ${response.status}）`
        };
    }
}

async function requestJson(url, options = {}) {
    const { body, headers = {}, ...rest } = options;
    const requestOptions = {
        ...rest,
        headers: { ...headers }
    };

    if (body !== undefined) {
        requestOptions.body = typeof body === 'string' || body instanceof FormData
            ? body
            : JSON.stringify(body);

        if (!(body instanceof FormData) && !requestOptions.headers['Content-Type']) {
            requestOptions.headers['Content-Type'] = 'application/json';
        }
    }

    const response = await fetch(url, requestOptions);
    const data = await readApiPayload(response);

    if (!response.ok) {
        throw new Error(data.error || `请求失败（HTTP ${response.status}）`);
    }

    return data;
}

function escapeHtml(value) {
    return String(value || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
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

function clearElement(element) {
    if (!element) {
        return;
    }

    while (element.firstChild) {
        element.removeChild(element.firstChild);
    }
}

function renderPlaceholder(element, className, message) {
    clearElement(element);
    const placeholder = document.createElement('div');
    placeholder.className = className;
    placeholder.textContent = message;
    element.appendChild(placeholder);
}

function setElementHidden(element, hidden) {
    if (element) {
        element.hidden = Boolean(hidden);
    }
}

function getStatTone(value) {
    if (value > 80) {
        return 'bad';
    }
    if (value > 50) {
        return 'warn';
    }
    return 'good';
}

function setStatValue(element, text, numericValue) {
    if (!element) {
        return;
    }

    element.textContent = text;
    element.classList.remove(...STAT_TONE_CLASSES);
    element.classList.add(`stat-value--${getStatTone(numericValue)}`);
}

function setOutputValue(value, autoManaged = true) {
    outputInput.value = value;
    outputInput.dataset.autoManaged = autoManaged ? 'true' : 'false';
    updateOutputPreview();
}

function updateOutputFolderSuggestion(force = false) {
    const canAutoUpdate = force || outputInput.dataset.autoManaged !== 'false' || !outputInput.value.trim();
    if (!canAutoUpdate) {
        return;
    }

    if (defaultOutputFolder) {
        setOutputValue(defaultOutputFolder, true);
        return;
    }

    if (selectedFolderAnalysis?.suggested_output_dir) {
        setOutputValue(selectedFolderAnalysis.suggested_output_dir, true);
        return;
    }

    setOutputValue('./output', true);
}

function formatModeLabel(mode) {
    return MODE_LABELS[mode] || mode;
}

function isPdfModeSelected() {
    return modeSelect.value === 'pdf';
}

function isMobiConversionEnabled() {
    return isPdfModeSelected() || convertToMobiCheckbox.checked;
}

function shouldKeepPdfOutput() {
    return keepPdfCheckbox.checked;
}

function updateFormatOptionState() {
    const pdfMode = isPdfModeSelected();
    const mobiEnabled = isMobiConversionEnabled();

    convertToMobiCheckbox.checked = mobiEnabled;
    convertToMobiCheckbox.disabled = pdfMode;

    if (!mobiEnabled) {
        keepPdfCheckbox.checked = true;
    }
    keepPdfCheckbox.disabled = !mobiEnabled;

    convertToMobiGroup.classList.toggle('checkbox-chip--disabled', convertToMobiCheckbox.disabled);
    keepPdfGroup.classList.toggle('checkbox-chip--disabled', keepPdfCheckbox.disabled);

    if (!mobiEnabled) {
        formatOptionsHelp.textContent = '当前只输出 PDF；若需选择是否保留 PDF，请先勾选 MOBI 转换。';
    } else if (shouldKeepPdfOutput()) {
        formatOptionsHelp.textContent = '转换完成后会同时保留 pdf 与 mobi 两个子目录。';
    } else {
        formatOptionsHelp.textContent = '转换完成后会自动删除 pdf 子目录，只保留 mobi 子目录。';
    }
}

function buildPreviewBaseName() {
    const previewVolume = selectedFolderAnalysis?.sample_volume || '01';
    const comicName = getCurrentComicName();

    if (modeSelect.value === 'batch') {
        return `${comicName || '漫画名'}_CH-001_to_CH-010`;
    }

    if (comicName) {
        return `${comicName} Vol.${previewVolume}`;
    }

    return selectedFolderAnalysis?.output_preview || `漫画名 Vol.${previewVolume}`;
}

function updateOutputPreview() {
    const previewBaseName = buildPreviewBaseName();
    const pdfMode = isPdfModeSelected();
    const mobiEnabled = isMobiConversionEnabled();
    const keepPdf = shouldKeepPdfOutput();
    const preferredExtension = (pdfMode || (mobiEnabled && !keepPdf)) ? 'mobi' : 'pdf';
    const previewText = `${previewBaseName}.${preferredExtension}`;

    outputNamePreview.textContent = previewText;

    const rootDir = (outputInput.value || './output').trim() || './output';
    const folderName = sanitizePathComponent(getCurrentComicName() || selectedFolderAnalysis?.comic_name || '漫画名');
    const pdfPath = `${rootDir}/${folderName}/pdf/${previewBaseName}.pdf`;
    const mobiPath = `${rootDir}/${folderName}/mobi/${previewBaseName}.mobi`;

    if (pdfMode) {
        outputPreviewHelp.textContent = keepPdf
            ? `输出结构：${mobiPath} ｜ 同时保留 ${rootDir}/${folderName}/pdf/`
            : `输出结构：${mobiPath} ｜ 转换完成后仅保留 mobi 子目录`;
    } else if (!mobiEnabled) {
        outputPreviewHelp.textContent = `输出结构：${pdfPath}`;
    } else if (keepPdf) {
        outputPreviewHelp.textContent = `输出结构：${pdfPath} ｜ 另生成 ${rootDir}/${folderName}/mobi/`;
    } else {
        outputPreviewHelp.textContent = `输出结构：${mobiPath} ｜ 转换完成后自动删除 ${rootDir}/${folderName}/pdf/`;
    }
}

function updateModeSpecificControls() {
    const isBatchMode = modeSelect.value === 'batch';

    setElementHidden(batchSizeGroup, !isBatchMode);
    updateFormatOptionState();
    setElementHidden(kindleProfileGroup, !isMobiConversionEnabled());

    updateOutputPreview();
}

function applyFolderAnalysis(data) {
    selectedFolderAnalysis = data;
    firstFileDisplay.textContent = data.first_file_name || '未找到漫画文件';

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

function renderConsoleOutput(target, lines) {
    if (!target) {
        return;
    }

    const wasNearBottom = (target.scrollHeight - target.scrollTop - target.clientHeight) < 24;
    const safeLines = Array.isArray(lines) ? lines : [];

    target.innerHTML = safeLines.length > 0
        ? safeLines.map(line => `<div class="console-line">${escapeHtml(line)}</div>`).join('')
        : '<div class="console-line">等待任务输出...</div>';

    if (wasNearBottom || safeLines.length <= 1) {
        target.scrollTop = target.scrollHeight;
    }
}

function getConsoleSignature(lines) {
    return Array.isArray(lines) ? lines.join('\n') : '';
}

function renderConsoleOutputs(lines, options = {}) {
    const safeLines = Array.isArray(lines) ? [...lines] : [];
    latestConsoleOutput = safeLines;

    const nextSignature = getConsoleSignature(safeLines);
    if (!options.force && nextSignature === lastConsoleSignature) {
        return;
    }

    lastConsoleSignature = nextSignature;
    renderConsoleOutput(consoleOutputPanel, safeLines);
    renderConsoleOutput(consoleOutputModal, safeLines);
}

function getConsolePollDelay() {
    if (document.hidden) {
        return HIDDEN_CONSOLE_POLL_MS;
    }

    return (hasActiveJobs || !consoleModal.hidden)
        ? FAST_CONSOLE_POLL_MS
        : IDLE_CONSOLE_POLL_MS;
}

function scheduleConsolePolling(delay = getConsolePollDelay()) {
    if (consolePollTimer) {
        clearTimeout(consolePollTimer);
    }

    consolePollTimer = window.setTimeout(() => {
        loadConsoleOutput();
    }, delay);
}

function syncActiveJobState(jobs) {
    const nextHasActiveJobs = Array.isArray(jobs)
        && jobs.some(job => ACTIVE_JOB_STATUSES.has(job.status));

    if (nextHasActiveJobs === hasActiveJobs) {
        return;
    }

    hasActiveJobs = nextHasActiveJobs;
    scheduleConsolePolling(hasActiveJobs ? 0 : getConsolePollDelay());
}

function openConsoleModal() {
    lastFocusedElement = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    consoleModal.hidden = false;
    document.body.classList.add('modal-open');
    renderConsoleOutputs(latestConsoleOutput, { force: true });
    closeConsoleModalBtn.focus();
    scheduleConsolePolling(0);
}

function closeConsoleModal() {
    if (consoleModal.hidden) {
        return;
    }

    consoleModal.hidden = true;
    document.body.classList.remove('modal-open');

    if (lastFocusedElement && typeof lastFocusedElement.focus === 'function') {
        lastFocusedElement.focus();
    }

    scheduleConsolePolling();
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
    modeSelect.addEventListener('change', () => {
        updateModeSpecificControls();
    });

    // MOBI conversion checkbox
    convertToMobiCheckbox.addEventListener('change', (e) => {
        if (isPdfModeSelected()) {
            e.target.checked = true;
        }
        updateModeSpecificControls();
    });

    keepPdfCheckbox.addEventListener('change', () => {
        updateFormatOptionState();
        updateOutputPreview();
    });

    comicNameInput.addEventListener('input', () => {
        updateOutputPreview();
        updateOutputFolderSuggestion();
    });

    outputInput.addEventListener('input', () => {
        outputInput.dataset.autoManaged = 'false';
        updateOutputPreview();
    });

    expandConsoleBtn.addEventListener('click', openConsoleModal);
    closeConsoleModalBtn.addEventListener('click', closeConsoleModal);

    consoleModal.addEventListener('click', (event) => {
        if (event.target === consoleModal) {
            closeConsoleModal();
        }
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && !consoleModal.hidden) {
            closeConsoleModal();
        }
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
    renderPlaceholder(fileList, 'loading', '加载中...');

    try {
        const data = await requestJson('/api/browse', {
            method: 'POST',
            body: { path }
        });

        currentPath = data.path;
        currentPathInput.value = data.path;
        currentPathInput.dataset.parent = data.parent;

        renderFileList(data.items);
    } catch (error) {
        console.error('Error loading directory:', error);
        renderPlaceholder(fileList, 'loading', `加载失败：${error.message}`);
        showNotification(`⚠ 加载目录失败: ${error.message}`, 'warning');
    }
}

function triggerDownload(path) {
    const url = `/api/download?path=${encodeURIComponent(path)}`;
    const link = document.createElement('a');
    link.href = url;
    link.target = '_blank';
    link.rel = 'noopener';
    document.body.appendChild(link);
    link.click();
    link.remove();
}

// Render file list
function renderFileList(items) {
    if (!Array.isArray(items) || items.length === 0) {
        renderPlaceholder(fileList, 'empty-state', '目录为空');
        return;
    }

    clearElement(fileList);
    const fragment = document.createDocumentFragment();

    items.forEach(item => {
        const fileItem = document.createElement('div');
        fileItem.className = 'file-item';

        const icon = document.createElement('div');
        icon.className = 'file-icon';
        icon.textContent = item.is_dir ? '📁' : '📄';

        const fileInfo = document.createElement('div');
        fileInfo.className = 'file-info';

        const fileName = document.createElement('div');
        fileName.className = 'file-name';
        fileName.textContent = item.name;
        fileInfo.appendChild(fileName);

        if (item.is_dir && item.file_count > 0) {
            const fileCount = document.createElement('div');
            fileCount.className = 'file-count';
            fileCount.textContent = `${item.file_count} 个文件`;
            fileInfo.appendChild(fileCount);
        }

        fileItem.append(icon, fileInfo);

        if (item.is_downloadable) {
            const fileActions = document.createElement('div');
            fileActions.className = 'file-actions';

            const downloadBtn = document.createElement('button');
            downloadBtn.type = 'button';
            downloadBtn.className = 'file-action-btn';
            downloadBtn.textContent = '⬇️ 下载';
            downloadBtn.title = `下载 ${item.name}`;
            downloadBtn.addEventListener('click', (event) => {
                event.stopPropagation();
                triggerDownload(item.path);
            });

            fileActions.appendChild(downloadBtn);
            fileItem.appendChild(fileActions);
        }

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

        fragment.appendChild(fileItem);
    });

    fileList.appendChild(fragment);
}

// Select folder
async function selectFolder(path) {
    selectedFolder = path;
    selectedFolderDisplay.textContent = path;
    selectedFolderAnalysis = null;
    firstFileDisplay.textContent = '读取中...';
    outputInput.dataset.autoManaged = 'true';
    updateOutputPreview();

    // 自动检测文件类型并切换模式
    await detectAndSwitchMode(path);
}

// Detect folder contents and switch mode automatically
async function detectAndSwitchMode(folderPath) {
    try {
        const data = await requestJson('/api/detect-mode', {
            method: 'POST',
            body: { path: folderPath }
        });

        const recommendedMode = data.recommended_mode;
        applyFolderAnalysis(data);

        // 切换到推荐的模式
        modeSelect.value = recommendedMode;

        updateModeSpecificControls();

        // 显示通知
        if (data.cbz_count > 0) {
            showNotification(`✓ 检测到 ${data.cbz_count} 个CBZ文件，已切换到CBZ模式`, 'info');
        } else if (data.zip_count > 0) {
            showNotification(`✓ 检测到 ${data.zip_count} 个ZIP文件，已切换到按书打包模式`, 'info');
        } else if (data.pdf_count > 0) {
            showNotification(`✓ 检测到 ${data.pdf_count} 个PDF文件，已切换到 PDF 转 MOBI 模式`, 'info');
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
    }
}

// Start conversion
async function startConversion() {
    if (!selectedFolder) {
        showNotification('⚠ 请先选择一个文件夹', 'warning');
        return;
    }

    if (isSubmittingJob) {
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
        convert_to_mobi: isMobiConversionEnabled(),
        keep_pdf: isMobiConversionEnabled() ? shouldKeepPdfOutput() : true,
        kindle_profile: formData.get('kindle_profile') || 'KPW5'
    };

    // Add batch_size only for batch mode
    if (params.mode === 'batch') {
        params.batch_size = parseInt(formData.get('batch_size'));
    }

    try {
        isSubmittingJob = true;
        startBtn.disabled = true;

        const data = await requestJson('/api/jobs', {
            method: 'POST',
            body: params
        });

        // Show success notification
        showNotification(`✓ 任务已提交: ${data.job_id.substring(0, 8)}`, 'success');
        hasActiveJobs = true;
        scheduleConsolePolling(0);

        // Refresh job list to show new job
        loadJobs();

    } catch (error) {
        console.error('Error starting conversion:', error);
        showNotification(`⚠ 启动转换失败: ${error.message}`, 'warning');
    } finally {
        isSubmittingJob = false;
        startBtn.disabled = false;
    }
}

// Cancel job
async function cancelJob(jobId) {
    // 添加二次确认
    if (!confirm('确定要取消这个任务吗？')) {
        return;
    }

    try {
        await requestJson(`/api/jobs/${jobId}/cancel`, {
            method: 'POST'
        });

        showNotification('✓ 任务取消请求已发送', 'success');

        // Refresh job list
        setTimeout(() => loadJobs(), 1000);

    } catch (error) {
        console.error('Error cancelling job:', error);
        showNotification(`⚠ 取消任务失败: ${error.message}`, 'warning');
    }
}

// Delete job
async function deleteJob(jobId) {
    try {
        await requestJson(`/api/jobs/${jobId}`, {
            method: 'DELETE'
        });

        showNotification('✓ 任务已删除', 'success');

        // Refresh job list
        loadJobs();

    } catch (error) {
        console.error('Error deleting job:', error);
        showNotification(`⚠ 删除任务失败: ${error.message}`, 'warning');
    }
}



// Load job history
async function loadJobs() {
    try {
        const data = await requestJson('/api/jobs');
        syncActiveJobState(data.jobs);
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
        const data = await requestJson('/api/jobs/clear', {
            method: 'POST'
        });

        showNotification(`✓ ${data.message}`, 'success');

        // Reload job list
        loadJobs();
    } catch (error) {
        console.error('Error clearing job history:', error);
        showNotification(`⚠ 清除历史记录失败: ${error.message}`, 'warning');
    }
}

// Render job list
function renderJobList(jobs) {
    if (!Array.isArray(jobs) || jobs.length === 0) {
        renderPlaceholder(jobList, 'empty-state', '暂无任务记录');
        return;
    }

    const sortedJobs = [...jobs].sort((a, b) => new Date(b.created_time) - new Date(a.created_time));
    const fragment = document.createDocumentFragment();

    sortedJobs.forEach(job => {
        const statusClass = job.status;
        const statusText = {
            pending: '⏳ 等待中',
            running: '▶️ 运行中',
            completed: '✅ 已完成',
            failed: '❌ 失败',
            cancelled: '⚠️ 已取消'
        }[job.status] || job.status;

        const progress = job.progress || {};
        const progressPercentage = Number(progress.percentage || 0);
        const progressMessage = progress.message || '';
        const progressInfo = Number.isFinite(progress.current) && Number.isFinite(progress.total) && progress.total > 0
            ? `${progress.current}/${progress.total}`
            : '';
        const terminalMessage = progressMessage || job.error || '';

        const jobItem = document.createElement('article');
        jobItem.className = `job-item ${statusClass}`;

        const header = document.createElement('div');
        header.className = 'job-header';

        const jobId = document.createElement('div');
        jobId.className = 'job-id';
        jobId.textContent = String(job.id || '').substring(0, 8);

        const status = document.createElement('div');
        status.className = `job-status ${statusClass}`;
        status.textContent = statusText;

        const actionButton = document.createElement('button');
        actionButton.type = 'button';
        actionButton.className = `job-action-btn ${ACTIVE_JOB_STATUSES.has(job.status) ? 'cancel-btn' : 'delete-btn'}`;
        actionButton.textContent = ACTIVE_JOB_STATUSES.has(job.status) ? '🛑 取消' : '🗑️ 删除';
        actionButton.addEventListener('click', () => {
            if (ACTIVE_JOB_STATUSES.has(job.status)) {
                cancelJob(job.id);
            } else {
                deleteJob(job.id);
            }
        });

        header.append(jobId, status, actionButton);

        const details = document.createElement('div');
        details.className = 'job-details';

        [['模式', formatModeLabel(job.parameters?.mode || 'book')], ['文件夹', job.parameters?.folder || ''], ['创建时间', new Date(job.created_time).toLocaleString('zh-CN')]]
            .forEach(([label, value]) => {
                const row = document.createElement('div');
                const strong = document.createElement('strong');
                strong.textContent = `${label}:`;
                row.append(strong, document.createTextNode(` ${value}`));
                details.appendChild(row);
            });

        if (job.status === 'running') {
            const progressInfoBlock = document.createElement('div');
            progressInfoBlock.className = 'job-progress-info';

            const progressBarContainer = document.createElement('div');
            progressBarContainer.className = 'job-progress-bar-container';

            const progressBar = document.createElement('div');
            progressBar.className = 'job-progress-bar';
            progressBar.style.width = `${progressPercentage}%`;
            progressBarContainer.appendChild(progressBar);

            const progressText = document.createElement('div');
            progressText.className = 'job-progress-text';

            const progressPercent = document.createElement('span');
            progressPercent.textContent = `${progressPercentage}%`;
            progressText.appendChild(progressPercent);

            if (progressInfo) {
                const progressCount = document.createElement('span');
                progressCount.className = 'job-progress-count';
                progressCount.textContent = progressInfo;
                progressText.appendChild(progressCount);
            }

            progressInfoBlock.append(progressBarContainer, progressText);

            if (progressMessage) {
                const message = document.createElement('div');
                message.className = 'job-progress-message';
                message.textContent = progressMessage;
                progressInfoBlock.appendChild(message);
            }

            details.appendChild(progressInfoBlock);
        }

        if (job.status !== 'running' && terminalMessage) {
            const terminal = document.createElement('div');
            terminal.className = 'job-progress-message';
            terminal.textContent = terminalMessage;
            details.appendChild(terminal);
        }

        if (job.status === 'completed' && progressInfo) {
            const processedRow = document.createElement('div');
            const strong = document.createElement('strong');
            strong.textContent = '处理数量:';
            processedRow.append(strong, document.createTextNode(` ${progressInfo}`));
            details.appendChild(processedRow);
        }

        if (job.error) {
            const errorRow = document.createElement('div');
            errorRow.className = 'job-error';
            const strong = document.createElement('strong');
            strong.textContent = '错误:';
            errorRow.append(strong, document.createTextNode(` ${job.error}`));
            details.appendChild(errorRow);
        }

        jobItem.append(header, details);
        fragment.appendChild(jobItem);
    });

    clearElement(jobList);
    jobList.appendChild(fragment);
}

// Load and update system stats
async function loadSystemStats() {
    try {
        const data = await requestJson('/api/system-stats');

        // Update CPU usage
        const cpuUsage = document.getElementById('cpu-usage');
        if (cpuUsage) {
            setStatValue(cpuUsage, `${data.cpu_percent}%`, Number(data.cpu_percent || 0));
        }

        // Update memory usage
        const memoryUsage = document.getElementById('memory-usage');
        if (memoryUsage) {
            setStatValue(
                memoryUsage,
                `${data.memory_percent}% (${data.memory_used_gb}/${data.memory_total_gb}GB)`,
                Number(data.memory_percent || 0)
            );
        }

    } catch (error) {
        console.error('Error loading system stats:', error);
    }
}

// Auto-refresh job list every 5 seconds
setInterval(() => {
    loadJobs();
}, JOB_LIST_POLL_MS);

// Load and update console output
async function loadConsoleOutput() {
    if (consolePollInFlight) {
        scheduleConsolePolling();
        return;
    }

    consolePollInFlight = true;

    try {
        const data = await requestJson('/api/console-output');
        renderConsoleOutputs(data.output || []);

    } catch (error) {
        console.error('Error loading console output:', error);
    } finally {
        consolePollInFlight = false;
        scheduleConsolePolling();
    }
}

// Auto-refresh system stats every 1 second
setInterval(() => {
    loadSystemStats();
}, SYSTEM_STATS_POLL_MS);

// Load system stats and console output on page load
loadSystemStats();
loadConsoleOutput();

document.addEventListener('visibilitychange', () => {
    scheduleConsolePolling(document.hidden ? HIDDEN_CONSOLE_POLL_MS : 0);
});
