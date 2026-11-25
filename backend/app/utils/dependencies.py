"""
HctrConvert — External Tool Checker & Subprocess Runner
─────────────────────────────────────────────────────
Verifies that FFmpeg (system or bundled via imageio-ffmpeg) and LibreOffice
are available and provides a single async subprocess runner shared across services.

SOFTWARE ENGINEERING PRINCIPLE: "Fail fast" & "DRY"
- Prefer system tools on PATH, fall back cleanly to bundled packages
- Give clear error messages about what's missing
- Share one subprocess execution helper across all CLI-backed services
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.exceptions import ConversionError, DependencyMissingError

logger = get_logger(__name__)


def check_ffmpeg() -> bool:
    """Return True if system FFmpeg or bundled imageio-ffmpeg is available."""
    try:
        get_ffmpeg_path()
        return True
    except DependencyMissingError:
        return False


def get_ffmpeg_path() -> str:
    """Get ffmpeg executable path (system PATH/config first, then imageio-ffmpeg)."""
    settings = get_settings()

    if Path(settings.FFMPEG_PATH).is_file():
        return settings.FFMPEG_PATH

    path = shutil.which(settings.FFMPEG_PATH)
    if path:
        logger.debug(f"Using system FFmpeg: {path}")
        return path

    try:
        import imageio_ffmpeg
        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled and Path(bundled).exists():
            logger.debug(f"Using bundled FFmpeg: {bundled}")
            return bundled
    except Exception:
        pass

    raise DependencyMissingError(
        "FFmpeg is not installed. Run `pip install imageio-ffmpeg` or install FFmpeg from "
        "https://ffmpeg.org/download.html (Windows: `winget install Gyan.FFmpeg`)."
    )


def check_libreoffice() -> bool:
    """Return True if LibreOffice/soffice is available."""
    try:
        find_libreoffice()
        return True
    except DependencyMissingError:
        return False


def check_builtin_documents() -> bool:
    """Return True if layout-preserving Python document libraries are installed."""
    try:
        import pymupdf     # noqa: F401
        import pdf2docx    # noqa: F401
        import pypandoc    # noqa: F401
        import docx        # noqa: F401
        import openpyxl    # noqa: F401
        return True
    except ImportError:
        return False


def find_libreoffice() -> str:
    """Locate LibreOffice executable, checking PATH and common locations."""
    settings = get_settings()

    # Check explicit config first
    if settings.LIBREOFFICE_PATH:
        if Path(settings.LIBREOFFICE_PATH).exists():
            return settings.LIBREOFFICE_PATH
        raise DependencyMissingError(
            f"Configured LibreOffice path not found: {settings.LIBREOFFICE_PATH}"
        )

    # Search PATH
    for name in ("soffice", "libreoffice"):
        path = shutil.which(name)
        if path:
            logger.info(f"LibreOffice found: {path}")
            return path

    # Windows default locations
    win_paths = [
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]
    for p in win_paths:
        if Path(p).exists():
            logger.info(f"LibreOffice found: {p}")
            return p

    raise DependencyMissingError(
        "LibreOffice not found. Install from https://www.libreoffice.org/download/ "
        "(Windows: `winget install TheDocumentFoundation.LibreOffice`)."
    )


async def run_cli_command(
    cmd: list[str],
    tool_name: str,
    timeout_seconds: int | None = None,
) -> bytes:
    """
    Execute an external CLI tool without a shell, enforcing a timeout so hung
    subprocesses are terminated instead of blocking workers indefinitely.
    """
    settings = get_settings()
    timeout = timeout_seconds or settings.CONVERSION_TIMEOUT_SECONDS

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
            await proc.communicate()
        except Exception:
            pass
        logger.error(f"{tool_name} timed out after {timeout}s")
        raise ConversionError(f"{tool_name} timed out after {timeout} seconds.")

    if proc.returncode != 0:
        error_msg = stderr.decode(errors="replace").strip()[-500:]
        logger.error(f"{tool_name} failed (exit {proc.returncode}): {error_msg}")
        raise ConversionError(f"{tool_name} error: {error_msg}")

    return stdout
