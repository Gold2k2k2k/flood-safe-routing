"""
Deterministic geometry & dynamic rerouting tests.
Run from repo root:
    python -m unittest tests/test_routing_geometry.py -v
"""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "backend"))

from app.schemas import FloodZoneItem, LatLng, RouteRequest
from app.services.routing_service import (
    compute_detour_waypoint,
    compute_safe_route,
    find_intersecting_flood_zones,
    haversine_meters,
    point_to_segment_distance_meters,
)


def _sample_flood_zone(severity: int = 2, status: str = "active") -> FloodZoneItem:
    return FloodZoneItem(
        event_id="evt_test_nhc",
        source="camera_ai",
        camera_id="cam_hcm_001",
        location_name="Ngã tư Nguyễn Hữu Cảnh - Tôn Đức Thắng",
        lat=10.7858,
        lng=106.7082,
        radius_meters=120.0,
        severity_level=severity,
        visual_cue="Nước ngập nửa bánh xe máy",
        estimated_depth_cm="20-35",
        passable_for_motorbike=severity < 2,
        confidence=0.92,
        vision_model="gemini-3.8-flash",
        status=status,
        updated_at="2026-11-11T10:00:00+07:00",
    )


class TestRoutingGeometry(unittest.TestCase):
    def test_haversine_symmetry_and_sanity(self) -> None:
        p1 = LatLng(lat=10.7769, lng=106.7009)
        p2 = LatLng(lat=10.7992, lng=106.7185)
        dist = haversine_meters(p1, p2)
        self.assertGreater(dist, 2500.0)
        self.assertLess(dist, 4000.0)
        self.assertAlmostEqual(dist, haversine_meters(p2, p1), places=4)

    def test_intersection_detects_severe_flood_on_segment(self) -> None:
        # Line passing almost straight through (10.7858, 106.7082)
        coords = [
            LatLng(lat=10.7800, lng=106.7030),
            LatLng(lat=10.7920, lng=106.7140),
        ]
        zone = _sample_flood_zone(severity=2)
        hits = find_intersecting_flood_zones(coords, [zone])
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].event_id, "evt_test_nhc")

    def test_minor_flood_level_1_does_not_force_reroute_block(self) -> None:
        coords = [
            LatLng(lat=10.7800, lng=106.7030),
            LatLng(lat=10.7920, lng=106.7140),
        ]
        minor_zone = _sample_flood_zone(severity=1)
        hits = find_intersecting_flood_zones(coords, [minor_zone])
        self.assertEqual(hits, [])

    def test_detour_waypoint_lies_outside_flood_radius(self) -> None:
        origin = LatLng(lat=10.7800, lng=106.7030)
        dest = LatLng(lat=10.7920, lng=106.7140)
        zone = _sample_flood_zone(severity=2)
        detour = compute_detour_waypoint(origin, dest, zone, offset_meters=350.0)
        dist_from_flood_center = haversine_meters(
            detour, LatLng(lat=zone.lat, lng=zone.lng)
        )
        self.assertGreater(dist_from_flood_center, zone.radius_meters)

    def test_compute_safe_route_reroutes_around_flood(self) -> None:
        req = RouteRequest(
            origin=LatLng(lat=10.7800, lng=106.7030),
            destination=LatLng(lat=10.7920, lng=106.7140),
            travel_mode="TWO_WHEELER",
            avoid_flood_zones=True,
        )
        zone = _sample_flood_zone(severity=2)
        res = asyncio.run(compute_safe_route(req, [zone]))
        self.assertTrue(res.rerouted)
        self.assertIn("evt_test_nhc", res.avoided_flood_zone_ids)
        self.assertIsNotNone(res.detour_waypoint_used)
        self.assertEqual(len(res.route_coordinates), 3)

        # Ensure resulting detour segments stay outside flood radius
        center = LatLng(lat=zone.lat, lng=zone.lng)
        for i in range(len(res.route_coordinates) - 1):
            seg_dist = point_to_segment_distance_meters(
                center, res.route_coordinates[i], res.route_coordinates[i + 1]
            )
            self.assertGreater(seg_dist, zone.radius_meters)


if __name__ == "__main__":
    unittest.main()
