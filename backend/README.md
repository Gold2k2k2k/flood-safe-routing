# Backend — Google Cloud API, Routes Orchestration & Firebase Sync

Thư mục dành cho dịch vụ backend triển khai trên **Google Cloud Run / Cloud Functions** (FastAPI hoặc Node.js Express) kết nối **Firebase Admin SDK**, **Gemini API** và **Google Routes API**.

## Các endpoint & tác vụ dự kiến
- `GET /api/health` — Kiểm tra trạng thái hệ thống.
- `GET /api/flood-zones` — Đọc các điểm ngập đang kích hoạt từ **Cloud Firestore**.
- `POST /api/reports` — Tiếp nhận ảnh crowdsourcing + GPS, lưu ảnh lên **Cloud Storage / Firebase Storage**, gọi module `ai-vision` (**Gemini 3.8 Flash**) chấm mức ngập và ghi Firestore để đồng bộ real-time.
- `POST /api/route` — Gọi **Google Routes API** (`TWO_WHEELER`, `computeAlternativeRoutes`) và xử lý kiểm tra giao cắt / chèn detour waypoint né các tọa độ ngập đang kích hoạt.
- `GET /api/heatmap` — Truy vấn dữ liệu lịch sử từ Firestore phục vụ **Google Maps HeatmapLayer**.
- **Camera Polling Worker:** Định kỳ kéo snapshot từ danh sách camera công cộng (`camera.0511.vn`) gửi sang Gemini phân tích.
