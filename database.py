import sqlite3
import json
from datetime import datetime
from config import DB_PATH, TARGET_GROUPS

def get_connection():
    """Khởi tạo kết nối SQLite với row_factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Khởi tạo các bảng lưu trữ (bài viết, nhóm theo dõi, cài đặt động) nếu chưa tồn tại."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Bảng bài viết
    cursor.execute("""
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
        crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    # Tự động thêm các cột phục vụ hệ thống định giá (nếu chưa có)
    columns_to_add = [
        ("model", "TEXT"),
        ("deal_price", "INTEGER"),
        ("market_price", "INTEGER"),
        ("discount_pct", "REAL"),
        ("is_deal", "INTEGER DEFAULT 0"),
        ("post_type", "TEXT")
    ]
    for col_name, col_type in columns_to_add:
        try:
            cursor.execute(f"ALTER TABLE posts ADD COLUMN {col_name} {col_type};")
        except sqlite3.OperationalError:
            pass  # Cột đã tồn tại

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_group_url ON posts(group_url);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_crawled_at ON posts(crawled_at);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_model ON posts(model);")

    # 2. Bảng nhóm theo dõi động (Dynamic Monitored Groups)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS monitored_groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        url TEXT UNIQUE NOT NULL,
        is_active INTEGER DEFAULT 1,
        priority INTEGER DEFAULT 1,
        last_scraped_at TIMESTAMP
    );
    """)

    # 3. Bảng cấu hình hệ thống động (Dynamic Settings)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_settings (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    """)

    # 4. Bảng cấu hình Output cho từng kênh Discord (Channel Output Configs)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS channel_configs (
        channel_key TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        webhook_url TEXT,
        is_enabled INTEGER DEFAULT 1,
        min_discount REAL DEFAULT 15.0,
        mention_tag TEXT DEFAULT '',
        show_images INTEGER DEFAULT 1
    );
    """)

    # Nạp sẵn 4 nhóm mặc định nếu bảng nhóm đang trống
    cursor.execute("SELECT COUNT(*) FROM monitored_groups")
    if cursor.fetchone()[0] == 0:
        for grp in TARGET_GROUPS:
            try:
                cursor.execute("""
                INSERT OR IGNORE INTO monitored_groups (name, url, is_active, priority)
                VALUES (?, ?, 1, 1)
                """, (grp["name"], grp["url"]))
            except Exception:
                pass

    # Nạp sẵn cấu hình cho 4 kênh Discord nếu chưa có
    cursor.execute("SELECT COUNT(*) FROM channel_configs")
    if cursor.fetchone()[0] == 0:
        from config import (
            DISCORD_DEAL_WEBHOOK_URL,
            DISCORD_DEAL_2_WEBHOOK_URL,
            DISCORD_BUY_WEBHOOK_URL,
            DISCORD_LOG_WEBHOOK_URL,
            MIN_DISCOUNT_PERCENT
        )
        default_channels = [
            ("deal_1", "⭐ Kèo Ngon 1 (Người Dùng)", DISCORD_DEAL_WEBHOOK_URL, 1, MIN_DISCOUNT_PERCENT, "", 1),
            ("deal_2", "📦 Kèo Ngon 2 (Thợ Xả)", DISCORD_DEAL_2_WEBHOOK_URL, 1, MIN_DISCOUNT_PERCENT, "", 1),
            ("buy", "🎯 Khách Tìm Mua", DISCORD_BUY_WEBHOOK_URL, 1, 0.0, "", 1),
            ("log", "📜 Log Toàn Bộ Bài", DISCORD_LOG_WEBHOOK_URL, 1, 0.0, "", 1)
        ]
        for c in default_channels:
            try:
                cursor.execute("""
                INSERT OR IGNORE INTO channel_configs (channel_key, name, webhook_url, is_enabled, min_discount, mention_tag, show_images)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """, c)
            except Exception:
                pass

    conn.commit()
    conn.close()


def is_post_exists(post_id: str) -> bool:
    """Kiểm tra xem post_id đã được lưu trong DB trước đó chưa."""
    if not post_id:
        return False
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM posts WHERE post_id = ? LIMIT 1", (post_id,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

def save_post(post_data: dict) -> bool:
    """
    Lưu bài viết mới vào DB. Trả về True nếu thêm mới thành công, False nếu đã tồn tại.
    """
    post_id = post_data.get("post_id")
    if not post_id or is_post_exists(post_id):
        return False

    media_json = json.dumps(post_data.get("media_urls", []), ensure_ascii=False)
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO posts (
            post_id, group_name, group_url, author_name, author_url,
            post_url, created_time, content, media_urls, crawled_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
        """, (
            post_id,
            post_data.get("group_name", ""),
            post_data.get("group_url", ""),
            post_data.get("author_name", ""),
            post_data.get("author_url", ""),
            post_data.get("post_url", ""),
            post_data.get("created_time", ""),
            post_data.get("content", ""),
            media_json
        ))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def update_deal_info(post_id: str, deal_data: dict):
    """Cập nhật kết quả thẩm định giá (model, deal_price, market_price...) cho bài viết."""
    if not post_id or not deal_data:
        return
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE posts SET
        model = ?,
        deal_price = ?,
        market_price = ?,
        discount_pct = ?,
        is_deal = ?
    WHERE post_id = ?
    """, (
        deal_data.get("model", ""),
        deal_data.get("deal_price", 0),
        deal_data.get("market_price", 0),
        deal_data.get("discount_pct", 0.0),
        1 if deal_data.get("is_deal") else 0,
        post_id
    ))
    conn.commit()
    conn.close()

def get_all_posts(limit: int = 100):
    """Lấy danh sách các bài viết gần nhất trong DB."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM posts ORDER BY crawled_at DESC LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    results = [dict(row) for row in rows]
    conn.close()
    return results

def get_total_posts_count() -> int:
    """Đếm tổng số bài viết đã lưu."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM posts")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_author_post_count(author_name: str, author_url: str) -> int:
    """Đếm số bài viết mà tác giả này đã từng đăng trên các nhóm theo dõi."""
    if not author_name and not author_url:
        return 0
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT COUNT(*) FROM posts
    WHERE (author_url != '' AND author_url = ?)
       OR (author_name != '' AND author_name = ?)
    """, (author_url, author_name))
    count = cursor.fetchone()[0]
    conn.close()
    return count

# ==================== QUẢN LÝ NHÓM THEO DÕI ĐỘNG ====================

def get_all_monitored_groups() -> list:
    """Lấy toàn bộ danh sách nhóm đang theo dõi."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM monitored_groups ORDER BY priority DESC, id ASC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_active_groups() -> list:
    """Lấy danh sách các nhóm đang BẬT theo dõi (is_active = 1)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM monitored_groups WHERE is_active = 1 ORDER BY priority DESC, id ASC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def add_monitored_group(name: str, url: str, priority: int = 1) -> tuple:
    """Thêm nhóm mới vào danh sách theo dõi. Trả về (bool, message)."""
    clean_url = url.strip().split("?")[0].rstrip("/")
    if not clean_url.startswith("http"):
        return False, "URL nhóm không hợp lệ (phải bắt đầu bằng https://...)"
    
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO monitored_groups (name, url, is_active, priority)
        VALUES (?, ?, 1, ?)
        """, (name.strip(), clean_url, priority))
        conn.commit()
        return True, f"Đã thêm nhóm '{name}' thành công!"
    except sqlite3.IntegrityError:
        return False, f"Nhóm này đã tồn tại trong danh sách theo dõi!"
    finally:
        conn.close()

def toggle_monitored_group(group_id: int) -> tuple:
    """Bật/Tắt trạng thái theo dõi của 1 nhóm."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, is_active FROM monitored_groups WHERE id = ?", (group_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False, "Không tìm thấy ID nhóm này!"
    
    new_state = 0 if row["is_active"] == 1 else 1
    cursor.execute("UPDATE monitored_groups SET is_active = ? WHERE id = ?", (new_state, group_id))
    conn.commit()
    conn.close()
    state_str = "BẬT" if new_state == 1 else "TẮT"
    return True, f"Đã chuyển trạng thái nhóm '{row['name']}' sang: {state_str}"

def delete_monitored_group(group_id: int) -> tuple:
    """Xóa nhóm khỏi danh sách theo dõi."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM monitored_groups WHERE id = ?", (group_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False, "Không tìm thấy nhóm để xóa!"
    
    cursor.execute("DELETE FROM monitored_groups WHERE id = ?", (group_id,))
    conn.commit()
    conn.close()
    return True, f"Đã xóa nhóm '{row['name']}' khỏi danh sách theo dõi."

def update_group_last_scraped(url: str):
    """Cập nhật thời gian vừa cào xong của nhóm."""
    clean_url = url.strip().split("?")[0].rstrip("/")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE monitored_groups 
    SET last_scraped_at = datetime('now', 'localtime')
    WHERE url LIKE ?
    """, (f"{clean_url}%",))
    conn.commit()
    conn.close()

# ==================== CẤU HÌNH ĐỘNG & THỐNG KÊ ====================

def get_setting(key: str, default: str = "") -> str:
    """Đọc cấu hình hệ thống từ DB."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM system_settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else default

def set_setting(key: str, value: str):
    """Lưu hoặc cập nhật cấu hình hệ thống vào DB."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO system_settings (key, value) VALUES (?, ?)
    ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (key, str(value)))
    conn.commit()
    conn.close()

def get_recent_deals(limit: int = 5) -> list:
    """Lấy danh sách các kèo thơm mới nhất."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM posts 
    WHERE is_deal = 1 
    ORDER BY crawled_at DESC LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_system_stats() -> dict:
    """Tổng hợp số liệu thống kê hệ thống toàn diện."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM posts")
    total_posts = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM posts WHERE is_deal = 1")
    total_deals = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM posts WHERE post_type = 'BUY'")
    total_buys = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM posts WHERE date(crawled_at) = date('now', 'localtime')")
    today_posts = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM monitored_groups")
    total_groups = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM monitored_groups WHERE is_active = 1")
    active_groups = cursor.fetchone()[0]

    conn.close()
    return {
        "total_posts": total_posts,
        "total_deals": total_deals,
        "total_buys": total_buys,
        "today_posts": today_posts,
        "total_groups": total_groups,
        "active_groups": active_groups
    }

# ==================== QUẢN LÝ CẤU HÌNH OUTPUT TỪNG KÊNH DISCORD ====================

def get_all_channel_configs() -> list:
    """Lấy danh sách cấu hình toàn bộ các kênh Discord."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM channel_configs ORDER BY rowid ASC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_channel_config(channel_key: str) -> dict:
    """Lấy cấu hình chi tiết của 1 kênh theo key (deal_1, deal_2, buy, log)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM channel_configs WHERE channel_key = ?", (channel_key,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {}

def update_channel_config(channel_key: str, **kwargs) -> tuple:
    """
    Cập nhật linh hoạt cấu hình cho 1 kênh:
    - webhook_url: str
    - is_enabled: int (0 hoặc 1)
    - min_discount: float
    - mention_tag: str (@everyone, @here, hoặc <@&role_id>)
    - show_images: int (0 hoặc 1)
    """
    allowed_fields = ["webhook_url", "is_enabled", "min_discount", "mention_tag", "show_images", "name"]
    updates = []
    values = []
    for k, v in kwargs.items():
        if k in allowed_fields and v is not None:
            updates.append(f"{k} = ?")
            values.append(v)
    
    if not updates:
        return False, "Không có tham số nào cần cập nhật."

    values.append(channel_key)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"UPDATE channel_configs SET {', '.join(updates)} WHERE channel_key = ?", values)
    affected = cursor.rowcount
    conn.commit()
    conn.close()

    if affected > 0:
        return True, f"Đã cập nhật cấu hình kênh '{channel_key}' thành công!"
    return False, f"Không tìm thấy kênh có key: {channel_key}"


