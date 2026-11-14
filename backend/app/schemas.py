"""Request and Response Pydantic schemas matching docs/api-and-data-contract.md."""

from __future__ import annotations

from typing import Any
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
    ttl_expires_at: str | None = None


class FloodZonesListResponse(BaseModel):
    count: int
    items: list[FloodZoneItem]


class FloodZoneDeleteResponse(BaseModel):
    deleted: bool
    event_id: str


class CrowdsourcingReportRequest(BaseModel):
    lat: float
    lng: float
    location_name: str = "Điểm báo ngập từ người dân"
    reporter_note: str = ""
    image_base64: str | None = None
    mock_severity_hint: int = Field(default=2, ge=0, le=3)


class CrowdsourcingReportResponse(BaseModel):
    report_id: str
    analysis: dict[str, Any]
    broadcasted_to_firestore: bool


class RouteRequest(BaseModel):
    origin: LatLng
    destination: LatLng
    travel_mode: str = "TWO_WHEELER"
    avoid_flood_zones: bool = True


class RouteResponse(BaseModel):
    rerouted: bool
    avoided_flood_zone_ids: list[str]
    detour_waypoint_used: LatLng | None = None
    detour_waypoints_used: list[LatLng] = Field(default_factory=list)
    baseline_route_coordinates: list[LatLng] = Field(default_factory=list)
    distance_meters: int
    duration_seconds: int
    encoded_polyline: str
    route_coordinates: list[LatLng]
    warning_message: str | None = None


class CameraItem(BaseModel):
    camera_id: str
    name: str
    city: str
    source: str = "public_traffic_camera"
    feed_url: str
    lat: float
    lng: float
    road_segment_id: str | None = None
    local_image_path: str | None = None
    default_severity_hint: int | None = Field(default=None, ge=0, le=3)


class CameraListResponse(BaseModel):
    count: int
    items: list[CameraItem]


class CameraPollRequest(BaseModel):
    camera_ids: list[str] | None = None
    mock_severity_hint: int | None = Field(default=None, ge=0, le=3)
    force_refresh: bool = False


class CameraPollResultItem(BaseModel):
    camera_id: str
    frame_source: str
    analysis: dict[str, Any]
    broadcasted_to_firestore: bool
    frame_delta_skipped: bool = False


class CameraPollResponse(BaseModel):
    polled_count: int
    flooded_count: int
    results: list[CameraPollResultItem]


class HeatmapPointItem(BaseModel):
    zone_id: str
    city: str
    district: str
    lat: float
    lng: float
    flood_frequency_30d: int
    avg_severity: float
    weight: float
    peak_trigger: str | None = None


class HeatmapResponse(BaseModel):
    count: int
    items: list[HeatmapPointItem]
