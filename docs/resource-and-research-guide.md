# Hướng Dẫn Chuẩn Bị Tài Nguyên & Tổng Hợp Research Kỹ Thuật

Tài liệu này hướng dẫn từng bước khởi tạo 3 tài nguyên Google (Gemini, Google Maps Platform, Firebase) và giải thích chi tiết các giải pháp kỹ thuật thực chiến đã nghiên cứu cho dự án.

---

## 1. Hướng Dẫn Khởi Tạo Nhanh Tài Nguyên Google (15–20 Phút)

### 1.1. Lấy `GEMINI_API_KEY` (Google AI Studio)
1. Truy cập https://aistudio.google.com/apikey và đăng nhập bằng tài khoản Google.
2. Nhấn **Create API key** -> chọn project Google Cloud của nhóm.
3. Dán key vào biến `GEMINI_API_KEY` trong file `.env`.
4. Biến `GEMINI_MODEL` mặc định đặt là `gemini-3.8-flash` (được đọc động từ `.env`, giúp chuyển đổi tức thời mà không cần sửa code).

### 1.2. Thiết lập Google Maps Platform (`Maps JS API` & `Routes API`)
1. Truy cập Google Cloud Console -> **APIs & Services -> Library**.
2. Tìm và nhấn **Enable** cho 3 API sau:
   - **Maps JavaScript API** (Hiển thị bản đồ, vẽ đường, vẽ Heatmap).
   - **Routes API** (Tính toán đường đi xe máy `TWO_WHEELER` và các tuyến thay thế).
   - **Places API (New)** (Gợi ý địa điểm khi người dùng nhập điểm đi / điểm đến).
3. Vào **APIs & Services -> Credentials -> Create Credentials -> API key**:
   - Điền vào `GOOGLE_MAPS_API_KEY` (dùng cho Backend gọi Routes API) và `VITE_GOOGLE_MAPS_API_KEY` (dùng cho Frontend hiển thị bản đồ).
   - *Lưu ý:* Khi nhúng Maps JS API v3.65+ ở Frontend, cấu hình `libraries={["geometry", "places"]}` (lớp Heatmap được vẽ qua `google.maps.OverlayView` Canvas trong `HeatmapOverlay.tsx` do `visualization.HeatmapLayer` đã bị Google ngừng hỗ trợ từ v3.65).

### 1.3. Thiết lập Firebase Project (`Firestore` & `Storage`)
1. Truy cập https://console.firebase.google.com/ -> **Add project** (liên kết cùng Google Cloud project ở trên).
2. Vào **Build -> Firestore Database -> Create database**:
   - Chọn khu vực gần Việt Nam (`asia-southeast1` - Singapore).
   - Chọn **Start in test mode** (cho phép đọc/ghi nhanh trong 30 ngày phục vụ Hackathon).
3. Lấy cấu hình cho **Frontend**:
   - Vào **Project Settings -> General -> Your apps -> Web app (`</>`)**, copy các thông số `apiKey`, `authDomain`, `projectId`, `storageBucket` dán vào các biến `VITE_FIREBASE_*` trong `.env`.
4. Lấy cấu hình cho **Backend**:
   - Vào **Project Settings -> Service accounts -> Generate new private key**.
   - Lưu file tải về dưới tên `serviceAccountKey.json` tại thư mục gốc của repo (file này đã được chặn trong `.gitignore`).

---

## 2. Tổng Hợp Nghiên Cứu Kỹ Thuật Thực Chiến (Technical Research)

### 2.1. Chiến lược lấy hình ảnh từ Camera giao thông công cộng không bị chặn CORS
- **Vấn đề:** Các cổng camera công cộng (như `https://camera.0511.vn` tại Đà Nẵng hoặc cổng thông tin giao thông TP.HCM) thường chặn truy cập chéo miền (CORS) từ trình duyệt hoặc dùng luồng HLS (`.m3u8`) / snapshot cập nhật theo chu kỳ.
- **Giải pháp thực thi:**
  1. Toàn bộ việc lấy ảnh từ camera được thực hiện ở **Backend/Worker (`ai-vision/src/camera_extractor.py`)** bằng thư viện `httpx` (với HTTP snapshot) hoặc `opencv-python-headless` (`cv2.VideoCapture` với luồng HLS/RTSP hoặc file video thực địa).
  2. **Kiến trúc đầu vào đa chế độ (Thực tiễn 100%, 0% hardcode kết quả AI):**
     - `mode="live_url"`: Kéo trực tiếp frame hiện tại từ URL snapshot của camera giao thông công cộng.
     - `mode="real_flood_footage"`: Đọc frame thực tế từ video ghi hình cảnh ngập thật tại đúng nút giao đó (dùng khi thuyết trình vào ngày nắng ráo nhưng vẫn muốn chứng minh Gemini 3.8 Flash tự nhận diện ảnh ngập thật theo thời gian thực).
     - `mode="crowdsourcing_upload"`: Nhận ảnh chụp trực tiếp từ điện thoại người dân/tài xế qua API `POST /api/reports`.

### 2.2. Giải thuật Dynamic Rerouting 2 lớp trên Google Routes API
Google `Routes API` (`POST https://routes.googleapis.com/directions/v2:computeRoutes`) không hỗ trợ truyền danh sách đa giác ngập (`avoid_polygons`). Để giải quyết triệt để cho xe máy:

1. **Bước 1 — Yêu cầu tuyến đường xe máy kèm phương án thay thế:**
   - Gửi header `X-Goog-FieldMask: routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline,routes.description`.
   - Body request:
     ```json
     {
       "origin": { "location": { "latLng": { "latitude": 10.7769, "longitude": 106.7009 } } },
       "destination": { "location": { "latLng": { "latitude": 10.7992, "longitude": 106.7185 } } },
       "travelMode": "TWO_WHEELER",
       "routingPreference": "TRAFFIC_AWARE",
       "computeAlternativeRoutes": true
     }
     ```
2. **Bước 2 — Kiểm tra giao cắt hình học với vùng ngập đỏ (`Flood Intersection Check`):**
   - Giải mã `encodedPolyline` thành danh sách tọa độ `[(lat_1, lng_1), (lat_2, lng_2), ...]`.
   - Với mỗi điểm ngập đang kích hoạt có `severity_level >= 2` tại tâm `(f_lat, f_lng)` và bán kính nguy hiểm `R` (mặc định `120m`), kiểm tra khoảng cách tối thiểu từ các đoạn thẳng trên polyline tới tâm `(f_lat, f_lng)`.
   - Nếu tuyến số 0 (tuyến ngắn nhất mặc định) đi vào trong bán kính `R`, duyệt tiếp các tuyến thay thế (`routes[1]`, `routes[2]`) và chọn tuyến đầu tiên không cắt vùng ngập.
3. **Bước 3 — Tự động sinh điểm vòng tránh (`Detour Via-Waypoint`) nếu mọi tuyến đều ngập:**
   - Nếu tất cả các tuyến trả về đều đi qua điểm ngập `(f_lat, f_lng)`, tính vector hướng di chuyển từ `origin` tới `destination`, sau đó lấy vector pháp tuyến (vuông góc) để dịch tâm `(f_lat, f_lng)` ra một khoảng `offset = 300m` (tạo thành tọa độ `detour_waypoint`).
   - Gọi lại `Routes API` với `intermediates: [{ "location": { "latLng": detour_waypoint }, "via": true }]` để ép lộ trình bẻ hướng vòng qua ngoài bán kính ngập.

### 2.3. Thiết kế Prompt chuẩn cho Gemini 3.8 Flash (Vision)
Để Gemini phân loại mức ngập chính xác cho người đi xe máy tại Việt Nam, prompt hệ thống trong `ai-vision/src/analyzer.py` sử dụng 3 mốc vật chuẩn phổ biến nhất trên đường phố Việt Nam:
- **Mép vỉa hè / lề đường** (cao khoảng 12–15 cm): Nếu nước mới mấp mé lề đường -> `severity_level = 1` (`MINOR`), xe máy đi chậm qua được.
- **Bánh xe máy / vành xe** (bán kính bánh xe máy phổ thông khoảng 25–30 cm): Nếu nước ngập từ 1/3 đến nửa bánh xe máy -> `severity_level = 2` (`MODERATE`), nguy cơ nước tràn vào bugi/ống xả gây chết máy rất cao -> `passable_for_motorbike = false`.
- **Ống xả / lốc máy / yên xe** (> 35 cm): Nước ngập lút bánh xe hoặc người dân phải dắt bộ -> `severity_level = 3` (`SEVERE`), phong tỏa hoàn toàn đối với xe máy.
