import { useCallback, useEffect, useRef, useState } from "react";
import { requestSafeRoute } from "../services/api";
import type { FloodZoneItem, LatLng, RouteResponse } from "../types/flood";

interface UseAutoRerouteParams {
  origin: LatLng;
  destination: LatLng;
  zones: FloodZoneItem[];
  avoidFloodZones?: boolean;
}

function buildSevereZonesSignature(zones: FloodZoneItem[]): string {
  return zones
    .filter((z) => z.status === "active" && z.severity_level >= 2)
    .map((z) => `${z.event_id}:${z.severity_level}:${z.lat.toFixed(5)}:${z.lng.toFixed(5)}`)
    .sort()
    .join("|");
}

export interface AutoRerouteEvent {
  id: number;
  triggeredByZoneCount: number;
  previousDistanceMeters: number | null;
  previousDurationSeconds: number | null;
  nextResult: RouteResponse;
}

export function useAutoReroute({
  origin,
  destination,
  zones,
  avoidFloodZones = true
}: UseAutoRerouteParams) {
  const [routeResult, setRouteResult] = useState<RouteResponse | null>(null);
  const [previousRouteResult, setPreviousRouteResult] = useState<RouteResponse | null>(null);
  const [loadingRoute, setLoadingRoute] = useState(false);
  const [routeError, setRouteError] = useState<string | null>(null);
  const [autoRerouteEvent, setAutoRerouteEvent] = useState<AutoRerouteEvent | null>(null);
  const zonesRef = useRef<FloodZoneItem[]>(zones);
  const routeResultRef = useRef<RouteResponse | null>(null);
  const lastEvaluatedSignatureRef = useRef<string>("");
  const rerouteCounterRef = useRef(0);

  zonesRef.current = zones;
  routeResultRef.current = routeResult;

  const computeRoute = useCallback(async (isAutoTriggered = false) => {
    setLoadingRoute(true);
    setRouteError(null);
    lastEvaluatedSignatureRef.current = buildSevereZonesSignature(zonesRef.current);
    const prevSnapshot = routeResultRef.current;
    try {
      const res = await requestSafeRoute({
        origin,
        destination,
        travel_mode: "TWO_WHEELER",
        avoid_flood_zones: avoidFloodZones
      });
      setPreviousRouteResult(prevSnapshot);
      setRouteResult(res);
      if (isAutoTriggered) {
        rerouteCounterRef.current += 1;
        setAutoRerouteEvent({
          id: rerouteCounterRef.current,
          triggeredByZoneCount: res.avoided_flood_zone_ids.length,
          previousDistanceMeters: prevSnapshot?.distance_meters ?? null,
          previousDurationSeconds: prevSnapshot?.duration_seconds ?? null,
          nextResult: res
        });
      }
    } catch (err) {
      setRouteError(err instanceof Error ? err.message : "Không thể tính lộ trình.");
    } finally {
      setLoadingRoute(false);
    }
  }, [origin, destination, avoidFloodZones]);

  const dismissAutoRerouteEvent = useCallback(() => {
    setAutoRerouteEvent(null);
  }, []);

  // Automatically trigger live rerouting whenever the active severe flood zones change
  useEffect(() => {
    if (!routeResult) return;
    const currentSignature = buildSevereZonesSignature(zones);
    if (currentSignature !== lastEvaluatedSignatureRef.current) {
      void computeRoute(true);
    }
  }, [zones, routeResult, computeRoute]);

  return {
    routeResult,
    previousRouteResult,
    loadingRoute,
    routeError,
    autoRerouteEvent,
    dismissAutoRerouteEvent,
    computeRoute
  };
}
