import pytest
from unittest.mock import patch
from app.db import init_db, get_connection
from app.scraper.appraiser import appraise_posts_batch

def test_appraise_posts_batch():
    init_db()
    conn = get_connection()

    test_posts = [
        # 1. Buy post (0-token filter)
        {
            "post_id": "test_batch_buy_1",
            "content": "Cần tìm mua màn hình 24 inch full viền",
            "media_urls": []
        },
        # 2. Non-price post (0-token filter)
        {
            "post_id": "test_batch_noprice_2",
            "content": "Xin tư vấn màn hình nào chơi game ngon trong tầm giá",
            "media_urls": []
        },
        # 3. Sell post with price (Dell U2422H)
        {
            "post_id": "test_batch_sell_3",
            "content": "Pass nhanh Dell U2422H fullbox còn bh 2026 giá 2tr7 gdtt HN",
            "media_urls": ["https://fbcdn.net/test3.jpg"],
            "author_name": "Tuấn Nguyễn"
        },
        # 4. Sell post with price (AOC 24G2)
        {
            "post_id": "test_batch_sell_4",
            "content": "Bán màn AOC 24G2 144hz ips giá 1tr9",
            "media_urls": ["https://fbcdn.net/test4.jpg"],
            "author_name": "Hoàng Nam"
        }
    ]

    # Insert raw posts into DB
    for p in test_posts:
        conn.execute("INSERT OR IGNORE INTO posts (post_id, content) VALUES (?, ?)", (p["post_id"], p["content"]))
    conn.commit()

    # Mock Gemini batch response
    mock_ai_response = [
        {
            "id": "test_batch_sell_3",
            "is_sell": True,
            "is_dealer": False,
            "model": "Dell UltraSharp U2422H",
            "price": 2700000,
            "market_price": 3800000,
            "dealer_buy_price": 3000000,
            "profit": 1100000,
            "is_deal": True
        },
        {
            "id": "test_batch_sell_4",
            "is_sell": True,
            "is_dealer": False,
            "model": "AOC 24G2",
            "price": 1900000,
            "market_price": 2400000,
            "dealer_buy_price": 2000000,
            "profit": 500000,
            "is_deal": True
        }
    ]

    with patch("app.scraper.appraiser.call_gemini_batch", return_value=mock_ai_response) as mock_batch:
        results = appraise_posts_batch(test_posts, batch_size=5)

        # Gemini should be called ONCE for the candidates, NOT 4 times!
        assert mock_batch.call_count == 1
        assert len(results) == 4

        # Post 1 should be BUY
        p1 = next(r for r in results if r["post_id"] == "test_batch_buy_1")
        assert p1["post_type"] == "BUY"
        assert p1["is_deal"] == 0

        # Post 2 should be non-deal
        p2 = next(r for r in results if r["post_id"] == "test_batch_noprice_2")
        assert p2["is_deal"] == 0

        # Post 3 should be Deal
        p3 = next(r for r in results if r["post_id"] == "test_batch_sell_3")
        assert p3["is_deal"] == 1
        assert p3["deal_price"] == 2700000
        assert p3["profit"] == 1100000
        assert p3["thumbnail_url"] == "https://fbcdn.net/test3.jpg"

        # Post 4 should be Deal
        p4 = next(r for r in results if r["post_id"] == "test_batch_sell_4")
        assert p4["is_deal"] == 1
        assert p4["deal_price"] == 1900000

    # Clean up test rows
    conn.execute("DELETE FROM posts WHERE post_id LIKE 'test_batch_%'")
    conn.commit()
