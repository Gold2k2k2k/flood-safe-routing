import { useCallback, useEffect, useState } from "react";
import { FloodMap } from "./components/FloodMap";
import { ReportModal } from "./components/ReportModal";
import { useAutoReroute } from "./hooks/useAutoReroute";
import { fetchCameras, fetchFloodZones, fetchHeatmapData, triggerCameraPoll } from "./services/api";
import { subscribeToActiveFloodZones } from "./services/firebase";
import type { CameraItem, FloodZoneItem, HeatmapPoint } from "./types/flood";

const DEMO_ORIGIN = { lat: 10.7800, lng: 106.7030 };
const DEMO_DESTINATION = { lat: 10.7920, lng: 106.7140 };

export function App() {
  const [zones, setZones] = useState<FloodZoneItem[]>([]);
  const [cameras, setCameras] = useState<CameraItem[]>([]);
  const [heatmapPoints, setHeatmapPoints] = useState<HeatmapPoint[]>([]);
  const [showHeatmap, setShowHeatmap] = useState(false);
  const [showReportModal, setShowReportModal] = useState(false);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [polling, setPolling] = useState(false);

  const { routeResult, loadingRoute, routeError, computeRoute } = useAutoReroute({
    origin: DEMO_ORIGIN,
    destination: DEMO_DESTINATION,
    zones
  });

  const refreshZonesAndCameras = useCallback(async () => {
    try {
      const [z, cams, heat] = await Promise.all([
        fetchFloodZones(),
        fetchCameras(),
        fetchHeatmapData()
      ]);
      setZones(z);
      setCameras(cams);
      setHeatmapPoints(heat);
      setStatusError(null);
    } catch (err) {
      setStatusError(
        err instanceof Error ? err.message : "Chưa kết nối được Backend API (:8000)."
      );
    }
  }, []);

  useEffect(() => {
    void refreshZonesAndCameras();
    return subscribeToActiveFloodZones(setZones, (err) => setStatusError(err.message));
  }, [refreshZonesAndCameras]);

  const handlePollCameras = async () => {
    setPolling(true);
    setStatusError(null);
    try {
      await triggerCameraPoll();
      await refreshZonesAndCameras();
    } catch (err) {
      setStatusError(err instanceof Error ? err.message : "Không thể poll camera.");
    } finally {
      setPolling(false);
    }
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "380px 1fr", height: "100vh" }}>
      <aside style={{ padding: "1.25rem", background: "#1e293b", overflowY: "auto" }}>
        <h1 style={{ fontSize: "1.25rem", margin: "0 0 0.35rem 0" }}>Flood-Safe Routing</h1>
        <p style={{ fontSize: "0.82rem", color: "#94a3b8", marginBottom: "1rem" }}>
          Gemini 3.8 Flash Vision • Google Maps & Routes API • Firebase Real-time
        </p>

        <div style={{ display: "grid", gap: "0.5rem", marginBottom: "1rem" }}>
          <button
            onClick={() => void computeRoute()}
            disabled={loadingRoute}
            style={{
              padding: "0.55rem 0.75rem",
              background: "#2563eb",
              color: "#fff",
              border: "none",
              borderRadius: "6px",
              cursor: "pointer"
            }}
          >
            {loadingRoute ? "Đang tính lộ trình..." : "Tính lộ trình né ngập (TWO_WHEELER)"}
          </button>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
            <button
              onClick={() => setShowHeatmap((v) => !v)}
              style={{
                padding: "0.5rem 0.6rem",
                background: showHeatmap ? "#dc2626" : "#334155",
                color: "#fff",
                border: "none",
                borderRadius: "6px",
                cursor: "pointer"
              }}
            >
              {showHeatmap ? "Tắt Heatmap" : "Bật Heatmap"}
            </button>
            <button
              onClick={() => setShowReportModal(true)}
              style={{
                padding: "0.5rem 0.6rem",
                background: "#b91c1c",
                color: "#fff",
                border: "none",
                borderRadius: "6px",
                cursor: "pointer"
              }}
            >
              + Báo ngập
            </button>
          </div>

          <button
            onClick={() => void handlePollCameras()}
            disabled={polling}
            style={{
              padding: "0.45rem 0.6rem",
              background: "#0f766e",
              color: "#fff",
              border: "none",
              borderRadius: "6px",
              cursor: "pointer",
              fontSize: "0.82rem"
            }}
          >
            {polling ? "Đang quét frame camera..." : `Quét Camera AI (${cameras.length} điểm)`}
          </button>
        </div>

        {(statusError || routeError) && (
          <div
            style={{
              padding: "0.65rem",
              borderRadius: "8px",
              background: "#451a03",
              color: "#fde68a",
              marginBottom: "0.85rem",
              fontSize: "0.8rem"
            }}
          >
            {routeError || statusError}
          </div>
        )}

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
            <strong>
              {routeResult.rerouted ? "ĐÃ TỰ ĐỘNG BẺ HƯỚNG (REROUTED)" : "LỘ TRÌNH AN TOÀN"}
            </strong>
            <div>
              Quãng đường: {(routeResult.distance_meters / 1000).toFixed(2)} km • Thời gian:{" "}
              {Math.max(1, Math.round(routeResult.duration_seconds / 60))} phút
            </div>
            {routeResult.warning_message && (
              <div style={{ marginTop: "0.25rem" }}>{routeResult.warning_message}</div>
            )}
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

      <main style={{ background: "#0f172a", height: "100%" }}>
        <FloodMap
          zones={zones}
          cameras={cameras}
          routeResult={routeResult}
          heatmapPoints={heatmapPoints}
          showHeatmap={showHeatmap}
        />
      </main>

      <ReportModal
        open={showReportModal}
        onClose={() => setShowReportModal(false)}
        onSubmitted={() => void refreshZonesAndCameras()}
      />
    </div>
  );
}
