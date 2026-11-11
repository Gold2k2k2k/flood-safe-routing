"""
Gemini 3.8 Flash (Vision) Flood Severity Analyzer.
Supports synchronous and async multimodal inference via google-genai SDK,
Pillow preprocessing (1024px resize), wet-road anti-hallucination prompting,
and strict USE_MOCK_FALLBACK gating.
"""

from __future__ import annotations

import io
import logging
import os
from datetime import datetime, timezone
from PIL import Image, ImageOps
from .schemas import FloodAnalysisLLMOutput, FloodAnalysisResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Bạn là hệ thống AI chuyên phân tích hình ảnh giao thông đô thị tại Việt Nam (TP.HCM, Hà Nội, Đà Nẵng).
Hãy quan sát bức ảnh đường phố và xác định mức độ ngập nước dựa trên các vật chuẩn thực tế:
- Mức 0 (SAFE): Mặt đường khô hoặc chỉ ướt mặt nhựa. Lưu ý: mặt đường ướt phản chiếu ánh đèn xe/đèn đường/bầu trời nhưng không có vũng nước đọng liên tục che khuất vạch kẻ đường hay dâng lên mép vỉa hè vẫn là Mức 0.
- Mức 1 (MINOR): Nước mới đọng sát mép vỉa hè / lề đường (< 15 cm), chưa ngập vành bánh xe máy -> passable_for_motorbike = true.
- Mức 2 (MODERATE): Nước ngập qua lề đường, chạm từ 1/3 đến nửa bánh xe máy (15-35 cm), tạo sóng nước quanh bánh xe và nguy cơ chết máy cao -> passable_for_motorbike = false.
- Mức 3 (SEVERE): Nước ngập lút quá nửa bánh xe, chạm ống xả/lốc máy/yên xe (> 35 cm) hoặc có người phải dắt bộ -> passable_for_motorbike = false.
Trả về đúng định dạng JSON theo schema."""


def _is_real_key(val: str | None) -> bool:
    if not val:
        return False
    lower = val.lower()
    return not (lower.startswith("your_") or "placeholder" in lower or "example" in lower)


def _should_use_mock() -> bool:
    use_mock = os.getenv("USE_MOCK_FALLBACK", "true").lower() in ("true", "1", "yes")
    has_real_key = _is_real_key(os.getenv("GEMINI_API_KEY", ""))
    if not has_real_key and not use_mock:
        raise RuntimeError(
            "GEMINI_API_KEY is missing/placeholder while USE_MOCK_FALLBACK=false."
        )
    return not has_real_key and use_mock


def preprocess_image_bytes(
    image_bytes: bytes, max_dim: int = 1024, quality: int = 80
) -> tuple[bytes, str]:
    """
    Downscale large camera/mobile images via Pillow before Gemini Vision upload.
    Returns (processed_bytes, mime_type). Falls back to original bytes if decode fails.
    """
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode != "RGB":
                img = img.convert("RGB")
            if max(img.size) > max_dim:
                img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=quality, optimize=True)
            return out.getvalue(), "image/jpeg"
    except Exception as exc:
        logger.debug("Pillow preprocessing skipped (using raw bytes): %s", exc)
        return image_bytes, "image/jpeg"


def _build_mock_result(model_name: str, mock_severity_hint: int) -> FloodAnalysisResult:
    is_flooded = mock_severity_hint >= 1
    passable = mock_severity_hint < 2
    if mock_severity_hint >= 3:
        cue = "Nước ngập sâu quá nửa bánh xe máy và chạm ống xả (Mock Fallback)"
        depth = ">35"
    elif mock_severity_hint == 2:
        cue = "Nước ngập quá mép lề đường và chạm khoảng nửa bánh xe máy (Mock Fallback)"
        depth = "20-35"
    elif mock_severity_hint == 1:
        cue = "Nước đọng nhẹ sát mép lề đường, xe máy đi chậm qua được (Mock Fallback)"
        depth = "5-15"
    else:
        cue = "Mặt đường thông thoáng, xe máy di chuyển bình thường (Mock Fallback)"
        depth = "0"

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


def _parse_gemini_response(response: object, model_name: str) -> FloodAnalysisResult:
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, FloodAnalysisLLMOutput):
        llm_out = parsed
    else:
        raw_text = getattr(response, "text", None)
        if not raw_text:
            raise ValueError("Gemini Vision returned empty response text.")
        llm_out = FloodAnalysisLLMOutput.model_validate_json(raw_text)

    return FloodAnalysisResult(
        **llm_out.model_dump(),
        vision_model=model_name,
        analyzed_at=datetime.now(timezone.utc).isoformat(),
    )


def analyze_flood_image(
    image_bytes: bytes | None = None,
    mime_type: str = "image/jpeg",
    mock_severity_hint: int = 2,
) -> FloodAnalysisResult:
    """
    Synchronous Gemini 3.8 Flash (Vision) analysis.
    Use analyze_flood_image_async() inside FastAPI async route handlers.
    """
    model_name = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    if _should_use_mock():
        return _build_mock_result(model_name, mock_severity_hint)
    if not image_bytes:
        raise ValueError("image_bytes is required when running Gemini Vision in live mode.")

    from google import genai
    from google.genai import types

    processed_bytes, processed_mime = preprocess_image_bytes(image_bytes)
    final_mime = processed_mime if processed_bytes != image_bytes else mime_type
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    response = client.models.generate_content(
        model=model_name,
        contents=[
            types.Part.from_bytes(data=processed_bytes, mime_type=final_mime),
            SYSTEM_PROMPT,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=FloodAnalysisLLMOutput,
            temperature=0.1,
        ),
    )
    return _parse_gemini_response(response, model_name)


async def analyze_flood_image_async(
    image_bytes: bytes | None = None,
    mime_type: str = "image/jpeg",
    mock_severity_hint: int = 2,
) -> FloodAnalysisResult:
    """
    Non-blocking async Gemini 3.8 Flash (Vision) analysis for FastAPI handlers.
    """
    model_name = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    if _should_use_mock():
        return _build_mock_result(model_name, mock_severity_hint)
    if not image_bytes:
        raise ValueError("image_bytes is required when running Gemini Vision in live mode.")

    from google import genai
    from google.genai import types

    processed_bytes, processed_mime = preprocess_image_bytes(image_bytes)
    final_mime = processed_mime if processed_bytes != image_bytes else mime_type
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    response = await client.aio.models.generate_content(
        model=model_name,
        contents=[
            types.Part.from_bytes(data=processed_bytes, mime_type=final_mime),
            SYSTEM_PROMPT,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=FloodAnalysisLLMOutput,
            temperature=0.1,
        ),
    )
    return _parse_gemini_response(response, model_name)
