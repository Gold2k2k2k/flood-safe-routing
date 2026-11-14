"""
Firebase Firestore Service with full read/write + TTL filtering,
flood_events_history aggregation, structured logging, and strict fallback gating.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from ..config import ROOT_DIR, settings
from ..schemas import CameraItem, FloodZoneItem

logger = logging.getLogger(__name__)
_IN_MEMORY_ZONES: list[FloodZoneItem] | None = None
_IN_MEMORY_HEATMAP: list[dict[str, Any]] | None = None


def _infer_city(lat: float, lng: float) -> str:
    """Infer Vietnamese municipality from geographic coordinates."""
    if 15.5 <= lat <= 16.5:
        return "Đà Nẵng"
    if lat >= 20.0:
        return "Hà Nội"
    return "TP.HCM"


def _require_firestore_or_mock() -> bool:
    """
    Return True when live Firestore should be used, False when mock fallback applies.
    Raises RuntimeError if USE_MOCK_FALLBACK=false and Firestore credentials are absent.
    """
    if settings.firebase_configured:
        return True
    if not settings.USE_MOCK_FALLBACK:
        raise RuntimeError(
            "Firebase Firestore is not configured (missing serviceAccountKey.json or FIREBASE_PROJECT_ID) "
            "while USE_MOCK_FALLBACK=false."
        )
    return False


def _get_firestore_client() -> Any:
    import firebase_admin
    from firebase_admin import credentials, firestore

    if not firebase_admin._apps:
        cred = credentials.Certificate(str(settings.resolved_credentials_path))
        firebase_admin.initialize_app(cred)
    return firestore.client()


def _is_not_expired(ttl_expires_at: str | None) -> bool:
    if not ttl_expires_at:
        return True
    try:
        expires = datetime.fromisoformat(ttl_expires_at.replace("Z", "+00:00"))
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return expires > datetime.now(timezone.utc)
    except Exception:
        return True


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
                ttl_expires_at=props.get("ttl_expires_at"),
            )
        )
    return zones


def _load_sample_heatmap() -> list[dict[str, Any]]:
    heatmap_path = ROOT_DIR / "data" / "heatmap_history.sample.json"
    if not heatmap_path.exists():
        return []
    items = json.loads(heatmap_path.read_text(encoding="utf-8"))
    for item in items:
        freq = float(item.get("flood_frequency_30d", 1))
        sev = float(item.get("avg_severity", 1.0))
        item["weight"] = round(freq * sev, 2)
    return items


def get_active_flood_zones() -> list[FloodZoneItem]:
    global _IN_MEMORY_ZONES
    if _require_firestore_or_mock():
        try:
            db = _get_firestore_client()
            docs = (
                db.collection("active_flood_zones")
                .where("status", "==", "active")
                .stream()
            )
            live_zones: list[FloodZoneItem] = []
            for doc in docs:
                data = doc.to_dict() or {}
                data.setdefault("event_id", doc.id)
                if _is_not_expired(data.get("ttl_expires_at")):
                    live_zones.append(FloodZoneItem(**data))
            return live_zones
        except Exception as exc:
            logger.warning("Firestore read failed; checking fallback gate: %s", exc)
            if not settings.USE_MOCK_FALLBACK:
                raise RuntimeError(f"Firestore read failed: {exc}") from exc

    if _IN_MEMORY_ZONES is None:
        _IN_MEMORY_ZONES = _load_sample_flood_zones()
    return [z for z in _IN_MEMORY_ZONES if z.status == "active" and _is_not_expired(z.ttl_expires_at)]


def upsert_flood_zone(zone: FloodZoneItem) -> bool:
    """Save active flood zone in memory and broadcast to Firestore if configured."""
    global _IN_MEMORY_ZONES, _IN_MEMORY_HEATMAP
    if not zone.ttl_expires_at:
        zone.ttl_expires_at = (
            datetime.now(timezone.utc) + timedelta(minutes=settings.FLOOD_ZONE_TTL_MINUTES)
        ).isoformat()

    if _IN_MEMORY_ZONES is None:
        _IN_MEMORY_ZONES = _load_sample_flood_zones()
    _IN_MEMORY_ZONES = [z for z in _IN_MEMORY_ZONES if z.event_id != zone.event_id]
    _IN_MEMORY_ZONES.append(zone)

    city = _infer_city(zone.lat, zone.lng)

    # In mock mode or local state, keep in-memory heatmap history updated
    if zone.severity_level >= 2:
        if _IN_MEMORY_HEATMAP is None:
            _IN_MEMORY_HEATMAP = _load_sample_heatmap()
        hist_record = {
            "zone_id": zone.event_id,
            "city": city,
            "district": zone.location_name or "Unknown",
            "lat": zone.lat,
            "lng": zone.lng,
            "flood_frequency_30d": 1,
            "avg_severity": float(zone.severity_level),
            "weight": round(1.0 * float(zone.severity_level), 2),
            "peak_trigger": zone.source,
            "recorded_at": zone.updated_at,
        }
        _IN_MEMORY_HEATMAP = [h for h in _IN_MEMORY_HEATMAP if h.get("zone_id") != zone.event_id]
        _IN_MEMORY_HEATMAP.append(hist_record)

    if not _require_firestore_or_mock():
        return False

    try:
        db = _get_firestore_client()
        db.collection("active_flood_zones").document(zone.event_id).set(
            zone.model_dump()
        )
        if zone.severity_level >= 2:
            db.collection("flood_events_history").document(zone.event_id).set(
                {
                    "zone_id": zone.event_id,
                    "city": city,
                    "district": zone.location_name or "Unknown",
                    "lat": zone.lat,
                    "lng": zone.lng,
                    "flood_frequency_30d": 1,
                    "avg_severity": float(zone.severity_level),
                    "peak_trigger": zone.source,
                    "recorded_at": zone.updated_at,
                },
                merge=True,
            )
        return True
    except Exception as exc:
        logger.warning("Failed to broadcast flood zone %s to Firestore: %s", zone.event_id, exc)
        if not settings.USE_MOCK_FALLBACK:
            raise RuntimeError(f"Firestore write failed: {exc}") from exc
        return False


def delete_flood_zone(event_id: str) -> bool:
    """Delete an active flood zone from in-memory state and Firestore if configured."""
    global _IN_MEMORY_ZONES
    if _IN_MEMORY_ZONES is None:
        _IN_MEMORY_ZONES = _load_sample_flood_zones()
    initial_count = len(_IN_MEMORY_ZONES)
    _IN_MEMORY_ZONES = [z for z in _IN_MEMORY_ZONES if z.event_id != event_id]
    deleted_in_mem = len(_IN_MEMORY_ZONES) < initial_count

    if _require_firestore_or_mock():
        try:
            db = _get_firestore_client()
            db.collection("active_flood_zones").document(event_id).delete()
            return True
        except Exception as exc:
            logger.warning("Failed to delete flood zone %s from Firestore: %s", event_id, exc)
            if not settings.USE_MOCK_FALLBACK:
                raise RuntimeError(f"Firestore delete failed: {exc}") from exc
            return False

    return deleted_in_mem


def reset_flood_zones_to_sample() -> list[FloodZoneItem]:
    """Reset active flood zones and in-memory heatmap back to seed sample datasets."""
    global _IN_MEMORY_ZONES, _IN_MEMORY_HEATMAP
    _IN_MEMORY_ZONES = _load_sample_flood_zones()
    _IN_MEMORY_HEATMAP = _load_sample_heatmap()

    if _require_firestore_or_mock():
        try:
            db = _get_firestore_client()
            batch = db.batch()
            for doc in db.collection("active_flood_zones").stream():
                batch.delete(doc.reference)
            for zone in _IN_MEMORY_ZONES:
                batch.set(
                    db.collection("active_flood_zones").document(zone.event_id),
                    zone.model_dump(),
                )
            batch.commit()
        except Exception as exc:
            logger.warning("Failed to reset Firestore flood zones: %s", exc)
            if not settings.USE_MOCK_FALLBACK:
                raise RuntimeError(f"Firestore reset failed: {exc}") from exc

    return list(_IN_MEMORY_ZONES)


def get_cameras() -> list[CameraItem]:
    if _require_firestore_or_mock():
        try:
            db = _get_firestore_client()
            docs = list(db.collection("cameras").stream())
            if docs:
                return [CameraItem(**(d.to_dict() or {})) for d in docs]
        except Exception as exc:
            logger.warning("Firestore cameras lookup failed; falling back to sample JSON: %s", exc)
            if not settings.USE_MOCK_FALLBACK:
                raise RuntimeError(f"Firestore cameras lookup failed: {exc}") from exc

    cameras_path = ROOT_DIR / "data" / "cameras.sample.json"
    if not cameras_path.exists():
        return []
    raw = json.loads(cameras_path.read_text(encoding="utf-8"))
    return [CameraItem(**item) for item in raw]


def get_heatmap_points() -> list[dict[str, Any]]:
    global _IN_MEMORY_HEATMAP
    if _require_firestore_or_mock():
        try:
            db = _get_firestore_client()
            docs = list(db.collection("flood_events_history").stream())
            if docs:
                items = [d.to_dict() or {} for d in docs]
                for item in items:
                    freq = float(item.get("flood_frequency_30d", 1))
                    sev = float(item.get("avg_severity", 1.0))
                    item["weight"] = round(freq * sev, 2)
                return items
        except Exception as exc:
            logger.warning("Firestore heatmap lookup failed; falling back to sample JSON: %s", exc)
            if not settings.USE_MOCK_FALLBACK:
                raise RuntimeError(f"Firestore heatmap lookup failed: {exc}") from exc

    if _IN_MEMORY_HEATMAP is None:
        _IN_MEMORY_HEATMAP = _load_sample_heatmap()
    return list(_IN_MEMORY_HEATMAP)
