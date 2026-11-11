"""
Gemini 3.8 Flash (Vision) Flood Severity Analyzer.
Supports real multimodal inference via google-genai SDK and deterministic mock fallback.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from .schemas import FloodAnalysisLLMOutput, FloodAnalysisResult

SYSTEM_PROMPT = """Bạn là hệ thống AI chuyên phân tích hình ảnh giao thông đô thị tại Việt Nam (TP.HCM, Hà Nội, Đà Nẵng).
Hãy quan sát bức ảnh đường phố và xác định mức độ ngập nước dựa trên các vật chuẩn thực tế:
- Mức 0 (SAFE): Mặt đường khô hoặc chỉ ướt mặt nhựa, không đọng nước.
- Mức 1 (MINOR): Nước mới đọng sát mép vỉa hè / lề đường (< 15 cm), chưa ngập vành bánh xe máy -> passable_for_motorbike = true.
- Mức 2 (MODERATE): Nước ngập qua lề đường, chạm từ 1/3 đến nửa bánh xe máy (15-35 cm), nguy cơ chết máy cao -> passable_for_motorbike = false.
- Mức 3 (SEVERE): Nước ngập lút quá nửa bánh xe, chạm ống xả/yên xe (> 35 cm) -> passable_for_motorbike = false.
Trả về đúng định dạng JSON theo schema."""


def _is_mock_mode() -> bool:
    use_mock = os.getenv("USE_MOCK_FALLBACK", "true").lower() in ("true", "1", "yes")
    api_key = os.getenv("GEMINI_API_KEY", "")
    has_real_key = bool(api_key) and not api_key.startswith("your_")
    return use_mock and not has_real_key


def analyze_flood_image(
    image_bytes: bytes | None = None,
    mime_type: str = "image/jpeg",
    mock_severity_hint: int = 2,
) -> FloodAnalysisResult:
    """
    Analyze a street camera frame or crowdsourced photo with Gemini 3.8 Flash (Vision).
    Falls back to mock output when USE_MOCK_FALLBACK=true and GEMINI_API_KEY is not set.
    """
    model_name = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

    if _is_mock_mode() or not image_bytes:
        is_flooded = mock_severity_hint >= 1
        passable = mock_severity_hint < 2
        cue = (
            "Nước ngập quá mép lề đường và chạm khoảng nửa bánh xe máy (Mock Fallback)"
            if mock_severity_hint >= 2
            else "Mặt đường thông thoáng, xe máy di chuyển bình thường (Mock Fallback)"
        )
        depth = "20-35" if mock_severity_hint == 2 else (">35" if mock_severity_hint >= 3 else "0-10")
        return FloodAnalysisResult(
            flood_detected=is_flooded,
            severity_level=mock_severity_hint,
            visual_cue=cue,
            estimated_depth_cm=depth,
            passable_for_motorbike=passable,
            confidence=0.91,
            vision_model=f"{model_name} (mock-fallback)",
            analyzed_at=datetime.now(timezone.utc).isoformat(),
        )

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    response = client.models.generate_content(
        model=model_name,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            SYSTEM_PROMPT,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=FloodAnalysisLLMOutput,
            temperature=0.1,
        ),
    )
    parsed = FloodAnalysisLLMOutput.model_validate_json(response.text)
    return FloodAnalysisResult(
        **parsed.model_dump(),
        vision_model=model_name,
        analyzed_at=datetime.now(timezone.utc).isoformat(),
    )
