"""
Two-Layer Dynamic Rerouting Service on top of Google Maps Platform Routes API v2.
1. Layer 1: Calls computeRoutes (TWO_WHEELER, computeAlternativeRoutes=True, NO intermediates)
   and selects the first route that does not intersect any active flood zone (severity >= 2).
2. Layer 2: If all Layer-1 routes intersect a flood zone, computes left & right perpendicular
   detour `via` waypoints (scaled by cos(lat)) and calls computeRoutes with intermediates
   (without computeAlternativeRoutes or optimizeWaypointOrder).
"""

from __future__ import annotations

import logging
import math
from typing import Any
import httpx

from ..config import settings
from ..schemas import FloodZoneItem, LatLng, RouteRequest, RouteResponse

logger = logging.getLogger(__name__)
ROUTES_API_V2_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
ROUTES_FIELD_MASK = (
    "routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline,routes.description"
)


def decode_encoded_polyline(encoded: str) -> list[LatLng]:
    """Decode Google Encoded Polyline (precision 5) into LatLng list."""
    if not encoded:
        return []
    try:
        import polyline as poly_lib  # type: ignore

        return [LatLng(lat=lat, lng=lng) for lat, lng in poly_lib.decode(encoded, 5)]
    except ImportError:
        coords: list[LatLng] = []
        index = lat = lng = 0
        while index < len(encoded):
            for is_lng in (False, True):
                shift = result = 0
                while True:
                    b = ord(encoded[index]) - 63
                    index += 1
                    result |= (b & 0x1F) << shift
                    shift += 5
                    if b < 0x20:
                        break
                delta = ~(result >> 1) if (result & 1) else (result >> 1)
                if is_lng:
                    lng += delta
                else:
                    lat += delta
            coords.append(LatLng(lat=lat / 1e5, lng=lng / 1e5))
        return coords


def haversine_meters(a: LatLng, b: LatLng) -> float:
    """Distance in meters between two geographic coordinates."""
    r = 6371000.0
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    dlat = math.radians(b.lat - a.lat)
    dlng = math.radians(b.lng - a.lng)
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(h))


def point_to_segment_distance_meters(p: LatLng, a: LatLng, b: LatLng) -> float:
    """Approximate minimum distance in meters from point p to line segment a-b."""
    if a.lat == b.lat and a.lng == b.lng:
        return haversine_meters(p, a)
    dx = b.lng - a.lng
    dy = b.lat - a.lat
    t = ((p.lng - a.lng) * dx + (p.lat - a.lat) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    proj = LatLng(lat=a.lat + t * dy, lng=a.lng + t * dx)
    return haversine_meters(p, proj)


def find_intersecting_flood_zones(
    coords: list[LatLng], flood_zones: list[FloodZoneItem]
) -> list[FloodZoneItem]:
    """Return all active flood zones (severity >= 2) intersected by the given polyline."""
    hit: list[FloodZoneItem] = []
    dangerous_zones = [
        z for z in flood_zones if z.severity_level >= 2 and z.status == "active"
    ]
    if len(coords) < 2:
        return hit

    for zone in dangerous_zones:
        center = LatLng(lat=zone.lat, lng=zone.lng)
        for i in range(len(coords) - 1):
            dist = point_to_segment_distance_meters(center, coords[i], coords[i + 1])
            if dist <= zone.radius_meters:
                hit.append(zone)
                break
    return hit


def compute_detour_candidates(
    origin: LatLng,
    destination: LatLng,
    flooded_zone: FloodZoneItem,
    offset_meters: float = 350.0,
) -> list[LatLng]:
    """
    Compute left and right perpendicular detour `via` waypoints outside the flood radius,
    scaling longitude offsets by cos(latitude).
    """
    cos_lat = max(0.1, math.cos(math.radians(flooded_zone.lat)))
    dx_m = (destination.lng - origin.lng) * 111111.0 * cos_lat
    dy_m = (destination.lat - origin.lat) * 111111.0
    length = math.hypot(dx_m, dy_m) or 1e-6

    # Perpendicular unit vectors in local meter space: (-dy, dx) and (dy, -dx)
    nx = -dy_m / length
    ny = dx_m / length

    candidates: list[LatLng] = []
    for sign in (1.0, -1.0):
        dlat = (sign * ny * offset_meters) / 111111.0
        dlng = (sign * nx * offset_meters) / (111111.0 * cos_lat)
        candidates.append(
            LatLng(
                lat=round(flooded_zone.lat + dlat, 6),
                lng=round(flooded_zone.lng + dlng, 6),
            )
        )
    return candidates


def compute_detour_waypoint(
    origin: LatLng,
    destination: LatLng,
    flooded_zone: FloodZoneItem,
    offset_meters: float = 350.0,
) -> LatLng:
    """Return the primary perpendicular detour waypoint outside the flood radius."""
    return compute_detour_candidates(origin, destination, flooded_zone, offset_meters)[0]


def build_routes_api_v2_payload(
    origin: LatLng,
    destination: LatLng,
    travel_mode: str = "TWO_WHEELER",
    via_waypoint: LatLng | None = None,
) -> dict[str, Any]:
    """
    Build a compliant Google Routes API v2 computeRoutes payload.
    Enforces hard API constraints:
    - Never set computeAlternativeRoutes=true when intermediates is present.
    - Never set optimizeWaypointOrder=true with via=true intermediates.
    - Never double-nest intermediates[].location.location.
    """
    body: dict[str, Any] = {
        "origin": {"location": {"latLng": {"latitude": origin.lat, "longitude": origin.lng}}},
        "destination": {
            "location": {"latLng": {"latitude": destination.lat, "longitude": destination.lng}}
        },
        "travelMode": travel_mode,
        "routingPreference": "TRAFFIC_AWARE",
        "polylineQuality": "HIGH_QUALITY",
        "polylineEncoding": "ENCODED_POLYLINE",
    }
    if via_waypoint is not None:
        body["intermediates"] = [
            {
                "location": {
                    "latLng": {
                        "latitude": via_waypoint.lat,
                        "longitude": via_waypoint.lng,
                    }
                },
                "via": True,
            }
        ]
    else:
        body["computeAlternativeRoutes"] = True
    return body


def _parse_duration_seconds(duration_str: str | None) -> int:
    if not duration_str:
        return 0
    try:
        return int(float(duration_str.rstrip("s")))
    except Exception:
        return 0


async def _call_routes_api_v2(
    origin: LatLng,
    destination: LatLng,
    travel_mode: str = "TWO_WHEELER",
    via_waypoint: LatLng | None = None,
) -> list[dict[str, Any]]:
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": settings.GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": ROUTES_FIELD_MASK,
    }
    payload = build_routes_api_v2_payload(
        origin=origin,
        destination=destination,
        travel_mode=travel_mode,
        via_waypoint=via_waypoint,
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(ROUTES_API_V2_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    return data.get("routes", [])


async def compute_safe_route(
    req: RouteRequest, active_zones: list[FloodZoneItem]
) -> RouteResponse:
    """
    Compute route between origin and destination using Two-Layer Flood Avoidance.
    Uses live Google Routes API v2 when GOOGLE_MAPS_API_KEY is configured;
    falls back cleanly to deterministic geometry when USE_MOCK_FALLBACK=true.
    """
    if settings.google_maps_configured:
        try:
            routes = await _call_routes_api_v2(
                req.origin, req.destination, travel_mode=req.travel_mode
            )
            if routes:
                decoded_routes = [
                    (
                        r,
                        decode_encoded_polyline(
                            r.get("polyline", {}).get("encodedPolyline", "")
                        ),
                    )
                    for r in routes
                ]

                if not req.avoid_flood_zones:
                    r0, coords0 = decoded_routes[0]
                    return RouteResponse(
                        rerouted=False,
                        avoided_flood_zone_ids=[],
                        detour_waypoint_used=None,
                        distance_meters=int(r0.get("distanceMeters", 0)),
                        duration_seconds=_parse_duration_seconds(r0.get("duration")),
                        encoded_polyline=r0.get("polyline", {}).get("encodedPolyline", ""),
                        route_coordinates=coords0 or [req.origin, req.destination],
                        warning_message=None,
                    )

                primary_hits = find_intersecting_flood_zones(
                    decoded_routes[0][1], active_zones
                )
                if not primary_hits:
                    r0, coords0 = decoded_routes[0]
                    return RouteResponse(
                        rerouted=False,
                        avoided_flood_zone_ids=[],
                        detour_waypoint_used=None,
                        distance_meters=int(r0.get("distanceMeters", 0)),
                        duration_seconds=_parse_duration_seconds(r0.get("duration")),
                        encoded_polyline=r0.get("polyline", {}).get("encodedPolyline", ""),
                        route_coordinates=coords0,
                        warning_message=None,
                    )

                # Layer 1: Check alternative routes returned by computeAlternativeRoutes=true
                for r_alt, coords_alt in decoded_routes[1:]:
                    if not find_intersecting_flood_zones(coords_alt, active_zones):
                        return RouteResponse(
                            rerouted=True,
                            avoided_flood_zone_ids=[z.event_id for z in primary_hits],
                            detour_waypoint_used=None,
                            distance_meters=int(r_alt.get("distanceMeters", 0)),
                            duration_seconds=_parse_duration_seconds(r_alt.get("duration")),
                            encoded_polyline=r_alt.get("polyline", {}).get(
                                "encodedPolyline", ""
                            ),
                            route_coordinates=coords_alt,
                            warning_message=(
                                f"Đã chuyển sang tuyến thay thế an toàn, né {len(primary_hits)} điểm ngập."
                            ),
                        )

                # Layer 2: Try left & right perpendicular `via` detour waypoints
                target_zone = primary_hits[0]
                offset_m = max(300.0, target_zone.radius_meters + 220.0)
                candidates = compute_detour_candidates(
                    req.origin, req.destination, target_zone, offset_meters=offset_m
                )
                best_safe: tuple[dict[str, Any], list[LatLng], LatLng] | None = None
                for cand in candidates:
                    detour_routes = await _call_routes_api_v2(
                        req.origin,
                        req.destination,
                        travel_mode=req.travel_mode,
                        via_waypoint=cand,
                    )
                    if not detour_routes:
                        continue
                    r_det = detour_routes[0]
                    coords_det = decode_encoded_polyline(
                        r_det.get("polyline", {}).get("encodedPolyline", "")
                    )
                    if not find_intersecting_flood_zones(coords_det, active_zones):
                        dist = int(r_det.get("distanceMeters", 0))
                        if best_safe is None or dist < int(
                            best_safe[0].get("distanceMeters", 10**9)
                        ):
                            best_safe = (r_det, coords_det, cand)

                if best_safe is not None:
                    r_best, coords_best, wp_best = best_safe
                    return RouteResponse(
                        rerouted=True,
                        avoided_flood_zone_ids=[z.event_id for z in primary_hits],
                        detour_waypoint_used=wp_best,
                        distance_meters=int(r_best.get("distanceMeters", 0)),
                        duration_seconds=_parse_duration_seconds(r_best.get("duration")),
                        encoded_polyline=r_best.get("polyline", {}).get(
                            "encodedPolyline", ""
                        ),
                        route_coordinates=coords_best,
                        warning_message=(
                            f"Đã tự động bẻ hướng né {len(primary_hits)} điểm ngập ({target_zone.location_name or target_zone.event_id})."
                        ),
                    )
        except Exception as exc:
            logger.warning("Google Routes API v2 call failed: %s", exc)
            if not settings.USE_MOCK_FALLBACK:
                raise RuntimeError(f"Google Routes API v2 call failed: {exc}") from exc
    elif not settings.USE_MOCK_FALLBACK:
        raise RuntimeError(
            "GOOGLE_MAPS_API_KEY is not configured while USE_MOCK_FALLBACK=false."
        )

    # Deterministic geometry fallback (USE_MOCK_FALLBACK=true)
    direct_coords = [req.origin, req.destination]
    hit_zones = (
        find_intersecting_flood_zones(direct_coords, active_zones)
        if req.avoid_flood_zones
        else []
    )

    detour_wp: LatLng | None = None
    if hit_zones:
        candidates = compute_detour_candidates(
            req.origin,
            req.destination,
            hit_zones[0],
            offset_meters=max(350.0, hit_zones[0].radius_meters + 220.0),
        )
        chosen = candidates[0]
        for cand in candidates:
            cand_path = [req.origin, cand, req.destination]
            if not find_intersecting_flood_zones(cand_path, active_zones):
                chosen = cand
                break
        detour_wp = chosen
        route_coords = [req.origin, detour_wp, req.destination]
    else:
        route_coords = direct_coords

    total_dist = 0.0
    for i in range(len(route_coords) - 1):
        total_dist += haversine_meters(route_coords[i], route_coords[i + 1])
    dist_int = max(100, int(total_dist * 1.2))
    dur_int = max(30, int(dist_int / 8.33))

    warning_msg = (
        f"Đã tự động bẻ hướng né {len(hit_zones)} điểm ngập ({hit_zones[0].location_name or hit_zones[0].event_id})."
        if hit_zones
        else None
    )

    return RouteResponse(
        rerouted=bool(hit_zones),
        avoided_flood_zone_ids=[z.event_id for z in hit_zones],
        detour_waypoint_used=detour_wp,
        distance_meters=dist_int,
        duration_seconds=dur_int,
        encoded_polyline="",
        route_coordinates=route_coords,
        warning_message=warning_msg,
    )
