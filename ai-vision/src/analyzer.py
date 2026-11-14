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

SYSTEM_PROMPT = """Bạn là hệ thống AI chuyên gia phân tích thị giác hình ảnh giao thông đô thị tại Việt Nam (Đà Nẵng, TP.HCM, Hà Nội).
Nhiệm vụ của bạn là quan sát ảnh camera giao thông hoặc ảnh người dân gửi về và phân loại chính xác mức độ ngập lụt dựa trên các vật chuẩn thực địa đô thị Việt Nam:

1. Thước đo vật chuẩn đô thị Việt Nam:
- Mép vỉa hè / bó vỉa tiêu chuẩn: cao khoảng 12 - 15 cm so với mặt đường.
- Bánh xe máy tiêu chuẩn (vành 14 - 17 inch): bán kính trục bánh khoảng 25 - 30 cm, toàn bộ đường kính khoảng 55 - 60 cm.
- Ống xả (pô xe) và lốc máy xe máy phổ thông (Wave, Sirius, Vision, Air Blade): cao khoảng 30 - 35 cm so với mặt đường.

2. Quy tắc phân loại mức độ ngập (severity_level):
- Mức 0 (SAFE) [depth = "0", passable_for_motorbike = true]:
  Mặt đường khô ráo hoặc chỉ ướt mặt nhựa đường sau mưa.
  QUAN TRỌNG - Phân biệt phản xạ mặt đường ướt (specular reflection): Mặt đường nhựa ướt có thể phản chiếu ánh đèn xe, đèn đường hoặc bầu trời nhưng KHÔNG có lớp nước đục tù đọng, vạch kẻ sơn đường vẫn nhìn rõ, mép vỉa hè khô ráo hoàn toàn -> Bắt buộc phân loại Mức 0 (SAFE).
- Mức 1 (MINOR) [depth = "5-15", passable_for_motorbike = true]:
  Nước mưa bắt đầu đọng thành vũng sát mép bó vỉa lề đường (< 15 cm, chưa tràn qua vỉa hè). Nước chưa ngập đến vành kim loại bánh xe máy. Xe máy di chuyển an toàn qua làn giữa đường.
- Mức 2 (MODERATE) [depth = "20-35", passable_for_motorbike = false]:
  Vỉa hè bị ngập (nước dâng > 15 cm). Nước đục dâng ngập từ 1/3 đến nửa bánh xe máy (khoảng 20 - 35 cm), che khuất hoàn toàn vạch kẻ đường, tạo sóng nước khi xe chạy qua. Nguy cơ nước tràn vào lọc gió hoặc chết máy rất cao -> Không an toàn cho xe máy.
- Mức 3 (SEVERE) [depth = ">35", passable_for_motorbike = false]:
  Ngập lụt nghiêm trọng (> 35 cm). Nước ngập lút quá nửa bánh xe máy, chạm hoặc vượt quá ống xả, lốc máy, sàn để chân hoặc yên xe. Xuất hiện cảnh người dân dắt bộ xe chết máy hoặc phương tiện bị bỏ lại giữa dòng nước sâu -> Tuyệt đối cấm xe máy qua lại.

3. Quy tắc phát hiện ảnh rác / không phải đường phố (Anti-spam & Non-street guardrail):
- Nếu bức ảnh không chụp khung cảnh đường sá/giao thông (ví dụ: ảnh selfie, trong nhà, tài liệu, phong cảnh không có mặt đường) hoặc ảnh bị mờ nhòe nghiêm trọng do hạt mưa bám kính, tối đen hoàn toàn không quan sát được: Đặt confidence < 0.5, flood_detected = false, severity_level = 0, visual_cue mô tả ảnh không rõ hoặc không phải đường phố.

Trả về đúng định dạng JSON theo schema đã chỉ định."""


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
    level = max(0, min(3, int(mock_severity_hint)))
    is_flooded = level >= 1
    passable = level < 2
    if level >= 3:
        cue = "Nước ngập sâu quá nửa bánh xe máy và chạm ống xả (Mock Fallback)"
        depth = ">35"
    elif level == 2:
        cue = "Nước ngập quá mép lề đường và chạm khoảng nửa bánh xe máy (Mock Fallback)"
        depth = "20-35"
    elif level == 1:
        cue = "Nước đọng nhẹ sát mép lề đường, xe máy đi chậm qua được (Mock Fallback)"
        depth = "5-15"
    else:
        cue = "Mặt đường thông thoáng, vạch kẻ đường rõ nét, xe máy di chuyển bình thường (Mock Fallback)"
        depth = "0"

    return FloodAnalysisResult(
        flood_detected=is_flooded,
        severity_level=level,
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

    payload = llm_out.model_dump()
    level = int(payload["severity_level"])
    # Enforce canonical contract invariants across severity_level, flood_detected, and passability
    payload["flood_detected"] = level >= 1
    payload["passable_for_motorbike"] = level < 2

    return FloodAnalysisResult(
        **payload,
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
