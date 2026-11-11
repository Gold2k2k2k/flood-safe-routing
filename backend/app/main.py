"""
FastAPI Main Entrypoint for Flood-Safe Routing.
Implements all endpoints defined in docs/api-and-data-contract.md.
"""

from __future__ import annotations

import base64
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import ROOT_DIR, settings
from .schemas import (
    CrowdsourcingReportRequest,
    FloodZoneItem,
    RouteRequest,
    RouteResponse,
)
from .services.firebase_service import (
    get_active_flood_zones,
    get_heatmap_points,
    upsert_flood_zone,
)
from .services.routing_service import compute_safe_route

# Allow importing ai-vision package from monorepo root
if str(ROOT_DIR / "ai-vision") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "ai-vision"))

from src.analyzer import analyze_flood_image  # type: ignore

app = FastAPI(
    title="Flood-Safe Routing API",
    description="Real-time AI Flood Detection (Gemini 3.8 Flash) & Dynamic Safe Rerouting (Google Maps Routes API + Firebase)",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.get("/api/flood-zones")
async def list_flood_zones() -> dict:
    zones = get_active_flood_zones()
    return {"count": len(zones), "items": [z.model_dump() for z in zones]}


@app.post("/api/reports")
async def create_crowdsourced_report(payload: CrowdsourcingReportRequest) -> dict:
    img_bytes: bytes | None = None
    if payload.image_base64:
        raw_b64 = payload.image_base64.split(",")[-1]
        try:
            img_bytes = base64.b64decode(raw_b64)
        except Exception:
            img_bytes = None

    analysis = analyze_flood_image(
        image_bytes=img_bytes,
        mock_severity_hint=payload.mock_severity_hint,
    )

    report_id = f"rep_{uuid.uuid4().hex[:6]}"
    broadcasted = False
    if analysis.severity_level >= 1:
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
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        broadcasted = upsert_flood_zone(new_zone)

    return {
        "report_id": report_id,
        "analysis": analysis.model_dump(),
        "broadcasted_to_firestore": broadcasted,
    }


@app.post("/api/route", response_model=RouteResponse)
async def calculate_route(payload: RouteRequest) -> RouteResponse:
    active_zones = get_active_flood_zones()
    return await compute_safe_route(payload, active_zones)


@app.get("/api/heatmap")
async def get_flood_heatmap() -> dict:
    items = get_heatmap_points()
    return {"count": len(items), "items": items}
