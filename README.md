# HctrConvert

HctrConvert is a self-hosted web app for converting documents, images, audio, and video without stripping layout or metadata. The frontend is plain HTML, CSS, and ES modules (`frontend/src`), and the backend is a FastAPI server (`backend/`) that streams uploads to temporary job files, runs the conversion, and deletes both files once the download finishes.

## What it converts

- **Documents:** `PDF`, `DOCX`, `ODT`, `RTF`, `XLSX`, `CSV`, `HTML`, `MD`, `TXT`, and `EPUB` work out of the box via PyMuPDF, `pdf2docx`, Pandoc, and `openpyxl` while keeping headings, tables, fonts, and embedded images intact. Legacy Office and slide formats (`.doc`, `.xls`, `.ods`, `.ppt`, `.pptx`, `.odp`) use headless LibreOffice if it is installed on the machine.
- **Images:** `JPG`, `PNG`, `WebP`, `GIF`, `BMP`, `TIFF`, `AVIF`, `HEIC`, `SVG`, `JXL`, `ICO`, `TGA`, `PSD`, and `EPS` via Pillow and PyMuPDF. Preserves EXIF orientation, color profiles, and multi-frame `GIF`/`WebP` animations.
- **Audio:** `MP3`, `WAV`, `FLAC`, `AAC`, `OGG`, `OPUS`, `M4A`, `WMA`, and `AIFF` via FFmpeg (bundled automatically through `imageio-ffmpeg` if `ffmpeg` is not on your `PATH`), keeping ID3/metadata tags.
- **Video:** `MP4`, `MKV`, `WebM`, `MOV`, `AVI`, `WMV`, `FLV`, `3GP`, `TS`, `OGV`, and `GIF` via FFmpeg with optional resolution, frame rate, and CRF controls.

## Running locally

Requires Python 3.11+.

```bash
cd backend
pip install -r requirements.txt
python run.py
```

Open `http://localhost:8001` in your browser. FastAPI serves both the web interface and the API from the same port (default is `8001` rather than `8000` to avoid clashing with common local services).

If you also want `.doc`, `.xls`, `.ods`, or PowerPoint conversions locally, install [LibreOffice](https://www.libreoffice.org/download/) (`winget install TheDocumentFoundation.LibreOffice` on Windows) — the backend picks it up automatically.

### Running with Docker

If you prefer not to install system tools locally, the root `Dockerfile` packages Python, FFmpeg, and LibreOffice together:

```bash
docker compose up --build
```

Then visit `http://localhost:8001`.

## Configuration

Settings live in `backend/app/core/config.py` and can be overridden with environment variables or a `backend/.env` file (see `backend/.env.example`):

- `PORT` — Server port (default `8001`)
- `MAX_FILE_SIZE_MB` — Per-file upload cap (default `500`)
- `MAX_CONCURRENT_JOBS` — Max simultaneous conversions (default `4`)
- `CONVERSION_TIMEOUT_SECONDS` — Subprocess timeout per job (default `300`)
- `CORS_ORIGINS` — Allowed origins list when hosting the frontend on a separate domain

## API

Interactive OpenAPI docs are served at `/docs` while the server is running.

- `GET /health` — Server status and detected conversion engines
- `GET /formats` and `GET /formats/matrix` — Supported input/output extensions by category
- `POST /convert` — Multipart upload (`file`, `target_format`, plus optional format parameters like `quality`, `width`, `height`, `bitrate`, `sample_rate`, `resolution`, `fps`, `crf`, `page_size`); streams back the converted file

## Tests

```bash
cd backend
python -m pytest -v
```
