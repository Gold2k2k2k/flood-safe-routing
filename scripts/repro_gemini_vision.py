"""
Reproducible CLI script for Gemini 3.8 Flash (Vision) Flood Analysis.
Usage:
    python scripts/repro_gemini_vision.py [optional_path_to_image.jpg]
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from PIL import Image

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "ai-vision"))

from src.analyzer import analyze_flood_image


def _create_synthetic_jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (320, 240), color=(40, 60, 80))
    img.save(buf, format="JPEG")
    return buf.getvalue()


def main() -> None:
    if len(sys.argv) > 1:
        img_path = Path(sys.argv[1])
        if not img_path.exists():
            print(f"[ERROR] Image file not found: {img_path}")
            raise SystemExit(1)
        image_bytes = img_path.read_bytes()
        source_label = str(img_path)
    else:
        image_bytes = _create_synthetic_jpeg_bytes()
        source_label = "<synthetic-test-frame>"

    result = analyze_flood_image(image_bytes=image_bytes, mock_severity_hint=2)
    print(f"=== AI Flood Vision Repro ({source_label}) ===")
    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
