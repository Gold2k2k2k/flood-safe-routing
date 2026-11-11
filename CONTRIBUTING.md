# Hướng Dẫn Đóng Góp & Quy Trình Làm Việc Nhóm (Contributor Guide)

Chào mừng các thành viên của đội phát triển **Flood-Safe Routing**! Tài liệu này giúp mọi thành viên khi `git clone` hoặc `git pull` repo về có thể nắm bắt ngay cấu trúc dự án, chạy thử môi trường trong **5 phút** và code song song mà không bị xung đột (conflict) hay phải chờ đợi nhau.

---

## 1. Onboarding Nhanh Trong 5 Phút (Quick Start)

### Bước 1: Kéo code mới nhất
```bash
git clone https://github.com/Gold2k2k2k/flood-safe-routing.git
cd flood-safe-routing
git pull origin main
```

### Bước 2: Tạo file `.env` từ mẫu
```bash
cp .env.example .env
```
> **Lưu ý quan trọng:** Mặc định trong `.env.example` có đặt `USE_MOCK_FALLBACK=true`. Điều này có nghĩa là **ngay cả khi bạn chưa nhận được API Key của Google Maps, Gemini hay Firebase từ nhóm trưởng**, bạn vẫn chạy được cả Backend, AI Vision và Frontend bằng dữ liệu mẫu trong `data/` mà không bị lỗi crash!

### Bước 3: Kiểm tra môi trường máy cá nhân
Chạy script kiểm tra tự động tại thư mục gốc:
```bash
python scripts/check_env.py
```
Script sẽ kiểm tra phiên bản Python/Node, tính toàn vẹn của dữ liệu mẫu `data/` và cho biết từng dịch vụ (Gemini, Google Maps, Firebase) đang ở chế độ **LIVE** hay **MOCK FALLBACK**.

---

## 2. Phân Chia Khu Vực Code (Tránh Conflict Tuyệt Đối)

Để 3–4 thành viên làm việc song song trong 24h mà không đụng chạm code của nhau, mỗi vai trò chỉ chỉnh sửa trong thư mục được giao:

| Vai trò | Thư mục làm việc chính | Nhánh Git chuẩn | Tài liệu cần đọc trước khi code |
| :--- | :--- | :--- | :--- |
| **TV1 — Frontend & Maps** | `frontend/` | `feat/frontend-map` | `docs/api-and-data-contract.md`, `frontend/README.md` |
| **TV2 — Backend & Routing** | `backend/` | `feat/backend-routes` | `docs/api-and-data-contract.md`, `docs/resource-and-research-guide.md` |
| **TV3 — AI Vision & Camera** | `ai-vision/` | `feat/ai-vision` | `docs/api-and-data-contract.md`, `ai-vision/README.md` |
| **TV4 — Data, QA & Pitch** | `data/`, `docs/` | `feat/data-and-qa` | `docs/idea-evaluation.md`, `docs/verification-and-demo-playbook.md` |

---

## 3. Quy Trình Git & Hợp Nhất Code (Git Workflow)

1. **Tạo nhánh riêng từ `main`:**
   ```bash
   git checkout main
   git pull origin main
   git checkout -b feat/<ten-module-cua-ban>
   ```
2. **Quy ước Commit (Conventional Commits):**
   - `feat(frontend): add Google Maps HeatmapLayer toggle`
   - `feat(backend): implement 2-layer detour waypoint in Routes API`
   - `feat(ai-vision): refine Gemini 3.8 Flash prompt for curb and wheel depth`
   - `fix(backend): handle empty polyline when origin equals destination`
   - `docs: update demo scenario coordinates`
3. **Đồng bộ thường xuyên:**
   - Mỗi **2–3 tiếng** (hoặc khi hoàn thành 1 Phase trong `docs/implementation-plan.md`), hãy `git pull --rebase origin main` và tạo Pull Request / merge vào `main` sau khi đã chạy `python scripts/check_env.py`.

---

## 4. Ba Nguyên Tắc Vàng Trong 24h Hackathon

1. **Contract-First (Hợp đồng dữ liệu là bất khả xâm phạm):**
   - Mọi thay đổi về tên trường JSON trong API hoặc Firestore Collection **bắt buộc** phải thông báo cho cả nhóm và cập nhật ngay vào `docs/api-and-data-contract.md`.
2. **Tuyệt đối không commit khóa bí mật (Secrets):**
   - Không bao giờ commit file `.env`, `serviceAccountKey.json` hoặc gắn cứng API Key trực tiếp vào file `.ts` / `.py`.
3. **Luôn giữ chế độ `USE_MOCK_FALLBACK` hoạt động:**
   - Khi viết thêm hàm gọi Gemini, Firestore hoặc Google Routes API, luôn giữ nhánh fallback trả về dữ liệu mẫu hợp lệ khi `USE_MOCK_FALLBACK=true` để đồng đội khác test giao diện/luồng tích hợp bất cứ lúc nào.
