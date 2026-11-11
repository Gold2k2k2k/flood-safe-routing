"""
Normalized Pydantic schemas for Gemini 3.8 Flash (Vision) structured outputs.
Matches docs/api-and-data-contract.md.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pydantic import BaseModel, Field


class FloodAnalysisLLMOutput(BaseModel):
    """Schema passed to Gemini response_schema for deterministic JSON output."""

    flood_detected: bool = Field(
        description="True if standing water or street flooding is visible."
    )
    severity_level: int = Field(
        ge=0,
        le=3,
        description="0=SAFE, 1=MINOR (curb edge <15cm), 2=MODERATE (half motorbike wheel 15-35cm), 3=SEVERE (>35cm).",
    )
    visual_cue: str = Field(
        description="Vietnamese description of water level relative to curb or motorbike wheels."
    )
    estimated_depth_cm: str = Field(
        description="Estimated water depth range in cm, e.g. '0', '5-15', '20-35', '>35'."
    )
    passable_for_motorbike: bool = Field(
        description="False when severity_level >= 2 (high risk of motorbike engine stalling)."
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0.",
    )


class FloodAnalysisResult(FloodAnalysisLLMOutput):
    """Full output returned to backend services."""

    vision_model: str = Field(default="gemini-3.8-flash")
    analyzed_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
