"""
Firebase Firestore Service with automatic fallback to local sample files in data/.
Allows contributors to run and test backend endpoints before Firebase credentials are set.
"""

from __future__ import annotations

import json
from typing import Any
from ..config import ROOT_DIR, settings
from ..schemas import FloodZoneItem

_IN_MEMORY_ZONES: list[FloodZoneItem] | None = None


def _load_sample_flood_zones() -> list[FloodZoneItem]:
    geojson_path = ROOT_DIR / "data" / "flood_events.sample.geojson"
    if not geojson_path.exists():
        return []
    raw = json.loads(geojson_path.read_text(encoding="utf-8"))
    zones: list[FloodZoneItem] = []
    for feat in raw.get("features", []):
        props = feat.get("properties", {})
        coords = feat.get("geometry", {}).get("coordinates", [106.7082, 10.7858])
        zones.append(
            FloodZoneItem(
                event_id=props.get("event_id", "evt_001"),
                source=props.get("source", "camera_ai"),
                camera_id=props.get("camera_id"),
                location_name=props.get(
                    "location_name", "Ngã tư Nguyễn Hữu Cảnh - Tôn Đức Thắng"
                ),
                lat=float(coords[1]),
                lng=float(coords[0]),
                radius_meters=float(props.get("radius_meters", 120.0)),
                severity_level=int(props.get("severity_level", 2)),
                visual_cue=props.get(
                    "visual_cue",
                    "Nước ngập quá mép lề đường và chạm nửa bánh xe máy",
                ),
                estimated_depth_cm=props.get("estimated_depth_cm", "20-35"),
                passable_for_motorbike=bool(
                    props.get("passable_for_motorbike", False)
                ),
                confidence=float(props.get("confidence", 0.91)),
                vision_model=props.get("vision_model", settings.GEMINI_MODEL),
                status=props.get("status", "active"),
                updated_at=props.get("updated_at", "2026-11-11T10:00:00+07:00"),
            )
        )
    return zones


def get_active_flood_zones() -> list[FloodZoneItem]:
    global _IN_MEMORY_ZONES
    if _IN_MEMORY_ZONES is None:
        _IN_MEMORY_ZONES = _load_sample_flood_zones()
    return list(_IN_MEMORY_ZONES)


def upsert_flood_zone(zone: FloodZoneItem) -> bool:
    """Save active flood zone in memory and broadcast to Firestore if configured."""
    global _IN_MEMORY_ZONES
    if _IN_MEMORY_ZONES is None:
        _IN_MEMORY_ZONES = _load_sample_flood_zones()
    _IN_MEMORY_ZONES = [z for z in _IN_MEMORY_ZONES if z.event_id != zone.event_id]
    _IN_MEMORY_ZONES.append(zone)

    if not settings.firebase_configured:
        return False

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore

        if not firebase_admin._apps:
            cred = credentials.Certificate(settings.GOOGLE_APPLICATION_CREDENTIALS)
            firebase_admin.initialize_app(cred)
        db = firestore.client()
        db.collection("active_flood_zones").document(zone.event_id).set(
            zone.model_dump()
        )
        return True
    except Exception:
        return False


def get_heatmap_points() -> list[dict[str, Any]]:
    heatmap_path = ROOT_DIR / "data" / "heatmap_history.sample.json"
    if not heatmap_path.exists():
        return []
    items = json.loads(heatmap_path.read_text(encoding="utf-8"))
    for item in items:
        freq = float(item.get("flood_frequency_30d", 1))
        sev = float(item.get("avg_severity", 1.0))
        item["weight"] = round(freq * sev, 2)
    return items
