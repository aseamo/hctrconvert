# HctrConvert

> Universal file converter — Documents, Images, Audio, Video.

## 📁 Project Structure

```
file converter/
├── Dockerfile                   ← Multi-stage container build (Python + FFmpeg + LibreOffice)
├── .dockerignore                ← Lean Docker build context filter
├── docker-compose.yml           ← Local container orchestration
├── README.md                    ← Project documentation
├── frontend/
│   └── src/
│       ├── index.html           ← Semantic & accessible HTML5 UI
│       ├── css/style.css        ← Styling (Orange / Dark Blue / Black theme)
│       └── js/
│           ├── config.js        ← Format registry & target compatibility matrix
│           ├── state.js         ← Centralized state & Blob URL lifecycle
│           ├── api.js           ← XHR upload-progress & health API client
│           ├── ui.js            ← Pure DOM rendering helpers
│           └── app.js           ← Main ES module controller & event wiring
└── backend/
    ├── run.py                   ← Entry point (`python run.py`)
    ├── requirements.txt         ← Python dependencies
    ├── pytest.ini               ← Pytest configuration
    ├── .env.example             ← Environment variable template
    ├── app/
    │   ├── main.py              ← App factory, lifespan sweeper & static serving
    │   ├── api/
    │   │   └── routes.py        ← HTTP endpoints (`/health`, `/formats`, `/formats/matrix`, `/convert`)
    │   ├── core/
    │   │   ├── config.py        ← Centralized Pydantic Settings
    │   │   ├── exceptions.py    ← Custom error taxonomy (`HctrConvertError`)
    │   │   ├── logging.py       ← Structured logging setup
    │   │   └── middleware.py    ← Request ID, timing & security headers
    │   ├── models/
    │   │   └── schemas.py       ← Enums, format registries, Pydantic schemas
    │   ├── services/
    │   │   ├── document_service.py ← Layout-preserving doc orchestrator
    │   │   ├── doc_renderers.py ← PDF, Pandoc, PyMuPDF Story & table renderers
    │   │   ├── image_service.py ← Fidelity-preserving image engine (Pillow, SVG, JXL, HEIC, EXIF, animations)
    │   │   ├── audio_service.py ← Metadata-preserving audio engine (FFmpeg)
    │   │   └── video_service.py ← Even-scaled yuv420p video engine (FFmpeg)
    │   └── utils/
    │       ├── file_utils.py    ← Path sanitization, job paths & stale temp sweeper
    │       └── dependencies.py  ← Tool discovery & timeout-enforced CLI runner
    └── tests/
        └── test_api.py          ← Integration & unit test suite
```

---

## 🚀 Quick Start

### Option A: Local Python Development

#### 1. Install Python Dependencies

```bash
cd backend
pip install -r requirements.txt
```

#### 2. System Dependencies (Optional for Legacy/ODF Documents)

`pip install -r requirements.txt` automatically includes **Pillow** (images), **imageio-ffmpeg** (bundled FFmpeg for audio & video), and a **built-in Python document converter** (`PDF`, `DOCX`, `XLSX`, `CSV`, `TXT`, `HTML`).

| Tool | Purpose | Download |
|------|---------|----------|
| **FFmpeg** *(bundled automatically)* | Audio & video conversion (uses `imageio-ffmpeg` fallback if not on `PATH`) | https://ffmpeg.org/download.html |
| **LibreOffice** *(optional)* | Needed only for legacy/ODF/presentation formats (`.doc`, `.odt`, `.rtf`, `.ods`, `.ppt`, `.pptx`, `.odp`, `.epub`) | https://www.libreoffice.org/download/ |

> **Windows:** `winget install TheDocumentFoundation.LibreOffice` installs LibreOffice cleanly; HctrConvert auto-detects it.

#### 3. Start the Server

```bash
cd backend
python run.py
```

Or with hot-reload:

```bash
cd backend
uvicorn app.main:app --reload --port 8001
```

Then open **http://localhost:8001** in your browser (FastAPI serves both the frontend UI and the API).
Interactive API docs are available at **http://localhost:8001/docs**.

---

### Option B: Docker (Includes FFmpeg & LibreOffice)

```bash
docker compose up --build
```

Then open **http://localhost:8001**.

---

## 🧪 Running Tests

```bash
cd backend
python -m pytest -v
```

---

## 🔌 API Reference

### `GET /health`
Returns server status, version, and availability of `ffmpeg` and `libreoffice`.

### `GET /formats`
Returns supported output formats grouped by category (`document`, `image`, `audio`, `video`).

### `POST /convert`
Converts an uploaded file to the target format and streams the result back as a download.

| Field | Type | Description |
|-------|------|-------------|
| `file` | File | The file to convert |
| `target_format` | string | Target extension (e.g. `webp`, `mp3`, `pdf`) |
| `category` | string | Optional: `document`, `image`, `audio`, `video` |
| `quality` | int | Image quality 1–100 (default: `90`) |
| `width` / `height` | int | Resize dimensions (`0` = auto) |
| `bitrate` | string | Audio bitrate kbps (default: `192`) |
| `sample_rate` | string | Audio sample rate Hz (default: `44100`) |
| `resolution` | string | Video resolution (default: `original`) |
| `fps` | string | Video frame rate (default: `original`) |
| `crf` | int | Video CRF quality 0–51 (default: `23`) |
| `page_size` | string | PDF page size (default: `A4`) |

---

## 🛡️ Security & Privacy
- Filenames are sanitized against path traversal before writing to disk
- Files are stored temporarily in `backend/tmp/` using unique job IDs
- Input and output files are deleted automatically after the response is sent (or on error)
- External tools are invoked via argument arrays (no shell injection)

---

## 🗺️ Roadmap
- [x] Layered FastAPI backend with Pydantic validation & structured logging
- [x] Docker & Docker Compose deployment
- [x] Automated unit & integration tests
- [ ] Drag-and-drop batch ZIP download
- [ ] API key + rate limiting
- [ ] WebSocket progress streaming
- [ ] More format support (3D, CAD, fonts)
