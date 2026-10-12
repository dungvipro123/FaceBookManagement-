"""
Cấu hình cho công cụ scrape bài viết Facebook Group
"""

# Danh sách 4 nhóm công khai cần cào
TARGET_GROUPS = [
    {
        "name": "Màn Hình Hà Nội",
        "url": "https://www.facebook.com/groups/manhinhhanoi"
    },
    {
        "name": "Hội Màn Hình 760589759199370",
        "url": "https://www.facebook.com/groups/760589759199370"
    },
    {
        "name": "Chợ Màn Hình PC Thanh Lý",
        "url": "https://www.facebook.com/groups/chomanhinhpcthanhly"
    },
    {
        "name": "Chợ Màn Hình 620686372835344",
        "url": "https://www.facebook.com/groups/620686372835344"
    }
]

# Số lượng bài mới tối đa muốn cào cho mỗi nhóm trong một lượt chạy
MAX_POSTS_PER_GROUP = 10

# Số lần cuộn trang tối đa cho mỗi nhóm (tránh cuộn vô tận nếu chưa gặp bài cũ)
MAX_SCROLLS_PER_GROUP = 8

# Chế độ chạy: False = Mở trình duyệt để bạn quan sát trực tiếp, True = Chạy ngầm
HEADLESS = False

# Thời gian nghỉ ngẫu nhiên (giây) giữa các lần cuộn trang
SCROLL_DELAY_MIN = 2.0
SCROLL_DELAY_MAX = 4.0

# Thời gian nghỉ (giây) giữa các nhóm để tránh bị Facebook nghi vấn
GROUP_DELAY_MIN = 4.0
GROUP_DELAY_MAX = 7.0

# File lưu cơ sở dữ liệu SQLite
DB_PATH = "facebook_posts.db"

# File cookie (tùy chọn: nếu có file này, bot sẽ tự nạp để tránh mọi popup đăng nhập)
COOKIES_FILE = "cookies.json"

# Cấu hình Proxy (Để trống "" nếu dùng mạng thường hoặc dùng VPN toàn máy)
# Ví dụ định dạng:
# "http://username:password@ip:port" hoặc "socks5://127.0.0.1:1080" hoặc "http://103.152.112.5:8080"
PROXY_SERVER = ""

import os

# Tự động nạp cấu hình từ file .env nếu có
def _load_env_file():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        except Exception:
            pass

_load_env_file()

# ==================== CẤU HÌNH CÁC KÊNH DISCORD ====================
# 1. KÊNH KÈO NGON 1 (Kèo thơm từ NGƯỜI DÙNG THỰC SỰ pass lại đồ zin):
DISCORD_DEAL_WEBHOOK_URL = os.getenv("DISCORD_DEAL_WEBHOOK_URL", "")

# 2. KÊNH KÈO NGON 2 (Kèo hời nhưng người đăng là THỢ / SHOP / LÁI BUÔN xả hàng):
DISCORD_DEAL_2_WEBHOOK_URL = os.getenv("DISCORD_DEAL_2_WEBHOOK_URL", "")

# 3. KÊNH KHÁCH TÌM MUA (Bắn riêng các bài khách cần mua đồ để vào báo giá chào hàng):
DISCORD_BUY_WEBHOOK_URL = os.getenv("DISCORD_BUY_WEBHOOK_URL", "")

# 4. KÊNH LOG (Bắn tất cả mọi bài cào được để theo dõi hoạt động theo thời gian thực):
DISCORD_LOG_WEBHOOK_URL = os.getenv("DISCORD_LOG_WEBHOOK_URL", "")

# Giữ tương thích:
DISCORD_WEBHOOK_URL = DISCORD_DEAL_WEBHOOK_URL

# ==================== CẤU HÌNH AI ĐỊNH GIÁ (GEMINI FLASH) ====================
# Điền Google Gemini API Key để AI tự thẩm định giá mọi loại màn hình (giữ token siêu thấp)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Ngưỡng giảm giá tối thiểu (%) so với giá thị trường để kích hoạt thông báo
MIN_DISCOUNT_PERCENT = 15.0

# ==================== CẤU HÌNH DISCORD BOT (ĐIỀU KHIỂN 2 CHIỀU) ====================
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_BOT_APP_ID = os.getenv("DISCORD_BOT_APP_ID", "")




