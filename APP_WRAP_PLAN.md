# Bản Kế Hoạch Xây Dựng Ứng Dụng Chạy Nền & Giao Diện Cài Đặt (Mini UI & System Tray)

> **Mục tiêu:** Đóng gói toàn bộ hệ thống FB Monitor Hunter thành 1 ứng dụng chạy ngầm dưới khay hệ thống Windows (System Tray - cạnh đồng hồ), không hiện cửa sổ dòng lệnh đen, đi kèm một giao diện (Mini UI) hiện đại để cài đặt thông số, quản lý nhóm và kênh Discord.

---

## 1. Lựa Chọn Kiến Trúc Ứng Dụng (Tech Stack Analysis)

Có 2 hướng tiếp cận chính để xây dựng ứng dụng Windows:

| Tiêu Chí | Hướng A: Native Desktop UI (PyQt6 / CustomTkinter) | Hướng B: System Tray + Mini Web Dashboard (Khuyên dùng) |
| :--- | :--- | :--- |
| **Công nghệ** | `pystray` + `customtkinter` | `pystray` + `FastAPI/Flask` + Vanilla CSS/HTML |
| **Cửa sổ chạy ngầm** | Thu nhỏ về khay hệ thống (System Tray) | Thu nhỏ về khay hệ thống (System Tray) |
| **Mở từ điện thoại** | ❌ Không (chỉ xem được trên PC) | ✅ **Có thể mở từ điện thoại khi chung Wi-Fi** (truy cập `http://IP_PC:8080`) |
| **Thẩm mỹ giao diện** | Khá đẹp theo phong cách Windows | Cực kỳ hiện đại, dark mode, animation mượt mà |
| **Độ ổn định & Nhẹ** | Khoảng 50MB RAM | Khoảng 35MB RAM, cực nhẹ |

👉 **Lựa chọn tối ưu:** **Hướng B (System Tray Icon + Local Web Mini-UI)** kết hợp công cụ mở cửa sổ mini (hoặc pop-up native bằng `pywebview` nếu muốn giống phần mềm máy tính độc lập).

---

## 2. Thiết Kế Các Tính Năng Của Ứng Dụng

### 2.1. Tiến Trình Chạy Ngầm & Khay Hệ Thống (System Tray Engine)
* **Ẩn cửa sổ Console:** Chạy bằng `pythonw.exe` (hoặc build `.exe`), không có màn hình đen nhấp nháy trên thanh taskbar.
* **Biểu tượng dưới khay hệ thống (cạnh đồng hồ Windows):**
  * Icon đổi màu theo trạng thái:
    * 🟢 **Xanh lá:** Bot đang quét bình thường.
    * 🟡 **Vàng:** Đang tạm dừng (Paused) hoặc đang bận quét bài.
    * 🔴 **Đỏ:** Mất mạng hoặc hết Quota Gemini.
  * **Menu chuột phải vào Tray Icon:**
    * ⚙️ **Mở Cài Đặt (Dashboard UI)**
    * 🚀 **Quét ngay lập tức**
    * ⏸️ **Tạm dừng / Tiếp tục**
    * 🔄 **Khởi động cùng Windows (Auto-start)**
    * ❌ **Thoát hoàn toàn ứng dụng**

---

### 2.2. Giao Diện Cài Đặt (Mini Settings UI)
Giao diện tinh gọn, đẹp mắt, chia thành 4 tab trực quan:

```
┌────────────────────────────────────────────────────────────────────────┐
│  🖥️ FB MONITOR HUNTER v2.0               [● Đang chạy ngầm] [▶ Quét]  │
├─────────────┬──────────────────────────────────────────────────────────┤
│ 📊 Tổng quan│  THỐNG KÊ REALTIME                                       │
│ 📋 Quản lý   │  • Tổng bài: 106  • Kèo thơm: 6  • Khách mua: 2         │
│    nhóm     │  • Quota Gemini 3.5: 200 OK (85ms)                       │
│ 📢 Kênh      │──────────────────────────────────────────────────────────│
│    Discord  │  TIẾN TRÌNH QUÉT                                         │
│ ⚙ Cài đặt    │  [████████████████████░░░░] Đang quét Màn Hình Hà Nội... │
└─────────────┴──────────────────────────────────────────────────────────┘
```

1. **Tab 1: Tổng Quan & Điều Khiển (Overview & Controls):**
   * Công tắc Bật / Tắt chế độ quét tự động.
   * Nút bấm `[🚀 Quét ngay]`.
   * Thước đo tình trạng API Gemini & Quota realtime.
   * Nhật ký hoạt động gần nhất (Live log).

2. **Tab 2: Quản Lý Nhóm Facebook (Groups Manager):**
   * Danh sách các nhóm kèm công tắc gạt **BẬT/TẮT**.
   * Ô nhập nhanh để thêm nhóm mới: `[ Tên Nhóm ]` + `[ Link Facebook ]` ➔ `[+ Thêm]`.
   * Nút xóa nhóm.

3. **Tab 3: Cấu Hình Output 4 Kênh Discord (Channels Output Config):**
   * Bảng cấu hình 4 kênh: Kèo 1, Kèo 2, Khách Mua, Log.
   * Mỗi kênh có:
     * Công tắc Bật/Tắt độc lập.
     * Ô sửa Webhook URL.
     * Con trượt chọn % giảm giá tối thiểu (ví dụ: kéo thanh trượt từ 10% đến 40%).
     * Chọn tag mention (`@everyone`, `@here`, hoặc không tag).
     * Bật/Tắt ảnh thumbnail.

4. **Tab 4: Cài Đặt Hệ Thống & Khởi Động (System Settings):**
   * Đổi Token Bot Discord, Gemini API Key trực tiếp trên giao diện (tự lưu vào `.env`).
   * Chỉnh thời gian hẹn giờ cào (mặc định 10 phút, 15 phút, 30 phút...).
   * Tùy chọn: **Tự động khởi động cùng Windows**.
   * Chế độ cào: Ẩn trình duyệt (Headless) hoặc Hiện trình duyệt để quan sát.

---

## 3. Lộ Trình Triển Khai (Roadmap)

### Bước 1: Xây Dựng Mini Web Server Cài Đặt (`ui_server.py`)
* Sử dụng module nhẹ để tạo REST API đọc/ghi trực tiếp từ SQLite `database.py` và `.env`.
* Giao diện HTML/CSS/JS thuần, không cài đặt cồng kềnh, Dark Mode sang trọng.

### Bước 2: Tích Hợp System Tray Icon (`tray_app.py`)
* Sử dụng thư viện `pystray` và `Pillow` để tạo icon góc phải màn hình.
* Đóng gói luồng chạy song song:
  * Luồng 1: Discord Bot (`bot.py`)
  * Luồng 2: Scheduler cào dữ liệu (`scraper.py`)
  * Luồng 3: Web Server UI (`ui_server.py`)
  * Luồng 4: System Tray Icon

### Bước 3: Đóng Gói Thành File `.exe` Hoặc Shortcut Khởi Động Không Console
* Tạo shortcut chạy qua `pythonw.exe` (không hiện cửa sổ đen).
* Viết script đăng ký Registry Windows để tự bật cùng máy tính.
* Tùy chọn đóng gói thành `FBMetaHunter.exe` độc lập bằng PyInstaller.
