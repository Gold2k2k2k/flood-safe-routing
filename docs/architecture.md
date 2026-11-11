# Kiến trúc kỹ thuật — Flood-Safe Routing (Google Tech Stack)

Tài liệu này mô tả chi tiết luồng dữ liệu thời gian thực, pipeline **Gemini 3.8 Flash (Vision)**, đồng bộ **Firebase / Google Cloud** và cơ chế **Dynamic Rerouting** trên **Google Maps Platform**.

## 1. Luồng xử lý thời gian thực (Real-time Pipeline)

1. **Thu nhận đa nguồn (Ingestion):**
   - *Nguồn Camera công cộng:* Worker chạy trên **Google Cloud Run / Cloud Functions** định kỳ lấy frame ảnh mới nhất (mỗi 15–30 giây) từ các camera có gắn sẵn tọa độ GPS (`camera_id`, `lat`, `lng`, `road_segment_id`).
   - *Nguồn Crowdsourcing:* Người dân/tài xế chụp hoặc tải ảnh qua Web App kèm tọa độ GPS hiện tại; ảnh được lưu tạm lên **Firebase Storage / Cloud Storage**.
2. **Phân tích hình ảnh bằng Gemini 3.8 Flash (Vision):**
   - Đầu vào: Frame ảnh RGB kèm prompt hướng dẫn nhận diện chuẩn mực nước theo vật chuẩn thực tế (**ngập lề đường**, **ngập nửa bánh xe**, **ngập sâu vượt ống xả/yên xe**).
   - Model cấu hình qua biến `GEMINI_MODEL` (mặc định `gemini-3.8-flash`).
   - Đầu ra JSON chuẩn hóa (`Structured Output`):
     ```json
     {
       "flood_detected": true,
       "severity_level": 2,
       "visual_cue": "Nước ngập quá mép lề đường và chạm nửa bánh xe máy",
       "estimated_depth_cm": "20-35",
       "passable_for_motorbike": false,
       "confidence": 0.91,
       "timestamp": "2026-11-11T10:00:00+07:00"
     }
     ```
   - Quy ước mức ngập (`severity_level`):
     - `0` (`SAFE`): Mặt đường khô hoặc chỉ ướt mưa nhẹ.
     - `1` (`MINOR`): Ngập mép lề đường (< 15 cm), xe máy đi chậm vẫn qua được (cảnh báo vàng).
     - `2` (`MODERATE`): Ngập khoảng nửa bánh xe (15–35 cm), nguy cơ chết máy cao (đánh dấu đỏ, kích hoạt rerouting né điểm ngập).
     - `3` (`SEVERE`): Ngập sâu (> 35 cm), tê liệt lưu thông xe máy (đánh dấu đỏ đậm, bắt buộc né hoàn toàn).
3. **Đồng bộ thời gian thực qua Firebase / Google Cloud:**
   - Khi `severity_level >= 2` (hoặc có cập nhật trạng thái mới), backend ghi bản ghi vào **Cloud Firestore** (`active_flood_zones`) kèm `ttl_expires_at` và lưu bản sao vào bảng lịch sử (`flood_events_history`).
   - Toàn bộ Web App của tài xế trong khu vực lắng nghe Firestore qua **real-time listener (`onSnapshot`)**, nhận cảnh báo đỏ ngay lập tức mà không cần tự vận hành WebSocket server riêng.

## 2. Dynamic Rerouting với Google Maps Platform (Maps JS & Routes API)

Vì **Google Routes API** (`computeRoutes`) không hỗ trợ truyền trực tiếp polygon/tọa độ để chặn đường như các routing engine tự host, hệ thống triển khai chiến lược 2 lớp kết hợp:

1. **Ưu tiên chế độ xe máy & nhiều tuyến thay thế:**
   - Gọi `Routes API` với `travelMode: "TWO_WHEELER"` và `computeAlternativeRoutes: true` để nhận các tuyến đường phù hợp cho xe máy và tài xế giao hàng ngách.
2. **Kiểm tra giao cắt vùng ngập & vòng tránh (Flood Intersection Check + Detour Waypoint):**
   - Giải mã polyline các tuyến đường trả về từ `Routes API` và kiểm tra khoảng cách tới các tọa độ ngập đỏ đang kích hoạt trong `active_flood_zones` (ví dụ bán kính an toàn `R = 80m–150m`).
   - Nếu tuyến chính đi xuyên qua vùng ngập đỏ:
     - **Lớp 1:** Chọn tuyến thay thế (`alternative route`) không giao cắt vùng ngập.
     - **Lớp 2:** Nếu tất cả tuyến mặc định đều đi qua vùng ngập, tính toán một **điểm trung gian vòng tránh (`via` waypoint)** nằm ở phía không ngập gần đó và gọi lại `Routes API` để bẻ hướng lộ trình an toàn.
3. **Tái định tuyến tức thời (Live Trigger):**
   - Khi `onSnapshot` của Firebase phát hiện điểm ngập đỏ mới xuất hiện trên polyline lộ trình hiện tại của tài xế, Web App tự động kích hoạt quy trình rerouting và vẽ lại đường đi mới trên **Maps JavaScript API**.

## 3. Flood Frequency Heatmap (Dữ liệu quy hoạch đô thị)

- Mọi sự kiện ngập đã được Gemini xác nhận từ `flood_events_history` (gồm `lat`, `lng`, `severity_level`, `duration_minutes`, `created_at`) được tổng hợp theo tần suất và trọng số mức ngập.
- Frontend dùng **`HeatmapOverlay` (`google.maps.OverlayView` Canvas)** trên nền Maps JS API v3.65+ (hoặc tùy chọn `deck.gl` `HeatmapLayer` vì `google.maps.visualization.HeatmapLayer` đã bị Google ngừng hỗ trợ từ v3.65) để hiển thị bản đồ nhiệt tần suất ngập trực tiếp trên nền bản đồ, phục vụ cơ quan quản lý đô thị đánh giá điểm nóng ngập lụt để cải tạo hạ tầng thoát nước.
