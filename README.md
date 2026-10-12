# Facebook Group Scraper (Thu Thập Bài Viết Mới Nhất)

Công cụ cào dữ liệu bài viết mới nhất từ các nhóm Facebook công khai bằng **Python + Playwright + SQLite**.

---

## 📌 Các Tính Năng Nổi Bật

1. **Luôn lấy bài mới nhất (Chronological):** Tự động điều hướng feed nhóm sang tham số `?sorting_setting=CHRONOLOGICAL` thay vì feed mặc định bị trộn bài cũ có tương tác.
2. **Cào tăng tiến (Incremental Crawling - Tránh cào trùng):** 
   - Quét từ trên xuống dưới.
   - Khi gặp một bài viết đã có sẵn trong cơ sở dữ liệu (`facebook_posts.db`), bot sẽ **ngay lập tức dừng cuộn nhóm đó** và chuyển sang nhóm tiếp theo để tiết kiệm thời gian và tài nguyên.
3. **Thu thập đầy đủ thông tin:**
   - Mã định danh bài viết (`post_id`), URL bài viết
   - Tên tác giả, URL trang cá nhân tác giả
   - Toàn bộ nội dung văn bản (tự động nhấn *"Xem thêm"* khi bài viết dài)
   - Danh sách link ảnh đính kèm chất lượng cao
   - Thời gian đăng bài thực tế
4. **Hệ thống Săn Kèo Thơm & Báo Discord Tức Thì:**
   - Tự động nhận diện model màn hình (Dell U2422H, LG 27GP850, AOC 24G2, Samsung Odyssey...) và bóc tách giá tiền (`2tr7`, `4500k`, `1.600.000đ`...).
   - So sánh với bảng giá thị trường [market_prices.json](file:///d:/New%20folder%20%283%29/market_prices.json).
   - Nếu rẻ hơn ngưỡng bạn đặt (mặc định `>= 15%`), bot sẽ **bắn ngay thông báo dạng Embed Card về kênh Discord** kèm link bài viết, ảnh, giá bán và số tiền tiết kiệm được!
5. **Hỗ trợ 2 chế độ:**
   - **Chế độ Guest (Mặc định):** Tự động đóng các popup đăng nhập/banner phiền toái.
   - **Chế độ Cookie (Khuyên dùng):** Có sẵn công cụ `login_and_save_cookie.py` giúp lưu phiên đăng nhập một lần, chạy mượt mà 100%.
6. **Xuất dữ liệu chuẩn:**
   - File Excel `facebook_posts.csv` (chuẩn font tiếng Việt UTF-8 BOM, mở trực tiếp bằng Excel không lỗi dấu tiếng Việt).
   - File JSON `facebook_posts.json` dành cho lập trình viên/tích hợp API.

---

## 🚀 Danh Sách 4 Nhóm Đã Cấu Hình Sẵn

Trong file [config.py](file:///d:/New%20folder%20%283%29/config.py):
1. **Màn Hình Hà Nội:** `https://www.facebook.com/groups/manhinhhanoi`
2. **Hội Màn Hình 760589759199370:** `https://www.facebook.com/groups/760589759199370`
3. **Chợ Màn Hình PC Thanh Lý:** `https://www.facebook.com/groups/chomanhinhpcthanhly`
4. **Chợ Màn Hình 620686372835344:** `https://www.facebook.com/groups/620686372835344`

---

## 🛠 Hướng Dẫn Sử Dụng

### 1. Chạy cào dữ liệu ngay lập tức
Mở Terminal tại thư mục này và chạy:
```bash
python main.py --run
```
*Lưu ý: Mặc định trình duyệt Chrome sẽ hiển thị (`HEADLESS = False` trong `config.py`) để bạn theo dõi trực quan quá trình quét.*

### 2. Xem menu điều khiển tương tác
```bash
python main.py
```
Bạn sẽ có các tùy chọn:
- `1`: Bắt đầu cào 4 nhóm
- `2`: Xem các bài viết vừa cào trong bảng trực quan
- `3`: Xuất dữ liệu ra file CSV và JSON

### 3. (Tùy chọn) Lưu Cookie để cào ổn định nhất
Nếu bạn muốn bot chạy ngầm không bao giờ bị Facebook chặn popup:
```bash
python login_and_save_cookie.py
```
Đăng nhập 1 tài khoản clone/phụ trên cửa sổ mở lên, sau đó nhấn phím Enter trên Terminal. File `cookies.json` sẽ được tạo và các lần cào sau bot sẽ tự động dùng.

### 4. Hệ Thống 4 Kênh Discord Tự Động Phân Luồng
Hệ thống tự động phân loại và điều hướng bài viết về 4 kênh riêng biệt:
1. **Kênh Kèo Ngon 1 (VIP User):** Chỉ nhận bài bán hời từ người dùng thật pass đồ (màu Đỏ rực kèm bảng tính lãi).
2. **Kênh Kèo Ngon 2 (Thợ Xả):** Nhận bài bán hời nhưng người đăng là Thợ / Cửa hàng xả hàng (màu Cam đậm).
3. **Kênh Khách Tìm Mua (Buyer Leads):** Nhận riêng các bài khách cần tìm mua để thợ/shop vào inbox chào giá ngay (màu Xanh Cyan).
4. **Kênh Log (Live Feed):** Nhận 100% mọi bài cào được để theo dõi hoạt động bot thời gian thực (màu Xanh Blurple).

**Cấu hình trong [config.py](file:///d:/New%20folder%20%283%29/config.py):**
```python
DISCORD_DEAL_WEBHOOK_URL   = "https://discord.com/api/webhooks/..." # Kênh Kèo Ngon 1
DISCORD_DEAL_2_WEBHOOK_URL = "https://discord.com/api/webhooks/..." # Kênh Kèo Ngon 2
DISCORD_BUY_WEBHOOK_URL    = "https://discord.com/api/webhooks/..." # Kênh Khách Tìm Mua
DISCORD_LOG_WEBHOOK_URL    = "https://discord.com/api/webhooks/..." # Kênh Log
```


---

## ⚙ Tùy Chỉnh Bảng Giá Thị Trường & Thông Số

- [market_prices.json](file:///d:/New%20folder%20%283%29/market_prices.json): Thêm mã màn hình và giá thị trường tham chiếu (VND) bạn quan tâm.
- [config.py](file:///d:/New%20folder%20%283%29/config.py):
  - `MIN_DISCOUNT_PERCENT`: Ngưỡng rẻ hơn bao nhiêu % thì mới bắn tin về Discord (mặc định: `15.0%`).
  - `MAX_POSTS_PER_GROUP`: Số bài mới tối đa mỗi nhóm (mặc định: `10`).
  - `HEADLESS`: Đặt `True` nếu muốn chạy ẩn không hiện cửa sổ trình duyệt.
  - `PROXY_SERVER`: Điền proxy nếu muốn đổi IP.


