"""
Contract and Mock-Fallback Tests for AI Vision and FastAPI Endpoints.
Run from repo root:
    python -m unittest tests/test_ai_and_contracts.py -v
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "ai-vision"))
sys.path.insert(0, str(ROOT_DIR / "backend"))

from fastapi.testclient import TestClient
from src.analyzer import analyze_flood_image
from src.schemas import FloodAnalysisResult
from app.main import app


class TestAIVisionAndContracts(unittest.TestCase):
    def setUp(self) -> None:
        self._prev_key = os.environ.get("GEMINI_API_KEY")
        self._prev_mock = os.environ.get("USE_MOCK_FALLBACK")
        os.environ["USE_MOCK_FALLBACK"] = "true"
        os.environ["GEMINI_API_KEY"] = "your_gemini_api_key"

    def tearDown(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
