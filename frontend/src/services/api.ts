/**
 * REST API client matching docs/api-and-data-contract.md
 */

import { envConfig } from "../config/env";
import type { FloodZoneItem, HeatmapPoint, RouteRequest, RouteResponse } from "../types/flood";

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
