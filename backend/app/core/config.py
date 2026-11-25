"""
HctrConvert — Configuration Module
───────────────────────────────────
Centralizes ALL configurable values into one place using Pydantic Settings.
Values can be overridden via environment variables or a .env file.

SOFTWARE ENGINEERING PRINCIPLE: "Configuration as Code"
- Never scatter magic numbers/strings across your codebase
- Every tunable value lives here
- Environment variables override defaults (12-Factor App)
"""
from __future__ import annotations

from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    """Application configuration — loaded once, cached, injected everywhere."""

    # ── App metadata ──────────────────────────────────────────────
    APP_NAME: str = "HctrConvert"
    APP_VERSION: str = "1.1.0"
    DEBUG: bool = False

    # ── Server ────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8001
    CORS_ORIGINS: list[str] = ["*"]  # Restrict in production!

    # ── File handling & concurrency ───────────────────────────────
    MAX_FILE_SIZE_MB: int = 500
    UPLOAD_DIR: Path = Path("tmp/uploads")
    OUTPUT_DIR: Path = Path("tmp/outputs")
    CLEANUP_AFTER_SECONDS: int = 3600       # Sweep orphaned files older than 1h
    CONVERSION_TIMEOUT_SECONDS: int = 300   # Kill hung CLI jobs after 5m
    MAX_CONCURRENT_JOBS: int = 4            # Bound parallel CPU-heavy jobs

    # ── Conversion defaults ───────────────────────────────────────
    DEFAULT_IMAGE_QUALITY: int = 90
    DEFAULT_AUDIO_BITRATE: str = "192"
    DEFAULT_AUDIO_SAMPLE_RATE: str = "44100"
    DEFAULT_VIDEO_CRF: int = 23

    # ── External tools ────────────────────────────────────────────
    FFMPEG_PATH: str = "ffmpeg"           # or full path
    LIBREOFFICE_PATH: str = ""            # auto-detect if empty

    # ── Logging ───────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

    @property
    def max_file_size_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024

    @field_validator("UPLOAD_DIR", "OUTPUT_DIR", mode="after")
    @classmethod
    def ensure_dirs_exist(cls, v: Path) -> Path:
        v.mkdir(parents=True, exist_ok=True)
        return v

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


@lru_cache()
def get_settings() -> Settings:
    """
    Singleton pattern — settings are loaded once and cached.
    Call get_settings() anywhere you need config.
    """
    return Settings()
