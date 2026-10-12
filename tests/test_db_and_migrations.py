import sqlite3
import pytest
from app.db import get_connection, init_db

def test_db_init_and_migrations():
    init_db()
    conn = get_connection()

    # Check schema_migrations
    versions = [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()]
    assert 1 in versions
    assert 2 in versions

    # Check Migration 2 columns on posts
    cols = [r[1] for r in conn.execute("PRAGMA table_info(posts)").fetchall()]
    assert "is_dealer" in cols
    assert "dealer_buy_price" in cols
    assert "profit" in cols
    assert "thumbnail_url" in cols

    # Check deliveries table uniqueness constraint
    conn.execute("INSERT OR IGNORE INTO posts (post_id, content) VALUES ('test_p1', 'Test content')")
    conn.commit()

    conn.execute("INSERT OR REPLACE INTO deliveries (post_id, channel_key, status_code) VALUES ('test_p1', 'deal_1', 200)")
    conn.commit()

    # Duplicate insertion with different status should conflict on UNIQUE(post_id, channel_key)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO deliveries (post_id, channel_key, status_code) VALUES ('test_p1', 'deal_1', 500)")

    # Clean up test row
    conn.execute("DELETE FROM posts WHERE post_id = 'test_p1'")
    conn.commit()
