/* ============================================================
   HctrConvert — Pure UI & DOM Rendering Helpers
   ============================================================ */

import { EXTENSION_GROUPS, FORMATS, getTargetCompatibility } from './config.js';
import { state } from './state.js';

export function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

export function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function getFileTypeInfo(filename) {
  const ext = filename.split('.').pop().toLowerCase();
  if (EXTENSION_GROUPS.document.includes(ext)) return { type: 'document', icon: 'fa-regular fa-file-lines', cls: 'document' };
  if (EXTENSION_GROUPS.image.includes(ext))    return { type: 'image',    icon: 'fa-regular fa-image',      cls: 'image' };
  if (EXTENSION_GROUPS.audio.includes(ext))    return { type: 'audio',    icon: 'fa-solid fa-music',        cls: 'audio' };
  if (EXTENSION_GROUPS.video.includes(ext))    return { type: 'video',    icon: 'fa-solid fa-film',         cls: 'video' };
  return { type: 'other', icon: 'fa-regular fa-file', cls: 'other' };
}

export function renderEngineStatus(deps, offline = false) {
  const container = document.getElementById('engineStatus');
  if (!container) return;

  if (offline) {
    container.innerHTML = `<span class="engine-pill partial"><i class="fa-solid fa-plug-circle-exclamation"></i> Backend offline — run <code>python run.py</code></span>`;
    return;
  }

  const docLabel = deps.libreoffice
    ? 'Docs: Full Suite (LibreOffice) ✓'
    : (deps.builtin_documents
        ? 'Docs: PDF · DOCX · ODT · RTF · XLSX · CSV · HTML · EPUB ✓'
        : 'Docs: Missing engine');
  const docClass = (deps.libreoffice || deps.builtin_documents) ? 'ready' : 'partial';
  const mediaLabel = deps.ffmpeg ? 'Audio & Video: FFmpeg ✓' : 'Audio & Video: FFmpeg missing';
  const mediaClass = deps.ffmpeg ? 'ready' : 'partial';

  container.innerHTML = `
    <span class="engine-pill ${docClass}"><i class="fa-solid ${docClass === 'ready' ? 'fa-check' : 'fa-triangle-exclamation'}"></i> ${docLabel}</span>
    <span class="engine-pill ready"><i class="fa-solid fa-check"></i> Images: Pillow + SVG/JXL ✓</span>
    <span class="engine-pill ${mediaClass}"><i class="fa-solid ${mediaClass === 'ready' ? 'fa-check' : 'fa-triangle-exclamation'}"></i> ${mediaLabel}</span>
  `;
}

export function renderFileList({ onRemoveFile, onClearAll }) {
  const list = document.getElementById('fileList');
  list.innerHTML = '';

  if (!state.files.length) return;

  if (state.files.length > 1) {
    const header = document.createElement('div');
    header.className = 'file-list-header';
    header.innerHTML = `
      <span>${state.files.length} files queued</span>
      <button type="button" class="clear-all-btn"><i class="fa-solid fa-trash-can"></i> Clear all</button>
    `;
    header.querySelector('.clear-all-btn').addEventListener('click', onClearAll);
    list.appendChild(header);
  }

  state.files.forEach((file, i) => {
    const info = getFileTypeInfo(file.name);
    const item = document.createElement('div');
    item.className = 'file-item';
    item.innerHTML = `
      <div class="file-icon ${info.cls}"><i class="${info.icon}"></i></div>
      <div class="file-info">
        <div class="file-name" title="${escHtml(file.name)}">${escHtml(file.name)}</div>
        <div class="file-size">${formatBytes(file.size)}</div>
      </div>
      <button type="button" class="file-remove" title="Remove file" aria-label="Remove ${escHtml(file.name)}">
        <i class="fa-solid fa-xmark"></i>
      </button>
    `;
    item.querySelector('.file-remove').addEventListener('click', () => onRemoveFile(i));
    list.appendChild(item);
  });
}

export function renderFormatGrid(onSelectFormat) {
  const grid = document.getElementById('formatGrid');
  grid.innerHTML = '';
  const tab = FORMATS[state.activeTab];

  // Clear selectedFormat if it became incompatible with newly added files
  if (state.selectedFormat) {
    const check = getTargetCompatibility(state.activeTab, state.files, state.selectedFormat, state.dependencies);
    if (!check.allowed) {
      state.selectedFormat = null;
    }
  }

  tab.outputs.forEach((fmt) => {
    const compat = getTargetCompatibility(state.activeTab, state.files, fmt, state.dependencies);
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'format-chip' + (state.selectedFormat === fmt ? ' selected' : '');
    chip.textContent = fmt.toUpperCase();
    chip.disabled = !compat.allowed;
    if (!compat.allowed) {
      chip.title = compat.reason;
    }
    chip.addEventListener('click', () => {
      if (compat.allowed) onSelectFormat(fmt);
    });
    grid.appendChild(chip);
  });
}

export function renderOptionsPanel() {
  const panel = document.getElementById('optionsPanel');
  panel.innerHTML = '';
  state.options = {};

  const tab = FORMATS[state.activeTab];
  tab.options.forEach((opt) => {
    const group = document.createElement('div');
    group.className = 'option-group';
    const label = document.createElement('label');
    label.htmlFor = `opt_${opt.id}`;
    label.textContent = opt.label;
    group.appendChild(label);

    let inputEl;
    if (opt.type === 'select') {
      inputEl = document.createElement('select');
      inputEl.className = 'option-input';
      inputEl.id = `opt_${opt.id}`;
      opt.choices.forEach((choice) => {
        const option = document.createElement('option');
        option.value = choice;
        option.textContent = choice;
        option.selected = choice === opt.default;
        inputEl.appendChild(option);
      });
    } else {
      inputEl = document.createElement('input');
      inputEl.type = 'number';
      inputEl.className = 'option-input';
      inputEl.id = `opt_${opt.id}`;
      inputEl.value = opt.default;
      if (opt.min !== undefined) inputEl.min = String(opt.min);
      if (opt.max !== undefined) inputEl.max = String(opt.max);
    }

    inputEl.addEventListener('change', (e) => {
      state.options[opt.id] = e.target.value;
    });

    group.appendChild(inputEl);
    panel.appendChild(group);
    state.options[opt.id] = opt.default;
  });
}

let toastTimeout;
export function showToast(message, type = 'info') {
  let toast = document.getElementById('toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'toast';
    toast.setAttribute('role', 'status');
    toast.setAttribute('aria-live', 'polite');
    toast.className = 'toast-banner';
    document.body.appendChild(toast);
  }

  const colors = {
    error: '#ef4444',
    success: '#22c55e',
    info: '#f97316',
  };

  toast.style.background = colors[type] || colors.info;
  toast.textContent = message;
  toast.style.display = 'block';

  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => {
    toast.style.display = 'none';
  }, 3500);
}
