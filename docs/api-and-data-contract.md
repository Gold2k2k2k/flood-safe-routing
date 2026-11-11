# Hợp Đồng Dữ Liệu & API (API & Firestore Data Contract)

> **Tài liệu bắt buộc cho tất cả thành viên (`Frontend`, `Backend`, `AI Vision`).** Mọi giao tiếp giữa các module phải tuân thủ chính xác tên trường và kiểu dữ liệu dưới đây để ghép code không bị lỗi.

---

## 1. Đầu Ra Chuẩn Của Module AI Vision (`FloodAnalysisResult`)

Module `ai-vision/src/analyzer.py` nhận đầu vào là `bytes` ảnh (từ camera giao thông hoặc ảnh người dùng upload) và trả về đối tượng Pydantic / JSON theo đúng cấu trúc sau:

```json
{
  "flood_detected": true,
  "severity_level": 2,
  "visual_cue": "Nước ngập qua mép lề đường và chạm khoảng nửa bánh xe máy",
  "estimated_depth_cm": "20-35",
  "passable_for_motorbike": false,
  "confidence": 0.92,
  "vision_model": "gemini-3.8-flash",
  "analyzed_at": "2026-11-11T10:30:00+07:00"
}
```

### Quy ước `severity_level`:
| Giá trị | Nhãn | Mô tả mốc trực quan (Visual Cue) | Xe máy qua được (`passable_for_motorbike`) | Hành động của Hệ thống |
| :---: | :--- | :--- | :---: | :--- |
| `0` | `SAFE` | Mặt đường khô ráo hoặc chỉ ướt mặt nhựa | `true` | Bình thường (Xanh) |
| `1` | `MINOR` | Nước đọng sát mép lề đường (< 15 cm), chưa ngập vành xe | `true` | Cảnh báo nhẹ (Vàng) |
| `2` | `MODERATE` | Ngập quá lề đường, chạm từ 1/3 đến nửa bánh xe máy (15–35 cm) | `false` | **Báo động Đỏ + Kích hoạt Dynamic Rerouting** |
| `3` | `SEVERE` | Ngập sâu lút bánh xe, chạm ống xả/yên xe (> 35 cm) | `false` | **Phong tỏa Đỏ Đậm + Bắt buộc Rerouting** |

---

## 2. Cấu Trúc Firebase Firestore Collections

### 2.1. Collection `active_flood_zones` (Đồng bộ Real-time qua `onSnapshot`)
Lưu các điểm đang bị ngập (`severity_level >= 1`) để hiển thị lên bản đồ và tránh đường:
```json
{
  "event_id": "evt_hcm_001",
  "source": "camera_ai",
  "camera_id": "cam_hcm_001",
  "location_name": "Ngã tư Nguyễn Hữu Cảnh - Tôn Đức Thắng",
  "lat": 10.7858,
  "lng": 106.7082,
  "radius_meters": 120,
  "severity_level": 2,
  "visual_cue": "Nước ngập quá mép lề đường và chạm nửa bánh xe máy",
  "estimated_depth_cm": "20-35",
  "passable_for_motorbike": false,
  "confidence": 0.91,
  "vision_model": "gemini-3.8-flash",
  "status": "active",
  "updated_at": "2026-11-11T10:00:00+07:00",
  "ttl_expires_at": "2026-11-11T10:30:00+07:00"
}
```
> `source` nhận một trong hai giá trị: `"camera_ai"` hoặc `"crowdsourcing_ai"`.

### 2.2. Collection `flood_events_history` (Phục vụ Heatmap Quy Hoạch Đô Thị)
Lưu lịch sử tần suất ngập theo khu vực:
```json
{
  "zone_id": "hcm_binh_thanh_nhc",
  "city": "TP.HCM",
  "district": "Bình Thạnh",
  "lat": 10.7895,
  "lng": 106.7124,
  "flood_frequency_30d": 12,
  "avg_severity": 2.3,
  "peak_trigger": "high_tide_and_rain"
}
```

---

## 3. Hợp Đồng REST API (Backend FastAPI — Cổng mặc định `8000`)

### 3.1. `GET /api/health`
Kiểm tra trạng thái hoạt động của server và chế độ cấu hình.
- **Response `200 OK`:**
  ```json
  {
    "status": "ok",
    "mock_fallback_enabled": true,
    "gemini_model": "gemini-3.8-flash",
    "services": {
      "gemini_configured": false,
      "google_maps_configured": false,
      "firebase_configured": false
    }
  }
  ```

### 3.2. `GET /api/flood-zones`
Trả về danh sách các vùng ngập đang kích hoạt (dùng cho khởi tạo ban đầu hoặc khi chưa bật Firestore listener).
- **Response `200 OK`:**
  ```json
  {
    "count": 1,
    "items": [
      {
        "event_id": "evt_001",
        "source": "camera_ai",
        "camera_id": "cam_hcm_001",
        "lat": 10.7858,
        "lng": 106.7082,
        "radius_meters": 120,
        "severity_level": 2,
        "visual_cue": "Nước ngập quá mép lề đường và chạm nửa bánh xe máy",
        "estimated_depth_cm": "20-35",
        "passable_for_motorbike": false,
        "confidence": 0.91,
        "status": "active",
        "updated_at": "2026-11-11T10:00:00+07:00"
      }
    ]
  }
  ```

### 3.3. `POST /api/reports`
Người dân / tài xế gửi báo cáo ngập kèm ảnh hiện trường (hoặc URL/base64 ảnh) và tọa độ GPS.
- **Request (`multipart/form-data` hoặc `application/json`):**
  ```json
  {
    "lat": 10.7858,
    "lng": 106.7082,
    "location_name": "Nguyễn Hữu Cảnh, Bình Thạnh",
    "reporter_note": "Nước dâng nhanh sau mưa 20 phút",
    "image_base64": "<chuỗi_base64_hoặc_để_trống_khi_test_mock>"
  }
  ```
- **Response `200 OK`:**
  ```json
  {
    "report_id": "rep_001",
    "analysis": {
      "flood_detected": true,
      "severity_level": 2,
      "visual_cue": "Nước ngập quá mép lề đường và chạm nửa bánh xe máy",
      "estimated_depth_cm": "20-35",
      "passable_for_motorbike": false,
      "confidence": 0.91,
      "vision_model": "gemini-3.8-flash"
    },
    "broadcasted_to_firestore": true
  }
  ```

### 3.4. `POST /api/route` (Dynamic Rerouting)
Tính toán lộ trình an toàn cho xe máy (`TWO_WHEELER`), tự động kiểm tra giao cắt với các điểm ngập đỏ (`severity_level >= 2`) và bẻ hướng nếu cần.
- **Request (`application/json`):**
  ```json
  {
    "origin": { "lat": 10.7769, "lng": 106.7009 },
    "destination": { "lat": 10.7992, "lng": 106.7185 },
    "travel_mode": "TWO_WHEELER",
    "avoid_flood_zones": true
  }
  ```
- **Response `200 OK`:**
  ```json
  {
    "rerouted": true,
    "avoided_flood_zone_ids": ["evt_001"],
    "detour_waypoint_used": { "lat": 10.7885, "lng": 106.7020 },
    "distance_meters": 4850,
    "duration_seconds": 780,
    "encoded_polyline": "}_ilA...",
    "route_coordinates": [
      { "lat": 10.7769, "lng": 106.7009 },
      { "lat": 10.7885, "lng": 106.7020 },
      { "lat": 10.7992, "lng": 106.7185 }
    ],
    "warning_message": "Đã tự động bẻ hướng né 1 điểm ngập sâu tại Ngã tư Nguyễn Hữu Cảnh."
  }
  ```

### 3.5. `GET /api/heatmap`
Lấy dữ liệu tổng hợp tần suất ngập phục vụ `google.maps.visualization.HeatmapLayer`.
- **Response `200 OK`:**
  ```json
  {
    "count": 2,
    "items": [
      {
        "zone_id": "hcm_binh_thanh_nhc",
        "city": "TP.HCM",
        "district": "Bình Thạnh",
        "lat": 10.7895,
        "lng": 106.7124,
        "flood_frequency_30d": 12,
        "avg_severity": 2.3,
        "weight": 27.6
      }
    ]
  }
  ```
