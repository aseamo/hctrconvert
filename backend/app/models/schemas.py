"""
HctrConvert — Pydantic Models (Schemas)
───────────────────────────────────────
Request/response schemas for the API layer.

SOFTWARE ENGINEERING PRINCIPLE: "Contract-first design"
- Define data shapes BEFORE writing business logic
- Pydantic validates inputs automatically — no manual checking
- These schemas also generate OpenAPI docs for free
"""
from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


# ── Category Enum (ordered: document, image, audio, video) ────────
class FileCategory(str, Enum):
    DOCUMENT = "document"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"


# ── Supported formats per category ────────────────────────────────
SUPPORTED_FORMATS: dict[FileCategory, set[str]] = {
    FileCategory.DOCUMENT: {"pdf","docx","odt","rtf","txt","xlsx","ods","csv","pptx","odp","html"},
    FileCategory.IMAGE:    {"jpg","jpeg","png","webp","gif","bmp","tiff","avif","ico","tga","heic","heif","jxl","pdf","eps"},
    FileCategory.AUDIO:    {"mp3","wav","flac","aac","ogg","opus","m4a","wma","aiff"},
    FileCategory.VIDEO:    {"mp4","mkv","avi","mov","webm","wmv","flv","3gp","ts","ogv","gif"},
}

INPUT_EXTENSIONS: dict[FileCategory, set[str]] = {
    FileCategory.DOCUMENT: {".pdf",".docx",".doc",".odt",".rtf",".txt",".xlsx",".xls",
                            ".ods",".csv",".pptx",".ppt",".odp",".html",".md",".epub"},
    FileCategory.IMAGE:    {".jpg",".jpeg",".png",".gif",".bmp",".webp",".tiff",".tif",
                            ".avif",".ico",".svg",".heic",".heif",".psd",".eps",
                            ".tga",".pcx",".jxl",".qoi",".dds",".ppm"},
    FileCategory.AUDIO:    {".mp3",".wav",".flac",".aac",".ogg",".opus",".m4a",".wma",
                            ".aiff",".aif",".ape",".wv",".mka",".au",".mp2"},
    FileCategory.VIDEO:    {".mp4",".mkv",".avi",".mov",".wmv",".flv",".webm",".m4v",
                            ".3gp",".ts",".ogv",".mpg",".mpeg",".asf",".rmvb"},
}


def detect_category(extension: str) -> FileCategory | None:
    """Detect file category from its extension."""
    ext = extension.lower()
    for cat, exts in INPUT_EXTENSIONS.items():
        if ext in exts:
            return cat
    return None


# ── Response models ───────────────────────────────────────────────
class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    dependencies: dict[str, bool] = {}


class ErrorResponse(BaseModel):
    detail: str
    error_code: str | None = None


class ConversionResult(BaseModel):
    filename: str
    original_name: str
    size_bytes: int
    category: FileCategory
    source_format: str
    target_format: str
