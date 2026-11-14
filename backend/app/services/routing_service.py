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
    preferred_side: float = 1.0,
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

    signs = (1.0, -1.0) if preferred_side >= 0 else (-1.0, 1.0)
    candidates: list[LatLng] = []
    for sign in signs:
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
    via_waypoints: list[LatLng] | None = None,
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
    wps: list[LatLng] = []
    if via_waypoints:
        wps.extend(via_waypoints)
    elif via_waypoint is not None:
        wps.append(via_waypoint)

    if wps:
        body["intermediates"] = [
            {
                "location": {
                    "latLng": {
                        "latitude": wp.lat,
                        "longitude": wp.lng,
                    }
                },
                "via": True,
            }
            for wp in wps
        ]
    else:
        body["computeAlternativeRoutes"] = True
    return body


def _parse_duration_seconds(duration_str: str | None) -> int:
    if not duration_str:
        return 0
    try:
        return int(float(duration_str.rstrip("s")))
    except Exception as exc:
        logger.warning("Unexpected Routes API duration '%s': %s", duration_str, exc)
        return 0


async def _call_routes_api_v2(
    origin: LatLng,
    destination: LatLng,
    travel_mode: str = "TWO_WHEELER",
    via_waypoint: LatLng | None = None,
    via_waypoints: list[LatLng] | None = None,
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
        via_waypoints=via_waypoints,
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(ROUTES_API_V2_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    return data.get("routes", [])


def compute_multi_zone_detour_waypoints(
    origin: LatLng,
    destination: LatLng,
    hit_zones: list[FloodZoneItem],
    all_active_zones: list[FloodZoneItem],
    preferred_side: float = 1.0,
    extra_offset_meters: float = 0.0,
) -> list[LatLng]:
    """
    Iteratively compute perpendicular left/right detour waypoints outside all dangerous flood zones
    (severity >= 2), handling consecutive flood zones as well as secondary adjacent flood zones
    encountered while detouring.
    """
    if not hit_zones:
        return []

    dangerous_zones = [
        z for z in all_active_zones if z.severity_level >= 2 and z.status == "active"
    ]
    if not dangerous_zones:
        dangerous_zones = [
            z for z in hit_zones if z.severity_level >= 2 and z.status == "active"
        ]

    detour_wps: list[LatLng] = []
    max_passes = 6

    for _ in range(max_passes):
        curr_path = [origin] + detour_wps + [destination]
        if not find_intersecting_flood_zones(curr_path, dangerous_zones):
            break

        # Locate the first segment along curr_path that intersects any dangerous flood zone
        target_seg_idx: int | None = None
        target_zone: FloodZoneItem | None = None
        for seg_idx in range(len(curr_path) - 1):
            seg_hits = find_intersecting_flood_zones(
                [curr_path[seg_idx], curr_path[seg_idx + 1]], dangerous_zones
            )
            if seg_hits:
                seg_hits.sort(
                    key=lambda z: haversine_meters(
                        curr_path[seg_idx], LatLng(lat=z.lat, lng=z.lng)
                    )
                )
                target_seg_idx = seg_idx
                target_zone = seg_hits[0]
                break

        if target_seg_idx is None or target_zone is None:
            break

        seg_a = curr_path[target_seg_idx]
        seg_b = curr_path[target_seg_idx + 1]

        offsets = (
            max(350.0, target_zone.radius_meters + 220.0) + extra_offset_meters,
            max(550.0, target_zone.radius_meters + 400.0) + extra_offset_meters,
            max(800.0, target_zone.radius_meters + 650.0) + extra_offset_meters,
        )

        # Nearby zones within 1 km of target_zone must be cleared immediately by this waypoint;
        # distant downstream zones (> 1 km away) are resolved by their own local waypoint in the next pass.
        target_center = LatLng(lat=target_zone.lat, lng=target_zone.lng)
        nearby_zones = [
            z
            for z in dangerous_zones
            if haversine_meters(target_center, LatLng(lat=z.lat, lng=z.lng)) <= 1000.0
        ]

        best_cand: LatLng | None = None

        for tier_idx, off in enumerate(offsets):
            raw_cands: list[tuple[LatLng, int]] = []
            c_global = compute_detour_candidates(
                origin,
                destination,
                target_zone,
                offset_meters=off,
                preferred_side=preferred_side,
            )
            for side_rank, c in enumerate(c_global):
                raw_cands.append((c, side_rank))

            if seg_a != origin or seg_b != destination:
                c_local = compute_detour_candidates(
                    seg_a,
                    seg_b,
                    target_zone,
                    offset_meters=off,
                    preferred_side=preferred_side,
                )
                for side_rank, c in enumerate(c_local):
                    raw_cands.append((c, side_rank))

            tier_cands: list[tuple[LatLng, int]] = []
            seen: set[tuple[float, float]] = set()
            for c, side_rank in raw_cands:
                key = (round(c.lat, 6), round(c.lng, 6))
                if key not in seen:
                    seen.add(key)
                    tier_cands.append((c, side_rank))

            tier_best: LatLng | None = None
            tier_best_score: tuple[int, int, int, float] = (
                999,
                999,
                999,
                float("inf"),
            )

            for cand, side_rank in tier_cands:
                # Candidate must genuinely clear target_zone on the local sub-segments
                if find_intersecting_flood_zones([seg_a, cand, seg_b], [target_zone]):
                    continue

                test_wps = (
                    detour_wps[:target_seg_idx] + [cand] + detour_wps[target_seg_idx:]
                )
                test_path = [origin] + test_wps + [destination]

                hits_nearby = len(
                    find_intersecting_flood_zones([seg_a, cand, seg_b], nearby_zones)
                )
                hits_total = len(
                    find_intersecting_flood_zones(test_path, dangerous_zones)
                )
                total_dist = sum(
                    haversine_meters(test_path[i], test_path[i + 1])
                    for i in range(len(test_path) - 1)
                )

                score = (hits_nearby, side_rank, hits_total, total_dist)
                if score < tier_best_score:
                    tier_best_score = score
                    tier_best = cand

            if tier_best is not None and tier_best_score[0] == 0:
                best_cand = tier_best
                break
            if best_cand is None and tier_best is not None:
                best_cand = tier_best

        if best_cand is None:
            break

        detour_wps.insert(target_seg_idx, best_cand)

    return detour_wps


def compute_multi_zone_detour_plans(
    origin: LatLng,
    destination: LatLng,
    hit_zones: list[FloodZoneItem],
    all_active_zones: list[FloodZoneItem],
) -> list[list[LatLng]]:
    """
    Generate distinct candidate `via` waypoint sequences (left corridor, right corridor,
    and wide bypass) for evaluation against Google Routes API v2 road networks.
    """
    plans: list[list[LatLng]] = []
    seen_signatures: set[tuple[tuple[float, float], ...]] = set()

    for side, extra_off in ((1.0, 0.0), (-1.0, 0.0), (1.0, 220.0), (-1.0, 220.0)):
        wps = compute_multi_zone_detour_waypoints(
            origin,
            destination,
            hit_zones,
            all_active_zones,
            preferred_side=side,
            extra_offset_meters=extra_off,
        )
        if not wps:
            continue
        sig = tuple((round(w.lat, 5), round(w.lng, 5)) for w in wps)
        if sig not in seen_signatures:
            seen_signatures.add(sig)
            plans.append(wps)

    return plans


def _format_reroute_warning(
    avoided_zones: list[FloodZoneItem], remaining_zones: list[FloodZoneItem]
) -> str:
    if avoided_zones and not remaining_zones:
        names = ", ".join(
            dict.fromkeys(z.location_name or z.event_id for z in avoided_zones[:2])
        )
        suffix = "..." if len(avoided_zones) > 2 else ""
        return f"Đã tự động bẻ hướng né {len(avoided_zones)} điểm ngập ({names}{suffix})."
    if avoided_zones and remaining_zones:
        return (
            f"Đã bẻ hướng giảm thiểu rủi ro (né {len(avoided_zones)} điểm ngập, "
            f"còn {len(remaining_zones)} điểm ngập gần điểm đầu/cuối cần chú ý)."
        )
    return (
        f"Cảnh báo: Không tìm được đường tránh hoàn toàn cho {len(remaining_zones)} điểm ngập trên lộ trình."
    )


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
                r0, coords0 = decoded_routes[0]
                baseline_coords = coords0 or [req.origin, req.destination]

                if not req.avoid_flood_zones:
                    return RouteResponse(
                        rerouted=False,
                        avoided_flood_zone_ids=[],
                        detour_waypoint_used=None,
                        detour_waypoints_used=[],
                        baseline_route_coordinates=baseline_coords,
                        distance_meters=int(r0.get("distanceMeters", 0)),
                        duration_seconds=_parse_duration_seconds(r0.get("duration")),
                        encoded_polyline=r0.get("polyline", {}).get("encodedPolyline", ""),
                        route_coordinates=baseline_coords,
                        warning_message=None,
                    )

                primary_hits = find_intersecting_flood_zones(
                    baseline_coords, active_zones
                )
                if not primary_hits:
                    return RouteResponse(
                        rerouted=False,
                        avoided_flood_zone_ids=[],
                        detour_waypoint_used=None,
                        detour_waypoints_used=[],
                        baseline_route_coordinates=baseline_coords,
                        distance_meters=int(r0.get("distanceMeters", 0)),
                        duration_seconds=_parse_duration_seconds(r0.get("duration")),
                        encoded_polyline=r0.get("polyline", {}).get("encodedPolyline", ""),
                        route_coordinates=baseline_coords,
                        warning_message=None,
                    )

                # Track best partial route in case destination itself sits inside a flood zone
                best_live_candidate: tuple[
                    int, int, dict[str, Any], list[LatLng], list[LatLng]
                ] = (
                    len(primary_hits),
                    int(r0.get("distanceMeters", 10**9)),
                    r0,
                    baseline_coords,
                    [],
                )

                # Layer 1: Check alternative routes returned by computeAlternativeRoutes=true
                for r_alt, coords_alt in decoded_routes[1:]:
                    alt_hits = find_intersecting_flood_zones(coords_alt, active_zones)
                    alt_dist = int(r_alt.get("distanceMeters", 10**9))
                    if not alt_hits:
                        return RouteResponse(
                            rerouted=True,
                            avoided_flood_zone_ids=[z.event_id for z in primary_hits],
                            detour_waypoint_used=None,
                            detour_waypoints_used=[],
                            baseline_route_coordinates=baseline_coords,
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
                    if (len(alt_hits), alt_dist) < (
                        best_live_candidate[0],
                        best_live_candidate[1],
                    ):
                        best_live_candidate = (
                            len(alt_hits),
                            alt_dist,
                            r_alt,
                            coords_alt,
                            [],
                        )

                # Layer 2: Evaluate perpendicular `via` detour plans (both sides & multi-zone)
                detour_plans = compute_multi_zone_detour_plans(
                    req.origin, req.destination, primary_hits, active_zones
                )
                best_safe_detour: tuple[
                    int, dict[str, Any], list[LatLng], list[LatLng]
                ] | None = None

                for plan_wps in detour_plans[:4]:
                    detour_routes = await _call_routes_api_v2(
                        req.origin,
                        req.destination,
                        travel_mode=req.travel_mode,
                        via_waypoints=plan_wps,
                    )
                    if not detour_routes:
                        continue
                    r_det = detour_routes[0]
                    coords_det = decode_encoded_polyline(
                        r_det.get("polyline", {}).get("encodedPolyline", "")
                    )
                    det_hits = find_intersecting_flood_zones(coords_det, active_zones)
                    det_dist = int(r_det.get("distanceMeters", 10**9))

                    if not det_hits:
                        if best_safe_detour is None or det_dist < best_safe_detour[0]:
                            best_safe_detour = (det_dist, r_det, coords_det, plan_wps)
                        # If both primary left & right corridors evaluated and at least one is clean, stop early
                        if len(detour_plans) <= 2 or best_safe_detour is not None:
                            if plan_wps == detour_plans[min(1, len(detour_plans) - 1)]:
                                break
                    elif (len(det_hits), det_dist) < (
                        best_live_candidate[0],
                        best_live_candidate[1],
                    ):
                        best_live_candidate = (
                            len(det_hits),
                            det_dist,
                            r_det,
                            coords_det,
                            plan_wps,
                        )

                if best_safe_detour is not None:
                    _, r_best, coords_best, wps_best = best_safe_detour
                    return RouteResponse(
                        rerouted=True,
                        avoided_flood_zone_ids=[z.event_id for z in primary_hits],
                        detour_waypoint_used=wps_best[0] if wps_best else None,
                        detour_waypoints_used=wps_best,
                        baseline_route_coordinates=baseline_coords,
                        distance_meters=int(r_best.get("distanceMeters", 0)),
                        duration_seconds=_parse_duration_seconds(r_best.get("duration")),
                        encoded_polyline=r_best.get("polyline", {}).get(
                            "encodedPolyline", ""
                        ),
                        route_coordinates=coords_best,
                        warning_message=_format_reroute_warning(primary_hits, []),
                    )

                # Best-effort live route when no completely flood-free corridor exists
                _, _, r_part, coords_part, wps_part = best_live_candidate
                rem_hits = find_intersecting_flood_zones(coords_part, active_zones)
                rem_ids = {z.event_id for z in rem_hits}
                avoided_zones = [z for z in primary_hits if z.event_id not in rem_ids]
                did_reroute = coords_part != baseline_coords
                return RouteResponse(
                    rerouted=did_reroute,
                    avoided_flood_zone_ids=[z.event_id for z in avoided_zones],
                    detour_waypoint_used=wps_part[0] if wps_part else None,
                    detour_waypoints_used=wps_part,
                    baseline_route_coordinates=baseline_coords,
                    distance_meters=int(r_part.get("distanceMeters", 0)),
                    duration_seconds=_parse_duration_seconds(r_part.get("duration")),
                    encoded_polyline=r_part.get("polyline", {}).get(
                        "encodedPolyline", ""
                    ),
                    route_coordinates=coords_part,
                    warning_message=_format_reroute_warning(avoided_zones, rem_hits),
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
    baseline_coords = list(direct_coords)
    hit_zones = (
        find_intersecting_flood_zones(direct_coords, active_zones)
        if req.avoid_flood_zones
        else []
    )

    detour_wps: list[LatLng] = []
    if hit_zones:
        detour_wps = compute_multi_zone_detour_waypoints(
            req.origin, req.destination, hit_zones, active_zones
        )
        route_coords = [req.origin] + detour_wps + [req.destination]
    else:
        route_coords = direct_coords

    rem_hits = (
        find_intersecting_flood_zones(route_coords, active_zones)
        if req.avoid_flood_zones
        else []
    )
    rem_ids = {z.event_id for z in rem_hits}
    all_hit_by_id = {z.event_id: z for z in hit_zones}
    avoided_zones = [z for z in hit_zones if z.event_id not in rem_ids]

    total_dist = 0.0
    for i in range(len(route_coords) - 1):
        total_dist += haversine_meters(route_coords[i], route_coords[i + 1])
    dist_int = max(100, int(total_dist * 1.2))
    dur_int = max(30, int(dist_int / 8.33))

    warning_msg = (
        _format_reroute_warning(avoided_zones, rem_hits)
        if all_hit_by_id
        else None
    )

    return RouteResponse(
        rerouted=bool(detour_wps),
        avoided_flood_zone_ids=[z.event_id for z in avoided_zones],
        detour_waypoint_used=detour_wps[0] if detour_wps else None,
        detour_waypoints_used=detour_wps,
        baseline_route_coordinates=baseline_coords,
        distance_meters=dist_int,
        duration_seconds=dur_int,
        encoded_polyline="",
        route_coordinates=route_coords,
        warning_message=warning_msg,
    )
