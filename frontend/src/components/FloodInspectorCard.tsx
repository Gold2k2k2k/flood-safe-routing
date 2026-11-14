import type { CameraItem, CameraPollResultItem, FloodZoneItem } from "../types/flood";

export type SelectedMapEntity =
  | { kind: "zone"; zone: FloodZoneItem }
  | { kind: "camera"; camera: CameraItem; pollResult?: CameraPollResultItem };

interface FloodInspectorCardProps {
  selected: SelectedMapEntity | null;
  onClose: () => void;
  onResolveZone?: (eventId: string) => void;
  onPollCamera?: (cameraId: string) => void;
  resolvingId?: string | null;
  pollingCameraId?: string | null;
}

const SEVERITY_COLORS: Record<number, { bg: string; label: string }> = {
  0: { bg: "#16a34a", label: "0 — Khô ráo" },
  1: { bg: "#ca8a04", label: "1 — Ngập nhẹ (<15 cm)" },
  2: { bg: "#ea580c", label: "2 — Ngập trung bình (15–30 cm)" },
  3: { bg: "#dc2626", label: "3 — Ngập sâu (>30 cm)" }
};

export function FloodInspectorCard({
  selected,
  onClose,
  onResolveZone,
  onPollCamera,
  resolvingId,
  pollingCameraId
}: FloodInspectorCardProps) {
  if (!selected) return null;

  if (selected.kind === "zone") {
    const { zone } = selected;
    const sevMeta = SEVERITY_COLORS[zone.severity_level] ?? SEVERITY_COLORS[2];
    const isResolving = resolvingId === zone.event_id;
    const passableText =
      zone.severity_level >= 2
        ? "⛔ Nguy hiểm cho xe máy (né tuyến)"
        : zone.severity_level === 1
          ? "⚠️ Xe máy đi chậm chú ý"
          : "✓ Lưu thông bình thường";

    return (
      <div
        style={{
          position: "absolute",
          right: "1rem",
          bottom: "1rem",
          width: "330px",
          maxWidth: "calc(100% - 2rem)",
          background: "rgba(15, 23, 42, 0.96)",
          border: "1px solid #334155",
          borderRadius: "12px",
          padding: "0.9rem 1rem",
          color: "#f8fafc",
          boxShadow: "0 14px 35px rgba(0,0,0,0.45)",
          zIndex: 20,
          backdropFilter: "blur(8px)"
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem" }}>
          <div>
            <div style={{ fontSize: "0.7rem", textTransform: "uppercase", letterSpacing: "0.06em", color: "#94a3b8" }}>
              AI Vision Inspector • {zone.source === "camera_ai" ? "Camera AI" : "Cộng đồng"}
            </div>
            <h4 style={{ margin: "0.2rem 0 0 0", fontSize: "0.95rem" }}>
              {zone.location_name || zone.event_id}
            </h4>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Đóng inspector"
            style={{ background: "transparent", border: "none", color: "#94a3b8", cursor: "pointer", fontSize: "1rem" }}
          >
            ✕
          </button>
        </div>

        <div style={{ marginTop: "0.65rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.78rem", marginBottom: "0.3rem" }}>
            <span style={{ color: "#e2e8f0", fontWeight: 600 }}>{sevMeta.label}</span>
            <span style={{ color: "#94a3b8" }}>{zone.estimated_depth_cm} cm</span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "4px", height: "6px" }}>
            {[0, 1, 2, 3].map((lvl) => (
              <div
                key={lvl}
                style={{
                  borderRadius: "999px",
                  background: lvl <= zone.severity_level ? sevMeta.bg : "#334155"
                }}
              />
            ))}
          </div>
        </div>

        <div
          style={{
            marginTop: "0.65rem",
            padding: "0.45rem 0.6rem",
            borderRadius: "6px",
            background: zone.severity_level >= 2 ? "rgba(220, 38, 38, 0.16)" : "rgba(202, 138, 4, 0.16)",
            color: zone.severity_level >= 2 ? "#fca5a5" : "#fde047",
            fontSize: "0.78rem",
            fontWeight: 600
          }}
        >
          {passableText}
        </div>

        <p style={{ margin: "0.6rem 0 0 0", fontSize: "0.8rem", color: "#cbd5e1", lineHeight: 1.4 }}>
          {zone.visual_cue}
        </p>

        <div
          style={{
            marginTop: "0.6rem",
            display: "flex",
            flexWrap: "wrap",
            gap: "0.5rem",
            fontSize: "0.72rem",
            color: "#94a3b8"
          }}
        >
          <span>Tin cậy: {Math.round(zone.confidence * 100)}%</span>
          <span>• Bán kính: {zone.radius_meters} m</span>
          <span>• {zone.vision_model}</span>
        </div>

        {onResolveZone && (
          <button
            type="button"
            disabled={isResolving}
            onClick={() => onResolveZone(zone.event_id)}
            style={{
              marginTop: "0.75rem",
              width: "100%",
              padding: "0.5rem 0.75rem",
              borderRadius: "8px",
              border: "1px solid #16a34a",
              background: "rgba(22, 163, 74, 0.2)",
              color: "#86efac",
              cursor: isResolving ? "wait" : "pointer",
              fontSize: "0.8rem",
              fontWeight: 600
            }}
          >
            {isResolving ? "Đang giải tỏa..." : "✓ Giải tỏa điểm ngập (Nước đã rút)"}
          </button>
        )}
      </div>
    );
  }

  const { camera, pollResult } = selected;
  const isPolling = pollingCameraId === camera.camera_id;

  return (
    <div
      style={{
        position: "absolute",
        right: "1rem",
        bottom: "1rem",
        width: "330px",
        maxWidth: "calc(100% - 2rem)",
        background: "rgba(15, 23, 42, 0.96)",
        border: "1px solid #334155",
        borderRadius: "12px",
        padding: "0.9rem 1rem",
        color: "#f8fafc",
        boxShadow: "0 14px 35px rgba(0,0,0,0.45)",
        zIndex: 20,
        backdropFilter: "blur(8px)"
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem" }}>
        <div>
          <div style={{ fontSize: "0.7rem", textTransform: "uppercase", letterSpacing: "0.06em", color: "#38bdf8" }}>
            Traffic Camera AI • {camera.city}
          </div>
          <h4 style={{ margin: "0.2rem 0 0 0", fontSize: "0.95rem" }}>{camera.name}</h4>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Đóng inspector"
          style={{ background: "transparent", border: "none", color: "#94a3b8", cursor: "pointer", fontSize: "1rem" }}
        >
          ✕
        </button>
      </div>

      <div style={{ marginTop: "0.5rem", fontSize: "0.75rem", color: "#94a3b8", display: "grid", gap: "0.2rem" }}>
        <div>Mã Camera: <code>{camera.camera_id}</code> • Nguồn: <code>{camera.source}</code></div>
        <div>Tọa độ: {camera.lat.toFixed(4)}, {camera.lng.toFixed(4)}{camera.road_segment_id ? ` • Tuyến: ${camera.road_segment_id}` : ""}</div>
      </div>

      {pollResult ? (
        <div
          style={{
            marginTop: "0.65rem",
            padding: "0.55rem 0.65rem",
            borderRadius: "8px",
            background: "#1e293b",
            border: "1px solid #334155",
            fontSize: "0.78rem"
          }}
        >
          <div style={{ fontWeight: 600, color: pollResult.analysis.severity_level >= 2 ? "#fca5a5" : "#86efac" }}>
            Kết quả quét gần nhất: Mức {pollResult.analysis.severity_level} ({pollResult.analysis.estimated_depth_cm} cm)
          </div>
          <div style={{ color: "#cbd5e1", marginTop: "0.25rem" }}>{pollResult.analysis.visual_cue}</div>
          <div style={{ color: "#94a3b8", fontSize: "0.7rem", marginTop: "0.25rem" }}>
            Tin cậy: {Math.round(pollResult.analysis.confidence * 100)}%
            {pollResult.frame_delta_skipped ? " • Cache hit (Frame không đổi)" : ""}
          </div>
        </div>
      ) : (
        <div style={{ marginTop: "0.6rem", fontSize: "0.78rem", color: "#94a3b8" }}>
          Chưa có kết quả quét trực tiếp trong phiên này. Bấm nút bên dưới để chạy AI Vision trên frame mới nhất.
        </div>
      )}

      {onPollCamera && (
        <button
          type="button"
          disabled={isPolling}
          onClick={() => onPollCamera(camera.camera_id)}
          style={{
            marginTop: "0.75rem",
            width: "100%",
            padding: "0.5rem 0.75rem",
            borderRadius: "8px",
            border: "none",
            background: "#0284c7",
            color: "#ffffff",
            cursor: isPolling ? "wait" : "pointer",
            fontSize: "0.8rem",
            fontWeight: 600
          }}
        >
          {isPolling ? "Đang trích xuất & phân tích frame..." : "🔍 Quét AI Camera này"}
        </button>
      )}
    </div>
  );
}
