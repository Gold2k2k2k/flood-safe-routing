# Quy Trình Kiểm Thử (Verify) & Kịch Bản Demo Sân Khấu

Tài liệu này cung cấp danh sách kiểm tra kỹ thuật (Verification Checklist) cho từng giai đoạn phát triển và kịch bản trình diễn (Demo Playbook) trước Ban Giám Khảo.

---

## 1. Checklist Kiểm Thử Kỹ Thuật (Verification Checklist)

### Bước 1: Kiểm tra cấu hình & cú pháp toàn dự án
Chạy lệnh sau tại thư mục gốc của repo:
```bash
python scripts/check_env.py
```
- [ ] Script báo `[OK]` cho tất cả các file dữ liệu mẫu trong `data/`.
- [ ] Không có lỗi thiếu thư viện hoặc lỗi cú pháp Python/TypeScript.

### Bước 2: Kiểm thử Module AI Vision (`ai-vision/`)
- [ ] **Test Case 1 (Đường khô / Mưa nhẹ):** Truyền ảnh đường phố bình thường -> `flood_detected: false`, `severity_level: 0`, `passable_for_motorbike: true`.
- [ ] **Test Case 2 (Ngập nửa bánh xe):** Truyền ảnh ngập thực tế tại TP.HCM/Hà Nội -> `flood_detected: true`, `severity_level >= 2`, `passable_for_motorbike: false`, `visual_cue` mô tả đúng mực nước so với bánh xe/lề đường.
- [ ] **Test Case 3 (Mock Fallback):** Khi `USE_MOCK_FALLBACK=true` hoặc ngắt mạng -> trả về JSON mẫu hợp lệ trong < 50ms mà không văng exception.

### Bước 3: Kiểm thử Module Backend & Dynamic Rerouting (`backend/`)
Khởi động server:
```bash
cd backend
uvicorn app.main:app --reload --port 8000
```
- [ ] `GET http://localhost:8000/api/health` trả về `status: "ok"`.
- [ ] `GET http://localhost:8000/api/flood-zones` trả về danh sách điểm ngập đang kích hoạt.
- [ ] `POST http://localhost:8000/api/route` với điểm đầu/cuối đi ngang qua Ngã tư Nguyễn Hữu Cảnh (`10.7858, 106.7082`):
  - Khi `avoid_flood_zones: false` -> đi thẳng qua điểm ngập (`rerouted: false`).
  - Khi `avoid_flood_zones: true` -> phát hiện giao cắt với điểm ngập `evt_001`, trả về `rerouted: true` kèm `detour_waypoint_used` và tuyến đường vòng an toàn.

### Bước 4: Kiểm thử Giao diện Bản đồ & Real-time (`frontend/`)
Khởi động giao diện:
```bash
cd frontend
npm install
npm run dev
```
- [ ] Bản đồ hiển thị đúng tâm đô thị (TP.HCM / Hà Nội), hiển thị các icon camera và vòng tròn đỏ vùng ngập.
- [ ] Khi thêm một báo cáo ngập mới qua Modal Crowdsourcing (`POST /api/reports`), vòng tròn cảnh báo đỏ xuất hiện ngay lập tức và lộ trình đang hiển thị tự động cập nhật sang đường vòng.
- [ ] Bật chế độ **Bản đồ nhiệt (Heatmap)** hiển thị rõ các vùng tần suất ngập cao cho bài toán quy hoạch đô thị.

---

## 2. Kịch Bản Demo Sân Khấu 3 Phút (Stage Demo Playbook)

| Thời lượng | Hành động trên màn hình | Thông điệp nhấn mạnh với Ban Giám Khảo |
| :--- | :--- | :--- |
| **0:00 – 0:40** | Mở giao diện **Flood-Safe Routing**, chọn điểm đi từ **Quận 1** về **Thảo Điền (TP.HCM)** cho xe máy (`TWO_WHEELER`). Tuyến đường ban đầu đi qua đường **Nguyễn Hữu Cảnh** đang màu xanh thông suốt. | *"Hiện tại các ứng dụng bản đồ thông thường dẫn tài xế đi thẳng vào Nguyễn Hữu Cảnh vì chưa phát hiện kẹt xe."* |
| **0:40 – 1:40** | Kích hoạt luồng frame camera thực tế lúc mưa lớn tại nút giao Nguyễn Hữu Cảnh (hoặc mời 1 thành viên chụp/upload ảnh ngập thực tế qua nút **Báo ngập Crowdsourcing**). Hiển thị kết quả JSON trực tiếp từ **Gemini 3.8 Flash Vision**. | *"Không cần con người canh màn hình camera: Gemini 3.8 Flash tự động đọc frame ảnh, nhận diện nước đã ngập nửa bánh xe máy (`severity_level: 2`) và kết luận xe máy không thể đi qua."* |
| **1:40 – 2:20** | Ngay khi Gemini trả kết quả, **Firebase Firestore** đồng bộ cảnh báo đỏ lên bản đồ. Lộ trình của tài xế lập tức chuyển từ đường cũ (nét đứt cảnh báo) sang **tuyến đường mới màu xanh lá** né hoàn toàn vùng ngập nhờ **Google Routes API**. | *"Chỉ trong chưa đầy 2 giây, toàn bộ tài xế trong khu vực nhận cảnh báo đỏ và được tự động bẻ hướng (Dynamic Rerouting) sang lộ trình an toàn, cứu xe khỏi chết máy."* |
| **2:20 – 3:00** | Bật công tắc **Bật Heatmap 30N** để hiển thị bản đồ nhiệt tần suất ngập 30 ngày qua cùng thẻ **Thống kê Ngập 30 Ngày (B2G Hạ tầng)** và thử bấm **Giải tỏa điểm ngập** / **Reset**. | *"Không chỉ cứu từng chiếc xe máy hôm nay, dữ liệu tích lũy tạo nên Bản đồ nhiệt tần suất ngập & Top 3 điểm nóng khơi thông — tài sản dữ liệu giúp cơ quan quản lý đô thị quy hoạch và cải tạo hạ tầng thoát nước."* |

---

## 3. Hướng Dẫn Triển Khai Nhanh (Vercel Multi-Service & Google Cloud Run)

### Phương án A: Vercel Multi-Service (`vercel.json`)
`vercel.json` đã cấu hình sẵn 3 service (`frontend` Vite static build, `backend` FastAPI tại `/api/*`, và `ai-vision` internal service):
1. Import repository vào Vercel (chọn **Root Directory** là `.` — mặc định của repo).
2. Không cần sửa Build Command/Output Directory (Vercel tự đọc `vercel.json`).
3. Khai báo Environment Variables trong Vercel Project Settings:
   - Demo nhanh (Mock Fallback): `USE_MOCK_FALLBACK=true`
   - Chạy Live API thật:
     - `USE_MOCK_FALLBACK=false`
     - `GEMINI_API_KEY=<key>`
     - `GOOGLE_MAPS_API_KEY=<key>`
     - `VITE_GOOGLE_MAPS_API_KEY=<key>` (tùy chọn; nếu bỏ trống UI tự dùng Interactive SVG Vector Map)
     - `FIREBASE_PROJECT_ID=<project_id>` và `FIREBASE_SERVICE_ACCOUNT_JSON=<nội dung 1 dòng JSON service account>`
     - `VITE_FIREBASE_*` (nếu muốn frontend dùng Firestore `onSnapshot` trực tiếp; nếu không, frontend tự fallback REST polling `/api/flood-zones` mỗi 4s)

### Phương án B: Google Cloud Run (Container `Dockerfile` gốc)
```bash
gcloud run deploy flood-safe-routing \
  --source . \
  --region asia-southeast1 \
  --allow-unauthenticated \
  --set-env-vars USE_MOCK_FALLBACK=true
```
(Có thể thay `USE_MOCK_FALLBACK=false` kèm các key thật khi chạy Live Google Tech Stack.)
