/* ============================================================
   HctrConvert — Main Application Controller (ES Module)
   ============================================================ */

import { FORMATS } from './config.js';
import { state, registerBlobUrl, revokeAllBlobUrls } from './state.js';
import { fetchHealth, convertFileWithProgress } from './api.js';
import {
  escHtml,
  getFileTypeInfo,
  renderEngineStatus,
  renderFileList,
  renderFormatGrid,
  renderOptionsPanel,
  showToast,
} from './ui.js';

// ───── Initialization ─────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  bindEvents();
  switchTab('document');
  refreshHealth();
});

async function refreshHealth() {
  try {
    const data = await fetchHealth();
    state.dependencies = data.dependencies || state.dependencies;
    renderEngineStatus(state.dependencies, false);
    if (state.files.length) {
      renderFormatGrid(selectFormat);
    }
  } catch {
    renderEngineStatus(null, true);
  }
}

// ───── Theme Management ───────────────────────────────────────
function initTheme() {
  const saved = localStorage.getItem('theme');
  if (saved === 'light' || saved === 'dark') {
    applyTheme(saved);
  }
}

function applyTheme(theme) {
  document.body.setAttribute('data-theme', theme);
  const icon = document.getElementById('theme-icon');
  if (icon) {
    icon.className = theme === 'light' ? 'fa-solid fa-sun' : 'fa-solid fa-moon';
  }
  localStorage.setItem('theme', theme);
}

function toggleTheme() {
  const current = document.body.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
  applyTheme(current === 'light' ? 'dark' : 'light');
}

// ───── Event Wiring (Zero Inline Handlers) ────────────────────
function bindEvents() {
  document.getElementById('themeToggleBtn')?.addEventListener('click', toggleTheme);

  // Category tabs
  document.querySelectorAll('.tab-btn').forEach((btn) => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  // Footer shortcut links
  document.querySelectorAll('[data-switch-tab]').forEach((link) => {
    link.addEventListener('click', () => switchTab(link.dataset.switchTab));
  });

  // Dropzone drag/drop + click + keyboard activation
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('fileInput');

  dropzone.addEventListener('click', () => fileInput.click());
  dropzone.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      fileInput.click();
    }
  });
  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('dragover');
  });
  dropzone.addEventListener('dragleave', () => {
    dropzone.classList.remove('dragover');
  });
  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    addFiles([...e.dataTransfer.files]);
  });

  fileInput.addEventListener('change', (e) => {
    addFiles([...e.target.files]);
    e.target.value = '';
  });

  // Advanced options toggle
  const optionsToggle = document.getElementById('optionsToggle');
  optionsToggle.addEventListener('click', toggleOptions);
  optionsToggle.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      toggleOptions();
    }
  });

  // Convert button
  document.getElementById('convertBtn').addEventListener('click', startConversion);

  // Supported formats section tabs
  document.querySelectorAll('.fmt-tab').forEach((btn) => {
    btn.addEventListener('click', () => showFormats(btn.dataset.panel, btn));
  });

  // FAQ accordions
  document.querySelectorAll('.faq-item').forEach((item) => {
    item.addEventListener('click', () => toggleFaq(item));
    item.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        toggleFaq(item);
      }
    });
  });
}

// ───── Tab & File Queue Management ────────────────────────────
function switchTab(tab) {
  if (!FORMATS[tab]) return;
  revokeAllBlobUrls();
  state.activeTab = tab;
  state.files = [];
  state.selectedFormat = null;

  document.querySelectorAll('.tab-btn').forEach((btn) => {
    const isActive = btn.dataset.tab === tab;
    btn.classList.toggle('active', isActive);
    btn.setAttribute('aria-selected', String(isActive));
  });

  document.getElementById('fileInput').accept = FORMATS[tab].accept;
  document.getElementById('drop-hint').textContent = FORMATS[tab].hint;

  refreshFileQueueUI();
  hideProgress();
}

function addFiles(newFiles) {
  if (!newFiles.length) return;

  // Auto-switch category tab if user drops a single-type batch onto another tab
  const firstInfo = getFileTypeInfo(newFiles[0].name);
  const isGifOnVideo = state.activeTab === 'video' && newFiles[0].name.toLowerCase().endsWith('.gif');
  if (
    state.files.length === 0 &&
    firstInfo.type !== 'other' &&
    firstInfo.type !== state.activeTab &&
    !isGifOnVideo
  ) {
    switchTab(firstInfo.type);
    showToast(`Switched to ${FORMATS[firstInfo.type].label} converter`, 'info');
  }

  newFiles.forEach((file) => {
    if (!state.files.some((x) => x.name === file.name && x.size === file.size)) {
      state.files.push(file);
    }
  });

  refreshFileQueueUI();
}

function removeFile(index) {
  state.files.splice(index, 1);
  refreshFileQueueUI();
  if (state.files.length === 0) {
    hideProgress();
  }
}

function clearAllFiles() {
  revokeAllBlobUrls();
  state.files = [];
  state.selectedFormat = null;
  refreshFileQueueUI();
  hideProgress();
}

function refreshFileQueueUI() {
  renderFileList({ onRemoveFile: removeFile, onClearAll: clearAllFiles });
  const selector = document.getElementById('formatSelector');
  if (state.files.length > 0) {
    const wasHidden = selector.style.display === 'none';
    selector.style.display = 'block';
    renderFormatGrid(selectFormat);
    if (wasHidden) {
      renderOptionsPanel();
    }
  } else {
    selector.style.display = 'none';
  }
}

function selectFormat(fmt) {
  state.selectedFormat = fmt;
  document.querySelectorAll('.format-chip').forEach((chip) => {
    chip.classList.toggle('selected', chip.textContent.toLowerCase() === fmt);
  });
}

function toggleOptions() {
  const panel = document.getElementById('optionsPanel');
  const toggle = document.getElementById('optionsToggle');
  const isOpen = panel.classList.toggle('open');
  toggle.classList.toggle('options-open', isOpen);
  toggle.setAttribute('aria-expanded', String(isOpen));
}

function hideProgress() {
  document.getElementById('progressArea').style.display = 'none';
  document.getElementById('progressFiles').innerHTML = '';
}

// ───── Conversion Execution ───────────────────────────────────
async function startConversion() {
  if (!state.files.length) {
    showToast('Please add at least one file.', 'error');
    return;
  }
  if (!state.selectedFormat) {
    showToast('Please select an output format.', 'error');
    return;
  }

  revokeAllBlobUrls();

  const btn = document.getElementById('convertBtn');
  btn.disabled = true;
  btn.classList.add('loading');
  btn.querySelector('span').textContent = 'Converting…';

  document.getElementById('progressArea').style.display = 'block';
  const progressFiles = document.getElementById('progressFiles');
  progressFiles.innerHTML = '';

  state.files.forEach((file, i) => {
    const item = document.createElement('div');
    item.className = 'progress-item';
    item.id = `prog_${i}`;
    item.innerHTML = `
      <div class="progress-header">
        <span class="progress-name">${escHtml(file.name)}</span>
        <span class="progress-status converting" id="status_${i}">Uploading…</span>
      </div>
      <div class="progress-bar-wrap">
        <div class="progress-bar-fill" id="bar_${i}" style="width:0%"></div>
      </div>
      <div class="progress-actions" id="actions_${i}"></div>
    `;
    progressFiles.appendChild(item);
  });

  await Promise.all(state.files.map((file, i) => runSingleConversion(file, i)));

  btn.disabled = false;
  btn.classList.remove('loading');
  btn.querySelector('span').textContent = 'Convert Now';
}

async function runSingleConversion(file, index) {
  const bar = document.getElementById(`bar_${index}`);
  const statusEl = document.getElementById(`status_${index}`);
  const actionsEl = document.getElementById(`actions_${index}`);

  try {
    const { blob, outName } = await convertFileWithProgress({
      file,
      targetFormat: state.selectedFormat,
      category: state.activeTab,
      options: state.options,
      onProgress: (pct, label) => {
        if (bar) bar.style.width = `${pct}%`;
        if (statusEl && pct < 100) statusEl.textContent = label;
      },
    });

    const url = registerBlobUrl(URL.createObjectURL(blob));
    bar.style.width = '100%';
    statusEl.textContent = 'Done ✓';
    statusEl.className = 'progress-status done';

    actionsEl.innerHTML = `
      <a class="btn-download" href="${url}" download="${escHtml(outName)}">
        <i class="fa-solid fa-download"></i> Download ${escHtml(outName)}
      </a>
    `;
  } catch (err) {
    bar.style.width = '100%';
    bar.style.background = 'var(--error)';
    statusEl.textContent = 'Failed';
    statusEl.className = 'progress-status error';
    actionsEl.innerHTML = `<span class="progress-error-msg"><i class="fa-solid fa-circle-exclamation"></i> ${escHtml(err.message)}</span>`;
  }
}

// ───── Secondary Sections (Formats & FAQ) ─────────────────────
function showFormats(panelId, btn) {
  document.querySelectorAll('.fmt-panel').forEach((p) => p.classList.remove('active'));
  document.querySelectorAll('.fmt-tab').forEach((b) => {
    b.classList.remove('active');
    b.setAttribute('aria-selected', 'false');
  });
  document.getElementById(panelId)?.classList.add('active');
  btn.classList.add('active');
  btn.setAttribute('aria-selected', 'true');
}

function toggleFaq(item) {
  const isOpen = item.classList.toggle('open');
  item.setAttribute('aria-expanded', String(isOpen));
}
