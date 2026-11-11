"""
Reproducible CLI diagnostic for traffic camera snapshot extraction and JPEG verification.
Usage:
    python scripts/repro_camera_fetch.py [optional_snapshot_url]
"""

from __future__ import annotations

import asyncio
import io
import sys
from pathlib import Path
from PIL import Image

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "ai-vision"))

from src.camera_extractor import fetch_camera_snapshot


def _verify_image_bytes(raw: bytes) -> tuple[bool, tuple[int, int] | None]:
    try:
        with Image.open(io.BytesIO(raw)) as img:
            return True, img.size
    except Exception:
        return False, None


async def main() -> None:
    if len(sys.argv) > 1:
        url = sys.argv[1]
        print(f"Fetching live snapshot from: {url}")
        raw = await fetch_camera_snapshot(url)
        if not raw:
            print("[WARN] Snapshot unavailable (blocked/CORS/timeout/non-image).")
            raise SystemExit(0)
        ok, size = _verify_image_bytes(raw)
        print(f"[OK] Image valid={ok}, dimensions={size}, bytes={len(raw)}")
    else:
        # Deterministic local validation using an in-memory JPEG frame
        buf = io.BytesIO()
        Image.new("RGB", (640, 360), color=(30, 50, 70)).save(buf, format="JPEG")
        ok, size = _verify_image_bytes(buf.getvalue())
        print("=== Camera Extractor Repro (Local Verification) ===")
        print(f"[OK] Local JPEG decode check: valid={ok}, dimensions={size}")
        print("Pass an explicit snapshot URL as argv[1] to test a live HTTP camera feed.")


if __name__ == "__main__":
    asyncio.run(main())
