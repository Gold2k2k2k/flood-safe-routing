import React, { useEffect, useState } from "react";
import { envConfig, subscribeToActiveFloodZones } from "./services/firebase";
import { requestSafeRoute } from "./services/api";
import type { FloodZoneItem, RouteResponse } from "./types/flood";

export function App() {
  const [zones, setZones] = useState<FloodZoneItem[]>([]);
  const [routeResult, setRouteResult] = useState<RouteResponse | null>(null);
  const [showHeatmap, setShowHeatmap] = useState(false);

  useEffect(() => {
    return subscribeToActiveFloodZones(setZones);
  }, []);

  const handleTestReroute = async () => {
    const res = await requestSafeRoute({
      origin: { lat: 10.7769, lng: 106.7009 },
      destination: { lat: 10.7992, lng: 106.7185 },
      travel_mode: "TWO_WHEELER",
      avoid_flood_zones: true
    });
    setRouteResult(res);
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "360px 1fr", height: "100vh" }}>
      <aside style={{ padding: "1.25rem", background: "#1e293b", overflowY: "auto" }}>
        <h1 style={{ fontSize: "1.25rem", margin: "0 0 0.5rem 0" }}>Flood-Safe Routing</h1>
        <p style={{ fontSize: "0.85rem", color: "#94a3b8", marginBottom: "1rem" }}>
          Gemini 3.8 Flash Vision • Google Maps & Routes API • Firebase Real-time
        </p>

        <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem" }}>
          <button
            onClick={handleTestReroute}
            style={{
              padding: "0.5rem 0.75rem",
              background: "#2563eb",
              color: "#fff",
              border: "none",
              borderRadius: "6px",
              cursor: "pointer"
            }}
          >
            Tính lộ trình né ngập (TWO_WHEELER)
          </button>
          <button
            onClick={() => setShowHeatmap((v) => !v)}
            style={{
              padding: "0.5rem 0.75rem",
              background: showHeatmap ? "#dc2626" : "#334155",
              color: "#fff",
              border: "none",
              borderRadius: "6px",
              cursor: "pointer"
            }}
          >
            {showHeatmap ? "Tắt Heatmap" : "Bật Heatmap"}
          </button>
        </div>

        {routeResult && (
          <div
            style={{
              padding: "0.75rem",
              borderRadius: "8px",
              background: routeResult.rerouted ? "#7f1d1d" : "#14532d",
              marginBottom: "1rem",
              fontSize: "0.85rem"
            }}
          >
            <strong>{routeResult.rerouted ? "ĐÃ TỰ ĐỘNG BẺ HƯỚNG (REROUTED)" : "LỘ TRÌNH AN TOÀN"}</strong>
            <div>Quãng đường: {(routeResult.distance_meters / 1000).toFixed(2)} km</div>
            {routeResult.warning_message && <div>{routeResult.warning_message}</div>}
          </div>
        )}

        <h2 style={{ fontSize: "0.95rem", marginBottom: "0.5rem" }}>
          Điểm ngập đang kích hoạt ({zones.length})
        </h2>
        {zones.map((z) => (
          <div
            key={z.event_id}
            style={{
              padding: "0.75rem",
              background: "#0f172a",
              borderRadius: "8px",
              marginBottom: "0.5rem",
              borderLeft: z.severity_level >= 2 ? "4px solid #ef4444" : "4px solid #eab308",
              fontSize: "0.85rem"
            }}
          >
            <div style={{ fontWeight: 600 }}>{z.location_name || z.event_id}</div>
            <div style={{ color: "#cbd5e1" }}>{z.visual_cue}</div>
            <div style={{ color: "#94a3b8", fontSize: "0.75rem", marginTop: "0.25rem" }}>
              Mức: {z.severity_level} ({z.estimated_depth_cm} cm) • Model: {z.vision_model}
            </div>
          </div>
        ))}
      </aside>

      <main
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#0f172a",
          padding: "2rem"
        }}
      >
        <div style={{ textAlign: "center", maxWidth: "560px" }}>
          <h2>Khung Bản Đồ Số (Google Maps JS API)</h2>
          <p style={{ color: "#94a3b8" }}>
            {envConfig.hasGoogleMapsKey
              ? "Đã nhận VITE_GOOGLE_MAPS_API_KEY — Sẵn sàng render <APIProvider> & <Map>."
              : "Đang chạy chế độ Mock Fallback (chưa điền VITE_GOOGLE_MAPS_API_KEY trong .env)."}
          </p>
        </div>
      </main>
    </div>
  );
}
