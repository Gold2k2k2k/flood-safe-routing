"""Request and Response Pydantic schemas matching docs/api-and-data-contract.md."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LatLng(BaseModel):
    lat: float
    lng: float


class FloodZoneItem(BaseModel):
    event_id: str
    source: str = "camera_ai"
    camera_id: str | None = None
    location_name: str | None = None
    lat: float
    lng: float
    radius_meters: float = 120.0
    severity_level: int = Field(ge=0, le=3)
    visual_cue: str
    estimated_depth_cm: str
    passable_for_motorbike: bool
    confidence: float
    vision_model: str = "gemini-3.8-flash"
    status: str = "active"
    updated_at: str


class CrowdsourcingReportRequest(BaseModel):
    lat: float
    lng: float
    location_name: str = "Điểm báo ngập từ người dân"
    reporter_note: str = ""
    image_base64: str | None = None
    mock_severity_hint: int = Field(default=2, ge=0, le=3)


class RouteRequest(BaseModel):
    origin: LatLng
    destination: LatLng
    travel_mode: str = "TWO_WHEELER"
    avoid_flood_zones: bool = True


class RouteResponse(BaseModel):
    rerouted: bool
    avoided_flood_zone_ids: list[str]
    detour_waypoint_used: LatLng | None = None
    distance_meters: int
    duration_seconds: int
    encoded_polyline: str
    route_coordinates: list[LatLng]
    warning_message: str | None = None
