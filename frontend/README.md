# Frontend — Web App Bản Đồ Số (Google Maps Platform & Firebase)

Thư mục dành cho mã nguồn giao diện Web App (React + Vite / Next.js + **Google Maps JavaScript API** + **Firebase Web SDK**).

## Các module dự kiến
- **Live Flood Map (`Maps JavaScript API`):** Hiển thị bản đồ số đô thị (TP.HCM, Hà Nội), marker camera giao thông và vùng cảnh báo đỏ khi AI phát hiện ngập.
- **Real-time Alert Listener (`Firebase Firestore`):** Lắng nghe `onSnapshot` theo thời gian thực để cập nhật điểm ngập tức thì tới mọi tài xế trong khu vực.
- **Dynamic Rerouting UI (`Google Routes API`):** Chọn điểm đi/đến (ưu tiên chế độ `TWO_WHEELER` cho xe máy), phát hiện tuyến đường cắt vùng ngập và tự động vẽ lộ trình bẻ hướng an toàn.
- **Crowdsourcing Report Modal:** Cho phép người dân/tài xế chụp hoặc tải ảnh hiện trường kèm GPS gửi lên backend cho Gemini phân tích.
- **Flood Heatmap View (`HeatmapLayer`):** Bật/tắt lớp bản đồ nhiệt tần suất ngập phục vụ phân tích hạ tầng đô thị.
