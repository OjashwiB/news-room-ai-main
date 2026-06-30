from langchain.tools import tool
from typing import Optional
import logging
import requests
import json
import re
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime
from config.settings import settings

logger = logging.getLogger(__name__)

_PROMO_PATH = Path("./assets/promo_with_audio.mp4")
_OUTRO_PATH = Path("./assets/outro.mp4")
# Target resolution — match HeyGen's native output; promo/outro scale down to fit
_OUT_W, _OUT_H, _OUT_FPS = 1280, 720, 30


def _get_ffmpeg() -> str | None:
    """Return the FFmpeg executable path (system PATH or imageio-ffmpeg bundle)."""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return "ffmpeg"
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe:
            return exe
    except Exception:
        pass
    return None


def assemble_final_video(broadcast_path: Path) -> Path | None:
    """
    Assemble the final broadcast video:  [promo] + broadcast + [outro]
    Promo and outro are optional — each is included only if its file exists in ./assets/.
    All clips are scaled to _OUT_W × _OUT_H at _OUT_FPS (straight scale, no letterbox —
    all assets should be 16:9).
    Returns the path to the assembled file, or None if nothing to assemble / FFmpeg fails.
    """
    has_promo = _PROMO_PATH.exists()
    has_outro = _OUTRO_PATH.exists()

    if not has_promo and not has_outro:
        logger.info("[video_editor] No promo or outro found — skipping assembly")
        return None

    ffmpeg = _get_ffmpeg()
    if not ffmpeg:
        logger.warning("[video_editor] FFmpeg not found — skipping assembly")
        return None

    # Build ordered clip list: promo (opt) → broadcast → outro (opt)
    clips: list[Path] = []
    if has_promo:
        clips.append(_PROMO_PATH)
    clips.append(broadcast_path)
    if has_outro:
        clips.append(_OUTRO_PATH)

    n = len(clips)
    scale = f"scale={_OUT_W}:{_OUT_H},fps={_OUT_FPS},setsar=1"

    # Build filter_complex dynamically for n inputs
    parts = []
    for i in range(n):
        parts.append(f"[{i}:v]{scale}[v{i}]")
        parts.append(f"[{i}:a]aresample=44100,aformat=sample_fmts=fltp[a{i}]")
    stream_pairs = "".join(f"[v{i}][a{i}]" for i in range(n))
    parts.append(f"{stream_pairs}concat=n={n}:v=1:a=1[vout][aout]")
    filter_complex = ";".join(parts)

    out_path = broadcast_path.parent / f"final_{broadcast_path.stem}.mp4"
    cmd = [ffmpeg, "-y"]
    for clip in clips:
        cmd += ["-i", str(clip)]
    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(out_path),
    ]

    parts_desc = " + ".join(
        ("promo" if c == _PROMO_PATH else "outro" if c == _OUTRO_PATH else "broadcast")
        for c in clips
    )
    logger.info(f"[video_editor] Assembling: {parts_desc} → {out_path.name}")
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=600)
        if result.returncode != 0:
            logger.warning(
                f"[video_editor] FFmpeg assembly failed (rc={result.returncode}): "
                f"{result.stderr.decode(errors='replace')[-800:]}"
            )
            return None
        size = out_path.stat().st_size
        logger.info(f"[video_editor] Assembled final video ({size:,} bytes): {out_path.name}")
        return out_path
    except Exception as e:
        logger.warning(f"[video_editor] assemble_final_video error: {e}")
        return None


# Keep old name as alias so nothing else breaks
prepend_promo = assemble_final_video


def compose_foreground_layers(video_path: Path, layers: list) -> Path | None:
    """
    FFmpeg: composite n foreground overlay images/videos on top of the broadcast video.
    Preserves the original video duration and audio. Outputs to fg_{stem}.mp4 in the
    same directory. Returns the output path, or None if layers is empty or FFmpeg fails.
    """
    if not layers:
        return None

    ffmpeg = _get_ffmpeg()
    if not ffmpeg:
        logger.warning("[video_editor] FFmpeg not found — skipping foreground layers")
        return None

    _project_root = Path(__file__).resolve().parent.parent
    resolved: list[tuple] = []
    for l in layers:
        src = Path(l.source)
        if not src.is_absolute():
            src = _project_root / l.source
        if src.exists():
            resolved.append((l, src))
        else:
            logger.warning(f"[video_editor] Foreground layer file not found: {src}")

    if not resolved:
        logger.warning("[video_editor] No foreground layer files found — skipping")
        return None

    out_path = video_path.parent / f"fg_{video_path.stem}.mp4"

    cmd = [ffmpeg, "-y", "-i", str(video_path)]
    for layer, src in resolved:
        if src.suffix.lower() in (".mp4", ".mov", ".webm"):
            cmd += ["-stream_loop", "-1", "-i", str(src)]
        else:
            cmd += ["-loop", "1", "-i", str(src)]

    def _scale(layer) -> str:
        if layer.width and layer.height:
            return f"scale={layer.width}:{layer.height}"
        if layer.width:
            return f"scale={layer.width}:-2"
        if layer.height:
            return f"scale=-2:{layer.height}"
        return "scale=iw:ih"

    filter_parts = []
    prev = "0:v"
    for i, (layer, _) in enumerate(resolved, 1):
        s_label = f"s{i}"
        o_label = f"o{i}"
        filter_parts.append(f"[{i}:v]{_scale(layer)}[{s_label}]")
        filter_parts.append(f"[{prev}][{s_label}]overlay={layer.x}:{layer.y}[{o_label}]")
        prev = o_label

    cmd += [
        "-filter_complex", ";".join(filter_parts),
        "-map", f"[{prev}]",
        "-map", "0:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(out_path),
    ]

    layers_desc = ", ".join(src.name for _, src in resolved)
    logger.info(f"[video_editor] Compositing foreground layers: {layers_desc}")
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=600)
        if result.returncode != 0:
            logger.warning(
                f"[video_editor] Foreground layers FFmpeg failed (rc={result.returncode}): "
                f"{result.stderr.decode(errors='replace')[-800:]}"
            )
            return None
        size = out_path.stat().st_size
        logger.info(f"[video_editor] Foreground composite done ({size:,} bytes): {out_path.name}")
        return out_path
    except Exception as e:
        logger.warning(f"[video_editor] compose_foreground_layers error: {e}")
        return None


@tool
def download_video(
    url: str,
    filename: Optional[str] = None,
    directory: Optional[str] = None,
) -> str:
    """
    Download a video file from a URL and save it to disk.

    Args:
        url: The video URL to download
        filename: Output filename (auto-generated if not provided)
        directory: Save directory (defaults to ./output/media)

    Returns:
        Path to the saved file, or error message
    """
    save_dir = directory or settings.MEDIA_DIR
    Path(save_dir).mkdir(parents=True, exist_ok=True)

    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"anchor_video_{timestamp}.mp4"

    filepath = Path(save_dir) / filename

    try:
        logger.info(f"[download_video] Downloading from {url}")
        response = requests.get(url, stream=True, timeout=120)
        if not response.ok:
            return f"Error: HTTP {response.status_code} downloading video"

        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        size = filepath.stat().st_size
        logger.info(f"[download_video] Saved {filepath} ({size:,} bytes)")
        return str(filepath)

    except Exception as e:
        logger.error(f"[download_video] Error: {e}", exc_info=True)
        return f"Error downloading video: {str(e)}"


@tool
def extract_graphic_cues(script: str) -> str:
    """
    Parse a broadcast script and extract all [GRAPHIC: ...] cues.

    Args:
        script: The full broadcast script text

    Returns:
        JSON string with list of graphic cues in order
    """
    cues = re.findall(r'\[GRAPHIC:\s*([^\]]+)\]', script, re.IGNORECASE)
    logger.info(f"[extract_graphic_cues] Found {len(cues)} graphic cues")
    return json.dumps({"graphic_cues": cues, "count": len(cues)})


@tool
def save_video_package(
    package_data: str,
    directory: Optional[str] = None,
) -> str:
    """
    Save the video package metadata JSON to disk.

    Args:
        package_data: JSON string containing the video package metadata
        directory: Save directory (defaults to ./output/media)

    Returns:
        Path to saved package file, or error message
    """
    save_dir = directory or settings.MEDIA_DIR
    Path(save_dir).mkdir(parents=True, exist_ok=True)

    filepath = Path(save_dir) / "video_package.json"

    try:
        # Validate it's valid JSON
        data = json.loads(package_data)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info(f"[save_video_package] Saved {filepath}")
        return str(filepath)
    except json.JSONDecodeError as e:
        return f"Error: Invalid JSON — {str(e)}"
    except Exception as e:
        logger.error(f"[save_video_package] Error: {e}", exc_info=True)
        return f"Error saving package: {str(e)}"
