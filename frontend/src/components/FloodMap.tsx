import { useEffect } from "react";
import {
  AdvancedMarker,
  APIProvider,
  Map,
  Pin,
  useMap,
  useMapsLibrary
} from "@vis.gl/react-google-maps";
import { envConfig } from "../config/env";
import { HeatmapOverlay } from "./HeatmapOverlay";
import type { CameraItem, FloodZoneItem, HeatmapPoint, RouteResponse } from "../types/flood";

interface FloodMapProps {
  zones: FloodZoneItem[];
  cameras: CameraItem[];
  routeResult: RouteResponse | null;
  heatmapPoints: HeatmapPoint[];
  showHeatmap: boolean;
}

const DEFAULT_CENTER = { lat: 10.7858, lng: 106.7082 };

function FloodCirclesLayer({ zones }: { zones: FloodZoneItem[] }) {
  const map = useMap();
  const mapsLib = useMapsLibrary("maps");

  useEffect(() => {
    if (!map || !mapsLib) return;
    const circles = zones.map((zone) => {
      const color = zone.severity_level >= 2 ? "#ef4444" : "#eab308";
      return new mapsLib.Circle({
        map,
        center: { lat: zone.lat, lng: zone.lng },
        radius: zone.radius_meters,
        fillColor: color,
        fillOpacity: 0.32,
        strokeColor: color,
        strokeWeight: 2
      });
    });

    return () => {
      circles.forEach((c) => c.setMap(null));
    };
  }, [map, mapsLib, zones]);

  return null;
}

function RoutePolylineLayer({ routeResult }: { routeResult: RouteResponse | null }) {
  const map = useMap();
  const mapsLib = useMapsLibrary("maps");

  useEffect(() => {
    if (!map || !mapsLib || !routeResult || routeResult.route_coordinates.length < 2) {
      return;
    }

    const line = new mapsLib.Polyline({
      map,
      path: routeResult.route_coordinates,
      strokeColor: routeResult.rerouted ? "#22c55e" : "#3b82f6",
      strokeOpacity: 0.9,
      strokeWeight: 5
    });

    return () => {
      line.setMap(null);
    };
  }, [map, mapsLib, routeResult]);

  return null;
}

export function FloodMap({
  zones,
  cameras,
  routeResult,
  heatmapPoints,
  showHeatmap
}: FloodMapProps) {
  if (!envConfig.hasGoogleMapsKey) {
    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          height: "100%",
          padding: "2rem",
          textAlign: "center"
        }}
      >
        <h2 style={{ marginBottom: "0.5rem" }}>Google Maps JS API — Mock Fallback Preview</h2>
        <p style={{ color: "#94a3b8", maxWidth: "560px", lineHeight: 1.5 }}>
          Chưa phát hiện <code>VITE_GOOGLE_MAPS_API_KEY</code> trong <code>.env</code>. Dữ liệu
          vùng ngập ({zones.length}), camera ({cameras.length}), heatmap ({heatmapPoints.length} điểm)
          và kết quả Dynamic Rerouting vẫn đồng bộ trực tiếp từ Backend API ở panel bên trái.
        </p>
        {routeResult && (
          <div
            style={{
              marginTop: "1rem",
              padding: "0.75rem 1rem",
              background: "#1e293b",
              borderRadius: "8px",
              fontSize: "0.85rem",
              textAlign: "left"
            }}
          >
            <div>
              <strong>Lộ trình trả về:</strong> {routeResult.route_coordinates.length} điểm tọa độ
            </div>
            <div>
              <strong>Trạng thái Heatmap:</strong> {showHeatmap ? "Đang bật" : "Đang tắt"}
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <APIProvider
      apiKey={envConfig.googleMapsApiKey}
      libraries={["geometry", "places"]}
    >
      <Map
        defaultCenter={DEFAULT_CENTER}
        defaultZoom={14}
        mapId="DEMO_MAP_ID"
        style={{ width: "100%", height: "100%" }}
      >
        <FloodCirclesLayer zones={zones} />
        <RoutePolylineLayer routeResult={routeResult} />
        <HeatmapOverlay visible={showHeatmap} points={heatmapPoints} />

        {zones.map((z) => (
          <AdvancedMarker
            key={z.event_id}
            position={{ lat: z.lat, lng: z.lng }}
            title={`${z.location_name || z.event_id} (Mức ${z.severity_level})`}
          >
            <Pin
              background={z.severity_level >= 2 ? "#ef4444" : "#eab308"}
              borderColor="#ffffff"
              glyphColor="#ffffff"
            />
          </AdvancedMarker>
        ))}

        {cameras.map((cam) => (
          <AdvancedMarker
            key={cam.camera_id}
            position={{ lat: cam.lat, lng: cam.lng }}
            title={`Camera: ${cam.name}`}
          >
            <Pin background="#0284c7" borderColor="#ffffff" glyphColor="#ffffff" />
          </AdvancedMarker>
        ))}
      </Map>
    </APIProvider>
  );
}
