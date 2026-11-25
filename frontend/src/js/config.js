/* ============================================================
   HctrConvert — Frontend Configuration & Format Matrix
   ============================================================ */

// Same-origin when served by FastAPI; port 8001 fallback for standalone dev servers
export const API_BASE = (
  window.location.protocol === 'file:' ||
  ['5500', '5173', '3000'].includes(window.location.port)
)
  ? 'http://localhost:8001'
  : '';

export const FORMATS = {
  document: {
    label: 'Document',
    icon: 'fa-regular fa-file-lines',
    accept: '.pdf,.docx,.doc,.odt,.rtf,.txt,.xlsx,.xls,.ods,.csv,.pptx,.ppt,.odp,.html,.md,.epub',
    hint: 'Supports PDF, DOCX, ODT, RTF, XLSX, CSV, PPTX, TXT, HTML, MD, EPUB',
    outputs: ['pdf', 'docx', 'odt', 'rtf', 'txt', 'xlsx', 'ods', 'csv', 'pptx', 'odp', 'html'],
    options: [
      { id: 'page_size', label: 'Page Size (PDF)', type: 'select', default: 'A4', choices: ['A4', 'A3', 'Letter', 'Legal'] },
    ],
  },
  image: {
    label: 'Image',
    icon: 'fa-regular fa-image',
    accept: '.jpg,.jpeg,.png,.gif,.bmp,.webp,.tiff,.tif,.avif,.ico,.svg,.heic,.heif,.psd,.eps,.tga,.pcx,.jxl,.qoi,.dds,.ppm',
    hint: 'Supports JPG, PNG, WebP, GIF, BMP, TIFF, AVIF, HEIC, SVG, JXL, PSD and more',
    outputs: ['jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp', 'tiff', 'avif', 'ico', 'tga', 'heic', 'jxl'],
    options: [
      { id: 'quality', label: 'Quality (1–100)', type: 'number', default: 90, min: 1, max: 100 },
      { id: 'width', label: 'Width (px, 0=auto)', type: 'number', default: 0, min: 0, max: 16384 },
      { id: 'height', label: 'Height (px, 0=auto)', type: 'number', default: 0, min: 0, max: 16384 },
    ],
  },
  audio: {
    label: 'Audio',
    icon: 'fa-solid fa-music',
    accept: '.mp3,.wav,.flac,.aac,.ogg,.opus,.m4a,.wma,.aiff,.aif,.ape,.wv,.mka,.au,.mp2',
    hint: 'Supports MP3, WAV, FLAC, AAC, OGG, OPUS, M4A, WMA, AIFF and more',
    outputs: ['mp3', 'wav', 'flac', 'aac', 'ogg', 'opus', 'm4a', 'wma', 'aiff'],
    options: [
      { id: 'bitrate', label: 'Bitrate (kbps)', type: 'select', default: '192', choices: ['64', '128', '192', '256', '320'] },
      { id: 'sample_rate', label: 'Sample Rate (Hz)', type: 'select', default: '44100', choices: ['22050', '44100', '48000', '96000'] },
    ],
  },
  video: {
    label: 'Video',
    icon: 'fa-solid fa-film',
    accept: '.mp4,.mkv,.avi,.mov,.wmv,.flv,.webm,.m4v,.3gp,.ts,.ogv,.mpg,.mpeg,.asf,.rmvb,.gif',
    hint: 'Supports MP4, MKV, AVI, MOV, WebM, WMV, FLV, 3GP, TS, OGV and more',
    outputs: ['mp4', 'mkv', 'avi', 'mov', 'webm', 'wmv', 'flv', '3gp', 'ts', 'ogv', 'gif'],
    options: [
      { id: 'resolution', label: 'Resolution', type: 'select', default: 'original', choices: ['original', '3840x2160', '1920x1080', '1280x720', '854x480', '640x360'] },
      { id: 'fps', label: 'Frame Rate (fps)', type: 'select', default: 'original', choices: ['original', '60', '30', '25', '24', '15'] },
      { id: 'crf', label: 'Quality (CRF 0–51)', type: 'number', default: 23, min: 0, max: 51 },
    ],
  },
};

export const EXTENSION_GROUPS = {
  document: ['pdf','docx','doc','odt','rtf','txt','xlsx','xls','ods','csv','pptx','ppt','odp','html','md','epub'],
  image:    ['jpg','jpeg','png','gif','bmp','webp','tiff','tif','avif','ico','svg','heic','heif','psd','eps','tga','pcx','jxl','qoi','dds','ppm'],
  audio:    ['mp3','wav','flac','aac','ogg','opus','m4a','wma','aiff','aif','ape','wv','mka','au','mp2'],
  video:    ['mp4','mkv','avi','mov','wmv','flv','webm','m4v','3gp','ts','ogv','mpg','mpeg','asf','rmvb'],
};

const DOC_WORD_TARGETS = new Set(['pdf', 'docx', 'odt', 'rtf', 'txt', 'html']);
const DOC_SHEET_TARGETS = new Set(['pdf', 'xlsx', 'ods', 'csv', 'html', 'docx', 'odt', 'rtf', 'txt']);
const DOC_SLIDE_TARGETS = new Set(['pdf', 'pptx', 'odp', 'html']);
const LIBREOFFICE_ONLY_EXTS = new Set(['doc', 'xls', 'ods', 'ppt', 'pptx', 'odp']);
const LIBREOFFICE_ONLY_TARGETS = new Set(['ods', 'pptx', 'odp']);

/**
 * Check whether `targetFmt` is compatible with all queued files on the active tab.
 * Returns `{ allowed: boolean, reason: string }`.
 */
export function getTargetCompatibility(activeTab, files, targetFmt, dependencies) {
  if (activeTab !== 'document' || !files.length) {
    return { allowed: true, reason: '' };
  }

  const hasLibreOffice = Boolean(dependencies?.libreoffice);

  for (const file of files) {
    const ext = file.name.split('.').pop().toLowerCase();

    if (!hasLibreOffice && (LIBREOFFICE_ONLY_EXTS.has(ext) || LIBREOFFICE_ONLY_TARGETS.has(targetFmt))) {
      if (ext !== targetFmt) {
        return {
          allowed: false,
          reason: `Converting .${ext} → .${targetFmt} requires LibreOffice installed`,
        };
      }
    }

    if (['xlsx', 'xls', 'ods', 'csv'].includes(ext)) {
      if (!DOC_SHEET_TARGETS.has(targetFmt)) {
        return { allowed: false, reason: `.${targetFmt.toUpperCase()} is not a spreadsheet/document export target for .${ext}` };
      }
    } else if (['pptx', 'ppt', 'odp'].includes(ext)) {
      if (!DOC_SLIDE_TARGETS.has(targetFmt)) {
        return { allowed: false, reason: `.${targetFmt.toUpperCase()} is not a presentation export target for .${ext}` };
      }
    } else {
      if (!DOC_WORD_TARGETS.has(targetFmt)) {
        return { allowed: false, reason: `.${targetFmt.toUpperCase()} is for spreadsheets/presentations, not .${ext} documents` };
      }
    }
  }

  return { allowed: true, reason: '' };
}
