/**
 * Shared TypeScript contracts matching docs/api-and-data-contract.md
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
  distance_meters: number;
  duration_seconds: number;
  encoded_polyline: string;
  route_coordinates: LatLng[];
  warning_message?: string | null;
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
}
