/**
 * REST API client matching docs/api-and-data-contract.md
 */

import { envConfig } from "../config/env";
import type {
  CameraItem,
  CameraPollResponse,
  CrowdsourcingReportPayload,
  CrowdsourcingReportResponse,
  FloodZoneItem,
  HeatmapPoint,
  RouteRequest,
  RouteResponse
} from "../types/flood";

export async function fetchFloodZones(): Promise<FloodZoneItem[]> {
  const res = await fetch(`${envConfig.apiBaseUrl}/api/flood-zones`);
  if (!res.ok) throw new Error(`Failed to fetch flood zones: ${res.status}`);
  const data = await res.json();
  return data.items ?? [];
}

export async function requestSafeRoute(payload: RouteRequest): Promise<RouteResponse> {
  const res = await fetch(`${envConfig.apiBaseUrl}/api/route`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!res.ok) throw new Error(`Route calculation failed: ${res.status}`);
  return res.json();
}

export async function fetchHeatmapData(): Promise<HeatmapPoint[]> {
  const res = await fetch(`${envConfig.apiBaseUrl}/api/heatmap`);
  if (!res.ok) throw new Error(`Failed to fetch heatmap data: ${res.status}`);
  const data = await res.json();
  return data.items ?? [];
}

export async function fetchCameras(): Promise<CameraItem[]> {
  const res = await fetch(`${envConfig.apiBaseUrl}/api/cameras`);
  if (!res.ok) throw new Error(`Failed to fetch cameras: ${res.status}`);
  const data = await res.json();
  return data.items ?? [];
}

export async function submitFloodReport(
  payload: CrowdsourcingReportPayload
): Promise<CrowdsourcingReportResponse> {
  const res = await fetch(`${envConfig.apiBaseUrl}/api/reports`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!res.ok) throw new Error(`Failed to submit report: ${res.status}`);
  return res.json();
}

export async function triggerCameraPoll(cameraIds?: string[]): Promise<CameraPollResponse> {
  const res = await fetch(`${envConfig.apiBaseUrl}/api/cameras/poll`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cameraIds ? { camera_ids: cameraIds } : {})
  });
  if (!res.ok) throw new Error(`Camera poll failed: ${res.status}`);
  return res.json();
}
