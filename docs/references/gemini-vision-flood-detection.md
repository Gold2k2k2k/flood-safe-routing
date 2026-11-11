# Deep Reference: Gemini Vision Flood Detection (`google-genai` SDK)

This document defines exact, reproducible patterns for implementing real-time street flood severity classification using the **Google GenAI Python SDK (`google-genai`)** and **Gemini 3.8 Flash (Vision)**.

---

## 1. Official SDK Pattern (`google-genai` >= 1.0.0)

> **Important:** Use the modern `from google import genai` package (`google-genai`), **NOT** the legacy `google-generativeai` library.

### Synchronous & Async Multimodal Structured Output

```python
import os
from google import genai
from google.genai import types
from pydantic import BaseModel, Field


class FloodAnalysisLLMOutput(BaseModel):
    flood_detected: bool = Field(
        description="True if standing water or street flooding is visible."
    )
    severity_level: int = Field(
        ge=0,
        le=3,
        description="0=SAFE, 1=MINOR (curb edge <15cm), 2=MODERATE (half motorbike wheel 15-35cm), 3=SEVERE (>35cm).",
    )
    visual_cue: str = Field(
        description="Vietnamese description of water depth relative to curb or motorbike wheels."
    )
    estimated_depth_cm: str = Field(
        description="Estimated water depth range in cm: '0', '5-15', '20-35', or '>35'."
    )
    passable_for_motorbike: bool = Field(
        description="False when severity_level >= 2 due to high engine-stalling risk."
    )
    confidence: float = Field(ge=0.0, le=1.0)


def infer_flood_sync(image_bytes: bytes, mime_type: str = "image/jpeg") -> FloodAnalysisLLMOutput:
    model_name = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

    response = client.models.generate_content(
        model=model_name,
        contents=[image_part, SYSTEM_PROMPT],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=FloodAnalysisLLMOutput,
            temperature=0.1,
        ),
    )
    # Prefer SDK-parsed Pydantic instance; fallback to model_validate_json(response.text)
    if getattr(response, "parsed", None) is not None:
        return response.parsed
    return FloodAnalysisLLMOutput.model_validate_json(response.text)
```

For FastAPI async endpoints (`/api/reports`, `/api/cameras/poll`), avoid blocking the event loop by either using `client.aio.models.generate_content(...)` or `fastapi.concurrency.run_in_threadpool(...)`.

```python
async def infer_flood_async(image_bytes: bytes, mime_type: str = "image/jpeg") -> FloodAnalysisLLMOutput:
    model_name = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    response = await client.aio.models.generate_content(
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
    if getattr(response, "parsed", None) is not None:
        return response.parsed
    return FloodAnalysisLLMOutput.model_validate_json(response.text)
```

---

## 2. Vietnamese Urban Visual Calibration Rubric

Why absolute centimeter regression from a single 2D traffic camera fails, and how **reference-object prompting** solves it:

| Severity | Label | Real-world Vietnamese Street Anchor | `passable_for_motorbike` | Map & Routing Action |
| :---: | :--- | :--- | :---: | :--- |
| `0` | `SAFE` | Dry asphalt or damp rain sheen; lane markings clearly visible | `true` | Normal (Green/None) |
| `1` | `MINOR` | Water pooling at curb/gutter edge (`< 15 cm`), motorbike tire rims stay above water | `true` | Yellow caution marker (no detour required) |
| `2` | `MODERATE` | Curb submerged; water reaches 1/3 to 1/2 of motorbike wheels (`15–35 cm`), water ripples around tires | `false` | **Red Zone (`severity >= 2`) + Trigger Dynamic Rerouting** |
| `3` | `SEVERE` | Deep flood (`> 35 cm`); wheels mostly submerged, exhaust/crankcase level or riders walking bikes | `false` | **Dark Red Block + Mandatory Rerouting** |

### Anti-Hallucination & Edge-Case Guardrails
1. **Wet-Road Reflections vs. Standing Floods:** Instruct the prompt explicitly that wet asphalt reflecting headlights/sky is `severity_level = 0` unless continuous standing water covers lane markings or obscures curbs/tires.
2. **Low-Visibility Confidence Gate:** Compare `result.confidence` against `FLOOD_ALERT_THRESHOLD` (default `0.65`). If `confidence < 0.65` (e.g., severe lens rain blur or pitch-dark frame), mark for secondary crowdsourcing verification before triggering automatic road blocking.
3. **Model Configuration Portability:** Always configure via `GEMINI_MODEL` in `.env` (default `gemini-3.8-flash`). If your Google AI Studio key/project routes to a specific preview or GA tag at runtime, changing `.env` switches the model cleanly without code edits.

---

## 3. Quota & Latency Optimization for 24h Demo

1. **Image Downscaling Before Upload:** Traffic snapshots and phone photos often exceed 2–5 MB. Resize images to max `1024px` width/height via `Pillow` (`Image.thumbnail`) and JPEG quality `80` before calling `types.Part.from_bytes` — reduces payload size by ~85% and lowers multimodal latency below `1.5–2.5s`.
2. **Per-Camera Polling & Frame Diff Gate:** Only call Gemini when:
   - At least `CAMERA_POLL_INTERVAL_SECONDS` (30s) has elapsed, AND
   - Mean pixel delta against the previous cached frame exceeds a threshold (skip completely identical static snapshots).

---

## 4. Reproducible Verification

```bash
# Test Mock Fallback or Live Gemini Vision using a local image
python scripts/repro_gemini_vision.py
python scripts/repro_gemini_vision.py path/to/flood_photo.jpg
```
