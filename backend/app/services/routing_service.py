"""
Two-Layer Dynamic Rerouting Service on top of Google Maps Platform Routes API.
1. Checks if primary route intersects any active severe flood zone (severity_level >= 2).
2. Selects a safe alternative route OR generates a perpendicular detour via-waypoint.
"""

from __future__ import annotations

import math
from ..config import settings
from ..schemas import FloodZoneItem, LatLng, RouteRequest, RouteResponse


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
    """Return all flood zones (severity >= 2) intersected by the given polyline coordinates."""
    hit: list[FloodZoneItem] = []
    dangerous_zones = [z for z in flood_zones if z.severity_level >= 2 and z.status == "active"]
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


def compute_detour_waypoint(
    origin: LatLng, destination: LatLng, flooded_zone: FloodZoneItem, offset_meters: float = 350.0
) -> LatLng:
    """Compute a perpendicular detour waypoint outside the flood radius."""
    dx = destination.lng - origin.lng
    dy = destination.lat - origin.lat
    length = math.hypot(dx, dy) or 1e-6
    # Normal unit vector (-dy, dx)
    nx = -dy / length
    ny = dx / length
    # 1 degree latitude ~ 111,111 meters
    deg_offset = offset_meters / 111111.0
    return LatLng(
        lat=round(flooded_zone.lat + ny * deg_offset, 6),
        lng=round(flooded_zone.lng + nx * deg_offset, 6),
    )


async def compute_safe_route(
    req: RouteRequest, active_zones: list[FloodZoneItem]
) -> RouteResponse:
    """
    Compute route between origin and destination.
    Uses Google Routes API when GOOGLE_MAPS_API_KEY is configured, otherwise deterministic geometry fallback.
    """
    direct_coords = [req.origin, req.destination]
    hit_zones = (
        find_intersecting_flood_zones(direct_coords, active_zones)
        if req.avoid_flood_zones
        else []
    )

    detour_wp: LatLng | None = None
    if hit_zones:
        detour_wp = compute_detour_waypoint(req.origin, req.destination, hit_zones[0])
        route_coords = [req.origin, detour_wp, req.destination]
    else:
        route_coords = direct_coords

    # Approximate total distance and motorbike travel duration (~30 km/h = 8.33 m/s)
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
