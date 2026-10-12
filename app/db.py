import sqlite3
import threading
from typing import Optional, List, Dict, Any, Tuple
from app.paths import get_db_path

# Thread-local storage for SQLite connections
_local = threading.local()

def get_connection() -> sqlite3.Connection:
    """Returns a thread-local SQLite connection configured for WAL mode."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        db_path = get_db_path()
        conn = sqlite3.connect(str(db_path), timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        _local.conn = conn
    return conn

def init_db() -> None:
    """Initializes tables, creates indexes, and performs idempotent migrations."""
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Migration tracking table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. Posts table
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
        model TEXT,
        deal_price INTEGER,
        market_price INTEGER,
        discount_pct REAL,
        is_deal INTEGER DEFAULT 0,
        post_type TEXT DEFAULT 'SELL',
        is_dealer INTEGER DEFAULT 0,
        dealer_buy_price INTEGER DEFAULT 0,
        profit INTEGER DEFAULT 0,
        thumbnail_url TEXT DEFAULT '',
        crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Ensure Migration 2 columns exist on posts if created previously
    migration_2_columns = [
        ("model", "TEXT"),
        ("deal_price", "INTEGER"),
        ("market_price", "INTEGER"),
        ("discount_pct", "REAL"),
        ("is_deal", "INTEGER DEFAULT 0"),
        ("post_type", "TEXT DEFAULT 'SELL'"),
        ("is_dealer", "INTEGER DEFAULT 0"),
        ("dealer_buy_price", "INTEGER DEFAULT 0"),
        ("profit", "INTEGER DEFAULT 0"),
        ("thumbnail_url", "TEXT DEFAULT ''"),
    ]
    for col_name, col_def in migration_2_columns:
        try:
            cursor.execute(f"ALTER TABLE posts ADD COLUMN {col_name} {col_def};")
        except sqlite3.OperationalError:
            pass  # Column already exists

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_crawled ON posts(crawled_at);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_is_deal ON posts(is_deal);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_type ON posts(post_type);")

    # 3. Monitored groups table
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

    # 4. Channel configs table
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

    # 5. Deliveries table (Migration 2)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS deliveries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id TEXT NOT NULL,
        channel_key TEXT NOT NULL,
        delivered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status_code INTEGER DEFAULT 200,
        UNIQUE(post_id, channel_key),
        FOREIGN KEY(post_id) REFERENCES posts(post_id) ON DELETE CASCADE
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_deliveries_post_chan ON deliveries(post_id, channel_key);")

    # 6. System settings table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """)

    # Record migration version 2
    cursor.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES (1);")
    cursor.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES (2);")

    # Seed default groups if empty
    cursor.execute("SELECT COUNT(*) FROM monitored_groups;")
    if cursor.fetchone()[0] == 0:
        default_groups = [
            ("Màn Hình Máy Tính Cũ Hà Nội", "https://www.facebook.com/groups/1004107450379879/", 1, 1),
            ("Chợ Linh Kiện Máy Tính Hà Nội", "https://www.facebook.com/groups/chomaytinhcu/", 1, 2),
            ("Hội Mua Bán Màn Hình PC", "https://www.facebook.com/groups/manhinhpc/", 1, 2),
            ("Thanh Lý Màn Hình Gaming", "https://www.facebook.com/groups/gamingmonitors/", 1, 3),
        ]
        cursor.executemany("""
        INSERT OR IGNORE INTO monitored_groups (name, url, is_active, priority)
        VALUES (?, ?, ?, ?)
        """, default_groups)

    # Seed 4 standard channel configs if empty
    cursor.execute("SELECT COUNT(*) FROM channel_configs;")
    if cursor.fetchone()[0] == 0:
        default_channels = [
            ("deal_1", "Kèo Người Bán Riêng", "", 1, 15.0, "", 1),
            ("deal_2", "Kèo Thợ / Cửa Hàng", "", 1, 20.0, "", 1),
            ("buy", "Khách Cần Mua", "", 1, 0.0, "", 1),
            ("log", "Nhật Ký & Toàn Bộ Bài", "", 1, 0.0, "", 0),
        ]
        cursor.executemany("""
        INSERT OR IGNORE INTO channel_configs (channel_key, name, webhook_url, is_enabled, min_discount, mention_tag, show_images)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, default_channels)

    # Seed default system settings if empty
    cursor.execute("SELECT COUNT(*) FROM system_settings;")
    if cursor.fetchone()[0] == 0:
        default_settings = [
            ("scan_interval_minutes", "15"),
            ("headless", "true"),
            ("gemini_model", "gemini-3.5-flash"),
            ("lan_access_enabled", "false"),
            ("web_port", "8080"),
            ("autostart", "false"),
        ]
        cursor.executemany("""
        INSERT OR IGNORE INTO system_settings (key, value)
        VALUES (?, ?)
        """, default_settings)

    conn.commit()
