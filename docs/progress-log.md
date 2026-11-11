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
