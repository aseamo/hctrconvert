# ── HctrConvert Dockerfile ───────────────────────────────────────
# Multi-stage build: install deps in a builder, then copy to slim runtime
#
# SOFTWARE ENGINEERING PRINCIPLE: "Infrastructure as Code"
# - The entire runtime environment is defined in this file
# - Anyone can reproduce the exact same setup with `docker build`
# - Multi-stage keeps the final image small

# ── Stage 1: Builder ─────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies for Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libjpeg-dev zlib1g-dev libwebp-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: Runtime ─────────────────────────────────────────────
FROM python:3.12-slim

LABEL maintainer="HctrConvert" \
      description="Universal file converter" \
      version="1.0.0"

WORKDIR /app

# Install runtime dependencies: FFmpeg + LibreOffice + OpenCV/PyMuPDF shared libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libreoffice-common libreoffice-writer libreoffice-calc libreoffice-impress \
    libjpeg62-turbo libwebp7 libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY backend/ /app/
COPY frontend/ /frontend/

# Create temp directories
RUN mkdir -p tmp/uploads tmp/outputs

# Non-root user for security
RUN useradd --create-home appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8001

# Health check (reads dynamic PORT injected by cloud hosts, defaults to 8001)
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://localhost:{os.getenv(\"PORT\", \"8001\")}/health')"

CMD ["python", "run.py"]
