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


def clear_camera_frame_cache() -> None:
    """Clear in-memory camera frame cache, e.g. for demo resets or tests."""
    _LAST_CAMERA_FRAMES.clear()


def should_skip_unchanged_frame(
    camera_id: str,
    curr_bytes: bytes | None,
    threshold: float = 0.04,
) -> bool:
    """
    Check if camera frame is virtually identical to the previous frame.
    If curr_bytes is None, returns False.
    If previous frame exists and delta < threshold, returns True (skip).
    Otherwise caches curr_bytes and returns False (proceed).
    """
    if not curr_bytes:
        return False
    prev = _LAST_CAMERA_FRAMES.get(camera_id)
    if prev is not None:
        delta = compute_frame_delta(prev, curr_bytes)
        if delta < threshold:
            return True
    _LAST_CAMERA_FRAMES[camera_id] = curr_bytes
    return False


async def fetch_camera_snapshot(feed_url: str, timeout_sec: float = 8.0) -> bytes | None:
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
    except Exception:
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

    snapshot_url = camera_meta.get("snapshot_url") or camera_meta.get("feed_url")
    if snapshot_url:
        raw = await fetch_camera_snapshot(str(snapshot_url))
        if raw:
            return raw, "http_snapshot"

    return None, "mock_fallback"
