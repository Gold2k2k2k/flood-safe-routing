import React, { useState } from "react";
import { submitFloodReport } from "../services/api";
import type { CrowdsourcingReportResponse, SeverityLevel } from "../types/flood";

interface ReportModalProps {
  open: boolean;
  onClose: () => void;
  onSubmitted: () => void;
}

export function ReportModal({ open, onClose, onSubmitted }: ReportModalProps) {
  const [locationName, setLocationName] = useState("Ngã tư Nguyễn Hữu Cảnh, Bình Thạnh");
  const [lat, setLat] = useState("10.7862");
  const [lng, setLng] = useState("106.7085");
  const [note, setNote] = useState("Nước dâng nhanh ngập nửa bánh xe máy");
  const [imageBase64, setImageBase64] = useState<string | null>(null);
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
        mock_severity_hint: 2 as SeverityLevel
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
        background: "rgba(15, 23, 42, 0.75)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: "440px",
          background: "#1e293b",
          borderRadius: "10px",
          padding: "1.25rem",
          color: "#f8fafc"
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.75rem" }}>
          <h3 style={{ margin: 0 }}>Báo điểm ngập (Crowdsourcing + Gemini AI)</h3>
          <button
            type="button"
            onClick={onClose}
            style={{ background: "transparent", color: "#94a3b8", border: "none", cursor: "pointer" }}
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} style={{ display: "grid", gap: "0.65rem", fontSize: "0.85rem" }}>
          <label>
            Vị trí
            <input
              value={locationName}
              onChange={(e) => setLocationName(e.target.value)}
              style={{ width: "100%", padding: "0.45rem", marginTop: "0.2rem", boxSizing: "border-box" }}
            />
          </label>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
            <label>
              Latitude
              <input
                value={lat}
                onChange={(e) => setLat(e.target.value)}
                style={{ width: "100%", padding: "0.45rem", marginTop: "0.2rem", boxSizing: "border-box" }}
              />
            </label>
            <label>
              Longitude
              <input
                value={lng}
                onChange={(e) => setLng(e.target.value)}
                style={{ width: "100%", padding: "0.45rem", marginTop: "0.2rem", boxSizing: "border-box" }}
              />
            </label>
          </div>
          <label>
            Mô tả nhanh
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              style={{ width: "100%", padding: "0.45rem", marginTop: "0.2rem", boxSizing: "border-box" }}
            />
          </label>
          <label>
            Ảnh hiện trường (tùy chọn khi test Mock Fallback)
            <input type="file" accept="image/*" onChange={handleFileChange} style={{ marginTop: "0.2rem" }} />
          </label>

          {error && <div style={{ color: "#fca5a5" }}>{error}</div>}
          {result && (
            <div style={{ padding: "0.6rem", background: "#0f172a", borderRadius: "6px" }}>
              <div>
                <strong>AI Verdict:</strong> Mức {result.analysis.severity_level} ({result.analysis.estimated_depth_cm} cm)
              </div>
              <div style={{ color: "#cbd5e1" }}>{result.analysis.visual_cue}</div>
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            style={{
              padding: "0.55rem",
              background: "#dc2626",
              color: "#fff",
              border: "none",
              borderRadius: "6px",
              cursor: "pointer"
            }}
          >
            {submitting ? "Đang gửi Gemini phân tích..." : "Gửi ảnh & Cảnh báo"}
          </button>
        </form>
      </div>
    </div>
  );
}
