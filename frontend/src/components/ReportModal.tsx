import React, { useState } from "react";
import { submitFloodReport } from "../services/api";
import type { CrowdsourcingReportResponse, SeverityLevel } from "../types/flood";

interface ReportModalProps {
  open: boolean;
  onClose: () => void;
  onSubmitted: () => void;
}

const QUICK_HOTSPOTS: Array<{ label: string; locationName: string; lat: string; lng: string }> = [
  {
    label: "Ngã tư Nguyễn Hữu Cảnh",
    locationName: "Ngã tư Nguyễn Hữu Cảnh, Bình Thạnh",
    lat: "10.7862",
    lng: "106.7085"
  },
  {
    label: "Thảo Điền - Quốc Hương",
    locationName: "Đường Quốc Hương - Xuân Thủy, Thảo Điền",
    lat: "10.8032",
    lng: "106.7280"
  },
  {
    label: "Tôn Đức Thắng - Thủ Thiêm",
    locationName: "Giao lộ Tôn Đức Thắng - Nguyễn Siêu, Quận 1",
    lat: "10.7815",
    lng: "106.7052"
  },
  {
    label: "Hàm Nghi (Đà Nẵng)",
    locationName: "Nút giao Hàm Nghi - Hùng Vương, Thanh Khê",
    lat: "16.0604",
    lng: "108.2116"
  }
];

const SEVERITY_OPTIONS: Array<{ level: SeverityLevel; label: string; color: string }> = [
  { level: 0, label: "0: Khô", color: "#16a34a" },
  { level: 1, label: "1: Ngập nhẹ", color: "#ca8a04" },
  { level: 2, label: "2: Ngập vừa", color: "#ea580c" },
  { level: 3, label: "3: Ngập sâu", color: "#dc2626" }
];

export function ReportModal({ open, onClose, onSubmitted }: ReportModalProps) {
  const [locationName, setLocationName] = useState("Ngã tư Nguyễn Hữu Cảnh, Bình Thạnh");
  const [lat, setLat] = useState("10.7862");
  const [lng, setLng] = useState("106.7085");
  const [note, setNote] = useState("Nước dâng nhanh ngập nửa bánh xe máy");
  const [mockSeverity, setMockSeverity] = useState<SeverityLevel>(2);
  const [imageBase64, setImageBase64] = useState<string | null>(null);
  const [gpsStatus, setGpsStatus] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CrowdsourcingReportResponse | null>(null);

  if (!open) return null;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") {
        setImageBase64(reader.result);
      }
    };
    reader.readAsDataURL(file);
  };

  const handleUseMyGps = () => {
    if (!("geolocation" in navigator)) {
      setGpsStatus("Trình duyệt không hỗ trợ Geolocation.");
      return;
    }
    setGpsStatus("Đang định vị GPS...");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLat(pos.coords.latitude.toFixed(6));
        setLng(pos.coords.longitude.toFixed(6));
        setLocationName("Vị trí GPS người dân hiện tại");
        setGpsStatus(`Đã lấy tọa độ GPS (±${Math.round(pos.coords.accuracy)} m)`);
      },
      (geoErr) => {
        setGpsStatus(`Không lấy được GPS: ${geoErr.message}`);
      },
      { enableHighAccuracy: true, timeout: 8000 }
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await submitFloodReport({
        lat: Number(lat),
        lng: Number(lng),
        location_name: locationName,
        reporter_note: note,
        image_base64: imageBase64,
        mock_severity_hint: mockSeverity
      });
      setResult(res);
      onSubmitted();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Gửi báo cáo thất bại.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(15, 23, 42, 0.78)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "1rem",
        zIndex: 1000
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: "480px",
          maxHeight: "92vh",
          overflowY: "auto",
          background: "#1e293b",
          border: "1px solid #334155",
          borderRadius: "12px",
          padding: "1.25rem",
          color: "#f8fafc"
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
          <h3 style={{ margin: 0, fontSize: "1.05rem" }}>Báo điểm ngập (Crowdsourcing + Gemini AI)</h3>
          <button
            type="button"
            onClick={onClose}
            style={{ background: "transparent", color: "#94a3b8", border: "none", cursor: "pointer", fontSize: "1.1rem" }}
          >
            ✕
          </button>
        </div>

        <div style={{ marginBottom: "0.75rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.4rem" }}>
            <span style={{ fontSize: "0.75rem", color: "#94a3b8" }}>Chọn nhanh điểm hay ngập hoặc lấy GPS:</span>
            <button
              type="button"
              onClick={handleUseMyGps}
              style={{
                padding: "0.3rem 0.55rem",
                fontSize: "0.75rem",
                borderRadius: "6px",
                border: "1px solid #38bdf8",
                background: "rgba(56, 189, 248, 0.14)",
                color: "#7dd3fc",
                cursor: "pointer"
              }}
            >
              📍 Lấy vị trí GPS của tôi
            </button>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem" }}>
            {QUICK_HOTSPOTS.map((spot) => (
              <button
                key={spot.label}
                type="button"
                onClick={() => {
                  setLocationName(spot.locationName);
                  setLat(spot.lat);
                  setLng(spot.lng);
                  setGpsStatus(null);
                }}
                style={{
                  padding: "0.25rem 0.55rem",
                  fontSize: "0.72rem",
                  borderRadius: "999px",
                  border: "1px solid #475569",
                  background: locationName === spot.locationName ? "#2563eb" : "#0f172a",
                  color: "#e2e8f0",
                  cursor: "pointer"
                }}
              >
                {spot.label}
              </button>
            ))}
          </div>
          {gpsStatus && <div style={{ fontSize: "0.72rem", color: "#7dd3fc", marginTop: "0.3rem" }}>{gpsStatus}</div>}
        </div>

        <form onSubmit={handleSubmit} style={{ display: "grid", gap: "0.65rem", fontSize: "0.85rem" }}>
          <label>
            Tên vị trí / Tuyến đường
            <input
              value={locationName}
              onChange={(e) => setLocationName(e.target.value)}
              style={{
                width: "100%",
                padding: "0.45rem",
                marginTop: "0.2rem",
                boxSizing: "border-box",
                background: "#0f172a",
                color: "#f8fafc",
                border: "1px solid #334155",
                borderRadius: "6px"
              }}
            />
          </label>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
            <label>
              Latitude
              <input
                value={lat}
                onChange={(e) => setLat(e.target.value)}
                style={{
                  width: "100%",
                  padding: "0.45rem",
                  marginTop: "0.2rem",
                  boxSizing: "border-box",
                  background: "#0f172a",
                  color: "#f8fafc",
                  border: "1px solid #334155",
                  borderRadius: "6px"
                }}
              />
            </label>
            <label>
              Longitude
              <input
                value={lng}
                onChange={(e) => setLng(e.target.value)}
                style={{
                  width: "100%",
                  padding: "0.45rem",
                  marginTop: "0.2rem",
                  boxSizing: "border-box",
                  background: "#0f172a",
                  color: "#f8fafc",
                  border: "1px solid #334155",
                  borderRadius: "6px"
                }}
              />
            </label>
          </div>
          <label>
            Mô tả hiện trường
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              style={{
                width: "100%",
                padding: "0.45rem",
                marginTop: "0.2rem",
                boxSizing: "border-box",
                background: "#0f172a",
                color: "#f8fafc",
                border: "1px solid #334155",
                borderRadius: "6px"
              }}
            />
          </label>

          <div>
            <div style={{ marginBottom: "0.25rem", fontSize: "0.8rem" }}>
              Mức ngập giả định (khi chạy Mock Fallback không kèm Key):
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.35rem" }}>
              {SEVERITY_OPTIONS.map((opt) => (
                <button
                  key={opt.level}
                  type="button"
                  onClick={() => setMockSeverity(opt.level)}
                  style={{
                    padding: "0.38rem 0.25rem",
                    borderRadius: "6px",
                    border: mockSeverity === opt.level ? "2px solid #ffffff" : "1px solid #475569",
                    background: mockSeverity === opt.level ? opt.color : "#0f172a",
                    color: "#f8fafc",
                    fontSize: "0.72rem",
                    fontWeight: 600,
                    cursor: "pointer"
                  }}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          <label>
            Ảnh hiện trường (hiển thị Preview & gửi Gemini Vision)
            <input type="file" accept="image/*" onChange={handleFileChange} style={{ marginTop: "0.25rem", display: "block" }} />
          </label>

          {imageBase64 && (
            <div style={{ position: "relative" }}>
              <img
                src={imageBase64}
                alt="Preview ảnh ngập"
                style={{
                  width: "100%",
                  maxHeight: "170px",
                  objectFit: "cover",
                  borderRadius: "8px",
                  border: "1px solid #334155"
                }}
              />
              <button
                type="button"
                onClick={() => setImageBase64(null)}
                style={{
                  position: "absolute",
                  top: "0.4rem",
                  right: "0.4rem",
                  background: "rgba(15,23,42,0.85)",
                  color: "#f8fafc",
                  border: "1px solid #475569",
                  borderRadius: "6px",
                  padding: "0.2rem 0.5rem",
                  fontSize: "0.72rem",
                  cursor: "pointer"
                }}
              >
                Xóa ảnh
              </button>
            </div>
          )}

          {error && <div style={{ color: "#fca5a5" }}>{error}</div>}
          {result && (
            <div
              style={{
                padding: "0.7rem",
                background: "#0f172a",
                borderRadius: "8px",
                borderLeft: result.analysis.severity_level >= 2 ? "4px solid #ef4444" : "4px solid #22c55e"
              }}
            >
              <div style={{ fontWeight: 700, marginBottom: "0.2rem" }}>
                Gemini Verdict: Mức {result.analysis.severity_level} • {result.analysis.estimated_depth_cm} cm (Tin cậy {Math.round(result.analysis.confidence * 100)}%)
              </div>
              <div style={{ color: "#cbd5e1", fontSize: "0.8rem" }}>{result.analysis.visual_cue}</div>
              <div style={{ color: "#94a3b8", fontSize: "0.72rem", marginTop: "0.25rem" }}>
                Report ID: <code>{result.report_id}</code> •{" "}
                {result.analysis.flood_detected ? "Đã kích hoạt cảnh báo vùng ngập" : "Không ghi nhận ngập"}
              </div>
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            style={{
              padding: "0.6rem",
              background: "#dc2626",
              color: "#fff",
              border: "none",
              borderRadius: "8px",
              cursor: submitting ? "wait" : "pointer",
              fontWeight: 600
            }}
          >
            {submitting ? "Đang gửi Gemini phân tích..." : "Gửi ảnh & Cảnh báo ngập"}
          </button>
        </form>
      </div>
    </div>
  );
}
