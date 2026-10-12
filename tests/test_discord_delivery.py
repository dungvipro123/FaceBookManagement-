import pytest
from unittest.mock import patch, MagicMock
from app.db import init_db, get_connection
from app.discord.notifier import (
    dispatch_post,
    record_delivery,
    is_already_delivered
)
from app.discord.formatting import format_vnd, build_deal_payload, build_buy_payload

def test_vnd_formatting():
    assert format_vnd(2700000) == "2.700.000 đ"
    assert format_vnd(0) == "0 đ"

def test_exclusive_deal_routing():
    init_db()
    conn = get_connection()

    # Configure dummy webhook URLs so dispatch doesn't skip
    conn.execute("UPDATE channel_configs SET webhook_url = 'https://discord.com/api/webhooks/1/token', is_enabled = 1, min_discount = 15.0 WHERE channel_key IN ('deal_1', 'deal_2', 'buy')")
    # Insert posts to satisfy foreign key
    conn.execute("INSERT OR IGNORE INTO posts (post_id, content) VALUES ('test_private_123', 'Private seller')")
    conn.execute("INSERT OR IGNORE INTO posts (post_id, content) VALUES ('test_dealer_456', 'Dealer post')")
    conn.execute("INSERT OR IGNORE INTO posts (post_id, content) VALUES ('test_buy_789', 'Buy lead')")
    conn.commit()

    # 1. Private Seller Deal (is_dealer = 0)
    private_deal = {
        "post_id": "test_private_123",
        "model": "Dell U2422H",
        "deal_price": 2700000,
        "market_price": 3800000,
        "discount_pct": 28.9,
        "is_deal": 1,
        "is_dealer": 0,
        "post_type": "SELL"
    }

    with patch("app.discord.notifier.send_webhook_with_retry", return_value=204) as mock_send:
        res = dispatch_post(private_deal)
        assert res.get("deal_1") is True
        assert "deal_2" not in res
        assert is_already_delivered("test_private_123", "deal_1")
        assert not is_already_delivered("test_private_123", "deal_2")

    # 2. Dealer Deal (is_dealer = 1)
    dealer_deal = {
        "post_id": "test_dealer_456",
        "model": "Dell U2422H",
        "deal_price": 2800000,
        "market_price": 3800000,
        "discount_pct": 26.3,
        "is_deal": 1,
        "is_dealer": 1,
        "post_type": "SELL"
    }

    with patch("app.discord.notifier.send_webhook_with_retry", return_value=200) as mock_send:
        res = dispatch_post(dealer_deal)
        assert res.get("deal_2") is True
        assert "deal_1" not in res
        assert is_already_delivered("test_dealer_456", "deal_2")
        assert not is_already_delivered("test_dealer_456", "deal_1")

    # 3. Customer Buy Lead (post_type = 'BUY')
    buy_lead = {
        "post_id": "test_buy_789",
        "content": "Cần tìm mua màn hình Dell 24 inch",
        "post_type": "BUY",
        "is_deal": 0
    }

    with patch("app.discord.notifier.send_webhook_with_retry", return_value=200) as mock_send:
        res = dispatch_post(buy_lead)
        assert res.get("buy") is True
        assert "deal_1" not in res
        assert "deal_2" not in res
        assert is_already_delivered("test_buy_789", "buy")

    # Clean up test rows
    conn.execute("DELETE FROM deliveries WHERE post_id IN ('test_private_123', 'test_dealer_456', 'test_buy_789')")
    conn.commit()
