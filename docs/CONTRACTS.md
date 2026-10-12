# Hợp Đồng Giao Tiếp Giữa Các Module (System Contracts v2.1)
> **Trạng thái:** Bản chính thức v2.1 (Phê duyệt có điều kiện, tiến hành Phase 1).  
> **Mục tiêu:** Bản đặc tả kỹ thuật toàn diện cho `FB Monitor Hunter v2.0`. Tất cả các module (`app/`, `ui/`, `scraper/`, `discord/`) bắt buộc phải tuân thủ chuẩn xác hợp đồng này.

---

## 1. Trạng Thái Chung Ứng Dụng (Shared AppState) & Hàm Sức Khỏe (Health Color)

### 1.1. Dataclass `AppState`
Đặt tại `app/state.py`, đồng bộ thread-safe qua `threading.Lock`.

```python
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

@dataclass
class AppState:
    boot_id: str = ""                    # UUID4 sinh khi khởi động app
    is_paused: bool = False             # Người dùng tạm dừng quét
    is_scanning: bool = False           # Đang có tiến trình cào đang chạy
    
    # Facebook Session & Crawler
    fb_status: str = "unknown"          # "ok" | "checkpoint" | "captcha" | "rate_limited" | "logged_out" | "unknown"
    current_group: Optional[str] = None # Nhóm đang cào tại thời điểm hiện tại
    scan_progress: Optional[Dict[str, Any]] = None 
    # Ví dụ: {"current_index": 2, "total_groups": 5, "current_group": "Màn Hình Hà Nội", "percent": 40.0}
    last_scan_time: Optional[str] = None # ISO-8601 UTC
    next_scan_time: Optional[str] = None # ISO-8601 UTC
    
    # Gemini AI Status
    gemini_status: str = "untested"     # "ok" | "quota_exceeded" | "model_not_found" | "network_error" | "untested"
    gemini_model: str = "gemini-3.5-flash"
    gemini_latency_ms: float = 0.0      # Lần đo gần nhất (ms)
    gemini_latency_history: List[float] = field(default_factory=list) # Tối đa 20 điểm đo gần nhất
    
    # Thống kê nhanh
    total_posts: int = 0
    total_deals: int = 0
    total_buys: int = 0
    today_posts: int = 0
    active_groups_count: int = 0
    
    # Lỗi gần nhất
    last_error: Optional[Dict[str, str]] = None 
    # Ví dụ: {"timestamp": "2026-10-12T06:20:00Z", "module": "scraper", "message": "Facebook checkpoint detected"}

    # Bộ nhớ đệm Log thời gian thực (FIFO Ring Buffer: Tối đa 100 dòng)
    recent_logs: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def status(self) -> str:
        color = health_color(self)
        if color == "red":
            return "error"
        if self.is_scanning:
            return "scanning"
        if self.is_paused or color == "amber":
            return "paused"
        return "idle"
```

### 1.2. Hàm Tính Toán Màu Sức Khỏe Duy Nhất `health_color(state)`
Hàm chuẩn `health_color(state: AppState) -> str` (`"green"` | `"amber"` | `"red"`):
```python
def health_color(state: AppState) -> str:
    # 1. Các trường hợp khẩn cấp -> RED
    if state.fb_status in ("logged_out", "checkpoint", "captcha"):
        return "red"
    if state.gemini_status in ("quota_exceeded", "model_not_found", "network_error"):
        return "red"

    # 2. Các trạng thái cảnh báo / bận / tạm dừng / chưa rõ -> AMBER
    if state.fb_status in ("unknown", "rate_limited"):
        return "amber"
    if state.gemini_status in ("untested",):
        return "amber"
    if state.is_scanning or state.is_paused:
        return "amber"

    # 3. Hoạt động bình thường -> GREEN
    return "green"
```
Icon khay hệ thống Windows (`pystray`) và Dashboard Hero Core cùng sử dụng giá trị này để đổi màu trong vòng **2 giây**.

---

## 2. Bảo Mật, Xác Thực & Chuẩn Hóa Dữ Liệu

### 2.1. Xác Thực Mạng LAN & Quản Lý Session
* **Loopback (`127.0.0.1` / `localhost`):** Mặc định tin cậy, không bắt buộc đăng nhập PIN.
* **Mạng LAN:** Bắt buộc `lan_access_enabled == true`.
* **Cơ chế Session phía Server (Revocable Sessions):**
  * `POST /api/auth/login`: Nhận `{"pin": "..."}`. Dùng `hmac.compare_digest` để so sánh với mã PIN.
  * Khi đăng nhập thành công, server sinh `session_token` ngẫu nhiên (UUID4 / 32 bytes hex), lưu vào bộ nhớ có thể thu hồi (revocable store), và set HttpOnly Cookie:
    `Set-Cookie: session_token=<token>; HttpOnly; SameSite=Lax; Path=/; Max-Age=2592000`
  * Chấp nhận xác thực qua **Cookie `session_token`** HOẶC Header `X-Dashboard-PIN: <pin>` (so khớp bằng `hmac.compare_digest`).
  * **Loại bỏ hoàn toàn tham số `?token=` khỏi URL** (đặc biệt ở SSE) để ngăn rò rỉ token qua access log và lịch sử duyệt web.
* **Xoay Vòng Mã PIN (`POST /api/auth/rotate-pin`):**
  * Chỉ cho phép gọi từ **Loopback** (`127.0.0.1`).
  * Tự động sinh mã PIN ngẫu nhiên mới, hủy toàn bộ các session hiện có, và trả về mã PIN mới **một lần duy nhất**.
  * **TUYỆT ĐỐI KHÔNG BAO GIỜ GHI MÃ PIN VÀO FILE LOG!**
  * Endpoint `GET /api/settings` **KHÔNG BAO GIỜ** trả về `lan_pin`, chỉ trả về `{"lan_pin_set": true/false}`.
* **Chống Brute Force:** Tối đa 5 lần thử sai trong 5 phút trên một IP client. Vượt quá sẽ bị khóa 15 phút (trả về HTTP 429).
* **Cảnh báo Plain-HTTP LAN:** Giao tiếp qua mạng LAN cục bộ dùng HTTP thông thường tiềm ẩn rủi ro nghe lén gói tin trên Wi-Fi công cộng. Chỉ sử dụng chế độ LAN trên mạng gia đình / văn phòng nội bộ tin cậy.

### 2.2. Kiểm Tra Host Allow-List Trên Toàn Bộ Requests (CSRF / Rebinding Protection)
Áp dụng middleware kiểm tra header `Host` trên **TẤT CẢ các phương thức HTTP (cả GET và non-GET)**:
* `Host` hợp lệ: `127.0.0.1:<port>`, `localhost:<port>`, hoặc `IP_LAN:<port>` (chỉ khi `lan_access_enabled == true`).
* Trên các request thay đổi dữ liệu (`POST`, `PUT`, `PATCH`, `DELETE`): Kiểm tra thêm `Origin` / `Referer` (nếu có) phải khớp với Host hợp lệ.

### 2.3. Quy Tắc Che Giấu Bí Mật (Masking Rule)
Áp dụng cho: `GEMINI_API_KEY`, `DISCORD_BOT_TOKEN`, `DISCORD_BOT_APP_ID`, `webhook_url`:
* **Nếu độ dài chuỗi <= 8 ký tự:** Thay toàn bộ bằng cố định `"••••••••"`.
* **Nếu độ dài chuỗi > 8 ký tự:** Giữ lại **4 ký tự cuối**, toàn bộ phần trước thay bằng `"••••••••"` (Ví dụ: `••••••••PXA`, `••••••••3myAZ`).
* Bí mật không bao giờ được ghi vào log ở dạng văn bản rõ.

### 2.4. Tiêu Chuẩn Kiểm Tra Hợp Lệ Dữ Liệu Đầu Vào (Input Validation)
1. **Webhook URL Discord:** Bắt buộc khớp Regex chuẩn Discord:
   `^https://(?:ptb\.|canary\.)?discord\.com/api/webhooks/\d+/[A-Za-z0-9_-]+$`
2. **Nhóm Facebook:** Chỉ chấp nhận URL thuộc miền Facebook và bắt đầu bằng:
   `^https://(?:www\.)?facebook\.com/groups/[A-Za-z0-9._-]+/?$`
   (Từ chối tất cả các trang cá nhân, fanpage, hoặc URL ngoài).
3. **Mention Tag:** Khớp Regex:
   `^(|@everyone|@here|<@&\d+>|<@\d+>)$`
4. **Độ ưu tiên nhóm (Priority):** Số nguyên từ `1` đến `5`.
5. **Cờ Boolean:** `headless`, `autostart`, `lan_access_enabled` bắt buộc là kiểu boolean thực thụ.
6. **Tên model Gemini:** Bắt buộc khớp charset an toàn: `^[a-zA-Z0-9._-]+$` (ví dụ: `gemini-3.5-flash`).

---

## 3. Lược Đồ Cơ Sở Dữ Liệu SQLite (WAL Mode & Migration 2)

* **Vị trí lưu trữ:** `%APPDATA%/FBMonitorHunter/data/facebook_posts.db`
* **Cấu hình:** `PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA foreign_keys=ON;`
* **Phiên bản Schema hiện tại:** `schema_version = 2`.

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS posts (
    post_id TEXT PRIMARY KEY,
    group_name TEXT,
    group_url TEXT,
    author_name TEXT,
    author_url TEXT,
    post_url TEXT,
    created_time TEXT,
    content TEXT,
    media_urls TEXT,
    model TEXT,
    deal_price INTEGER,
    market_price INTEGER,
    discount_pct REAL,
    is_deal INTEGER DEFAULT 0,
    post_type TEXT DEFAULT 'SELL',       -- 'SELL' | 'BUY'
    -- Bổ sung Migration 2:
    is_dealer INTEGER DEFAULT 0,         -- 0 = Người dùng pass, 1 = Thợ/Shop xả
    dealer_buy_price INTEGER DEFAULT 0,  -- Giá thợ nên thu để có lãi
    profit INTEGER DEFAULT 0,            -- Lãi dự tính (market_price - deal_price)
    thumbnail_url TEXT DEFAULT '',       -- Ảnh đại diện trích xuất
    crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_posts_crawled ON posts(crawled_at);
CREATE INDEX IF NOT EXISTS idx_posts_is_deal ON posts(is_deal);
CREATE INDEX IF NOT EXISTS idx_posts_type ON posts(post_type);

CREATE TABLE IF NOT EXISTS monitored_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    url TEXT UNIQUE NOT NULL,
    is_active INTEGER DEFAULT 1,
    priority INTEGER DEFAULT 1,          -- 1 đến 5
    last_scraped_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS channel_configs (
    channel_key TEXT PRIMARY KEY,        -- 'deal_1' | 'deal_2' | 'buy' | 'log'
    name TEXT NOT NULL,
    webhook_url TEXT,
    is_enabled INTEGER DEFAULT 1,
    min_discount REAL DEFAULT 15.0,      -- 0.0 đến 99.0%
    mention_tag TEXT DEFAULT '',
    show_images INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id TEXT NOT NULL,
    channel_key TEXT NOT NULL,
    delivered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status_code INTEGER DEFAULT 200,
    UNIQUE(post_id, channel_key),        -- Đảm bảo mỗi bài chỉ gửi đến 1 kênh đúng 1 lần
    FOREIGN KEY(post_id) REFERENCES posts(post_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_deliveries_post_chan ON deliveries(post_id, channel_key);

CREATE TABLE IF NOT EXISTS system_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

---

## 4. Bảng Khóa Cấu Hình Hệ Thống (Config Keys Table)

| Khóa Cấu Hình (Key) | Kiểu Dữ Liệu | Mặc Định | Giới Hạn Hợp Lệ | Yêu Cầu Khởi Động Lại? | Lưu Trữ |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `scan_interval_minutes` | `int` | `15` | `10` đến `1440` | `false` (Hot reload ngay) | SQLite |
| `headless` | `bool` | `true` | `true` / `false` | `false` | SQLite |
| `gemini_model` | `str` | `"gemini-3.5-flash"` | Charset `^[a-zA-Z0-9._-]+$` | `false` | SQLite |
| `lan_access_enabled` | `bool` | `false` | `true` / `false` | **`true` (requires_restart)** | SQLite |
| `web_port` | `int` | `8080` | `1024` đến `65535` | **`true` (requires_restart)** | SQLite |
| `autostart` | `bool` | `false` | `true` / `false` | `false` (Cập nhật Registry ngay) | SQLite |
| `GEMINI_API_KEY` | `str` | `""` | Không rỗng | `false` | `.env` |
| `DISCORD_BOT_TOKEN` | `str` | `""` | Tùy chọn | `false` | `.env` |
| `DISCORD_BOT_APP_ID` | `str` | `""` | Tùy chọn | `false` | `.env` |

---

## 5. Quy Tắc Phân Phối Bài Viết Đến Discord (Routing Specification)

1. **Phân phối Kèo Thơm (Chính xác 1 Kênh Kèo cho mỗi bài viết):**
   * **Người Bán Riêng Lẻ (`is_dealer == 0`):** Định tuyến độc quyền vào kênh **`deal_1`**. Điều kiện bắn: Kênh `deal_1` đang bật (`is_enabled == 1`) và `discount_pct >= deal_1.min_discount`.
   * **Thợ / Cửa Hàng / Lái Buôn (`is_dealer == 1`):** Định tuyến độc quyền vào kênh **`deal_2`**. Điều kiện bắn: Kênh `deal_2` đang bật (`is_enabled == 1`) và `discount_pct >= deal_2.min_discount`.
   * **Nguyên tắc At-Least-Once Delivery:** Bản ghi trong bảng `deliveries` **chỉ được phép chèn vào khi Discord phản hồi HTTP status 2xx**. Nếu lỗi 429 hoặc 5xx, không chèn bản ghi và tiến hành retry.
2. **Khách Tìm Mua (`post_type == 'BUY'`):**
   * Định tuyến độc quyền vào kênh **`buy`** nếu kênh đang bật. Chèn bản ghi vào `deliveries(post_id, 'buy')` khi bắn thành công (2xx).
3. **Kênh Log & Hệ Thống (`channel_key == 'log'`):**
   * Nhận toàn bộ bài cào được và các sự kiện hệ thống.
   * **Send Queue có cơ chế gom mảng (Batching):** Để tránh bị Discord rate limit, kênh log sử dụng hàng đợi bất đồng bộ gửi theo lô (batch tối đa 5 embeds / request hoặc giãn cách tối thiểu 1.5s giữa các lần gửi).

---

## 6. Danh Mục Mã Lỗi & HTTP Status Code Mapping

| Error Code | HTTP Status | Ý Nghĩa / Tình Huống Phát Sinh |
| :--- | :--- | :--- |
| `UNAUTHORIZED` | **401** | Chưa đăng nhập hoặc Session token không tồn tại. |
| `FORBIDDEN` | **403** | Sai mã PIN hoặc vi phạm Host/Origin header allow-list. |
| `RATE_LIMITED` | **429** | Thử mã PIN sai quá 5 lần / 5 phút. |
| `VALIDATION_ERROR` | **422** | Dữ liệu đầu vào sai kiểu, sai regex, sai phạm vi min/max. |
| `NOT_FOUND` | **404** | Không tìm thấy nhóm hoặc kênh Discord theo ID/Key. |
| `CONFLICT` | **409** | URL nhóm đã tồn tại trong danh sách hoặc đang có tác vụ quét chạy dở. |
| `SYSTEM_BUSY` | **409** | Hệ thống đang bận, không thể thực hiện thao tác xung đột. |
| `INTERNAL_ERROR` | **500** | Lỗi ngoại lệ hệ thống chưa xử lý phía server. |

Cấu trúc Error Envelope:
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "URL nhóm phải có định dạng https://facebook.com/groups/...",
    "details": { "field": "url", "received": "https://google.com" }
  }
}
```

---

## 7. Danh Mục API Endpoints Chi Tiết

Mọi response thành công trả về `{ "success": true, "data": ... }`.

### 7.1. Xác Thực & Sức Khỏe
* `GET /api/health`: Probe nhẹ, trả về `{"status": "ok", "uptime_seconds": 120}`.
* `POST /api/auth/login`: Body `{"pin": "123456"}`. Thiết lập cookie `session_token`.
* `POST /api/auth/logout`: Xóa session cookie.
* `POST /api/auth/rotate-pin`: **Loopback only**. Sinh PIN mới, thu hồi toàn bộ session, trả về `{"pin": "928371"}` 1 lần duy nhất.

### 7.2. Trạng Thái & Điều Khiển
* `GET /api/status`: Trả về `AppState` (tất cả secret đã mask, `health_color`, `gemini_latency_history`).
* `GET /api/deals?limit=20&page=1`: Lấy danh sách kèo thơm kèm phân trang, thông tin thợ, thumbnail và lãi dự tính.
* `POST /api/actions/scan-now`: Kích hoạt quét ngay lập tức.
* `POST /api/actions/pause`: Tạm dừng quét.
* `POST /api/actions/resume`: Tiếp tục quét.
* `POST /api/actions/test-quota`: **Luôn trả về HTTP 200** với trường `status`:
  * `{"success": true, "data": {"status": "ok", "latency_ms": 82.5, "model": "gemini-3.5-flash"}}`
  * `{"success": true, "data": {"status": "quota_exceeded", "message": "Quá hạn mức 429"}}`
  * `{"success": true, "data": {"status": "model_not_found", "message": "Model 404 không tồn tại"}}`
  * `{"success": true, "data": {"status": "network_error", "message": "Lỗi kết nối"}}`
* `POST /api/actions/restart-server`: Yêu cầu supervisor khởi động lại tiến trình server (sau khi đổi port hoặc lan bind).

### 7.3. Nhóm Facebook & Kênh Discord
* `GET /api/groups`: Danh sách nhóm theo dõi.
* `POST /api/groups`: Body `{"name": str, "url": str, "priority": int}` (URL chuẩn hóa).
* `PATCH /api/groups/{id}`: Body `{"name"?, "url"?, "priority"?}`.
* `PATCH /api/groups/{id}/toggle`: Đổi trạng thái `is_active`.
* `DELETE /api/groups/{id}`: Xóa nhóm.
* `GET /api/channels`: Trả về 4 kênh với webhook đã mask.
* `PATCH /api/channels/{key}`: Cập nhật cấu hình kênh.
* `POST /api/channels/{key}/test`: Gửi tin nhắn test tới webhook.

### 7.4. Cài Đặt Hệ Thống & Secrets
* `GET /api/settings`: Trả về các giá trị runtime kèm cờ `requires_restart` và `{"lan_pin_set": true}` (không lộ PIN).
* `POST /api/settings`: Cập nhật cấu hình runtime.
* `PUT /api/secrets`: **Write-only**. Body `{"gemini_api_key"?, "discord_bot_token"?, "discord_bot_app_id"?}`. Lưu trực tiếp vào `.env`, trả về danh sách các key đã được mask.

---

## 8. Đặc Tả Server-Sent Events (SSE) `/api/logs/stream`

* **Bảo mật:** Xác thực qua Cookie `session_token` hoặc Header `X-Dashboard-PIN`. Tối đa **5 clients kết nối đồng thời** (ngăn chặn cạn kiệt tài nguyên).
* **Đồng bộ đa luồng:** Xuất bản event từ background thread qua `asyncio_loop.call_soon_threadsafe()`.
* **Heartbeat:** Mỗi 15 giây gửi ping: `: heartbeat <ISO-8601>\n\n`.
* **Sự kiện đầu tiên khi kết nối:** Server gửi sự kiện thông báo `boot_id`:
  ```text
  id: 0
  event: init
  data: {"boot_id": "c859d079-98e2-48f9-a1fc-70a7b3c97894", "replay_logs": [...]}
  ```
* `event: log`: `{"timestamp": "...", "level": "INFO", "message": "..."}`
* `event: progress`: `{"current_index": 1, "total_groups": 4, "current_group": "...", "percent": 25.0}`
* `event: status`: `{"status": "scanning", "health_color": "amber", "is_scanning": true, ...}`
* `event: settings`: `{"key": "scan_interval_minutes", "value": 20}` (**Tuyệt đối không gửi giá trị secret**).
* `event: deal`:
  ```json
  {
    "post_id": "2451204592291001",
    "product_name": "Dell Ultrasharp U2422H",
    "deal_price": 2700000,
    "market_price": 3600000,
    "discount_pct": 25.0,
    "dealer_buy_price": 3000000,
    "profit": 900000,
    "author_name": "Tuấn Thành",
    "is_dealer": false,
    "thumbnail_url": "https://...",
    "created_time": "15 phút trước",
    "post_url": "https://facebook.com/groups/...",
    "channel_keys": ["deal_1"]
  }
  ```
