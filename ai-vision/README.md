# AI Vision — Gemini 3.8 Flash Flood Detection

Thư mục dành cho pipeline xử lý ảnh thời gian thực sử dụng **Gemini 3.8 Flash (Vision / Multimodal)** để bóc tách và đánh giá mức độ ngập từ camera giao thông công cộng & ảnh crowdsourcing.

## Nhiệm vụ chính
1. **Frame Extractor:** Lấy snapshot/frame định kỳ từ luồng camera công cộng (ví dụ `camera.0511.vn`) hoặc tiếp nhận ảnh người dùng gửi lên.
2. **Gemini Multimodal Flood Classifier:** Gửi ảnh kèm prompt nhận diện dựa trên các mốc trực quan (**ngập lề đường**, **ngập nửa bánh xe**, **ngập sâu**) qua biến cấu hình `GEMINI_MODEL` (`gemini-3.8-flash`).
3. **Structured JSON Output:** Chuẩn hóa kết quả (`severity_level` `0`–`3`, `visual_cue`, `passable_for_motorbike`, `confidence`) để ghi vào **Firebase Firestore**, bật cảnh báo đỏ trên bản đồ và kích hoạt **Dynamic Rerouting**.
