# Nhật Ký Kiểm Tra Tiến Độ Dự Án (Project Audit & Progress Log)

> Tài liệu ghi nhận trung thực hiện trạng kỹ thuật của repository **`flood-safe-routing`** tại thời điểm kiểm tra trước khi bước vào giai đoạn phát triển tính năng live và triển khai trong ngày thi, phục vụ đối chiếu quy định **"Dự án có sẵn tối đa 30%"** và tiêu chí đánh giá của Hội đồng Mentor / Ban Tổ Chức.

---

## 1. Thông Tin Phiên Kiểm Tra

- **Thời điểm kiểm tra:** `2026-11-11 12:37 (+07:00)`
- **Commit gốc được kiểm tra:** `547a38a` (`refactor: harden contracts, async AI vision, Routes v2 detour math, ...`)
- **Trạng thái môi trường cục bộ:**
  - `Python 3.10.7` & `Node.js v24.18.0` đã cài sẵn.
  - Chưa có file `.env` và `serviceAccountKey.json` (đang chạy mặc định theo `.env.example` với `USE_MOCK_FALLBACK=true`).
  - Thư mục `frontend/node_modules/` chưa cài đặt (`npm install` và `npm run build` chưa chạy).
- **Kết quả kiểm thử tự động đã chạy thực tế:**
  - `python scripts/check_env.py` -> `[READY]` (dữ liệu mẫu JSON/GeoJSON hợp lệ; toàn bộ dịch vụ Google ở chế độ `MOCK FALLBACK MODE`).
  - `python -m unittest discover -s tests -v` -> **14/14 tests PASS** (`2.045s`, kiểm thử hợp đồng schema, hình học detour và luồng FastAPI ở chế độ Mock).
  - `python scripts/repro_routing.py`, `repro_gemini_vision.py`, `repro_camera_fetch.py` -> Chạy thành công ở chế độ Mock/Local synthetic frame.

---

## 2. Đánh Giá Tiến Độ Trung Thực Theo Từng Hạng Mục

| Hạng mục | Trọng số sản phẩm | Mức hoàn thiện thực tế | Đã có (Pre-work / Skeleton) | Chưa làm / Phải build trong ngày thi (Phần >70% còn lại) |
| :--- | :---: | :---: | :--- | :--- |
| **1. Tài liệu, Hợp đồng API & Test Harness** (`docs/`, `scripts/`, `tests/`) | 10% | **~90%** | Tài liệu kiến trúc, schema contract, kế hoạch 24h, kịch bản demo, 3 script `repro_*` và 14 unit tests mock. | Cập nhật tài liệu theo thay đổi thực tế khi tích hợp live API và kết quả benchmark thật. |
| **2. AI Vision & Camera Ingestion** (`ai-vision/`) | 20% | **~30%** | Wrapper SDK `google-genai` (sync/async), Pillow resize 1024px, schema `FloodAnalysisResult`, hàm tiện ích `compute_frame_delta`, HTTP/OpenCV reader cơ bản, mock fallback. | - Chưa test/tinh chỉnh độ chính xác trên ảnh/video ngập thực tế (mục tiêu Phase 1 >= 90%).<br>- Chưa có background polling worker định kỳ & cơ chế cache frame-delta thực tế.<br>- Chưa có danh sách URL snapshot/stream thật từ camera giao thông VN (`cameras.sample.json` mới trỏ homepage `camera.0511.vn`).<br>- Chưa cài `opencv-python-headless` trong `requirements.txt`. |
| **3. Backend API & Dynamic Rerouting** (`backend/`) | 25% | **~35%** | Khung FastAPI 7 endpoints (`/api/health`, `/api/flood-zones`, `/api/reports`, `/api/cameras`, `/api/cameras/poll`, `/api/route`, `/api/heatmap`), toán học Haversine + `via` detour 2 phía, Firebase Firestore client với in-memory fallback. | - Chưa chạy thử với Google `Routes API v2` thật (`TWO_WHEELER` + `via` detour trên bản đồ TP.HCM/HN).<br>- Lớp 2 mới tính detour theo `primary_hits[0]` (chưa xử lý đa điểm ngập liên tiếp).<br>- `POST /api/reports` mới nhận JSON, chưa hỗ trợ `multipart/form-data` và chưa upload ảnh lên **Firebase/Cloud Storage**.<br>- `flood_events_history` đang gán cứng `city="TP.HCM"` và `flood_frequency_30d=1` thay vì cộng dồn.<br>- Chưa có scheduler tự động quét camera nền. |
| **4. Frontend Bản Đồ & Giao Diện Demo** (`frontend/`) | 25% | **~20%** | Bộ khung React + Vite + TS: `FloodMap.tsx`, `HeatmapOverlay.tsx` (`OverlayView` Canvas tương thích v3.65+), `ReportModal.tsx`, `useAutoReroute.ts`, `firebase.ts` (`onSnapshot` fallback polling). | - Chưa `npm install` và chưa kiểm tra compile TypeScript (`tsc -b && vite build`).<br>- `App.tsx` đang gắn cứng `DEMO_ORIGIN` & `DEMO_DESTINATION`, chưa có ô nhập tìm kiếm địa điểm (Places API) hoặc chọn điểm trực tiếp trên bản đồ.<br>- Chưa vẽ song song tuyến đường gốc bị ngập (nét đứt đỏ) và tuyến vòng an toàn (xanh lá).<br>- Chưa có InfoWindow xem chi tiết ảnh/JSON Gemini khi bấm vào camera hoặc điểm ngập.<br>- `ReportModal` chưa có nút lấy GPS trình duyệt; chưa có cảnh báo banner/âm thanh khi tự động bẻ hướng. |
| **5. Dữ Liệu Thật, Live Keys & Triển Khai Cloud Run** (`data/`, Cloud Run) | 20% | **~5%** | 3 file mẫu nhỏ (`2` camera stub, `1` điểm ngập GeoJSON, `2` điểm heatmap). | - **0%** cấu hình triển khai **Google Cloud Run** (chưa có `Dockerfile`, `.dockerignore`, script deploy hay URL `*.run.app`).<br>- **0%** bộ ảnh/video ngập thực địa tại các nút giao VN.<br>- **0%** API Keys thật (`GEMINI_API_KEY`, `GOOGLE_MAPS_API_KEY`, `FIREBASE_*`, `serviceAccountKey.json`) và chưa kiểm thử End-to-End live. |

### Tổng Kết Phần Trăm Hoàn Thiện Hiện Tại
- **Ước lượng tổng thể có trọng số:**
  $$(10\% \times 0.90) + (20\% \times 0.30) + (25\% \times 0.35) + (25\% \times 0.20) + (20\% \times 0.05) = \mathbf{28.75\%}$$
- **Kết luận trung thực:** Dự án hiện tại mới đạt mức **~28–29% ($\le 30\%$)** — hoàn toàn ở trạng thái **khung kiến trúc, hợp đồng dữ liệu và chế độ mô phỏng ngoại tuyến (Mock Fallback)**. Toàn bộ phần tích hợp live **Gemini Vision trên ảnh thật**, **Google Routes API v2 thật**, **Firebase Firestore/Storage thật**, **UI tương tác đầy đủ**, **dữ liệu thực địa**, và **triển khai Google Cloud Run** (~71% khối lượng sản phẩm hoàn chỉnh) sẽ được triển khai trực tiếp trong thời gian thi.

---

## 3. Việc Cần Làm Ngay Khi Bắt Đầu Build Chính Thức

1. **Hạ tầng & Công cụ:** Chạy `cd frontend && npm install && npm run build`, cài `gcloud` CLI, nạp `.env` + `serviceAccountKey.json` từ tài nguyên nhóm và tạo `Dockerfile` triển khai **Google Cloud Run**.
2. **Dữ liệu & AI Vision:** Nạp 5–10 ảnh/video ngập thực tế vào `data/`, bỏ mock fallback để đo độ chính xác thực tế của `Gemini 3.8 Flash`, bổ sung upload ảnh lên Firebase Storage.
3. **Backend & Frontend:** Kiểm thử live `Routes API v2`, bổ sung chọn điểm Đi/Đến (Places API / click map), vẽ song song tuyến cũ (đỏ nét đứt) vs tuyến né ngập (xanh lá) và InfoWindow hiển thị kết quả phân tích của Gemini.
4. **Quy trình Git:** Các thành viên tách nhánh theo `CONTRIBUTING.md`, commit và push đều đặn theo từng Phase để Mentor theo dõi tiến độ.

---

## 4. Cập Nhật Thực Thi: Hoàn Thành Phase 1 & Phase 2 (`2026-11-14`)

- **Thời điểm cập nhật:** `2026-11-14 09:40 (+07:00)`
- **Phạm vi hoàn thành:** Trọn vẹn **Phase 1** & **Phase 2** theo [implementation_plan.md](file:///e:/Bách/GDG%202026/implementation_plan.md).
- **Chi tiết hạng mục đã hoàn thiện:**
  1. **Phase 1 — Hợp đồng dữ liệu, Bộ dữ liệu thực địa & AI Vision (`docs/`, `ai-vision/`, `data/`):**
     - Cập nhật [docs/api-and-data-contract.md](file:///e:/Bách/GDG%202026/docs/api-and-data-contract.md) và đồng bộ 1:1 giữa `backend/app/schemas.py` và `frontend/src/types/flood.ts` (`baseline_route_coordinates`, `detour_waypoints_used`, `frame_delta_skipped`, `force_refresh`, `local_image_path`, `default_severity_hint`, `POST /api/flood-zones/reset`, `DELETE /api/flood-zones/{event_id}`).
     - Tinh chỉnh `SYSTEM_PROMPT` chống ảo giác mặt đường ướt / ảnh rác trong `ai-vision/src/analyzer.py`, bổ sung chuẩn hóa tính nhất quán schema và hàng rào độ tin cậy `FLOOD_ALERT_THRESHOLD`.
     - Hoàn thiện bộ đệm `frame_delta` + kết quả phân tích liền trước trong `ai-vision/src/camera_extractor.py` giúp bỏ qua frame tĩnh (`delta < 0.04`), tiết kiệm lượt gọi Gemini API.
     - Mở rộng bộ dữ liệu mẫu: **9 camera** giao thông (TP.HCM, Đà Nẵng, Hà Nội), **5 vùng ngập** kích hoạt, **10 điểm lịch sử Heatmap** và **4 frame ảnh đường phố mẫu** (`level_0_safe.jpg` -> `level_3_severe.jpg`).
  2. **Phase 2 — Dynamic Rerouting Đa Điểm Ngập & Quản Trị Vòng Đời Sự Kiện (`backend/`):**
     - Nâng cấp thuật toán **Two-Layer Flood Avoidance** trong `backend/app/services/routing_service.py`: trả về `baseline_route_coordinates`, xử lý né đa vùng ngập liên tiếp và vùng ngập lân cận theo từng phân đoạn (`compute_multi_zone_detour_waypoints`, `compute_multi_zone_detour_plans`), giữ vững cả 5 ràng buộc cứng của Google `Routes API v2`.
     - Sửa logic cộng dồn thực tế `flood_frequency_30d`, tính lại trung bình trượt `avg_severity` và `weight` trong `backend/app/services/firebase_service.py` cho cả chế độ in-memory lẫn Firestore thật.
     - Hoàn thiện `POST /api/reports` hỗ trợ song song `application/json` và `multipart/form-data`, tích hợp `frame_delta_skipped` vào `POST /api/cameras/poll`, bổ sung `POST /api/flood-zones/reset` và `DELETE /api/flood-zones/{event_id}` trong `backend/app/main.py`.
     - Khắc phục vòng lặp gọi lại `/api/route` trong `frontend/src/hooks/useAutoReroute.ts` khi tồn tại vùng ngập ở thành phố khác không cắt lộ trình.
- **Kết quả kiểm chứng tự động:**
  - `python scripts/check_env.py` -> `[READY]` (`9` cameras, `5` flood zones, `10` heatmap records).
  - `python -m unittest discover -s tests -v` -> **20/20 tests PASS** (`0` warnings).
  - `python scripts/repro_routing.py`, `repro_gemini_vision.py`, `repro_camera_fetch.py` -> **PASS**.
  - `cd frontend && npm run build` (`tsc -b && vite build`) -> **PASS** (`0` lỗi TypeScript/Vite).
- **Giai đoạn tiếp theo:** Bắt đầu **Phase 3** (Giao diện bản đồ Before/After Polyline, chọn điểm Đi/Đến & Preset kịch bản, Thẻ AI Vision Inspector, và Bản đồ Vector tương tác dự phòng).

---

## 5. Cập Nhật Thực Thi: Hoàn Thành Phase 3, Phase 4, Phase 5 & Sẵn Sàng Deploy (`2026-11-14`)

- **Thời điểm cập nhật:** `2026-11-14 11:05 (+07:00)`
- **Phạm vi hoàn thành:** Hoàn thành toàn bộ **Phase 3 (Interactive Map & AI Inspector)**, **Phase 4 (Crowdsourcing GPS, Auto-Reroute Alert, B2G Analytics)**, và **Phase 5 (Deployment Readiness, Unit Tests & Verification)** theo [implementation_plan_fast_track.md](file:///C:/Users/Long/.gemini/antigravity/brain/7fc6fb50-38ef-48a4-8298-8153688b1553/implementation_plan_fast_track.md).
- **Chi tiết hạng mục đã hoàn thiện:**
  1. **Phase 3 — Giao diện Bản đồ & AI Vision Inspector (`frontend/`):**
     - Nâng cấp `frontend/src/components/FloodMap.tsx`: vẽ song song tuyến đường gốc bị ngập (**đỏ nét đứt**) và tuyến vòng an toàn (**xanh lá** kèm các điểm `detour_waypoints_used`, hoặc xanh dương nếu tuyến thông suốt); bổ sung **Interactive SVG Vector Fallback Map** (zoom cục bộ theo cụm đô thị, grid đường phố, heatmap radial blobs, chọn điểm A/B bằng click map) khi thiếu `VITE_GOOGLE_MAPS_API_KEY`.
     - Tạo `frontend/src/components/FloodInspectorCard.tsx`: hiển thị thanh mức ngập `0..3`, độ sâu ước tính (`cm`), huy hiệu an toàn xe máy, `visual_cue`, độ tin cậy, nút **Giải tỏa điểm ngập** (`DELETE /api/flood-zones/{event_id}`) và nút **Quét AI Camera này**.
     - Nâng cấp `frontend/src/App.tsx`: bổ sung 3 Route Presets (*Q.1 → Thảo Điền*, *Q.1 → Thủ Đức đa điểm ngập*, *Đà Nẵng*), chế độ chạm bản đồ chọn Điểm A/B, nút **↻ Reset** (`POST /api/flood-zones/reset`).
  2. **Phase 4 — Crowdsourcing UX, Cảnh Báo Tự Động & B2G Analytics:**
     - Nâng cấp `frontend/src/components/ReportModal.tsx`: nút **📍 Lấy vị trí GPS của tôi** (`navigator.geolocation`), chip chọn nhanh hotspot, preview ảnh hiện trường, bộ chọn mức ngập Mock Fallback `0..3`, và thẻ kết quả phân tích Gemini.
     - Nâng cấp `frontend/src/hooks/useAutoReroute.ts` + `App.tsx`: Banner cảnh báo **TỰ ĐỘNG BẺ LÁI REAL-TIME** kèm âm thanh Web Audio API (có nút tắt tiếng) và bảng chênh lệch cự ly / thời gian; thẻ **Thống kê Ngập 30 Ngày (B2G Hạ tầng)** liệt kê Top 3 điểm nóng ưu tiên khơi thông khi bật Heatmap.
  3. **Phase 5 — Vercel Multi-Service, Google Cloud Run & Kiểm Thử:**
     - Hoàn thiện `backend/app/main.py` gọi qua `backend/app/services/ai_vision_client.py` (hỗ trợ cả in-process lẫn `AI_VISION_URL` HTTP service binding trên `vercel.json`), cập nhật `frontend/src/config/env.ts` (same-origin `/api/*` trên `PROD`), hỗ trợ `FIREBASE_SERVICE_ACCOUNT_JSON` + embedded seed data fallback trong `backend/app/config.py` và `firebase_service.py`.
     - Bổ sung `Dockerfile` và `.dockerignore` ở thư mục gốc để deploy 1-lệnh lên **Google Cloud Run**.
     - Mở rộng `tests/test_ai_and_contracts.py` lên tổng **23 unit tests PASS** (gồm test `httpx.MockTransport` cho `ai_vision_client.py`, truyền lỗi `503`, và cấu hình `FIREBASE_SERVICE_ACCOUNT_JSON`).
- **Kết quả kiểm chứng tự động mới nhất:**
  - `python scripts/check_env.py` -> `[READY]`
  - `python -m unittest discover -s tests -v` -> **23/23 tests PASS**
  - `python scripts/repro_routing.py`, `repro_gemini_vision.py`, `repro_camera_fetch.py` -> **PASS**
  - `Set-Location frontend; npm run build` (`tsc -b && vite build`) -> **PASS** (`dist/` built in ~2.2s, `0` lỗi)
