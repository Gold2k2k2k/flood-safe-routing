"""
Traffic Camera & Real Flood Footage Frame Extractor.
Implements compliant backend adapters (http_snapshot, local_image, local_video)
and lightweight Pillow frame-delta filtering to conserve Gemini API quota.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any
import httpx
from PIL import Image, ImageChops

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent

_LAST_CAMERA_FRAMES: dict[str, bytes] = {}
_LAST_CAMERA_ANALYSES: dict[str, Any] = {}


def clear_camera_frame_cache() -> None:
    """Clear in-memory camera frame and analysis caches, e.g. for demo resets or tests."""
    _LAST_CAMERA_FRAMES.clear()
    _LAST_CAMERA_ANALYSES.clear()


def get_cached_camera_analysis(camera_id: str) -> Any | None:
    """Return the most recent cached FloodAnalysisResult for camera_id, if any."""
    return _LAST_CAMERA_ANALYSES.get(camera_id)


def record_camera_frame_analysis(
    camera_id: str, frame_bytes: bytes | None, analysis: Any
) -> None:
    """Store latest frame bytes and AI analysis result for frame-delta deduplication."""
    if frame_bytes:
        _LAST_CAMERA_FRAMES[camera_id] = frame_bytes
    _LAST_CAMERA_ANALYSES[camera_id] = analysis


def should_skip_unchanged_frame(
    camera_id: str,
    curr_bytes: bytes | None,
    threshold: float = 0.04,
    commit_frame: bool = True,
) -> bool:
    """
    Check if camera frame is virtually identical to the previous frame.
    If curr_bytes is None, returns False.
    If previous frame exists and delta < threshold, returns True (skip).
    Otherwise optionally caches curr_bytes and returns False (proceed).
    """
    if not curr_bytes:
        return False
    prev = _LAST_CAMERA_FRAMES.get(camera_id)
    if prev is not None:
        delta = compute_frame_delta(prev, curr_bytes)
        if delta < threshold:
            return True
    if commit_frame:
        _LAST_CAMERA_FRAMES[camera_id] = curr_bytes
    return False


def _looks_like_snapshot_endpoint(url: str) -> bool:
    """Return True only when URL explicitly points to a camera image/snapshot endpoint."""
    lower = url.lower().strip()
    if not lower.startswith(("http://", "https://")):
        return False
    image_exts = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
    if lower.split("?", 1)[0].endswith(image_exts):
        return True
    hints = ("snapshot", "frame", "capture", "still", "/img", "/image", "cam_img")
    return any(hint in lower for hint in hints)


def _build_synthetic_camera_frame(camera_meta: dict[str, Any]) -> bytes:
    """Generate a compact deterministic JPEG frame when local/snapshot assets are unavailable."""
    severity = int(camera_meta.get("default_severity_hint") or 0)
    palette = {
        0: (64, 110, 82),
        1: (132, 122, 68),
        2: (146, 98, 56),
        3: (128, 52, 52),
    }
    color = palette.get(severity, (100, 100, 100))
    buf = io.BytesIO()
    Image.new("RGB", (128, 72), color=color).save(buf, format="JPEG", quality=75)
    return buf.getvalue()


async def fetch_camera_snapshot(feed_url: str, timeout_sec: float = 2.5) -> bytes | None:
    """
    Download a single JPEG/PNG snapshot from a traffic camera HTTP endpoint.
    Returns None if the feed is unreachable or non-image so callers can degrade gracefully.
    """
    try:
        async with httpx.AsyncClient(timeout=timeout_sec, follow_redirects=True) as client:
            resp = await client.get(feed_url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "").lower()
            is_jpeg = resp.content[:2] == b"\xff\xd8"
            is_png = resp.content[:8] == b"\x89PNG\r\n\x1a\n"
            if "image" in content_type or is_jpeg or is_png:
                return resp.content
            logger.debug("Snapshot URL %s returned non-image content-type: %s", feed_url, content_type)
    except Exception as exc:
        logger.warning("Failed to fetch snapshot from %s: %s", feed_url, exc)
        return None
    return None


def load_local_frame(frame_path: str | Path) -> bytes | None:
    """Load a real flood frame from disk for deterministic stage demos."""
    p = Path(frame_path)
    if not p.is_absolute() and not p.exists():
        p = ROOT_DIR / p
    if p.exists() and p.is_file():
        return p.read_bytes()
    return None


def extract_frame_from_video(video_path_or_stream: str, frame_index: int = 0) -> bytes | None:
    """
    Sample a JPEG frame from a recorded flood clip or stream via OpenCV (optional dependency).
    """
    try:
        import cv2  # type: ignore
    except ImportError:
        logger.warning("opencv-python-headless not installed; video extraction unavailable.")
        return None

    cap = cv2.VideoCapture(video_path_or_stream)
    if not cap.isOpened():
        logger.warning("Could not open video/stream source: %s", video_path_or_stream)
        return None
    try:
        if frame_index > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = cap.read()
        if not ok or frame is None:
            return None
        ok_enc, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        return bytes(buf) if ok_enc else None
    finally:
        cap.release()


def compute_frame_delta(prev_bytes: bytes, curr_bytes: bytes) -> float:
    """
    Compute normalized mean pixel delta [0.0, 1.0] on 32x32 grayscale thumbnails.
    Used to skip redundant Gemini Vision calls on static camera snapshots.
    """
    try:
        with (
            Image.open(io.BytesIO(prev_bytes)) as img1,
            Image.open(io.BytesIO(curr_bytes)) as img2,
        ):
            g1 = img1.convert("L").resize((32, 32))
            g2 = img2.convert("L").resize((32, 32))
            diff = ImageChops.difference(g1, g2)
            if hasattr(diff, "get_flattened_data"):
                pixels = list(diff.get_flattened_data())
            else:
                pixels = list(diff.getdata())
            if not pixels:
                return 1.0
            return sum(pixels) / (len(pixels) * 255.0)
    except Exception as exc:
        logger.warning("Frame delta computation failed; treating frame as changed: %s", exc)
        return 1.0


async def extract_frame_for_camera(camera_meta: dict[str, Any]) -> tuple[bytes | None, str]:
    """
    Dispatch frame ingestion according to camera metadata adapter type.
    Returns (frame_bytes, frame_source_label).
    """
    local_image = camera_meta.get("local_image_path")
    if local_image:
        raw = load_local_frame(local_image)
        if raw:
            return raw, "local_image"

    local_video = camera_meta.get("local_video_path")
    if local_video:
        vp = Path(local_video)
        if not vp.is_absolute() and not vp.exists():
            vp = ROOT_DIR / vp
        raw = extract_frame_from_video(str(vp))
        if raw:
            return raw, "local_video"

    explicit_snapshot = camera_meta.get("snapshot_url")
    if explicit_snapshot:
        raw = await fetch_camera_snapshot(str(explicit_snapshot))
        if raw:
            return raw, "http_snapshot"

    feed_url = camera_meta.get("feed_url")
    if feed_url and _looks_like_snapshot_endpoint(str(feed_url)):
        raw = await fetch_camera_snapshot(str(feed_url))
        if raw:
            return raw, "http_snapshot"

    return _build_synthetic_camera_frame(camera_meta), "mock_fallback"
