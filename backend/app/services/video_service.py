"""
HctrConvert — Video Conversion Service
───────────────────────────────────────
Handles all video format conversions using FFmpeg.

SOFTWARE ENGINEERING PRINCIPLE: "Strategy Pattern"
- Different output formats need different codec, quality, and muxer flags
- Preserves metadata (-map_metadata 0) and ensures even dimensions + yuv420p
  pixel format for maximum player compatibility
"""
from __future__ import annotations

import re
from pathlib import Path

from app.core.logging import get_logger
from app.core.exceptions import InvalidTargetFormatError
from app.utils.dependencies import get_ffmpeg_path, run_cli_command

logger = get_logger(__name__)

# Codec strategy map: format → [video_codec_flags, audio_codec_flags]
CODEC_MAP: dict[str, list[str]] = {
    "mp4":  ["-c:v", "libx264",    "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart"],
    "mkv":  ["-c:v", "libx264",    "-pix_fmt", "yuv420p", "-c:a", "aac"],
    "webm": ["-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p", "-b:v", "0",   "-c:a", "libopus"],
    "ogv":  ["-c:v", "libtheora",  "-pix_fmt", "yuv420p", "-c:a", "libvorbis"],
    "avi":  ["-c:v", "mpeg4",      "-pix_fmt", "yuv420p", "-c:a", "libmp3lame"],
    "mov":  ["-c:v", "libx264",    "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart"],
    "wmv":  ["-c:v", "wmv2",       "-pix_fmt", "yuv420p", "-c:a", "wmav2"],
    "flv":  ["-c:v", "libx264",    "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "44100"],
    "3gp":  ["-c:v", "libx264",    "-pix_fmt", "yuv420p", "-c:a", "aac"],
    "ts":   ["-c:v", "libx264",    "-pix_fmt", "yuv420p", "-c:a", "aac"],
}

CRF_FORMATS = {"mp4", "mkv", "webm", "mov", "flv", "3gp", "ts"}
QV_31_FORMATS = {"avi", "wmv"}
QV_THEORA_FORMATS = {"ogv"}

# GIF needs a special filter chain for high-quality palette generation
GIF_FILTER = "split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
RESOLUTION_RE = re.compile(r"^\d{2,5}x\d{2,5}$")


async def convert_video(
    src: Path,
    dst: Path,
    target_format: str,
    resolution: str = "original",
    fps: str = "original",
    crf: int = 23,
) -> Path:
    """
    Convert a video file to the target format using FFmpeg.

    Args:
        src:            Path to source video
        dst:            Path for output video
        target_format:  Target format (e.g. "mp4", "webm", "gif")
        resolution:     Target resolution "WxH" or "original"
        fps:            Target frame rate or "original"
        crf:            Quality factor 0-51 (lower = better quality)

    Returns:
        Path to the converted file
    """
    if resolution != "original" and not RESOLUTION_RE.match(resolution):
        raise InvalidTargetFormatError(f"Invalid video resolution: {resolution}")
    if fps != "original" and (not fps.isdigit() or not (1 <= int(fps) <= 240)):
        raise InvalidTargetFormatError(f"Invalid video frame rate: {fps}")

    ffmpeg = get_ffmpeg_path()
    clamped_crf = max(0, min(51, crf))
    cmd = [ffmpeg, "-y", "-i", str(src), "-map_metadata", "0"]

    if target_format == "gif":
        gif_filters = []
        if fps != "original":
            gif_filters.append(f"fps={fps}")
        if resolution != "original":
            gif_filters.append(f"scale={resolution.replace('x', ':')}:flags=lanczos")
        prefix = f"{','.join(gif_filters)}," if gif_filters else ""
        cmd += ["-vf", f"{prefix}{GIF_FILTER}", "-loop", "0"]
    else:
        cmd += CODEC_MAP.get(target_format, ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac"])

        if target_format in CRF_FORMATS:
            cmd += ["-crf", str(clamped_crf)]
        elif target_format in QV_31_FORMATS:
            qv = max(1, min(31, round(1 + (clamped_crf / 51) * 30)))
            cmd += ["-q:v", str(qv)]
        elif target_format in QV_THEORA_FORMATS:
            qv = max(0, min(10, round(10 - (clamped_crf / 51) * 10)))
            cmd += ["-q:v", str(qv)]

        if resolution != "original":
            w_str, h_str = resolution.split("x")
            even_w = max(2, (int(w_str) // 2) * 2)
            even_h = max(2, (int(h_str) // 2) * 2)
            cmd += ["-vf", f"scale={even_w}:{even_h}"]
        else:
            # Ensure even width/height for all yuv420p video encoders (x264, wmv2, mpeg4, theora)
            cmd += ["-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2"]

        if fps != "original":
            cmd += ["-r", fps]

    cmd.append(str(dst))

    logger.info(
        f"Converting video: {src.name} → {target_format} "
        f"(res={resolution}, fps={fps}, crf={clamped_crf})"
    )
    await run_cli_command(cmd, "FFmpeg")
    logger.info(f"Video saved: {dst.name} ({dst.stat().st_size} bytes)")
    return dst
