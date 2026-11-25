/* ============================================================
   HctrConvert — Backend API Client (with real XHR upload progress)
   ============================================================ */

import { API_BASE } from './config.js';

export async function fetchHealth() {
  const resp = await fetch(`${API_BASE}/health`);
  if (!resp.ok) {
    throw new Error(`Health check failed (HTTP ${resp.status})`);
  }
  return resp.json();
}

/**
 * Upload and convert a single file with real upload progress reporting.
 * Upload phase reports 0..55%; server processing smoothly advances 55..92%;
 * completion jumps to 100%.
 */
export function convertFileWithProgress({ file, targetFormat, category, options, onProgress }) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_BASE}/convert`, true);
    xhr.responseType = 'blob';

    let processingTimer = null;
    let currentPct = 0;

    const report = (pct, label) => {
      currentPct = Math.max(currentPct, Math.min(100, pct));
      onProgress?.(currentPct, label);
    };

    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable && e.total > 0) {
        const uploadPct = Math.round((e.loaded / e.total) * 55);
        report(uploadPct, uploadPct < 55 ? 'Uploading…' : 'Processing…');
      }
    });

    xhr.upload.addEventListener('load', () => {
      report(58, 'Converting…');
      processingTimer = setInterval(() => {
        if (currentPct < 92) {
          report(currentPct + 3, 'Converting…');
        }
      }, 220);
    });

    xhr.addEventListener('load', async () => {
      clearInterval(processingTimer);

      if (xhr.status >= 200 && xhr.status < 300) {
        const disposition = xhr.getResponseHeader('Content-Disposition') || '';
        const match = disposition.match(/filename="?([^"]+)"?/);
        const outName = match ? match[1] : `converted.${targetFormat}`;
        report(100, 'Done ✓');
        resolve({ blob: xhr.response, outName });
        return;
      }

      // Parse JSON error response from Blob
      let detail = `HTTP ${xhr.status}`;
      try {
        const text = await xhr.response.text();
        const parsed = JSON.parse(text);
        if (parsed?.detail) detail = parsed.detail;
      } catch {
        // Keep HTTP status fallback
      }
      reject(new Error(detail));
    });

    xhr.addEventListener('error', () => {
      clearInterval(processingTimer);
      reject(new Error('Cannot reach backend server (start it with: python run.py)'));
    });

    xhr.addEventListener('abort', () => {
      clearInterval(processingTimer);
      reject(new Error('Conversion cancelled.'));
    });

    const formData = new FormData();
    formData.append('file', file);
    formData.append('target_format', targetFormat);
    formData.append('category', category);
    Object.entries(options).forEach(([k, v]) => formData.append(k, v));

    xhr.send(formData);
  });
}
