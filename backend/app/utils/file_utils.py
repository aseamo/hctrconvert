"""
HctrConvert — File Utilities
────────────────────────────
Helpers for file I/O, path sanitization, and orphan temp-file sweeping.

SOFTWARE ENGINEERING PRINCIPLE: "Defense in depth"
- Sanitize filenames to prevent path traversal attacks
- Generate unique job IDs to prevent collisions
- Clean up temp files on completion, on error, and via periodic stale sweeps
"""
from __future__ import annotations

import re
import time
import uuid
import shutil
from pathlib import Path
from contextlib import contextmanager
from typing import Generator

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def generate_job_id() -> str:
    """Generate a unique job identifier."""
    return uuid.uuid4().hex[:16]


def sanitize_filename(filename: str) -> str:
    """
    Strip dangerous characters from a filename.
    Prevents directory traversal and special char injection.
    """
    name = Path(filename).name
    name = re.sub(r"[^\w\-.]", "_", name)
    name = re.sub(r"\.{2,}", ".", name)
    name = re.sub(r"_{2,}", "_", name)
    return name or "unnamed"


def get_input_path(job_id: str, extension: str) -> Path:
    """Build the input file path for a conversion job."""
    settings = get_settings()
    return settings.UPLOAD_DIR / f"{job_id}{extension}"


def get_output_path(job_id: str, stem: str, target_format: str) -> Path:
    """Build the output file path for a conversion job."""
    settings = get_settings()
    return settings.OUTPUT_DIR / f"{job_id}_{stem}.{target_format}"


def cleanup_files(*paths: Path) -> None:
    """Silently delete files or directories, logging any errors."""
    for p in paths:
        try:
            if p.is_file():
                p.unlink()
                logger.debug(f"Cleaned up: {p}")
            elif p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
                logger.debug(f"Cleaned up dir: {p}")
        except Exception as e:
            logger.warning(f"Failed to clean up {p}: {e}")


def sweep_stale_temp_files(max_age_seconds: int | None = None) -> int:
    """
    Remove orphaned temporary files/directories older than `max_age_seconds`.
    Returns the number of removed entries.
    """
    settings = get_settings()
    ttl = settings.CLEANUP_AFTER_SECONDS if max_age_seconds is None else max_age_seconds
    cutoff = time.time() - ttl
    removed = 0

    for folder in (settings.UPLOAD_DIR, settings.OUTPUT_DIR):
        if not folder.exists():
            continue
        for entry in list(folder.iterdir()):
            try:
                if entry.stat().st_mtime <= cutoff:
                    cleanup_files(entry)
                    removed += 1
            except FileNotFoundError:
                continue
            except Exception as e:
                logger.warning(f"Stale sweep skipped {entry}: {e}")

    if removed:
        logger.info(f"Swept {removed} stale temporary item(s)")
    return removed


@contextmanager
def temp_file_context(*paths: Path) -> Generator[None, None, None]:
    """Context manager that cleans up temp files if an exception occurs."""
    try:
        yield
    except Exception:
        cleanup_files(*paths)
        raise
