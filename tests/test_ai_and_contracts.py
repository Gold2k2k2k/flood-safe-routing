"""
Contract, Image Preprocessing, Frame Delta, and FastAPI Endpoint Tests.
Run from repo root:
    python -m unittest tests/test_ai_and_contracts.py -v
"""

from __future__ import annotations

import io
import os
import sys
import unittest
from pathlib import Path
from PIL import Image

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "ai-vision"))
sys.path.insert(0, str(ROOT_DIR / "backend"))

from fastapi.testclient import TestClient
from src.analyzer import analyze_flood_image, preprocess_image_bytes
from src.camera_extractor import clear_camera_frame_cache, compute_frame_delta
from src.schemas import FloodAnalysisResult
from app.main import app
from app.services import firebase_service


def _png_bytes(width: int, height: int, color: tuple[int, int, int]) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=color).save(buf, format="PNG")
    return buf.getvalue()


class TestAIVisionAndContracts(unittest.TestCase):
    def setUp(self) -> None:
        self._prev_key = os.environ.get("GEMINI_API_KEY")
        self._prev_mock = os.environ.get("USE_MOCK_FALLBACK")
        os.environ["USE_MOCK_FALLBACK"] = "true"
        os.environ["GEMINI_API_KEY"] = "your_gemini_api_key"
        firebase_service._IN_MEMORY_ZONES = None
        firebase_service._IN_MEMORY_HEATMAP = None
        clear_camera_frame_cache()

    def tearDown(self) -> None:
        firebase_service._IN_MEMORY_ZONES = None
        firebase_service._IN_MEMORY_HEATMAP = None
        clear_camera_frame_cache()
        if self._prev_key is None:
            os.environ.pop("GEMINI_API_KEY", None)
        else:
            os.environ["GEMINI_API_KEY"] = self._prev_key
        if self._prev_mock is None:
            os.environ.pop("USE_MOCK_FALLBACK", None)
        else:
            os.environ["USE_MOCK_FALLBACK"] = self._prev_mock

    def test_mock_analyzer_conforms_to_schema_across_levels(self) -> None:
        safe = analyze_flood_image(b"fake-bytes", mock_severity_hint=0)
        self.assertIsInstance(safe, FloodAnalysisResult)
        self.assertFalse(safe.flood_detected)
        self.assertTrue(safe.passable_for_motorbike)

        moderate = analyze_flood_image(b"fake-bytes", mock_severity_hint=2)
        self.assertTrue(moderate.flood_detected)
        self.assertEqual(moderate.severity_level, 2)
        self.assertFalse(moderate.passable_for_motorbike)

    def test_preprocess_image_bytes_downscales_large_image(self) -> None:
        huge_png = _png_bytes(2000, 1500, (80, 90, 100))
        processed, mime = preprocess_image_bytes(huge_png, max_dim=1024)
        self.assertEqual(mime, "image/jpeg")
        with Image.open(io.BytesIO(processed)) as out_img:
            self.assertLessEqual(max(out_img.size), 1024)

    def test_compute_frame_delta_detects_static_vs_changed_frames(self) -> None:
        black = _png_bytes(64, 64, (0, 0, 0))
        white = _png_bytes(64, 64, (255, 255, 255))
        self.assertEqual(compute_frame_delta(black, black), 0.0)
        self.assertGreater(compute_frame_delta(black, white), 0.95)

    def test_fastapi_endpoints_match_data_contract(self) -> None:
        client = TestClient(app)

        health = client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        h_json = health.json()
        self.assertEqual(h_json["status"], "ok")
        self.assertIn("services", h_json)

        zones = client.get("/api/flood-zones")
        self.assertEqual(zones.status_code, 200)
        z_json = zones.json()
        self.assertGreaterEqual(z_json["count"], 1)

        cams = client.get("/api/cameras")
        self.assertEqual(cams.status_code, 200)
        self.assertGreaterEqual(cams.json()["count"], 1)

        poll = client.post(
            "/api/cameras/poll",
            json={"camera_ids": ["cam_hcm_001"], "mock_severity_hint": 2},
        )
        self.assertEqual(poll.status_code, 200)
        p_json = poll.json()
        self.assertEqual(p_json["polled_count"], 1)
        self.assertEqual(p_json["flooded_count"], 1)

        report = client.post(
            "/api/reports",
            json={
                "lat": 10.7862,
                "lng": 106.7085,
                "location_name": "Test Spot",
                "mock_severity_hint": 2,
            },
        )
        self.assertEqual(report.status_code, 200)
        rep_json = report.json()
        self.assertIn("report_id", rep_json)
        self.assertEqual(rep_json["analysis"]["severity_level"], 2)

        route = client.post(
            "/api/route",
            json={
                "origin": {"lat": 10.7800, "lng": 106.7030},
                "destination": {"lat": 10.7920, "lng": 106.7140},
                "travel_mode": "TWO_WHEELER",
                "avoid_flood_zones": True,
            },
        )
        self.assertEqual(route.status_code, 200)
        r_json = route.json()
        self.assertTrue(r_json["rerouted"])
        self.assertIn("evt_001", r_json["avoided_flood_zone_ids"])

        heatmap = client.get("/api/heatmap")
        self.assertEqual(heatmap.status_code, 200)
        self.assertGreaterEqual(heatmap.json()["count"], 1)

    def test_camera_poll_frame_delta_deduplication_and_force_refresh(self) -> None:
        client = TestClient(app)

        first = client.post("/api/cameras/poll", json={"camera_ids": ["cam_hcm_001"]})
        self.assertEqual(first.status_code, 200)
        r1 = first.json()["results"][0]
        self.assertEqual(r1["frame_source"], "local_image")
        self.assertFalse(r1["frame_delta_skipped"])
        self.assertEqual(r1["analysis"]["severity_level"], 2)

        second = client.post("/api/cameras/poll", json={"camera_ids": ["cam_hcm_001"]})
        self.assertEqual(second.status_code, 200)
        r2 = second.json()["results"][0]
        self.assertTrue(r2["frame_delta_skipped"])
        self.assertFalse(r2["broadcasted_to_firestore"])
        self.assertEqual(r2["analysis"]["severity_level"], 2)

        forced = client.post(
            "/api/cameras/poll",
            json={"camera_ids": ["cam_hcm_001"], "force_refresh": True},
        )
        self.assertEqual(forced.status_code, 200)
        self.assertFalse(forced.json()["results"][0]["frame_delta_skipped"])

    def test_multipart_form_report_and_heatmap_history_accumulation(self) -> None:
        client = TestClient(app)

        initial_heat = client.get("/api/heatmap").json()["items"]
        nhc_before = next(h for h in initial_heat if h["zone_id"] == "hcm_binh_thanh_nhc")
        self.assertEqual(nhc_before["flood_frequency_30d"], 16)

        img_file = _png_bytes(320, 240, (110, 90, 70))
        resp = client.post(
            "/api/reports",
            data={
                "lat": "10.7859",
                "lng": "106.7083",
                "location_name": "Nguyễn Hữu Cảnh (cạnh cầu vượt)",
                "reporter_note": "Ngập sâu lút ống xả",
                "mock_severity_hint": "3",
            },
            files={"image": ("flood_scene.png", img_file, "image/png")},
        )
        self.assertEqual(resp.status_code, 200)
        rep = resp.json()
        self.assertEqual(rep["analysis"]["severity_level"], 3)

        updated_heat = client.get("/api/heatmap").json()["items"]
        nhc_after = next(h for h in updated_heat if h["zone_id"] == "hcm_binh_thanh_nhc")
        self.assertEqual(nhc_after["flood_frequency_30d"], 17)
        expected_avg = round((16 * 2.4 + 3.0) / 17.0, 2)
        self.assertEqual(nhc_after["avg_severity"], expected_avg)
        self.assertEqual(nhc_after["weight"], round(17 * expected_avg, 2))

    def test_flood_zone_delete_and_reset_demo_lifecycle(self) -> None:
        client = TestClient(app)

        del_resp = client.delete("/api/flood-zones/evt_001")
        self.assertEqual(del_resp.status_code, 200)
        self.assertTrue(del_resp.json()["deleted"])

        route_clear = client.post(
            "/api/route",
            json={
                "origin": {"lat": 10.7800, "lng": 106.7030},
                "destination": {"lat": 10.7920, "lng": 106.7140},
                "travel_mode": "TWO_WHEELER",
                "avoid_flood_zones": True,
            },
        )
        self.assertEqual(route_clear.status_code, 200)
        self.assertFalse(route_clear.json()["rerouted"])

        reset_resp = client.post("/api/flood-zones/reset", json={})
        self.assertEqual(reset_resp.status_code, 200)
        ids_after_reset = [z["event_id"] for z in reset_resp.json()["items"]]
        self.assertIn("evt_001", ids_after_reset)

    def test_mock_disabled_returns_503_when_keys_missing(self) -> None:
        os.environ["USE_MOCK_FALLBACK"] = "false"
        client = TestClient(app)
        resp = client.post(
            "/api/reports",
            json={"lat": 10.78, "lng": 106.70, "mock_severity_hint": 2},
        )
        self.assertEqual(resp.status_code, 503)


if __name__ == "__main__":
    unittest.main()
