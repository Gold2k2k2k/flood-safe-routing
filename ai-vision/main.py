"""
Internal FastAPI ASGI entrypoint for the `ai-vision` Vercel service.
Receives internal service-to-service requests from `backend` via the `AI_VISION_URL` binding.
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.analyzer import _is_real_key, analyze_flood_image_async
from src.camera_extractor import (
    clear_camera_frame_cache,
    extract_frame_for_camera,
    get_cached_camera_analysis,
    record_camera_frame_analysis,
    should_skip_unchanged_frame,
)
from src.schemas import FloodAnalysisResult

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Flood-Safe Routing — Internal AI Vision Service",
    version="0.2.0",
)


class AnalyzeRequest(BaseModel):
    image_base64: str | None = None
    mime_type: str = "image/jpeg"
    mock_severity_hint: int = Field(default=2, ge=0, le=3)


class CameraPollSingleRequest(BaseModel):
    camera: dict[str, Any]
    mock_severity_hint: int = Field(default=2, ge=0, le=3)
    force_refresh: bool = False
    hint_explicitly_set: bool = False


class CameraPollSingleResponse(BaseModel):
    frame_source: str
    analysis: dict[str, Any]
    frame_delta_skipped: bool = False


@app.exception_handler(RuntimeError)
async def handle_runtime_error(_: Request, exc: RuntimeError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "ai-vision"}


@app.post("/analyze", response_model=FloodAnalysisResult)
async def analyze_endpoint(payload: AnalyzeRequest) -> FloodAnalysisResult:
    img_bytes: bytes | None = None
    if payload.image_base64:
        try:
            img_bytes = base64.b64decode(payload.image_base64)
        except Exception as exc:
            logger.warning("Failed to decode base64 payload in ai-vision /analyze: %s", exc)
            img_bytes = None

    return await analyze_flood_image_async(
        image_bytes=img_bytes,
        mime_type=payload.mime_type,
        mock_severity_hint=payload.mock_severity_hint,
    )


@app.post("/cameras/poll-item", response_model=CameraPollSingleResponse)
async def poll_camera_item_endpoint(
    payload: CameraPollSingleRequest,
) -> CameraPollSingleResponse:
    camera_id = str(payload.camera.get("camera_id", "unknown_cam"))
    frame_bytes, frame_source = await extract_frame_for_camera(payload.camera)

    cached_analysis = get_cached_camera_analysis(camera_id)
    gemini_configured = _is_real_key(os.getenv("GEMINI_API_KEY", ""))
    hint_changed_in_mock = (
        not gemini_configured
        and payload.hint_explicitly_set
        and cached_analysis is not None
        and payload.mock_severity_hint != cached_analysis.severity_level
    )

    if (
        not payload.force_refresh
        and cached_analysis is not None
        and not hint_changed_in_mock
        and should_skip_unchanged_frame(camera_id, frame_bytes, commit_frame=False)
    ):
        return CameraPollSingleResponse(
            frame_source=frame_source,
            analysis=cached_analysis.model_dump(),
            frame_delta_skipped=True,
        )

    analysis = await analyze_flood_image_async(
        image_bytes=frame_bytes,
        mock_severity_hint=payload.mock_severity_hint,
    )
    record_camera_frame_analysis(camera_id, frame_bytes, analysis)
    return CameraPollSingleResponse(
        frame_source=frame_source,
        analysis=analysis.model_dump(),
        frame_delta_skipped=False,
    )


@app.post("/cache/clear")
async def clear_cache_endpoint() -> dict[str, bool]:
    clear_camera_frame_cache()
    return {"cleared": True}
