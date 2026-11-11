# Backend — API Gateway & Dynamic Rerouting Service

Thư mục dành cho dịch vụ backend (gợi ý stack: FastAPI / Node.js Express + OSRM/Valhalla hoặc graph routing tùy biến).

## Các endpoint dự kiến
- `GET /api/health` — Kiểm tra trạng thái hệ thống.
- `GET /api/flood-zones` — Danh sách các điểm/vùng ngập đang kích hoạt theo thời gian thực.
- `POST /api/reports` — Tiếp nhận ảnh crowdsourcing kèm tọa độ GPS, chuyển sang `ai-vision` phân tích và phát cảnh báo.
- `POST /api/route` — Tính toán lộ trình giữa 2 điểm có tránh các vùng ngập đang kích hoạt (Dynamic Rerouting).
- `GET /api/heatmap` — Trả về dữ liệu tổng hợp tần suất ngập theo không gian và thời gian.
