# AI Vision — Flood Detection & Severity Estimation

Thư mục dành cho pipeline xử lý ảnh thời gian thực (bóc tách frame từ camera giao thông công cộng & ảnh người dùng báo cáo).

## Nhiệm vụ chính
1. **Frame Extractor:** Lấy snapshot/frame định kỳ từ luồng camera công cộng (ví dụ `camera.0511.vn`) hoặc xử lý ảnh crowdsourcing upload lên.
2. **Flood Level Classifier:** Nhận diện sự hiện diện của nước ngập và phân loại mức độ ngập (`0: SAFE`, `1: MINOR`, `2: MODERATE`, `3: SEVERE`) cùng độ tin cậy (`confidence`).
3. **Output chuẩn hóa:** Xuất sự kiện ngập gắn tọa độ để cập nhật lên bản đồ và kích hoạt Dynamic Rerouting.
