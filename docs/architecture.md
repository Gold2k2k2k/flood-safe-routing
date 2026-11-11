# Kiến trúc kỹ thuật — Flood-Safe Routing

Tài liệu này mô tả chi tiết luồng dữ liệu, mô hình đánh giá mức ngập và nguyên lý điều hướng động (Dynamic Rerouting) cho bản Demo 24h.

## 1. Luồng xử lý thời gian thực (Real-time Pipeline)

1. **Thu nhận (Ingestion):**
   - *Nguồn Camera công cộng:* Worker định kỳ lấy snapshot/frame mới nhất (mỗi 15–30 giây) từ danh sách camera có gắn sẵn tọa độ GPS (`camera_id`, `lat`, `lng`, `road_segment_id`).
   - *Nguồn Crowdsourcing:* Người dùng/tài xế chụp ảnh trực tiếp qua Web App kèm tọa độ GPS hiện tại và mô tả ngắn.
2. **Phân tích AI (AI Flood Vision):**
   - Đầu vào: Ảnh RGB từ camera hoặc người dùng.
   - Đầu ra JSON chuẩn hóa:
     ```json
     {
       "flood_detected": true,
       "severity_level": 2,
       "estimated_depth_cm": "25-40",
       "passable_for_motorbike": false,
       "confidence": 0.89,
       "timestamp": "2026-11-11T10:00:00+07:00"
     }
     ```
   - Quy ước mức ngập (`severity_level`):
     - `0` (`SAFE`): Đường khô hoặc chỉ ẩm ướt bề mặt.
     - `1` (`MINOR`): Ngập nhẹ (< 15 cm), xe máy đi chậm vẫn qua được (tăng chi phí tuyến đường).
     - `2` (`MODERATE`): Ngập nửa bánh xe (15–35 cm), nguy cơ chết máy cao (cảnh báo đỏ, ưu tiên né).
     - `3` (`SEVERE`): Ngập sâu (> 35 cm), không thể lưu thông cho xe máy (chặn cạnh trên đồ thị đường).

## 2. Dynamic Rerouting (Điều hướng né điểm ngập)

Khi tính toán tuyến đường từ điểm `A` đến điểm `B`:
- Hệ thống lấy danh sách các điểm/đoạn ngập đang kích hoạt (TTL tự động hết hạn nếu không còn xác nhận mới hoặc camera hết ngập).
- Mỗi đoạn đường (graph edge $e$) có trọng số di chuyển hiệu chỉnh:

$$
w'(e) = \begin{cases}
\infty & \text{nếu } \text{severity}(e) \ge 2 \text{ (né/chặn với xe máy)} \\
w(e) \times (1 + \alpha \cdot \text{severity}(e)) & \text{nếu } \text{severity}(e) = 1 \\
w(e) & \text{nếu } \text{severity}(e) = 0
\end{cases}
$$

- Khi một điểm ngập mới (`severity >= 2`) xuất hiện trên lộ trình hiện tại của tài xế, Web App nhận sự kiện cập nhật (WebSocket / Polling) và kích hoạt **Dynamic Rerouting** ngay lập tức.

## 3. Flood Frequency Heatmap (Dữ liệu quy hoạch đô thị)

- Mọi sự kiện ngập đã được xác thực đều được ghi log lịch sử `(lat, lng, severity_level, duration_minutes, weather_context, created_at)`.
- Dữ liệu được tổng hợp theo ô lưới không gian (Spatial Grid / H3 Hexagon) để vẽ **Heatmap tần suất ngập**, hỗ trợ cơ quan quản lý đô thị xác định các "điểm đen" thoát nước cần ưu tiên cải tạo.
