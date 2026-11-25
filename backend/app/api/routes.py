"""
HctrConvert — API Routes
────────────────────────
All HTTP endpoint definitions live here.

SOFTWARE ENGINEERING PRINCIPLE: "Thin controllers + Bounded Concurrency"
- Routes validate input, stream uploads safely, acquire a concurrency slot,
  delegate to single-responsibility services, and return RFC MIME responses.
"""
from __future__ import annotations

import asyncio
import mimetypes
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.exceptions import (
    ConversionError,
    FileTooLargeError,
    UnsupportedFormatError,
    InvalidTargetFormatError,
)
from app.models.schemas import (
    FileCategory,
    HealthResponse,
    SUPPORTED_FORMATS,
    INPUT_EXTENSIONS,
    detect_category,
)
from app.services.image_service import convert_image
from app.services.audio_service import convert_audio
from app.services.video_service import convert_video
from app.services.document_service import convert_document
from app.utils.file_utils import (
    generate_job_id,
    sanitize_filename,
    get_input_path,
    get_output_path,
    cleanup_files,
)
from app.utils.dependencies import (
    check_builtin_documents,
    check_ffmpeg,
    check_libreoffice,
)

logger = get_logger(__name__)

router = APIRouter()

UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MB
ALLOWED_PAGE_SIZES = {"A4", "A3", "Letter", "Legal"}

# Extra MIME types not always registered on minimal OS installations
EXTRA_MIME_TYPES = {
    "webp": "image/webp",
    "avif": "image/avif",
    "heic": "image/heic",
    "heif": "image/heif",
    "jxl":  "image/jxl",
    "opus": "audio/opus",
    "flac": "audio/flac",
    "m4a":  "audio/mp4",
    "mkv":  "video/x-matroska",
    "webm": "video/webm",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "odt":  "application/vnd.oasis.opendocument.text",
    "ods":  "application/vnd.oasis.opendocument.spreadsheet",
    "odp":  "application/vnd.oasis.opendocument.presentation",
}

_job_semaphore: asyncio.Semaphore | None = None


def _get_job_semaphore() -> asyncio.Semaphore:
    global _job_semaphore
    if _job_semaphore is None:
        _job_semaphore = asyncio.Semaphore(get_settings().MAX_CONCURRENT_JOBS)
    return _job_semaphore


def _guess_media_type(filename: str, target_fmt: str) -> str:
    if target_fmt in EXTRA_MIME_TYPES:
        return EXTRA_MIME_TYPES[target_fmt]
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


# ── Health Check ──────────────────────────────────────────────────
@router.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint reporting app status and engine readiness."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=settings.APP_VERSION,
        dependencies={
            "ffmpeg": check_ffmpeg(),
            "libreoffice": check_libreoffice(),
            "builtin_documents": check_builtin_documents(),
        },
    )


# ── Supported Formats ────────────────────────────────────────────
@router.get("/formats")
async def list_formats():
    """Return all supported output formats per category in UI order."""
    return {
        cat.value: sorted(fmts)
        for cat, fmts in SUPPORTED_FORMATS.items()
    }


@router.get("/formats/matrix")
async def format_matrix():
    """Return full input and output format capabilities per category."""
    return {
        cat.value: {
            "inputs": sorted(ext.lstrip(".") for ext in INPUT_EXTENSIONS[cat]),
            "outputs": sorted(SUPPORTED_FORMATS[cat]),
        }
        for cat in FileCategory
    }


# ── Main Convert Endpoint ────────────────────────────────────────
@router.post("/convert")
async def convert(
    file: UploadFile = File(...),
    target_format: str = Form(...),
    category: Optional[str] = Form(None),
    # Image options
    quality: int = Form(90, ge=1, le=100),
    width: int = Form(0, ge=0, le=16384),
    height: int = Form(0, ge=0, le=16384),
    # Audio options
    bitrate: str = Form("192"),
    sample_rate: str = Form("44100"),
    # Video options
    resolution: str = Form("original"),
    fps: str = Form("original"),
    crf: int = Form(23, ge=0, le=51),
    # Document options
    page_size: str = Form("A4"),
):
    """
    Upload a file and convert it to the target format.
    Streams upload chunks to disk, bounds concurrency, and deletes temp files after response.
    """
    settings = get_settings()
    job_id = generate_job_id()

    # ── 1. Validate input file & options ──────────────────────
    if not file.filename:
        raise UnsupportedFormatError("No filename provided.")

    if page_size not in ALLOWED_PAGE_SIZES:
        raise InvalidTargetFormatError(f"Invalid page size: {page_size}")

    safe_name = sanitize_filename(file.filename)
    ext = Path(safe_name).suffix.lower()

    ext_category = detect_category(ext)
    if ext_category is None:
        raise UnsupportedFormatError(f"Unsupported file type: {ext}")

    detected = ext_category
    if category:
        try:
            requested_cat = FileCategory(category)
            if requested_cat == ext_category or (
                ext == ".gif" and requested_cat == FileCategory.VIDEO
            ):
                detected = requested_cat
        except ValueError:
            pass

    # ── 2. Validate target format ─────────────────────────────
    target_fmt = target_format.lower().lstrip(".")
    if target_fmt not in SUPPORTED_FORMATS.get(detected, set()):
        raise InvalidTargetFormatError(
            f"Cannot convert {detected.value} to '{target_fmt}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_FORMATS[detected]))}"
        )

    # ── 3. Stream uploaded file to disk ───────────────────────
    input_path = get_input_path(job_id, ext)
    stem = Path(safe_name).stem
    output_name = f"{stem}.{target_fmt}"
    output_path = get_output_path(job_id, stem, target_fmt)

    total_bytes = 0
    try:
        with input_path.open("wb") as out_f:
            while chunk := await file.read(UPLOAD_CHUNK_SIZE):
                total_bytes += len(chunk)
                if total_bytes > settings.max_file_size_bytes:
                    raise FileTooLargeError(
                        f"File exceeds {settings.MAX_FILE_SIZE_MB} MB limit."
                    )
                out_f.write(chunk)

        if total_bytes == 0:
            raise UnsupportedFormatError("Uploaded file is empty.")

        logger.info(
            f"Job {job_id}: {safe_name} ({total_bytes} bytes) → {target_fmt}"
        )

        # ── 4. Dispatch under bounded concurrency ─────────────
        async with _get_job_semaphore():
            if detected == FileCategory.DOCUMENT:
                output_path = await convert_document(
                    input_path, output_path, target_fmt,
                    job_id=job_id, page_size=page_size,
                )
            elif detected == FileCategory.IMAGE:
                await convert_image(
                    input_path, output_path, target_fmt,
                    quality=quality, width=width, height=height,
                )
            elif detected == FileCategory.AUDIO:
                await convert_audio(
                    input_path, output_path, target_fmt,
                    bitrate=bitrate, sample_rate=sample_rate,
                )
            elif detected == FileCategory.VIDEO:
                await convert_video(
                    input_path, output_path, target_fmt,
                    resolution=resolution, fps=fps, crf=crf,
                )

        if not output_path.exists():
            raise ConversionError("Conversion produced no output file.")

    except Exception:
        cleanup_files(input_path, output_path)
        raise

    # ── 5. Return the file (auto-cleanup after response) ──────
    return FileResponse(
        path=str(output_path),
        filename=output_name,
        media_type=_guess_media_type(output_name, target_fmt),
        background=BackgroundTask(cleanup_files, input_path, output_path),
    )
