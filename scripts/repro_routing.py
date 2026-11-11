"""
Reproducible CLI script demonstrating Two-Layer Flood-Safe Rerouting
against active flood zones loaded from data/flood_events.sample.geojson.
Usage:
    python scripts/repro_routing.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "backend"))

from app.schemas import LatLng, RouteRequest
from app.services.firebase_service import get_active_flood_zones
from app.services.routing_service import compute_safe_route


async def main() -> None:
    zones = get_active_flood_zones()
    req = RouteRequest(
        origin=LatLng(lat=10.7800, lng=106.7030),
        destination=LatLng(lat=10.7920, lng=106.7140),
        travel_mode="TWO_WHEELER",
        avoid_flood_zones=True,
    )
    res = await compute_safe_route(req, zones)
    print("=== Flood-Safe Routing Repro Output ===")
    print(f"Active flood zones loaded: {len(zones)}")
    print(json.dumps(res.model_dump(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
