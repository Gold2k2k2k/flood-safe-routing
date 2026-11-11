import { useCallback, useEffect, useState } from "react";
import { requestSafeRoute } from "../services/api";
import type { FloodZoneItem, LatLng, RouteResponse } from "../types/flood";

interface UseAutoRerouteParams {
  origin: LatLng;
  destination: LatLng;
  zones: FloodZoneItem[];
}

export function useAutoReroute({ origin, destination, zones }: UseAutoRerouteParams) {
  const [routeResult, setRouteResult] = useState<RouteResponse | null>(null);
  const [loadingRoute, setLoadingRoute] = useState(false);
  const [routeError, setRouteError] = useState<string | null>(null);

  const computeRoute = useCallback(async () => {
    setLoadingRoute(true);
    setRouteError(null);
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

  // Automatically trigger live rerouting if a new severe flood zone appears that wasn't already avoided
  useEffect(() => {
    if (!routeResult) return;
    const avoided = new Set(routeResult.avoided_flood_zone_ids);
    const hasNewSevereZone = zones.some(
      (z) => z.status === "active" && z.severity_level >= 2 && !avoided.has(z.event_id)
    );
    if (hasNewSevereZone) {
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
