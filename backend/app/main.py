"""
FastAPI Main Entrypoint for Flood-Safe Routing.
Implements all endpoints defined in docs/api-and-data-contract.md with non-blocking
async AI inference, strict RuntimeError -> 503 handling, and camera polling.
"""

from __future__ import annotations

import base64
import sys
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import ROOT_DIR, settings
from .schemas import (
    CameraListResponse,
    CameraPollRequest,
    CameraPollResponse,
    CameraPollResultItem,
    CrowdsourcingReportRequest,
    CrowdsourcingReportResponse,
    FloodZoneItem,
    FloodZonesListResponse,
    HeatmapResponse,
    RouteRequest,
    RouteResponse,
)
from .services.firebase_service import (
    get_active_flood_zones,
    get_cameras,
    get_heatmap_points,
    upsert_flood_zone,
)
from .services.routing_service import compute_safe_route

# Load ai-vision modules cleanly without colliding with generic `src` packages
_AI_VISION_ROOT = ROOT_DIR / "ai-vision"
if str(_AI_VISION_ROOT) not in sys.path:
    sys.path.insert(0, str(_AI_VISION_ROOT))

from src.analyzer import analyze_flood_image_async  # type: ignore
from src.camera_extractor import extract_frame_for_camera  # type: ignore

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


@app.get("/api/health")
async def health_check() -> dict:
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


@app.post("/api/reports", response_model=CrowdsourcingReportResponse)
async def create_crowdsourced_report(
    payload: CrowdsourcingReportRequest,
) -> CrowdsourcingReportResponse:
    img_bytes: bytes | None = None
    if payload.image_base64:
        raw_b64 = payload.image_base64.split(",")[-1]
        try:
            img_bytes = base64.b64decode(raw_b64)
        except Exception:
            img_bytes = None

    analysis = await analyze_flood_image_async(
        image_bytes=img_bytes,
        mock_severity_hint=payload.mock_severity_hint,
    )

    report_id = f"rep_{uuid.uuid4().hex[:6]}"
    broadcasted = False
    if analysis.severity_level >= 1:
        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=settings.FLOOD_ZONE_TTL_MINUTES)
        new_zone = FloodZoneItem(
            event_id=report_id,
            source="crowdsourcing_ai",
            camera_id=None,
            location_name=payload.location_name,
            lat=payload.lat,
            lng=payload.lng,
            radius_meters=120.0,
            severity_level=analysis.severity_level,
            visual_cue=analysis.visual_cue,
            estimated_depth_cm=analysis.estimated_depth_cm,
            passable_for_motorbike=analysis.passable_for_motorbike,
            confidence=analysis.confidence,
            vision_model=analysis.vision_model,
            status="active",
            updated_at=now.isoformat(),
            ttl_expires_at=expires.isoformat(),
        )
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

    results: list[CameraPollResultItem] = []
    flooded_count = 0

    for cam in cameras:
        frame_bytes, frame_source = await extract_frame_for_camera(cam.model_dump())
        analysis = await analyze_flood_image_async(
            image_bytes=frame_bytes,
            mock_severity_hint=req.mock_severity_hint,
        )
        broadcasted = False
        if analysis.severity_level >= 1:
            flooded_count += 1
            now = datetime.now(timezone.utc)
            expires = now + timedelta(minutes=settings.FLOOD_ZONE_TTL_MINUTES)
            zone = FloodZoneItem(
                event_id=f"cam_evt_{cam.camera_id}",
                source="camera_ai",
                camera_id=cam.camera_id,
                location_name=cam.name,
                lat=cam.lat,
                lng=cam.lng,
                radius_meters=120.0,
                severity_level=analysis.severity_level,
                visual_cue=analysis.visual_cue,
                estimated_depth_cm=analysis.estimated_depth_cm,
                passable_for_motorbike=analysis.passable_for_motorbike,
                confidence=analysis.confidence,
                vision_model=analysis.vision_model,
                status="active",
                updated_at=now.isoformat(),
                ttl_expires_at=expires.isoformat(),
            )
            broadcasted = upsert_flood_zone(zone)

        results.append(
            CameraPollResultItem(
                camera_id=cam.camera_id,
                frame_source=frame_source,
                analysis=analysis.model_dump(),
                broadcasted_to_firestore=broadcasted,
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
