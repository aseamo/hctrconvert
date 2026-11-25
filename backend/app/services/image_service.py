"""
HctrConvert — Image Conversion Service
───────────────────────────────────────
Handles all image format conversions using Pillow + PyMuPDF (for SVG).

SOFTWARE ENGINEERING PRINCIPLE: "Preserve Fidelity"
- Applies EXIF orientation before processing so rotated photos stay upright
- Preserves ICC color profiles and normalized EXIF metadata where supported
- Preserves all animation frames and timing when converting animated GIF/WebP/APNG
- Renders vector SVG inputs cleanly via PyMuPDF
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.logging import get_logger
from app.core.exceptions import ConversionError, DependencyMissingError

logger = get_logger(__name__)

# Formats that do not support alpha transparency in Pillow
OPAQUE_FORMATS = {"JPEG", "BMP", "EPS", "PDF"}
ANIMATED_TARGET_FORMATS = {"GIF", "WEBP", "PNG", "TIFF"}

# Extension → Pillow format name overrides
FORMAT_MAP = {
    "jpg": "JPEG",
    "jpeg": "JPEG",
    "heic": "HEIF",
    "heif": "HEIF",
}


async def convert_image(
    src: Path,
    dst: Path,
    target_format: str,
    quality: int = 90,
    width: int = 0,
    height: int = 0,
) -> Path:
    """
    Convert an image file to the target format while preserving metadata,
    ICC color profiles, orientation, and animation frames.
    """
    try:
        from PIL import Image, ImageOps, ImageSequence
    except ImportError:
        raise DependencyMissingError(
            "Pillow not installed. Run: pip install Pillow pillow-heif pillow-jxl-plugin"
        )

    _register_plugins()

    def _do_convert():
        logger.info(f"Converting image: {src.name} → {target_format}")
        pil_format = FORMAT_MAP.get(target_format.lower(), target_format.upper())

        if src.suffix.lower() == ".svg":
            img = _open_svg_as_image(src, width=width, height=height)
            try:
                _save_single_image(img, dst, pil_format, quality, width, height, Image, ImageOps)
            finally:
                img.close()
        else:
            with Image.open(src) as img:
                is_animated = getattr(img, "is_animated", False) and getattr(img, "n_frames", 1) > 1
                if is_animated and pil_format in ANIMATED_TARGET_FORMATS:
                    _save_animated_image(img, dst, pil_format, quality, width, height, Image, ImageSequence)
                else:
                    _save_single_image(img, dst, pil_format, quality, width, height, Image, ImageOps)

        logger.info(f"Image saved: {dst.name} ({dst.stat().st_size} bytes)")

    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, _do_convert)
    except DependencyMissingError:
        raise
    except Exception as e:
        raise ConversionError(f"Image conversion failed: {e}") from e

    return dst


def _open_svg_as_image(src: Path, width: int, height: int):
    """Rasterize an SVG vector file into a crisp RGBA Pillow Image using PyMuPDF."""
    try:
        import pymupdf
        from PIL import Image
    except ImportError:
        raise DependencyMissingError("PyMuPDF is required to convert SVG files. Run: pip install PyMuPDF")

    doc = pymupdf.open(str(src))
    try:
        page = doc[0]
        rect = page.rect
        scale_x = (width / rect.width) if width > 0 and rect.width > 0 else 2.0
        scale_y = (height / rect.height) if height > 0 and rect.height > 0 else scale_x
        if width == 0 and height > 0 and rect.height > 0:
            scale_x = scale_y
        matrix = pymupdf.Matrix(scale_x, scale_y)
        pix = page.get_pixmap(matrix=matrix, alpha=True)
        return Image.frombytes("RGBA", (pix.width, pix.height), pix.samples)
    finally:
        doc.close()


def _save_single_image(img, dst: Path, pil_format: str, quality: int, width: int, height: int, Image, ImageOps) -> None:
    """Convert and save a single-frame image while preserving EXIF & ICC profile."""
    icc_profile = img.info.get("icc_profile")
    exif_bytes = None
    try:
        exif_obj = img.getexif()
        img = ImageOps.exif_transpose(img)
        if exif_obj and len(exif_obj) > 0:
            exif_obj[0x0112] = 1  # Orientation is now baked into pixels
            exif_bytes = exif_obj.tobytes()
    except Exception:
        img = ImageOps.exif_transpose(img)

    transparency_formats = {"PNG", "GIF", "WEBP", "TGA", "ICO", "TIFF", "AVIF", "HEIF", "JXL"}
    if img.mode not in ("RGB", "RGBA", "L", "P"):
        target_mode = "RGBA" if pil_format in transparency_formats else "RGB"
        img = img.convert(target_mode)

    if width > 0 or height > 0:
        orig_w, orig_h = img.size
        new_w = max(1, width or int(orig_w * (height / orig_h)))
        new_h = max(1, height or int(orig_h * (width / orig_w)))
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        logger.info(f"Resized: {orig_w}x{orig_h} → {new_w}x{new_h}")

    if pil_format in OPAQUE_FORMATS and img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGB")

    save_kwargs: dict = {}
    if pil_format in ("JPEG", "WEBP", "AVIF", "HEIF", "JXL"):
        save_kwargs["quality"] = max(1, min(100, quality))
    if pil_format == "PNG":
        save_kwargs["optimize"] = True
    if icc_profile and pil_format in ("JPEG", "PNG", "WEBP", "TIFF", "AVIF", "HEIF"):
        save_kwargs["icc_profile"] = icc_profile
    if exif_bytes and pil_format in ("JPEG", "PNG", "WEBP", "TIFF"):
        save_kwargs["exif"] = exif_bytes

    img.save(dst, format=pil_format, **save_kwargs)


def _save_animated_image(img, dst: Path, pil_format: str, quality: int, width: int, height: int, Image, ImageSequence) -> None:
    """Preserve all frames, durations, and loop count for animated images."""
    frames = []
    durations = []
    loop_count = img.info.get("loop", 0)

    for frame in ImageSequence.Iterator(img):
        durations.append(frame.info.get("duration", img.info.get("duration", 100)))
        fr = frame.convert("RGBA")
        if width > 0 or height > 0:
            orig_w, orig_h = fr.size
            new_w = max(1, width or int(orig_w * (height / orig_h)))
            new_h = max(1, height or int(orig_h * (width / orig_w)))
            fr = fr.resize((new_w, new_h), Image.Resampling.LANCZOS)
        frames.append(fr)

    save_kwargs: dict = {
        "save_all": True,
        "append_images": frames[1:],
        "duration": durations,
        "loop": loop_count,
    }
    if pil_format == "WEBP":
        save_kwargs["quality"] = max(1, min(100, quality))

    frames[0].save(dst, format=pil_format, **save_kwargs)


def _register_plugins():
    """Register optional Pillow plugins for HEIC/HEIF and JPEG XL (JXL) support."""
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except ImportError:
        pass
    try:
        import pillow_jxl  # noqa: F401
    except ImportError:
        pass
