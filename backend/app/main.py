"""
FastAPI Main Entrypoint for Flood-Safe Routing.
Implements all endpoints defined in docs/api-and-data-contract.md with non-blocking
async AI inference, strict RuntimeError -> 503 handling, frame-delta camera polling,
and stage demo lifecycle controls.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .config import settings
from .schemas import (
    CameraListResponse,
    CameraPollRequest,
    CameraPollResponse,
    CameraPollResultItem,
    CrowdsourcingReportRequest,
    CrowdsourcingReportResponse,
    FloodZoneDeleteResponse,
    FloodZoneItem,
    FloodZonesListResponse,
    HeatmapResponse,
    RouteRequest,
    RouteResponse,
)
from .services.ai_vision_client import (
    analyze_flood_image_bound,
    clear_vision_cache_bound,
    poll_camera_frame_bound,
)
from .services.firebase_service import (
    delete_flood_zone,
    get_active_flood_zones,
    get_cameras,
    get_heatmap_points,
    reset_flood_zones_to_sample,
    upsert_flood_zone,
)
from .services.routing_service import compute_safe_route

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Flood-Safe Routing API",
    description="Real-time AI Flood Detection (Gemini 3.8 Flash) & Dynamic Safe Rerouting (Google Maps Routes API + Firebase)",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RuntimeError)
async def handle_runtime_config_error(_: Request, exc: RuntimeError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


def _build_zone_from_analysis(
    *,
    event_id: str,
    source: str,
    camera_id: str | None,
    location_name: str,
    lat: float,
    lng: float,
    analysis: Any,
) -> FloodZoneItem | None:
    """
    Convert an AI FloodAnalysisResult into an active FloodZoneItem, applying the
    FLOOD_ALERT_THRESHOLD confidence guardrail so blurry/low-confidence frames
    do not falsely block roads with severity >= 2.
    """
    if analysis.severity_level < 1:
        return None

    low_conf = float(analysis.confidence) < settings.FLOOD_ALERT_THRESHOLD
    if low_conf and analysis.severity_level == 1:
        logger.info(
            "Skipping low-confidence minor flood report %s (confidence=%.2f < %.2f)",
            event_id,
            analysis.confidence,
            settings.FLOOD_ALERT_THRESHOLD,
        )
        return None

    effective_severity = analysis.severity_level
    effective_passable = analysis.passable_for_motorbike
    effective_cue = analysis.visual_cue
    if low_conf and effective_severity >= 2:
        logger.warning(
            "Downgrading low-confidence flood alert %s from level %d to 1 (confidence=%.2f < %.2f)",
            event_id,
            effective_severity,
            analysis.confidence,
            settings.FLOOD_ALERT_THRESHOLD,
        )
        effective_severity = 1
        effective_passable = True
        effective_cue = f"{analysis.visual_cue} (Cần xác minh thêm - độ tin cậy thấp)"

    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=settings.FLOOD_ZONE_TTL_MINUTES)
    return FloodZoneItem(
        event_id=event_id,
        source=source,
        camera_id=camera_id,
        location_name=location_name,
        lat=lat,
        lng=lng,
        radius_meters=120.0,
        severity_level=effective_severity,
        visual_cue=effective_cue,
        estimated_depth_cm=analysis.estimated_depth_cm,
        passable_for_motorbike=effective_passable,
        confidence=analysis.confidence,
        vision_model=analysis.vision_model,
        status="active",
        updated_at=now.isoformat(),
        ttl_expires_at=expires.isoformat(),
    )


async def _parse_report_payload(
    request: Request,
) -> tuple[CrowdsourcingReportRequest, bytes | None, str]:
    """Support both application/json (base64) and multipart/form-data (UploadFile) report submissions."""
    content_type = request.headers.get("content-type", "").lower()
    img_bytes: bytes | None = None
    mime_type = "image/jpeg"

    if "multipart/form-data" in content_type:
        form = await request.form()
        try:
            raw_data: dict[str, Any] = {}
            for key in (
                "lat",
                "lng",
                "location_name",
                "reporter_note",
                "image_base64",
                "mock_severity_hint",
            ):
                val = form.get(key)
                if isinstance(val, str) and val != "":
                    raw_data[key] = val

            upload = form.get("image") or form.get("file")
            if upload is not None and hasattr(upload, "read"):
                img_bytes = await upload.read()  # type: ignore[union-attr]
                upload_ct = getattr(upload, "content_type", None)
                if isinstance(upload_ct, str) and upload_ct.startswith("image/"):
                    mime_type = upload_ct

            try:
                payload = CrowdsourcingReportRequest.model_validate(raw_data)
            except ValidationError as exc:
                raise RequestValidationError(exc.errors()) from exc
        finally:
            await form.close()
    else:
        try:
            body_json = await request.json()
        except Exception as exc:
            raise RequestValidationError(
                [{"loc": ("body",), "msg": f"Invalid JSON body: {exc}", "type": "value_error.jsondecode"}]
            ) from exc
        try:
            payload = CrowdsourcingReportRequest.model_validate(body_json)
        except ValidationError as exc:
            raise RequestValidationError(exc.errors()) from exc

    if img_bytes is None and payload.image_base64:
        header_and_data = payload.image_base64.split(",", 1)
        if len(header_and_data) == 2 and "image/" in header_and_data[0]:
            mime_type = header_and_data[0].split(";")[0].replace("data:", "").strip() or "image/jpeg"
        raw_b64 = header_and_data[-1]
        try:
            img_bytes = base64.b64decode(raw_b64)
        except Exception as exc:
            logger.warning("Invalid base64 image in /api/reports; ignoring image_base64: %s", exc)
            img_bytes = None

    return payload, img_bytes, mime_type


@app.get("/api/health")
async def health_check() -> dict[str, Any]:
    return {
        "status": "ok",
        "mock_fallback_enabled": settings.USE_MOCK_FALLBACK,
        "gemini_model": settings.GEMINI_MODEL,
        "services": {
            "gemini_configured": settings.gemini_configured,
            "google_maps_configured": settings.google_maps_configured,
            "firebase_configured": settings.firebase_configured,
        },
    }


@app.get("/api/flood-zones", response_model=FloodZonesListResponse)
async def list_flood_zones() -> FloodZonesListResponse:
    zones = get_active_flood_zones()
    return FloodZonesListResponse(count=len(zones), items=zones)


@app.post("/api/flood-zones/reset", response_model=FloodZonesListResponse)
async def reset_flood_zones() -> FloodZonesListResponse:
    """Reset active flood zones, heatmap history, and camera frame cache back to initial sample state."""
    await clear_vision_cache_bound()
    zones = reset_flood_zones_to_sample()
    return FloodZonesListResponse(count=len(zones), items=zones)


@app.delete("/api/flood-zones/{event_id}", response_model=FloodZoneDeleteResponse)
async def remove_flood_zone(event_id: str) -> FloodZoneDeleteResponse:
    """Resolve/delete a specific active flood zone by event_id."""
    deleted = delete_flood_zone(event_id)
    return FloodZoneDeleteResponse(deleted=deleted, event_id=event_id)


@app.post(
    "/api/reports",
    response_model=CrowdsourcingReportResponse,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": CrowdsourcingReportRequest.model_json_schema()
                },
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["lat", "lng"],
                        "properties": {
                            "lat": {"type": "number"},
                            "lng": {"type": "number"},
                            "location_name": {"type": "string"},
                            "reporter_note": {"type": "string"},
                            "mock_severity_hint": {"type": "integer", "minimum": 0, "maximum": 3},
                            "image": {"type": "string", "format": "binary"},
                        },
                    }
                },
            },
        }
    },
)
async def create_crowdsourced_report(request: Request) -> CrowdsourcingReportResponse:
    payload, img_bytes, mime_type = await _parse_report_payload(request)

    analysis = await analyze_flood_image_bound(
        image_bytes=img_bytes,
        mime_type=mime_type,
        mock_severity_hint=payload.mock_severity_hint,
    )

    report_id = f"rep_{uuid.uuid4().hex[:6]}"
    broadcasted = False
    new_zone = _build_zone_from_analysis(
        event_id=report_id,
        source="crowdsourcing_ai",
        camera_id=None,
        location_name=payload.location_name,
        lat=payload.lat,
        lng=payload.lng,
        analysis=analysis,
    )
    if new_zone is not None:
        broadcasted = upsert_flood_zone(new_zone)

    return CrowdsourcingReportResponse(
        report_id=report_id,
        analysis=analysis.model_dump(),
        broadcasted_to_firestore=broadcasted,
    )


@app.get("/api/cameras", response_model=CameraListResponse)
async def list_cameras() -> CameraListResponse:
    cameras = get_cameras()
    return CameraListResponse(count=len(cameras), items=cameras)


@app.post("/api/cameras/poll", response_model=CameraPollResponse)
async def poll_cameras(
    payload: CameraPollRequest | None = None,
) -> CameraPollResponse:
    req = payload or CameraPollRequest()
    cameras = get_cameras()
    if req.camera_ids:
        selected = set(req.camera_ids)
        cameras = [c for c in cameras if c.camera_id in selected]

    async def _poll_single(cam: Any) -> tuple[Any, str, Any, bool]:
        effective_hint = (
            req.mock_severity_hint
            if req.mock_severity_hint is not None
            else (
                cam.default_severity_hint
                if cam.default_severity_hint is not None
                else 2
            )
        )
        frame_source, analysis, frame_delta_skipped = await poll_camera_frame_bound(
            camera_meta=cam.model_dump(),
            effective_hint=effective_hint,
            force_refresh=req.force_refresh,
            hint_explicitly_set=(req.mock_severity_hint is not None),
        )
        return cam, frame_source, analysis, frame_delta_skipped

    polled_items = await asyncio.gather(*(_poll_single(cam) for cam in cameras))

    results: list[CameraPollResultItem] = []
    flooded_count = 0

    for cam, frame_source, analysis, frame_delta_skipped in polled_items:

        if frame_delta_skipped:
            if analysis.severity_level >= 1:
                flooded_count += 1
            results.append(
                CameraPollResultItem(
                    camera_id=cam.camera_id,
                    frame_source=frame_source,
                    analysis=analysis.model_dump(),
                    broadcasted_to_firestore=False,
                    frame_delta_skipped=True,
                )
            )
            continue

        broadcasted = False
        event_id = f"cam_evt_{cam.camera_id}"
        if analysis.severity_level >= 1:
            flooded_count += 1
            zone = _build_zone_from_analysis(
                event_id=event_id,
                source="camera_ai",
                camera_id=cam.camera_id,
                location_name=cam.name,
                lat=cam.lat,
                lng=cam.lng,
                analysis=analysis,
            )
            if zone is not None:
                broadcasted = upsert_flood_zone(zone)
        else:
            delete_flood_zone(event_id)

        results.append(
            CameraPollResultItem(
                camera_id=cam.camera_id,
                frame_source=frame_source,
                analysis=analysis.model_dump(),
                broadcasted_to_firestore=broadcasted,
                frame_delta_skipped=False,
            )
        )

    return CameraPollResponse(
        polled_count=len(results),
        flooded_count=flooded_count,
        results=results,
    )


@app.post("/api/route", response_model=RouteResponse)
async def calculate_route(payload: RouteRequest) -> RouteResponse:
    active_zones = get_active_flood_zones()
    return await compute_safe_route(payload, active_zones)


@app.get("/api/heatmap", response_model=HeatmapResponse)
async def get_flood_heatmap() -> HeatmapResponse:
    items = get_heatmap_points()
    return HeatmapResponse(count=len(items), items=items)
