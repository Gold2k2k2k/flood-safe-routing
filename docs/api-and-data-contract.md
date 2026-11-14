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
        "vision_model": "gemini-3.8-flash",
        "status": "active",
        "updated_at": "2026-11-11T10:00:00+07:00",
        "ttl_expires_at": "2026-11-11T10:15:00+07:00"
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
- **Các trường mở rộng trong `RouteResponse`:**
  - `baseline_route_coordinates`: `list[LatLng]` — Danh sách tọa độ của lộ trình trực tiếp ban đầu (trước khi né ngập), dùng để frontend vẽ đường nét đứt đỏ so sánh trước/sau khi né ngập.
  - `detour_waypoints_used`: `list[LatLng]` — Danh sách toàn bộ các điểm vòng tránh (`via` detour waypoints) được chèn vào lộ trình khi né một hoặc nhiều vùng ngập.
  - `detour_waypoint_used`: `LatLng | None` — Điểm vòng tránh đầu tiên (giữ lại để đảm bảo tương thích ngược).
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
    "detour_waypoints_used": [
      { "lat": 10.7885, "lng": 106.7020 }
    ],
    "baseline_route_coordinates": [
      { "lat": 10.7769, "lng": 106.7009 },
      { "lat": 10.7992, "lng": 106.7185 }
    ],
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
Lấy dữ liệu tổng hợp tần suất ngập phục vụ lớp bản đồ nhiệt (`HeatmapOverlay` trên `google.maps.OverlayView` Canvas).
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

### 3.6. `GET /api/cameras`
Lấy danh sách các điểm camera giao thông đang theo dõi (kèm tọa độ GPS và tên tuyến đường).
- **Các trường mở rộng trong `CameraItem`:**
  - `local_image_path`: `str | None` — Đường dẫn tương đối hoặc tuyệt đối tới file ảnh tĩnh mẫu trên đĩa (ví dụ: `"data/sample_frames/level_2_moderate.jpg"`) dùng cho kiểm thử offline hoặc stage demo.
  - `default_severity_hint`: `int | None` — Mức độ ngập mặc định (`0..3`) dùng làm gợi ý khi kích hoạt mock polling nếu client không chỉ định rõ.
- **Response `200 OK`:**
  ```json
  {
    "count": 7,
    "items": [
      {
        "camera_id": "cam_dn_001",
        "name": "Ngã tư Hàm Nghi - Nguyễn Văn Linh",
        "city": "Đà Nẵng",
        "source": "public_traffic_camera",
        "feed_url": "https://camera.0511.vn",
        "lat": 16.0604,
        "lng": 108.2104,
        "road_segment_id": "seg_dn_hnnvl_01",
        "local_image_path": "data/sample_frames/level_2_moderate.jpg",
        "default_severity_hint": 2
      }
    ]
  }
  ```

### 3.7. `POST /api/cameras/poll`
Kích hoạt kiểm tra snapshot/frame mới nhất từ danh sách camera (hoặc một tập `camera_ids` chỉ định), đưa qua `ai-vision` phân tích và đồng bộ vào Firestore nếu phát hiện ngập (`severity_level >= 1`).
- **Các trường mở rộng:**
  - Request: `force_refresh: bool = False` — Nếu `true`, ép phân tích lại AI bỏ qua bộ đệm sai khác frame delta (frame-delta hash deduplication).
  - Response item (`CameraPollResultItem`): `frame_delta_skipped: bool = False` — Đánh dấu frame không thay đổi so với lần poll trước (`delta < 0.04`) nên đã bỏ qua gọi AI để tiết kiệm quota.
- **Request (`application/json`, tùy chọn body rỗng):**
  ```json
  {
    "camera_ids": ["cam_dn_001"],
    "mock_severity_hint": 2,
    "force_refresh": false
  }
  ```
- **Response `200 OK`:**
  ```json
  {
    "polled_count": 1,
    "flooded_count": 1,
    "results": [
      {
        "camera_id": "cam_dn_001",
        "frame_source": "local_image",
        "analysis": {
          "flood_detected": true,
          "severity_level": 2,
          "visual_cue": "Nước ngập quá mép lề đường và chạm khoảng nửa bánh xe máy",
          "estimated_depth_cm": "20-35",
          "passable_for_motorbike": false,
          "confidence": 0.92,
          "vision_model": "gemini-3.8-flash (mock-fallback)",
          "analyzed_at": "2026-11-14T01:30:00+00:00"
        },
        "broadcasted_to_firestore": false,
        "frame_delta_skipped": false
      }
    ]
  }
  ```

### 3.8. Các Endpoint Điều Khiển Kịch Bản Demo Sân Khấu (Demo Scenario Control)

#### `POST /api/flood-zones/reset`
Khôi phục danh sách các vùng ngập về trạng thái mẫu ban đầu từ file `data/flood_events.sample.geojson` và xóa sạch bộ đệm frame camera trong bộ nhớ (`_LAST_CAMERA_FRAMES`). Phục vụ việc reset demo nhiều lần trên sân khấu mà không cần khởi động lại backend.
- **Request (`application/json`):** Body rỗng `{}`
- **Response `200 OK`:** Trả về `FloodZonesListResponse`
  ```json
  {
    "count": 4,
    "items": [
      {
        "event_id": "evt_001",
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
        "updated_at": "2026-11-11T10:00:00+07:00"
      }
    ]
  }
  ```

#### `DELETE /api/flood-zones/{event_id}`
Xóa hoặc giải tỏa một vùng ngập đang kích hoạt (cả trong bộ nhớ và Firestore), phục vụ kịch bản demo: khi nước rút hoặc đội cứu hộ xử lý xong điểm ngập, đường sẽ thông trở lại và hệ thống hủy reroute.
- **Path Parameter:** `event_id: str` (ví dụ: `evt_dn_001`)
- **Response `200 OK`:**
  ```json
  {
    "deleted": true,
    "event_id": "evt_dn_001"
  }
  ```
