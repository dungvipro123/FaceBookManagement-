# Kế Hoạch Xây Dựng Hạ Tầng Hệ Thống "FB Monitor Hunter v2.0"
> **Mục tiêu:** Chuyển đổi công cụ từ script chạy cục bộ 1 chiều thành hệ thống dịch vụ chạy ngầm 24/7, nhận lệnh và điều khiển 2 chiều qua Discord (điện thoại), mở rộng cào đa nhóm không giới hạn và cấu hình động.

---

## 1. Kiến Trúc Tổng Thể (System Architecture)

```
[ Điện Thoại / PC (Discord App) ]
   │
   ├── Gõ lệnh Slash: /status, /scan, /addgroup, /quota, /pause...
   └── Bấm nút tương tác: [▶ Quét ngay] [⏸ Tạm dừng] [⚙ Cấu hình]
   │
   ▼ (Giao thức 2 chiều WebSocket Gateway)
[ DISCORD BOT CONTROLLER (discord.py) ]
   │
   ├── Quản lý cấu hình & Nhóm ──► [ SQLite Database ] (Groups, Settings, Posts)
   └── Kích hoạt tác vụ ──────────► [ TASK SCHEDULER & QUEUE ]
                                          │
                                          ▼
                                   [ PLAYWRIGHT ENGINE ]
                                   (Cào đa nhóm theo hàng đợi,
                                    giãn cách chống Checkpoint FB)
                                          │
                                          ├── Lọc bài & Trích xuất
                                          ▼
                                   [ AI APPRAISER ENGINE ]
                                   (Gemini 3.5 Flash + Failover Lite)
                                          │
                                          ├── Phân loại: DEAL 1 / DEAL 2 / BUY LEAD / LOG
                                          ▼
                                   [ DISCORD CHANNELS & ALERT ]
```

---

## 2. Các Trụ Cột Nâng Cấp Chi Tiết

### Trụ Cột 1: Giao Thức Điều Khiển 2 Chiều Từ Điện Thoại (Discord Bot Engine)
Thay vì chỉ gửi Webhook 1 chiều, nâng cấp thêm **Discord Bot Gateway (`discord.py`)** kết nối 2 chiều:
* **Hỗ trợ Slash Commands (`/`):**
  * `/status`: Xem tình trạng bot, số bài đã quét hôm nay, số kèo thơm, hạn mức API Gemini còn lại, tình trạng Cookie Facebook.
  * `/scan [group_id/all]`: Ra lệnh quét ngay lập tức một hoặc tất cả các nhóm mà không cần chờ tới lượt hẹn giờ.
  * `/pause` & `/resume`: Tạm dừng hoặc tiếp tục tiến trình cào khi cần bảo trì.
  * `/quota`: Kiểm tra tình trạng kết nối và phản hồi từ các model Gemini (`gemini-3.5-flash`, `gemini-3.1-flash-lite`).
  * `/addgroup <url> <tên>`: Thêm nhanh một group mới ngay trên điện thoại mà không cần vào code.
  * `/groups`: Liệt kê tất cả các group đang theo dõi và trạng thái bật/tắt.
  * `/set discount <số_%>`: Chỉnh sửa nhanh mức % giảm giá muốn lọc kèo (ví dụ đổi từ 15% lên 20%).
* **Thẻ Điều Khiển Tương Tác (Discord Buttons):**
  * Bảng tin trạng thái (Live Dashboard Card) được ghim ở kênh Quản Trị, có sẵn các nút bấm:
    * `[▶ Chạy ngay]`
    * `[⏸ Tạm dừng]`
    * `[🔄 Quét lại]`
    * `[📊 Báo cáo ngày]`

---

### Trụ Cột 2: Mở Rộng Cào Đa Nhóm & Chống Checkpoint Facebook
Khi tăng từ 4 nhóm lên 10 – 30 nhóm, Facebook sẽ dễ nghi ngờ hành vi cào dữ liệu nếu không phân bổ hợp lý:
* **Cơ Chế Hàng Đợi Xoay Vòng (Round-Robin with Priority):**
  * Không cào dồn dập nhiều nhóm cùng một lúc (tránh nghẽn CPU và bất thường lưu lượng mạng).
  * Phân tầng nhóm:
    * **Nhóm VIP (hoạt động dày):** Quét 3 – 5 phút/lần.
    * **Nhóm thường:** Quét 10 – 15 phút/lần.
  * Giãn cách thông minh giữa các nhóm (ngẫu nhiên 8 – 20 giây với hành vi cuộn chuột tự nhiên).
* **Quản Lý Phiên & Cookie Bền Vững:**
  * Tự động lưu và cập nhật session `cookies.json`.
  * Báo động ngay lập tức về Discord điện thoại nếu phát hiện Facebook yêu cầu đăng nhập lại (Session expired).

---

### Trụ Cột 3: Quản Lý Cấu Hình Động (Dynamic Configuration)
* Không cần mở code `config.py` để chỉnh sửa thủ công.
* Toàn bộ cấu hình được chuyển vào bảng `system_settings` và `monitored_groups` trong SQLite:
  * Cho phép bật/tắt từng nhóm (`is_active: 1/0`).
  * Tùy chỉnh độ trễ, số bài cào mỗi đợt.
  * Tùy chỉnh danh sách từ khóa thợ (`DEALER_KEYWORDS`).

---

### Trụ Cột 4: Hệ Thống Cảnh Báo & Giám Sát Quota Toàn Diện
* **Bộ Đếm Token & Request Realtime:** Ghi nhận số request đã gửi trong ngày đến Gemini.
* **Cảnh Báo Chạm Ngưỡng (Threshold Alert):**
  * Nếu Gemini trả về mã `429 (Hết hạn mức)` hoặc `503`:
    1. Bắn thông báo khẩn cấp màu đỏ/vàng vào kênh Discord Log:
       > ⚠️ **CẢNH BÁO QUOTA GEMINI:** Model `gemini-3.5-flash` vừa chạm giới hạn 429. Hệ thống đang tự động chuyển sang `gemini-3.1-flash-lite` (hoặc bộ phân tích tĩnh Regex).
    2. Ghi nhận thời gian cooldown và tự động thử lại khi hạn mức phục hồi.

---

## 3. Lộ Trình Triển Khai (Roadmap)

| Giai Đoạn | Công Việc Cụ Thể | Kết Quả Đạt Được |
| :--- | :--- | :--- |
| **Giai đoạn 1** | **Cảnh báo Quota ngay lập tức vào Kênh Log**<br>Tích hợp gửi tin thông báo về Discord Webhook mỗi khi Gemini gặp lỗi 429 hoặc chuyển đổi model. | Biết ngay tình trạng Quota từ điện thoại |
| **Giai đoạn 2** | **Cơ sở dữ liệu Động (Dynamic Groups & Settings)**<br>Chuyển danh sách nhóm và cài đặt vào SQLite để có thể thêm/bớt nhóm từ bên ngoài mà không cần sửa code. | Hỗ trợ mở rộng 10 - 20+ nhóm dễ dàng |
| **Giai đoạn 3** | **Xây dựng Discord Bot 2 chiều (`bot.py`)**<br>Tích hợp `discord.py`, tạo lệnh Slash `/status`, `/scan`, `/addgroup`, `/quota`, `/pause`. | Điều khiển toàn bộ máy chủ từ điện thoại |
| **Giai đoạn 4** | **Bảng điều khiển tương tác (Mobile Dashboard)**<br>Ghim thẻ Live Dashboard với các nút bấm `[Chạy ngay]`, `[Tạm dừng]`, `[Báo cáo]`. | Trải nghiệm quản trị chuyên nghiệp từ xa |
