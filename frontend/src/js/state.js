/* ============================================================
   HctrConvert — Centralized Application State
   ============================================================ */

export const state = {
  activeTab: 'document',
  files: [],
  selectedFormat: null,
  options: {},
  dependencies: {
    ffmpeg: true,
    libreoffice: false,
    builtin_documents: true,
  },
  blobUrls: new Set(),
};

export function registerBlobUrl(url) {
  state.blobUrls.add(url);
  return url;
}

export function revokeAllBlobUrls() {
  for (const url of state.blobUrls) {
    URL.revokeObjectURL(url);
  }
  state.blobUrls.clear();
}
