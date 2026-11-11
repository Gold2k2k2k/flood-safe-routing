# Data — Schemas & Sample Datasets

Thư mục lưu trữ schema chuẩn, tọa độ các điểm camera mẫu và dữ liệu mẫu dùng để seed **Firebase Firestore** và kiểm thử **Google Maps HeatmapLayer / Dynamic Rerouting** trong bản Demo 24h.

## Cấu trúc hiện có
- `cameras.sample.json` — Danh sách camera giao thông kèm tọa độ `(lat, lng)` và tên tuyến đường.
- `flood_events.sample.geojson` — Dữ liệu GeoJSON các điểm ngập mẫu để kiểm thử logic né vùng ngập với Routes API.
- `heatmap_history.sample.json` — Dữ liệu lịch sử tần suất ngập theo khu vực phục vụ trực quan hóa bản đồ nhiệt.
