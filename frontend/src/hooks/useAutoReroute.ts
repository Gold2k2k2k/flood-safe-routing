import { useCallback, useEffect, useRef, useState } from "react";
import { requestSafeRoute } from "../services/api";
import type { FloodZoneItem, LatLng, RouteResponse } from "../types/flood";

interface UseAutoRerouteParams {
  origin: LatLng;
  destination: LatLng;
  zones: FloodZoneItem[];
}

function buildSevereZonesSignature(zones: FloodZoneItem[]): string {
  return zones
    .filter((z) => z.status === "active" && z.severity_level >= 2)
    .map((z) => `${z.event_id}:${z.severity_level}:${z.lat.toFixed(5)}:${z.lng.toFixed(5)}`)
    .sort()
    .join("|");
}

export function useAutoReroute({ origin, destination, zones }: UseAutoRerouteParams) {
  const [routeResult, setRouteResult] = useState<RouteResponse | null>(null);
  const [loadingRoute, setLoadingRoute] = useState(false);
  const [routeError, setRouteError] = useState<string | null>(null);
  const zonesRef = useRef<FloodZoneItem[]>(zones);
  const lastEvaluatedSignatureRef = useRef<string>("");

  zonesRef.current = zones;

  const computeRoute = useCallback(async () => {
    setLoadingRoute(true);
    setRouteError(null);
    lastEvaluatedSignatureRef.current = buildSevereZonesSignature(zonesRef.current);
    try {
      const res = await requestSafeRoute({
        origin,
        destination,
        travel_mode: "TWO_WHEELER",
        avoid_flood_zones: true
      });
      setRouteResult(res);
    } catch (err) {
      setRouteError(err instanceof Error ? err.message : "Không thể tính lộ trình.");
    } finally {
      setLoadingRoute(false);
    }
  }, [origin, destination]);

  // Automatically trigger live rerouting whenever the active severe flood zones change
  useEffect(() => {
    if (!routeResult) return;
    const currentSignature = buildSevereZonesSignature(zones);
    if (currentSignature !== lastEvaluatedSignatureRef.current) {
      void computeRoute();
    }
  }, [zones, routeResult, computeRoute]);

  return {
    routeResult,
    loadingRoute,
    routeError,
    computeRoute
  };
}
