import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { type SelectedMapEntity } from "./components/FloodInspectorCard";
import { FloodMap, type MapClickMode } from "./components/FloodMap";
import { ReportModal } from "./components/ReportModal";
import { useAutoReroute } from "./hooks/useAutoReroute";
import {
  deleteFloodZone,
  fetchCameras,
  fetchFloodZones,
  fetchHeatmapData,
  resetFloodZones,
  triggerCameraPoll
} from "./services/api";
import { subscribeToActiveFloodZones } from "./services/firebase";
import type {
  CameraItem,
  CameraPollResultItem,
  FloodZoneItem,
  HeatmapPoint,
  LatLng
} from "./types/flood";

interface RoutePreset {
  id: string;
  label: string;
  origin: LatLng;
  destination: LatLng;
}

const ROUTE_PRESETS: RoutePreset[] = [
  {
    id: "hcm-nhc",
    label: "Q.1 → Thảo Điền (Nguyễn Hữu Cảnh)",
    origin: { lat: 10.78, lng: 106.703 },
    destination: { lat: 10.792, lng: 106.714 }
  },
  {
    id: "hcm-multi",
    label: "Q.1 → Thủ Đức (Đa điểm ngập)",
    origin: { lat: 10.7795, lng: 106.701 },
    destination: { lat: 10.8065, lng: 106.7315 }
  },
  {
    id: "danang-center",
    label: "Đà Nẵng: Thanh Khê → Hải Châu",
    origin: { lat: 16.058, lng: 108.204 },
    destination: { lat: 16.0715, lng: 108.2255 }
  }
];

function playEmergencyChime() {
  try {
    const AudioCtx =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    const now = ctx.currentTime;

    [660, 880].forEach((freq, idx) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "triangle";
      osc.frequency.setValueAtTime(freq, now + idx * 0.14);
      gain.gain.setValueAtTime(0.08, now + idx * 0.14);
      gain.gain.exponentialRampToValueAtTime(0.001, now + idx * 0.14 + 0.16);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(now + idx * 0.14);
      osc.stop(now + idx * 0.14 + 0.18);
    });
  } catch {
    // Ignore audio context restrictions in headless or muted browsers
  }
}

export function App() {
  const [zones, setZones] = useState<FloodZoneItem[]>([]);
  const [cameras, setCameras] = useState<CameraItem[]>([]);
  const [heatmapPoints, setHeatmapPoints] = useState<HeatmapPoint[]>([]);
  const [selectedPresetId, setSelectedPresetId] = useState<string>(ROUTE_PRESETS[0].id);
  const [origin, setOrigin] = useState<LatLng>(ROUTE_PRESETS[0].origin);
  const [destination, setDestination] = useState<LatLng>(ROUTE_PRESETS[0].destination);
  const [clickMode, setClickMode] = useState<MapClickMode>(null);

  const [showHeatmap, setShowHeatmap] = useState(false);
  const [zonesLoaded, setZonesLoaded] = useState(false);
  const [showReportModal, setShowReportModal] = useState(false);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [polling, setPolling] = useState(false);
  const [pollingCameraId, setPollingCameraId] = useState<string | null>(null);
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);
  const [soundMuted, setSoundMuted] = useState(false);
  const [selectedEntity, setSelectedEntity] = useState<SelectedMapEntity | null>(null);
  const [pollResultsByCamera, setPollResultsByCamera] = useState<Record<string, CameraPollResultItem>>({});

  const lastChimeIdRef = useRef<number>(0);

  const {
    routeResult,
    loadingRoute,
    routeError,
    autoRerouteEvent,
    dismissAutoRerouteEvent,
    computeRoute
  } = useAutoReroute({
    origin,
    destination,
    zones
  });

  useEffect(() => {
    if (!autoRerouteEvent || soundMuted) return;
    if (autoRerouteEvent.id === lastChimeIdRef.current) return;
    lastChimeIdRef.current = autoRerouteEvent.id;
    playEmergencyChime();
  }, [autoRerouteEvent, soundMuted]);

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
      setZonesLoaded(true);
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

  // Compute safe route automatically once zones are loaded and whenever A/B waypoints change
  useEffect(() => {
    if (!zonesLoaded) return;
    void computeRoute(false);
  }, [zonesLoaded, computeRoute]);

  const handleSelectPreset = (preset: RoutePreset) => {
    setSelectedPresetId(preset.id);
    setOrigin(preset.origin);
    setDestination(preset.destination);
    setClickMode(null);
  };

  const handleSelectCoordinate = (mode: "origin" | "destination", coord: LatLng) => {
    setSelectedPresetId("custom");
    if (mode === "origin") setOrigin(coord);
    else setDestination(coord);
    setClickMode(null);
  };

  const handlePollCameras = async (singleCameraId?: string) => {
    if (singleCameraId) setPollingCameraId(singleCameraId);
    else setPolling(true);
    setStatusError(null);
    try {
      const pollResp = await triggerCameraPoll(singleCameraId ? [singleCameraId] : undefined);
      setPollResultsByCamera((prev) => {
        const next = { ...prev };
        pollResp.results.forEach((item) => {
          next[item.camera_id] = item;
        });
        return next;
      });
      await refreshZonesAndCameras();
      if (singleCameraId) {
        const cam = cameras.find((c) => c.camera_id === singleCameraId);
        const resItem = pollResp.results.find((r) => r.camera_id === singleCameraId);
        if (cam && resItem) {
          setSelectedEntity({ kind: "camera", camera: cam, pollResult: resItem });
        }
      }
    } catch (err) {
      setStatusError(err instanceof Error ? err.message : "Không thể poll camera.");
    } finally {
      setPolling(false);
      setPollingCameraId(null);
    }
  };

  const handleResolveZone = async (eventId: string) => {
    setResolvingId(eventId);
    setStatusError(null);
    try {
      await deleteFloodZone(eventId);
      setSelectedEntity((prev) => (prev?.kind === "zone" && prev.zone.event_id === eventId ? null : prev));
      await refreshZonesAndCameras();
    } catch (err) {
      setStatusError(err instanceof Error ? err.message : "Không thể giải tỏa điểm ngập.");
    } finally {
      setResolvingId(null);
    }
  };

  const handleResetDemo = async () => {
    setResetting(true);
    setStatusError(null);
    try {
      const restored = await resetFloodZones();
      setZones(restored);
      setSelectedEntity(null);
      dismissAutoRerouteEvent();
      await refreshZonesAndCameras();
    } catch (err) {
      setStatusError(err instanceof Error ? err.message : "Không thể reset dữ liệu demo.");
    } finally {
      setResetting(false);
    }
  };

  const b2gAnalytics = useMemo(() => {
    const sorted = [...heatmapPoints].sort((a, b) => b.weight - a.weight);
    const totalIntensity = heatmapPoints.reduce((acc, p) => acc + p.weight, 0);
    return {
      totalPoints: heatmapPoints.length,
      totalIntensity: totalIntensity.toFixed(1),
      top3: sorted.slice(0, 3)
    };
  }, [heatmapPoints]);

  const distanceDeltaMeters =
    autoRerouteEvent && autoRerouteEvent.previousDistanceMeters !== null
      ? autoRerouteEvent.nextResult.distance_meters - autoRerouteEvent.previousDistanceMeters
      : null;

  const durationDeltaSeconds =
    autoRerouteEvent && autoRerouteEvent.previousDurationSeconds !== null
      ? autoRerouteEvent.nextResult.duration_seconds - autoRerouteEvent.previousDurationSeconds
      : null;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "400px 1fr", height: "100vh" }}>
      <aside style={{ padding: "1.15rem", background: "#1e293b", overflowY: "auto", borderRight: "1px solid #334155" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <h1 style={{ fontSize: "1.2rem", margin: "0 0 0.25rem 0" }}>Flood-Safe Routing</h1>
            <p style={{ fontSize: "0.78rem", color: "#94a3b8", margin: "0 0 0.85rem 0" }}>
              Gemini 3.8 Flash Vision • Google Routes API • Firebase Live
            </p>
          </div>
          <button
            type="button"
            onClick={() => setSoundMuted((m) => !m)}
            title={soundMuted ? "Bật âm cảnh báo" : "Tắt âm cảnh báo"}
            style={{
              padding: "0.3rem 0.5rem",
              borderRadius: "6px",
              border: "1px solid #334155",
              background: "#0f172a",
              color: "#cbd5e1",
              fontSize: "0.75rem",
              cursor: "pointer"
            }}
          >
            {soundMuted ? "🔇" : "🔔"}
          </button>
        </div>

        {/* Route Presets & Map Click Origin/Dest Controls */}
        <div
          style={{
            padding: "0.75rem",
            background: "#0f172a",
            borderRadius: "8px",
            border: "1px solid #334155",
            marginBottom: "0.85rem"
          }}
        >
          <div style={{ fontSize: "0.75rem", color: "#94a3b8", marginBottom: "0.4rem", fontWeight: 600 }}>
            Tuyến Demo / Tùy chỉnh Điểm A–B (Xe máy TWO_WHEELER)
          </div>
          <div style={{ display: "grid", gap: "0.35rem", marginBottom: "0.55rem" }}>
            {ROUTE_PRESETS.map((preset) => (
              <button
                key={preset.id}
                type="button"
                onClick={() => handleSelectPreset(preset)}
                style={{
                  textAlign: "left",
                  padding: "0.4rem 0.6rem",
                  borderRadius: "6px",
                  border: selectedPresetId === preset.id ? "1px solid #3b82f6" : "1px solid #334155",
                  background: selectedPresetId === preset.id ? "rgba(37, 99, 235, 0.22)" : "#1e293b",
                  color: "#f8fafc",
                  fontSize: "0.78rem",
                  cursor: "pointer"
                }}
              >
                {preset.label}
              </button>
            ))}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.4rem", fontSize: "0.74rem" }}>
            <button
              type="button"
              onClick={() => setClickMode((m) => (m === "origin" ? null : "origin"))}
              style={{
                padding: "0.38rem 0.5rem",
                borderRadius: "6px",
                border: clickMode === "origin" ? "1px solid #60a5fa" : "1px solid #334155",
                background: clickMode === "origin" ? "#1d4ed8" : "#1e293b",
                color: "#e2e8f0",
                cursor: "pointer"
              }}
            >
              📍 A: {origin.lat.toFixed(4)}, {origin.lng.toFixed(4)}
            </button>
            <button
              type="button"
              onClick={() => setClickMode((m) => (m === "destination" ? null : "destination"))}
              style={{
                padding: "0.38rem 0.5rem",
                borderRadius: "6px",
                border: clickMode === "destination" ? "1px solid #4ade80" : "1px solid #334155",
                background: clickMode === "destination" ? "#15803d" : "#1e293b",
                color: "#e2e8f0",
                cursor: "pointer"
              }}
            >
              🏁 B: {destination.lat.toFixed(4)}, {destination.lng.toFixed(4)}
            </button>
          </div>
        </div>

        {/* Main Actions */}
        <div style={{ display: "grid", gap: "0.5rem", marginBottom: "0.9rem" }}>
          <button
            onClick={() => void computeRoute(false)}
            disabled={loadingRoute}
            style={{
              padding: "0.6rem 0.75rem",
              background: "#2563eb",
              color: "#fff",
              border: "none",
              borderRadius: "8px",
              cursor: loadingRoute ? "wait" : "pointer",
              fontWeight: 600
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
                cursor: "pointer",
                fontSize: "0.82rem"
              }}
            >
              {showHeatmap ? "Tắt Heatmap 30N" : "Bật Heatmap 30N"}
            </button>
            <button
              onClick={() => setShowReportModal(true)}
              style={{
                padding: "0.5rem 0.6rem",
                background: "#b91c1c",
                color: "#fff",
                border: "none",
                borderRadius: "6px",
                cursor: "pointer",
                fontSize: "0.82rem",
                fontWeight: 600
              }}
            >
              + Báo ngập (AI)
            </button>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: "0.5rem" }}>
            <button
              onClick={() => void handlePollCameras()}
              disabled={polling}
              style={{
                padding: "0.48rem 0.6rem",
                background: "#0f766e",
                color: "#fff",
                border: "none",
                borderRadius: "6px",
                cursor: polling ? "wait" : "pointer",
                fontSize: "0.8rem"
              }}
            >
              {polling ? "Đang quét frame camera..." : `Quét Camera AI (${cameras.length} điểm)`}
            </button>
            <button
              onClick={() => void handleResetDemo()}
              disabled={resetting}
              title="Khôi phục danh sách điểm ngập mẫu ban đầu"
              style={{
                padding: "0.48rem 0.65rem",
                background: "#334155",
                color: "#e2e8f0",
                border: "1px solid #475569",
                borderRadius: "6px",
                cursor: resetting ? "wait" : "pointer",
                fontSize: "0.78rem"
              }}
            >
              {resetting ? "..." : "↻ Reset"}
            </button>
          </div>
        </div>

        {/* Emergency Auto-Reroute Live Banner */}
        {autoRerouteEvent && (
          <div
            style={{
              padding: "0.75rem",
              borderRadius: "8px",
              background: "linear-gradient(135deg, #7f1d1d, #991b1b)",
              border: "1px solid #f87171",
              marginBottom: "0.85rem",
              fontSize: "0.8rem"
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <strong>⚡ TỰ ĐỘNG BẺ LÁI REAL-TIME #{autoRerouteEvent.id}</strong>
              <button
                type="button"
                onClick={dismissAutoRerouteEvent}
                style={{ background: "transparent", border: "none", color: "#fecaca", cursor: "pointer" }}
              >
                ✕
              </button>
            </div>
            <div style={{ color: "#fee2e2", marginTop: "0.25rem" }}>
              Phát hiện thay đổi vùng ngập nghiêm trọng ({autoRerouteEvent.triggeredByZoneCount} điểm né).
              Đã chuyển sang tuyến vòng an toàn.
            </div>
            {(distanceDeltaMeters !== null || durationDeltaSeconds !== null) && (
              <div
                style={{
                  marginTop: "0.45rem",
                  padding: "0.4rem 0.5rem",
                  background: "rgba(15, 23, 42, 0.5)",
                  borderRadius: "6px",
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: "0.4rem",
                  fontSize: "0.75rem"
                }}
              >
                <span>
                  Chênh cự ly:{" "}
                  <strong>
                    {distanceDeltaMeters !== null
                      ? `${distanceDeltaMeters >= 0 ? "+" : ""}${(distanceDeltaMeters / 1000).toFixed(2)} km`
                      : "—"}
                  </strong>
                </span>
                <span>
                  Chênh thời gian:{" "}
                  <strong>
                    {durationDeltaSeconds !== null
                      ? `${durationDeltaSeconds >= 0 ? "+" : ""}${Math.round(durationDeltaSeconds / 60)} phút`
                      : "—"}
                  </strong>
                </span>
              </div>
            )}
          </div>
        )}

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
              marginBottom: "0.85rem",
              fontSize: "0.83rem"
            }}
          >
            <div style={{ fontWeight: 700 }}>
              {routeResult.rerouted ? "🛡️ ĐÃ BẺ HƯỚNG AN TOÀN (REROUTED)" : "✓ LỘ TRÌNH THÔNG THOÁNG"}
            </div>
            <div style={{ marginTop: "0.2rem" }}>
              Quãng đường: <strong>{(routeResult.distance_meters / 1000).toFixed(2)} km</strong> • Thời gian:{" "}
              <strong>{Math.max(1, Math.round(routeResult.duration_seconds / 60))} phút</strong>
            </div>
            {routeResult.avoided_flood_zone_ids.length > 0 && (
              <div style={{ fontSize: "0.74rem", color: "#fecaca", marginTop: "0.25rem" }}>
                Né {routeResult.avoided_flood_zone_ids.length} vùng ngập:{" "}
                <code>{routeResult.avoided_flood_zone_ids.join(", ")}</code>
              </div>
            )}
            {routeResult.warning_message && (
              <div style={{ marginTop: "0.25rem", color: "#f8fafc" }}>{routeResult.warning_message}</div>
            )}
          </div>
        )}

        {/* B2G Urban Analytics Summary Card when Heatmap is toggled ON */}
        {showHeatmap && (
          <div
            style={{
              padding: "0.75rem",
              borderRadius: "8px",
              background: "#0f172a",
              border: "1px solid #dc2626",
              marginBottom: "0.9rem",
              fontSize: "0.8rem"
            }}
          >
            <div style={{ fontWeight: 700, color: "#fca5a5", marginBottom: "0.35rem" }}>
              📊 Thống kê Ngập 30 Ngày (B2G Hạ tầng)
            </div>
            <div style={{ color: "#cbd5e1", marginBottom: "0.45rem" }}>
              Ghi nhận <strong>{b2gAnalytics.totalPoints}</strong> điểm ngập lịch sử • Chỉ số tích lũy:{" "}
              <strong>{b2gAnalytics.totalIntensity}</strong>
            </div>
            <div style={{ fontSize: "0.75rem", color: "#94a3b8", marginBottom: "0.25rem" }}>
              Top 3 điểm nóng ưu tiên khơi thông cống:
            </div>
            {b2gAnalytics.top3.map((pt, i) => (
              <div
                key={pt.zone_id}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: "0.5rem",
                  padding: "0.3rem 0",
                  borderTop: i > 0 ? "1px solid #1e293b" : "none",
                  fontSize: "0.74rem"
                }}
              >
                <span>
                  #{i + 1} {pt.district} ({pt.city}) — {pt.flood_frequency_30d} lượt
                  {pt.peak_trigger ? ` • ${pt.peak_trigger}` : ""}
                </span>
                <span style={{ color: "#f87171", fontWeight: 600, whiteSpace: "nowrap" }}>
                  Mức TB {pt.avg_severity.toFixed(1)}
                </span>
              </div>
            ))}
          </div>
        )}

        <h2 style={{ fontSize: "0.92rem", marginBottom: "0.5rem" }}>
          Điểm ngập đang kích hoạt ({zones.length})
        </h2>
        {zones.map((z) => {
          const isSelected = selectedEntity?.kind === "zone" && selectedEntity.zone.event_id === z.event_id;
          return (
            <div
              key={z.event_id}
              onClick={() => setSelectedEntity({ kind: "zone", zone: z })}
              style={{
                padding: "0.7rem",
                background: isSelected ? "#172554" : "#0f172a",
                borderRadius: "8px",
                marginBottom: "0.5rem",
                borderLeft: z.severity_level >= 2 ? "4px solid #ef4444" : "4px solid #eab308",
                borderTop: isSelected ? "1px solid #3b82f6" : "1px solid transparent",
                fontSize: "0.82rem",
                cursor: "pointer"
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", gap: "0.4rem" }}>
                <span style={{ fontWeight: 600 }}>{z.location_name || z.event_id}</span>
                <span style={{ color: "#94a3b8", fontSize: "0.72rem" }}>M{z.severity_level}</span>
              </div>
              <div style={{ color: "#cbd5e1", marginTop: "0.15rem" }}>{z.visual_cue}</div>
              <div style={{ color: "#94a3b8", fontSize: "0.72rem", marginTop: "0.25rem" }}>
                {z.estimated_depth_cm} cm • {z.source === "camera_ai" ? "Camera AI" : "Cộng đồng"} •{" "}
                {z.vision_model}
              </div>
            </div>
          );
        })}
      </aside>

      <main style={{ background: "#0f172a", height: "100%", minWidth: 0, minHeight: 0, position: "relative", overflow: "hidden" }}>
        <FloodMap
          origin={origin}
          destination={destination}
          clickMode={clickMode}
          onSelectCoordinate={handleSelectCoordinate}
          zones={zones}
          cameras={cameras}
          routeResult={routeResult}
          heatmapPoints={heatmapPoints}
          showHeatmap={showHeatmap}
          selectedEntity={selectedEntity}
          onSelectEntity={setSelectedEntity}
          pollResultsByCamera={pollResultsByCamera}
          onResolveZone={(id) => void handleResolveZone(id)}
          onPollCamera={(camId) => void handlePollCameras(camId)}
          resolvingId={resolvingId}
          pollingCameraId={pollingCameraId}
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
