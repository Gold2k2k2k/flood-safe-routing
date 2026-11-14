/**
 * Shared TypeScript contracts matching docs/api-and-data-contract.md and backend/app/schemas.py
 */

export interface LatLng {
  lat: number;
  lng: number;
}

export type SeverityLevel = 0 | 1 | 2 | 3;

export interface FloodZoneItem {
  event_id: string;
  source: "camera_ai" | "crowdsourcing_ai";
  camera_id?: string | null;
  location_name?: string | null;
  lat: number;
  lng: number;
  radius_meters: number;
  severity_level: SeverityLevel;
  visual_cue: string;
  estimated_depth_cm: string;
  passable_for_motorbike: boolean;
  confidence: number;
  vision_model: string;
  status: "active" | "resolved";
  updated_at: string;
  ttl_expires_at?: string | null;
}

export interface FloodAnalysisResult {
  flood_detected: boolean;
  severity_level: SeverityLevel;
  visual_cue: string;
  estimated_depth_cm: string;
  passable_for_motorbike: boolean;
  confidence: number;
  vision_model: string;
  analyzed_at: string;
}

export interface CrowdsourcingReportPayload {
  lat: number;
  lng: number;
  location_name?: string;
  reporter_note?: string;
  image_base64?: string | null;
  mock_severity_hint?: SeverityLevel;
}

export interface CrowdsourcingReportResponse {
  report_id: string;
  analysis: FloodAnalysisResult;
  broadcasted_to_firestore: boolean;
}

export interface RouteRequest {
  origin: LatLng;
  destination: LatLng;
  travel_mode?: "TWO_WHEELER" | "DRIVE";
  avoid_flood_zones?: boolean;
}

export interface RouteResponse {
  rerouted: boolean;
  avoided_flood_zone_ids: string[];
  detour_waypoint_used?: LatLng | null;
  detour_waypoints_used?: LatLng[];
  baseline_route_coordinates?: LatLng[];
  distance_meters: number;
  duration_seconds: number;
  encoded_polyline: string;
  route_coordinates: LatLng[];
  warning_message?: string | null;
}

export interface CameraItem {
  camera_id: string;
  name: string;
  city: string;
  source: string;
  feed_url: string;
  lat: number;
  lng: number;
  road_segment_id?: string | null;
  local_image_path?: string | null;
  default_severity_hint?: SeverityLevel | null;
}

export interface CameraPollRequest {
  camera_ids?: string[] | null;
  mock_severity_hint?: SeverityLevel | null;
  force_refresh?: boolean;
}

export interface CameraPollResultItem {
  camera_id: string;
  frame_source: string;
  analysis: FloodAnalysisResult;
  broadcasted_to_firestore: boolean;
  frame_delta_skipped: boolean;
}

export interface CameraPollResponse {
  polled_count: number;
  flooded_count: number;
  results: CameraPollResultItem[];
}

export interface FloodZoneDeleteResponse {
  deleted: boolean;
  event_id: string;
}

export interface HeatmapPoint {
  zone_id: string;
  city: string;
  district: string;
  lat: number;
  lng: number;
  flood_frequency_30d: number;
  avg_severity: number;
  weight: number;
  peak_trigger?: string | null;
}
