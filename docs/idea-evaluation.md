# Đánh Giá Ý Tưởng & Bộ Câu Hỏi Phản Biện Ban Giám Khảo (Idea Evaluation & Q&A)

Tài liệu này tổng hợp phân tích chuyên sâu về điểm mạnh, cơ hội, rủi ro của dự án **Flood-Safe Routing** và bộ câu trả lời mẫu cho các câu hỏi phản biện từ Ban Giám Khảo Hackathon.

---

## 1. Phân Tích SWOT Của Dự Án

### Điểm mạnh (Strengths)
- **Giải quyết đúng "điểm mù" của các ông lớn bản đồ:** Google Maps, Apple Maps hay Grab Maps rất mạnh về mật độ giao thông (traffic jam) dựa trên vận tốc GPS của đám đông, nhưng khi đường bắt đầu ngập, các xe phía trước vẫn di chuyển chậm khiến thuật toán lầm tưởng chỉ là kẹt xe nhẹ — cho đến khi hàng loạt xe đi vào và chết máy.
- **Tận dụng hạ tầng sẵn có (Zero Hardware CapEx):** Không cần lắp thêm cảm biến IoT đo mực nước đắt đỏ trên từng con đường; tận dụng ngay hàng ngàn camera giao thông công cộng sẵn có tại các đô thị kết hợp sức mạnh thị giác của **Gemini 3.8 Flash**.
- **Thiết kế chuyên biệt cho đặc thù giao thông Việt Nam:** Tập trung vào **xe máy (`TWO_WHEELER`)** và giao vận ngách (`last-mile delivery`), dùng chính chiếc bánh xe máy và lề đường làm thước đo mực nước trực quan cho AI.

### Điểm yếu / Thách thức nội tại (Weaknesses)
- Độ phủ của camera giao thông công cộng thường tập trung ở các trục đường chính và ngã tư lớn, trong khi nhiều hẻm nhỏ (ngách) không có camera cố định.
- **Cách khắc phục trong sản phẩm:** Kết hợp **Crowdsourcing** (tài xế công nghệ và người dân chụp ảnh báo ngập tại hẻm nhỏ, được Gemini kiểm duyệt tự động trong 2 giây).

### Cơ hội mở rộng (Opportunities)
- **B2C / B2B2C:** Tích hợp dưới dạng SDK/API cảnh báo vùng ngập cho các siêu ứng dụng gọi xe & giao hàng (Grab, Be, ShopeeFood, Ahamove).
- **B2G (Chính phủ & Đô thị thông minh):** Cung cấp bảng điều khiển và dữ liệu **Flood Frequency Heatmap** theo thời gian thực lẫn lịch sử cho Sở Giao thông Vận tải và Công ty Thoát nước Đô thị.

### Rủi ro & Cách phòng ngừa (Threats & Mitigations)
- *Rủi ro người dùng gửi ảnh giả / ảnh cũ (Spam Crowdsourcing):* Dùng chính **Gemini 3.8 Flash** để kiểm tra tính hợp lệ của ảnh (có phải ảnh đường phố ngập thật không, bối cảnh ngày/đêm có khớp với giờ gửi báo cáo không) và yêu cầu tối thiểu 2 báo cáo gần nhau hoặc xác nhận chéo với lượng mưa khu vực.

---

## 2. Bộ Câu Hỏi Phản Biện Thường Gặp Từ Ban Giám Khảo (Hackathon Q&A)

### Câu 1: *"Tại sao Google Maps chưa làm tính năng này? Nhóm có lợi thế gì?"*
- **Trả lời:** Google Maps hoạt động dựa trên dữ liệu遥측 (telemetry) tốc độ di chuyển toàn cầu và báo cáo sự cố tổng quát (tai nạn, kẹt xe), chưa kết nối chuyên sâu vào mạng lưới camera giao thông nội đô đặc thù của từng tỉnh/thành Việt Nam (như `camera.0511.vn` hay cổng giao thông TP.HCM) và chưa có bộ phân loại mức ngập chuyên biệt cho chiều cao ống xả xe máy. Giải pháp của nhóm đóng vai trò là lớp **Hyper-local Flood Intelligence** bổ trợ hoàn hảo lên trên nền tảng **Google Maps Platform (`Maps JS` & `Routes API`)**.

### Câu 2: *"Làm sao AI biết ngập bao nhiêu cm chỉ qua một bức ảnh 2D từ camera?"*
- **Trả lời:** Nhóm không yêu cầu AI đoán con số tuyệt đối trong chân không, mà hướng dẫn **Gemini 3.8 Flash (Vision)** so sánh mực nước với các **vật chuẩn có kích thước cố định luôn xuất hiện trên đường phố Việt Nam**:
  1. Mép vỉa hè tiêu chuẩn (12–15 cm).
  2. Bán kính bánh xe máy phổ thông (25–30 cm) và vị trí ống xả/lốc máy (~30–35 cm).
  Nhờ khả năng suy luận đa phương thức (Multimodal Reasoning), Gemini nhận diện nước đã chạm tới nửa bánh xe hay mới mấp mé lề đường để quyết định chính xác trường `passable_for_motorbike: true/false`.

### Câu 3: *"Lúc trời mưa to hoặc ban đêm camera bị mờ, lóa đèn pha thì sao?"*
- **Trả lời:**
  1. Với Gemini 3.8 Flash, ngay cả trong điều kiện thiếu sáng, hình ảnh phản chiếu mặt nước kết hợp với việc các phương tiện phải dạt lên sát vỉa hè hoặc sóng nước dạt ra hai bên bánh xe vẫn là dấu hiệu thị giác rất rõ ràng.
  2. Hệ thống luôn trả về trường `confidence` (độ tin cậy từ `0.0` đến `1.0`). Nếu ảnh quá mờ (`confidence < 0.65`), hệ thống chuyển điểm đó sang trạng thái "Cần xác minh" và ưu tiên đối chiếu thêm với báo cáo **Crowdsourcing** từ tài xế thực địa tại tọa độ đó.

### Câu 4: *"Google Routes API đâu có nút 'Né vùng ngập', nhóm làm Dynamic Rerouting bằng cách nào?"*
- **Trả lời:** Nhóm xây dựng thuật toán **2 lớp điều phối (Two-Layer Flood Avoidance)** phía trên Google Routes API:
  - **Lớp 1:** Yêu cầu `Routes API` trả về tập các tuyến đường thay thế (`computeAlternativeRoutes: true`) cho chế độ xe máy (`TWO_WHEELER`), giải mã polyline và loại bỏ các tuyến cắt qua bán kính vùng ngập đỏ trên Firestore.
  - **Lớp 2:** Nếu mọi tuyến mặc định đều đi xuyên qua vùng ngập, thuật toán tự động tính toán một tọa độ **điểm vòng tránh (`via` waypoint)** nằm ngoài bán kính ngập theo phương vuông góc với trục đường và gọi lại `Routes API` để ép lộ trình đi vòng an toàn.
