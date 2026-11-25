"""
HctrConvert — Audio Conversion Service
───────────────────────────────────────
Handles all audio format conversions using FFmpeg.

SOFTWARE ENGINEERING PRINCIPLE: "Abstraction"
- Wraps the complexity of FFmpeg commands behind a clean async interface
- Preserves audio metadata tags (-map_metadata 0) while stripping non-audio
  cover streams (-map 0:a) that break container muxers like M4A/OGG/WAV
"""
from __future__ import annotations

from pathlib import Path

from app.core.logging import get_logger
from app.core.exceptions import InvalidTargetFormatError
from app.utils.dependencies import get_ffmpeg_path, run_cli_command

logger = get_logger(__name__)

LOSSLESS_FORMATS = {"flac", "wav", "aiff", "alac"}
OPUS_SAMPLE_RATES = {"8000", "12000", "16000", "24000", "48000"}


async def convert_audio(
    src: Path,
    dst: Path,
    target_format: str,
    bitrate: str = "192",
    sample_rate: str = "44100",
) -> Path:
    """
    Convert an audio file to the target format using FFmpeg.

    Args:
        src:            Path to source audio file
        dst:            Path for output audio file
        target_format:  Target format (e.g. "mp3", "flac", "wav")
        bitrate:        Audio bitrate in kbps (e.g. "192", "320")
        sample_rate:    Sample rate in Hz (e.g. "44100", "48000")

    Returns:
        Path to the converted file
    """
    if not bitrate.isdigit() or not (32 <= int(bitrate) <= 1500):
        raise InvalidTargetFormatError(f"Invalid audio bitrate: {bitrate}")
    if not sample_rate.isdigit() or not (8000 <= int(sample_rate) <= 192000):
        raise InvalidTargetFormatError(f"Invalid audio sample rate: {sample_rate}")

    ffmpeg = get_ffmpeg_path()
    effective_sr = sample_rate
    if target_format == "opus" and sample_rate not in OPUS_SAMPLE_RATES:
        effective_sr = "48000"

    cmd = [
        ffmpeg, "-y",
        "-i", str(src),
        "-map", "0:a",
        "-map_metadata", "0",
    ]
    if target_format not in LOSSLESS_FORMATS:
        cmd += ["-b:a", f"{bitrate}k"]
    cmd += ["-ar", effective_sr, str(dst)]

    logger.info(
        f"Converting audio: {src.name} → {target_format} "
        f"(bitrate={bitrate}k, sr={effective_sr})"
    )
    await run_cli_command(cmd, "FFmpeg")
    logger.info(f"Audio saved: {dst.name} ({dst.stat().st_size} bytes)")
    return dst
