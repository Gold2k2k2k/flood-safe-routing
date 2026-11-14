"""
Client adapter for calling the internal `ai-vision` service.
- When `AI_VISION_URL` is injected at runtime by Vercel's service binding (or `vercel dev`),
  requests are sent over HTTP to the bound `ai-vision` service.
- When `AI_VISION_URL` is unset (standalone local uvicorn, CLI repro scripts, or unit tests),
  falls back cleanly to in-process calls into `ai-vision/src`.
"""

from __future__ import annotations

import base64
import logging
import sys
from typing import Any
from urllib.parse import urljoin

import httpx
from pydantic import BaseModel

from ..config import ROOT_DIR, settings

logger = logging.getLogger(__name__)


class VisionAnalysisPayload(BaseModel):
    flood_detected: bool
    severity_level: int
    visual_cue: str
    estimated_depth_cm: str
    passable_for_motorbike: bool
    confidence: float
    vision_model: str
    analyzed_at: str


def _resolve_service_url(path: str) -> str:
    base = settings.AI_VISION_URL.rstrip("/") + "/"
    return urljoin(base, path.lstrip("/"))


def _ensure_local_ai_vision_imports() -> tuple[Any, Any, Any, Any, Any, Any]:
    ai_vision_root = ROOT_DIR / "ai-vision"
    if str(ai_vision_root) not in sys.path:
        sys.path.insert(0, str(ai_vision_root))

    from src.analyzer import analyze_flood_image_async  # type: ignore
    from src.camera_extractor import (  # type: ignore
        clear_camera_frame_cache,
        extract_frame_for_camera,
        get_cached_camera_analysis,
        record_camera_frame_analysis,
        should_skip_unchanged_frame,
    )

    return (
        analyze_flood_image_async,
        clear_camera_frame_cache,
        extract_frame_for_camera,
        get_cached_camera_analysis,
        record_camera_frame_analysis,
        should_skip_unchanged_frame,
    )


def _raise_if_service_error(resp: httpx.Response) -> None:
    if resp.status_code == 503:
        try:
            detail = resp.json().get("detail", "AI Vision service unavailable (503).")
        except Exception:
            detail = resp.text or "AI Vision service unavailable (503)."
        raise RuntimeError(detail)
    resp.raise_for_status()


async def analyze_flood_image_bound(
    image_bytes: bytes | None = None,
    mime_type: str = "image/jpeg",
    mock_severity_hint: int = 2,
    http_transport: httpx.AsyncBaseTransport | None = None,
) -> VisionAnalysisPayload:
    if settings.AI_VISION_URL:
        encoded = base64.b64encode(image_bytes).decode("ascii") if image_bytes else None
        url = _resolve_service_url("/analyze")
        async with httpx.AsyncClient(timeout=20.0, transport=http_transport) as client:
            resp = await client.post(
                url,
                json={
                    "image_base64": encoded,
                    "mime_type": mime_type,
                    "mock_severity_hint": mock_severity_hint,
                },
            )
            _raise_if_service_error(resp)
            return VisionAnalysisPayload.model_validate(resp.json())

    analyze_fn, *_ = _ensure_local_ai_vision_imports()
    res = await analyze_fn(
        image_bytes=image_bytes,
        mime_type=mime_type,
        mock_severity_hint=mock_severity_hint,
    )
    return VisionAnalysisPayload.model_validate(res.model_dump())


async def poll_camera_frame_bound(
    camera_meta: dict[str, Any],
    effective_hint: int,
    force_refresh: bool = False,
    hint_explicitly_set: bool = False,
    http_transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[str, VisionAnalysisPayload, bool]:
    """
    Returns (frame_source, analysis_payload, frame_delta_skipped).
    """
    if settings.AI_VISION_URL:
        url = _resolve_service_url("/cameras/poll-item")
        async with httpx.AsyncClient(timeout=20.0, transport=http_transport) as client:
            resp = await client.post(
                url,
                json={
                    "camera": camera_meta,
                    "mock_severity_hint": effective_hint,
                    "force_refresh": force_refresh,
                    "hint_explicitly_set": hint_explicitly_set,
                },
            )
            _raise_if_service_error(resp)
            data = resp.json()
            return (
                str(data["frame_source"]),
                VisionAnalysisPayload.model_validate(data["analysis"]),
                bool(data.get("frame_delta_skipped", False)),
            )

    (
        analyze_fn,
        _,
        extract_frame_for_camera,
        get_cached_camera_analysis,
        record_camera_frame_analysis,
        should_skip_unchanged_frame,
    ) = _ensure_local_ai_vision_imports()

    camera_id = str(camera_meta.get("camera_id", "unknown_cam"))
    frame_bytes, frame_source = await extract_frame_for_camera(camera_meta)

    cached_analysis = get_cached_camera_analysis(camera_id)
    hint_changed_in_mock = (
        not settings.gemini_configured
        and hint_explicitly_set
        and cached_analysis is not None
        and effective_hint != cached_analysis.severity_level
    )

    if (
        not force_refresh
        and cached_analysis is not None
        and not hint_changed_in_mock
        and should_skip_unchanged_frame(camera_id, frame_bytes, commit_frame=False)
    ):
        return (
            frame_source,
            VisionAnalysisPayload.model_validate(cached_analysis.model_dump()),
            True,
        )

    analysis = await analyze_fn(
        image_bytes=frame_bytes,
        mock_severity_hint=effective_hint,
    )
    record_camera_frame_analysis(camera_id, frame_bytes, analysis)
    return (
        frame_source,
        VisionAnalysisPayload.model_validate(analysis.model_dump()),
        False,
    )


async def clear_vision_cache_bound(
    http_transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    if settings.AI_VISION_URL:
        url = _resolve_service_url("/cache/clear")
        try:
            async with httpx.AsyncClient(timeout=10.0, transport=http_transport) as client:
                resp = await client.post(url)
                _raise_if_service_error(resp)
        except Exception as exc:
            logger.warning("Failed to clear remote ai-vision cache at %s: %s", url, exc)
        return

    _, clear_camera_frame_cache, *_ = _ensure_local_ai_vision_imports()
    clear_camera_frame_cache()
