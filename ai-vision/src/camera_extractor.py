"""
Traffic Camera & Real Flood Footage Frame Extractor.
Fetches image snapshots from public camera feeds (e.g. camera.0511.vn) or local test frames
from the backend worker to avoid browser CORS restrictions.
"""

from __future__ import annotations

from pathlib import Path
import httpx


async def fetch_camera_snapshot(feed_url: str, timeout_sec: float = 8.0) -> bytes | None:
    """
    Download a single JPEG/PNG snapshot from a traffic camera HTTP endpoint.
    Returns None if the feed is unreachable so caller can handle gracefully.
    """
    try:
        async with httpx.AsyncClient(timeout=timeout_sec, follow_redirects=True) as client:
            resp = await client.get(feed_url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if "image" in content_type or resp.content[:2] == b"\xff\xd8":
                return resp.content
    except Exception:
        return None
    return None


def load_local_frame(frame_path: str | Path) -> bytes | None:
    """Load a real flood frame from disk for deterministic stage demos."""
    p = Path(frame_path)
    if p.exists() and p.is_file():
        return p.read_bytes()
    return None
