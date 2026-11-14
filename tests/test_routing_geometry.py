"""
Deterministic geometry, Google Routes API v2 constraint, and dynamic rerouting tests.
Run from repo root:
    python -m unittest tests/test_routing_geometry.py -v
"""

from __future__ import annotations

import asyncio
import math
import os
import sys
import unittest
from pathlib import Path

import httpx

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "backend"))

from app.schemas import FloodZoneItem, LatLng, RouteRequest
from app.services.routing_service import (
    _call_osrm_street_routes,
    build_routes_api_v2_payload,
    compute_detour_candidates,
    compute_detour_waypoint,
    compute_safe_route,
    decode_encoded_polyline,
    find_intersecting_flood_zones,
    haversine_meters,
    point_to_segment_distance_meters,
)


def _sample_flood_zone(
    severity: int = 2,
    status: str = "active",
    lat: float = 10.7858,
    lng: float = 106.7082,
) -> FloodZoneItem:
    return FloodZoneItem(
        event_id="evt_test_nhc",
        source="camera_ai",
        camera_id="cam_hcm_001",
        location_name="Ngã tư Nguyễn Hữu Cảnh - Tôn Đức Thắng",
        lat=lat,
        lng=lng,
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
    def setUp(self) -> None:
        self._prev_osrm = os.environ.get("USE_OSRM_STREET_FALLBACK")
        os.environ["USE_OSRM_STREET_FALLBACK"] = "false"

    def tearDown(self) -> None:
        if self._prev_osrm is None:
            os.environ.pop("USE_OSRM_STREET_FALLBACK", None)
        else:
            os.environ["USE_OSRM_STREET_FALLBACK"] = self._prev_osrm

    def test_haversine_symmetry_and_sanity(self) -> None:
        p1 = LatLng(lat=10.7769, lng=106.7009)
        p2 = LatLng(lat=10.7992, lng=106.7185)
        dist = haversine_meters(p1, p2)
        self.assertGreater(dist, 2500.0)
        self.assertLess(dist, 4000.0)
        self.assertAlmostEqual(dist, haversine_meters(p2, p1), places=4)

    def test_intersection_detects_severe_flood_on_segment(self) -> None:
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

    def test_detour_candidates_cover_both_sides_and_scale_with_cos_lat(self) -> None:
        origin = LatLng(lat=21.0000, lng=105.8000)
        dest = LatLng(lat=21.0200, lng=105.8000)  # Pure North-South -> normal is East-West
        zone = _sample_flood_zone(severity=2, lat=21.0100, lng=105.8000)
        cands = compute_detour_candidates(origin, dest, zone, offset_meters=350.0)
        self.assertEqual(len(cands), 2)
        for cand in cands:
            dist = haversine_meters(cand, LatLng(lat=zone.lat, lng=zone.lng))
            self.assertAlmostEqual(dist, 350.0, delta=15.0)
        # Opposite sides across longitude
        self.assertAlmostEqual(cands[0].lng - zone.lng, -(cands[1].lng - zone.lng), places=5)
        self.assertGreater(abs(cands[0].lng - zone.lng), 350.0 / 111111.0 / math.cos(math.radians(21.0)) * 0.9)

    def test_detour_waypoint_lies_outside_flood_radius(self) -> None:
        origin = LatLng(lat=10.7800, lng=106.7030)
        dest = LatLng(lat=10.7920, lng=106.7140)
        zone = _sample_flood_zone(severity=2)
        detour = compute_detour_waypoint(origin, dest, zone, offset_meters=350.0)
        dist_from_flood_center = haversine_meters(
            detour, LatLng(lat=zone.lat, lng=zone.lng)
        )
        self.assertGreater(dist_from_flood_center, zone.radius_meters)

    def test_routes_api_v2_payload_never_violates_google_constraints(self) -> None:
        origin = LatLng(lat=10.7769, lng=106.7009)
        dest = LatLng(lat=10.7992, lng=106.7185)

        layer1 = build_routes_api_v2_payload(origin, dest, travel_mode="TWO_WHEELER")
        self.assertTrue(layer1["computeAlternativeRoutes"])
        self.assertNotIn("intermediates", layer1)
        self.assertEqual(layer1["travelMode"], "TWO_WHEELER")

        via = LatLng(lat=10.7885, lng=106.7020)
        layer2 = build_routes_api_v2_payload(
            origin, dest, travel_mode="TWO_WHEELER", via_waypoint=via
        )
        self.assertNotIn("computeAlternativeRoutes", layer2)
        self.assertNotIn("optimizeWaypointOrder", layer2)
        self.assertEqual(len(layer2["intermediates"]), 1)
        inter = layer2["intermediates"][0]
        self.assertTrue(inter["via"])
        self.assertIn("latLng", inter["location"])
        self.assertNotIn("location", inter["location"])

    def test_polyline_decoder_standard_vector(self) -> None:
        pts = decode_encoded_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@")
        self.assertEqual(len(pts), 3)
        self.assertAlmostEqual(pts[0].lat, 38.5, places=4)
        self.assertAlmostEqual(pts[0].lng, -120.2, places=4)
        self.assertAlmostEqual(pts[2].lat, 43.252, places=3)
        self.assertAlmostEqual(pts[2].lng, -126.453, places=3)

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

        center = LatLng(lat=zone.lat, lng=zone.lng)
        for i in range(len(res.route_coordinates) - 1):
            seg_dist = point_to_segment_distance_meters(
                center, res.route_coordinates[i], res.route_coordinates[i + 1]
            )
            self.assertGreater(seg_dist, zone.radius_meters)

    def test_multi_zone_consecutive_flood_detour_and_baseline_coordinates(self) -> None:
        req = RouteRequest(
            origin=LatLng(lat=10.7795, lng=106.7010),
            destination=LatLng(lat=10.8065, lng=106.7315),
            travel_mode="TWO_WHEELER",
            avoid_flood_zones=True,
        )
        z1 = FloodZoneItem(
            event_id="evt_001",
            source="camera_ai",
            camera_id="cam_hcm_001",
            location_name="Ngã tư Nguyễn Hữu Cảnh - Tôn Đức Thắng",
            lat=10.7858,
            lng=106.7082,
            radius_meters=120.0,
            severity_level=2,
            visual_cue="Ngập nửa bánh xe máy",
            estimated_depth_cm="20-35",
            passable_for_motorbike=False,
            confidence=0.91,
            vision_model="gemini-3.8-flash",
            status="active",
            updated_at="2026-11-14T08:00:00+07:00",
        )
        z2 = FloodZoneItem(
            event_id="evt_hcm_002",
            source="camera_ai",
            camera_id="cam_hcm_002",
            location_name="Đường Quốc Hương - Xuân Thủy (Thảo Điền)",
            lat=10.8032,
            lng=106.7280,
            radius_meters=130.0,
            severity_level=3,
            visual_cue="Ngập sâu lút bánh xe",
            estimated_depth_cm=">35",
            passable_for_motorbike=False,
            confidence=0.94,
            vision_model="gemini-3.8-flash",
            status="active",
            updated_at="2026-11-14T08:00:00+07:00",
        )

        res = asyncio.run(compute_safe_route(req, [z1, z2]))
        self.assertTrue(res.rerouted)
        self.assertEqual(res.baseline_route_coordinates, [req.origin, req.destination])
        self.assertIn("evt_001", res.avoided_flood_zone_ids)
        self.assertIn("evt_hcm_002", res.avoided_flood_zone_ids)
        self.assertGreaterEqual(len(res.detour_waypoints_used), 2)
        self.assertEqual(res.detour_waypoint_used, res.detour_waypoints_used[0])
        self.assertEqual(
            find_intersecting_flood_zones(res.route_coordinates, [z1, z2]), []
        )

    def test_secondary_adjacent_zone_avoided_during_detour(self) -> None:
        origin = LatLng(lat=10.7800, lng=106.7000)
        dest = LatLng(lat=10.7800, lng=106.7200)
        primary_zone = _sample_flood_zone(severity=2, lat=10.7800, lng=106.7100)
        # Place a second flooded zone directly on the +offset (North) perpendicular detour spot
        cands = compute_detour_candidates(origin, dest, primary_zone, offset_meters=370.0)
        blocked_side = cands[0]
        adjacent_zone = FloodZoneItem(
            event_id="evt_adjacent_block",
            source="camera_ai",
            location_name="Điểm ngập lân cận phía Bắc",
            lat=blocked_side.lat,
            lng=blocked_side.lng,
            radius_meters=150.0,
            severity_level=3,
            visual_cue="Ngập sâu lút ống xả",
            estimated_depth_cm=">35",
            passable_for_motorbike=False,
            confidence=0.95,
            vision_model="gemini-3.8-flash",
            status="active",
            updated_at="2026-11-14T08:00:00+07:00",
        )

        req = RouteRequest(origin=origin, destination=dest, avoid_flood_zones=True)
        res = asyncio.run(compute_safe_route(req, [primary_zone, adjacent_zone]))
        self.assertTrue(res.rerouted)
        self.assertEqual(
            find_intersecting_flood_zones(
                res.route_coordinates, [primary_zone, adjacent_zone]
            ),
            [],
        )

    def test_routes_api_v2_multi_via_waypoints_payload_constraints(self) -> None:
        origin = LatLng(lat=10.7795, lng=106.7010)
        dest = LatLng(lat=10.8065, lng=106.7315)
        wps = [LatLng(lat=10.7837, lng=106.7106), LatLng(lat=10.8009, lng=106.7305)]
        payload = build_routes_api_v2_payload(origin, dest, via_waypoints=wps)
        self.assertNotIn("computeAlternativeRoutes", payload)
        self.assertNotIn("optimizeWaypointOrder", payload)
        self.assertEqual(len(payload["intermediates"]), 2)
        for inter in payload["intermediates"]:
            self.assertTrue(inter["via"])
            self.assertIn("latLng", inter["location"])
            self.assertNotIn("location", inter["location"])

    def test_compute_safe_route_raises_when_mock_disabled_and_key_missing(self) -> None:
        prev_mock = os.environ.get("USE_MOCK_FALLBACK")
        prev_key = os.environ.get("GOOGLE_MAPS_API_KEY")
        os.environ["USE_MOCK_FALLBACK"] = "false"
        os.environ["GOOGLE_MAPS_API_KEY"] = "your_google_maps_server_api_key"
        try:
            req = RouteRequest(
                origin=LatLng(lat=10.7800, lng=106.7030),
                destination=LatLng(lat=10.7920, lng=106.7140),
            )
            with self.assertRaises(RuntimeError):
                asyncio.run(compute_safe_route(req, []))
        finally:
            if prev_mock is None:
                os.environ.pop("USE_MOCK_FALLBACK", None)
            else:
                os.environ["USE_MOCK_FALLBACK"] = prev_mock
            if prev_key is None:
                os.environ.pop("GOOGLE_MAPS_API_KEY", None)
            else:
                os.environ["GOOGLE_MAPS_API_KEY"] = prev_key


    def test_osrm_street_routes_normalization_with_mock_transport(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertIn("/route/v1/driving/", request.url.path)
            return httpx.Response(
                200,
                json={
                    "code": "Ok",
                    "routes": [
                        {
                            "distance": 3120.4,
                            "duration": 290.0,
                            "geometry": "_p~iF~ps|U_ulLnnqC_mqNvxq`@",
                        }
                    ],
                },
            )

        res = asyncio.run(
            _call_osrm_street_routes(
                LatLng(lat=10.78, lng=106.703),
                LatLng(lat=10.792, lng=106.714),
                travel_mode="TWO_WHEELER",
                http_transport=httpx.MockTransport(handler),
            )
        )
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["distanceMeters"], 3120)
        self.assertEqual(res[0]["polyline"]["encodedPolyline"], "_p~iF~ps|U_ulLnnqC_mqNvxq`@")


if __name__ == "__main__":
    unittest.main()
