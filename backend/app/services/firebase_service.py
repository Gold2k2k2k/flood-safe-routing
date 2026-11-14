"""
Firebase Firestore Service with full read/write + TTL filtering,
flood_events_history aggregation, structured logging, and strict fallback gating.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..config import ROOT_DIR, settings
from ..schemas import CameraItem, FloodZoneItem

logger = logging.getLogger(__name__)
_IN_MEMORY_ZONES: list[FloodZoneItem] | None = None
_IN_MEMORY_HEATMAP: list[dict[str, Any]] | None = None


def _resolve_data_file(filename: str) -> Path | None:
    """Resolve sample data file across local repo root, CWD, or serverless bundle."""
    candidates = [
        ROOT_DIR / "data" / filename,
        Path.cwd() / "data" / filename,
        Path(__file__).resolve().parents[2] / "data" / filename,
    ]
    for path in candidates:
        if path.exists() and path.is_file():
            return path
    return None


def _embedded_fallback_zones() -> list[FloodZoneItem]:
    return [
        FloodZoneItem(
            event_id="evt_001",
            source="camera_ai",
            camera_id="cam_hcm_001",
            location_name="Ngã tư Nguyễn Hữu Cảnh - Tôn Đức Thắng",
            lat=10.7858,
            lng=106.7082,
            radius_meters=120.0,
            severity_level=2,
            visual_cue="Nước ngập quá mép lề đường và chạm nửa bánh xe máy",
            estimated_depth_cm="20-35",
            passable_for_motorbike=False,
            confidence=0.91,
            vision_model=settings.GEMINI_MODEL,
            status="active",
            updated_at="2026-11-14T08:00:00+07:00",
        ),
        FloodZoneItem(
            event_id="evt_hcm_002",
            source="camera_ai",
            camera_id="cam_hcm_002",
            location_name="Đường Quốc Hương - Xuân Thủy (Thảo Điền)",
            lat=10.8032,
            lng=106.7280,
            radius_meters=130.0,
            severity_level=3,
            visual_cue="Nước ngập sâu lút quá nửa bánh xe máy, chạm ống xả và lốc máy",
            estimated_depth_cm=">35",
            passable_for_motorbike=False,
            confidence=0.94,
            vision_model=settings.GEMINI_MODEL,
            status="active",
            updated_at="2026-11-14T08:30:00+07:00",
        ),
    ]


def _embedded_fallback_cameras() -> list[CameraItem]:
    return [
        CameraItem(
            camera_id="cam_hcm_001",
            name="Ngã tư Nguyễn Hữu Cảnh - Tôn Đức Thắng",
            city="TP.HCM",
            source="public_traffic_camera",
            feed_url="https://giaothong.hochiminhcity.gov.vn",
            lat=10.7858,
            lng=106.7082,
            road_segment_id="seg_hcm_nhc_01",
            local_image_path="data/sample_frames/level_2_moderate.jpg",
            default_severity_hint=2,
        ),
        CameraItem(
            camera_id="cam_hcm_002",
            name="Đường Quốc Hương - Xuân Thủy (Thảo Điền)",
            city="TP.HCM",
            source="public_traffic_camera",
            feed_url="https://giaothong.hochiminhcity.gov.vn",
            lat=10.8032,
            lng=106.7280,
            road_segment_id="seg_hcm_qh_01",
            local_image_path="data/sample_frames/level_3_severe.jpg",
            default_severity_hint=3,
        ),
    ]


def _embedded_fallback_heatmap() -> list[dict[str, Any]]:
    return [
        {
            "zone_id": "hcm_binh_thanh_nhc",
            "city": "TP.HCM",
            "district": "Bình Thạnh (Nguyễn Hữu Cảnh)",
            "lat": 10.7858,
            "lng": 106.7082,
            "flood_frequency_30d": 16,
            "avg_severity": 2.4,
            "weight": 38.4,
            "peak_trigger": "high_tide_and_rain",
        },
        {
            "zone_id": "hcm_thu_duc_quoc_huong",
            "city": "TP.HCM",
            "district": "TP. Thủ Đức (Quốc Hương - Thảo Điền)",
            "lat": 10.8032,
            "lng": 106.7280,
            "flood_frequency_30d": 19,
            "avg_severity": 2.6,
            "weight": 49.4,
            "peak_trigger": "high_tide_and_rain",
        },
    ]


def _approx_distance_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Fast spherical Haversine distance in meters for matching nearby flood history zones."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


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
        if settings.FIREBASE_SERVICE_ACCOUNT_JSON:
            cred_info = json.loads(settings.FIREBASE_SERVICE_ACCOUNT_JSON)
            cred = credentials.Certificate(cred_info)
        else:
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
    except Exception as exc:
        logger.warning("Malformed ttl_expires_at '%s'; treating zone as active: %s", ttl_expires_at, exc)
        return True


def _load_sample_flood_zones() -> list[FloodZoneItem]:
    geojson_path = _resolve_data_file("flood_events.sample.geojson")
    if geojson_path is None:
        logger.warning("flood_events.sample.geojson not found; using embedded fallback seed zones.")
        return _embedded_fallback_zones()
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
    heatmap_path = _resolve_data_file("heatmap_history.sample.json")
    if heatmap_path is None:
        logger.warning("heatmap_history.sample.json not found; using embedded fallback heatmap.")
        return _embedded_fallback_heatmap()
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


def _accumulate_history_entry(
    existing: dict[str, Any] | None,
    zone: FloodZoneItem,
    city: str,
    target_zone_id: str,
) -> dict[str, Any]:
    """Increment flood_frequency_30d and recalculate running avg_severity and thermal weight."""
    sev = float(zone.severity_level)
    if existing is not None:
        prev_freq = max(0, int(existing.get("flood_frequency_30d", 0)))
        prev_avg = float(existing.get("avg_severity", sev))
        new_freq = prev_freq + 1
        new_avg = round(((prev_avg * prev_freq) + sev) / new_freq, 2)
        district = existing.get("district")
        if not district or district == "Unknown":
            district = zone.location_name or "Khu vực ghi nhận ngập"
        return {
            **existing,
            "zone_id": str(existing.get("zone_id") or target_zone_id),
            "city": str(existing.get("city") or city),
            "district": district,
            "lat": float(existing.get("lat", zone.lat)),
            "lng": float(existing.get("lng", zone.lng)),
            "flood_frequency_30d": new_freq,
            "avg_severity": new_avg,
            "weight": round(new_freq * new_avg, 2),
            "peak_trigger": existing.get("peak_trigger") or zone.source,
            "recorded_at": zone.updated_at,
        }

    return {
        "zone_id": target_zone_id,
        "city": city,
        "district": zone.location_name or "Khu vực ghi nhận ngập",
        "lat": zone.lat,
        "lng": zone.lng,
        "flood_frequency_30d": 1,
        "avg_severity": round(sev, 2),
        "weight": round(sev, 2),
        "peak_trigger": zone.source,
        "recorded_at": zone.updated_at,
    }


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
    target_zone_id = zone.camera_id or zone.event_id

    # Accumulate flood_events_history in memory when severity_level >= 2
    if zone.severity_level >= 2:
        if _IN_MEMORY_HEATMAP is None:
            _IN_MEMORY_HEATMAP = _load_sample_heatmap()

        matched_idx: int | None = None
        for idx, h in enumerate(_IN_MEMORY_HEATMAP):
            hid = h.get("zone_id")
            if hid in (zone.event_id, zone.camera_id):
                matched_idx = idx
                break
            dist_m = _approx_distance_meters(
                float(h.get("lat", 0.0)),
                float(h.get("lng", 0.0)),
                zone.lat,
                zone.lng,
            )
            if dist_m <= 300.0:
                matched_idx = idx
                break

        if matched_idx is not None:
            existing_entry = _IN_MEMORY_HEATMAP[matched_idx]
            target_zone_id = str(existing_entry.get("zone_id") or target_zone_id)
            _IN_MEMORY_HEATMAP[matched_idx] = _accumulate_history_entry(
                existing_entry, zone, city, target_zone_id
            )
        else:
            _IN_MEMORY_HEATMAP.append(
                _accumulate_history_entry(None, zone, city, target_zone_id)
            )

    if not _require_firestore_or_mock():
        return False

    try:
        db = _get_firestore_client()
        db.collection("active_flood_zones").document(zone.event_id).set(
            zone.model_dump()
        )
        if zone.severity_level >= 2:
            hist_ref = db.collection("flood_events_history").document(target_zone_id)
            snap = hist_ref.get()
            existing_doc = (snap.to_dict() or {}) if getattr(snap, "exists", False) else None
            updated_hist = _accumulate_history_entry(
                existing_doc, zone, city, target_zone_id
            )
            hist_ref.set(updated_hist, merge=True)
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

    cameras_path = _resolve_data_file("cameras.sample.json")
    if cameras_path is None:
        logger.warning("cameras.sample.json not found; using embedded fallback cameras.")
        return _embedded_fallback_cameras()
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
