import time
import threading
import queue
import requests
from typing import Optional, Dict, Any, List
from app.db import get_connection
from app.state import state_manager
from app.discord.formatting import (
    build_deal_payload,
    build_buy_payload,
    build_log_embed
)

# Background batch queue for the log channel
_log_queue = queue.Queue(maxsize=500)
_log_worker_running = False
_log_worker_lock = threading.Lock()

def get_channel_config(channel_key: str) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM channel_configs WHERE channel_key = ?", (channel_key,)).fetchone()
    return dict(row) if row else None

def record_delivery(post_id: str, channel_key: str, status_code: int = 200) -> None:
    """Records delivery into SQLite deliveries table ONLY upon receiving HTTP 2xx from Discord."""
    conn = get_connection()
    conn.execute("""
    INSERT INTO deliveries (post_id, channel_key, status_code)
    VALUES (?, ?, ?)
    ON CONFLICT(post_id, channel_key) DO UPDATE SET status_code = excluded.status_code;
    """, (post_id, channel_key, status_code))
    conn.commit()

def is_already_delivered(post_id: str, channel_key: str) -> bool:
    conn = get_connection()
    row = conn.execute("SELECT 1 FROM deliveries WHERE post_id = ? AND channel_key = ?", (post_id, channel_key)).fetchone()
    return bool(row)

def send_webhook_with_retry(webhook_url: str, payload: dict, max_retries: int = 3) -> Optional[int]:
    """
    Sends Discord webhook request with 429 Retry-After handling.
    Returns HTTP status code if successful (2xx), or None on permanent failure.
    """
    if not webhook_url:
        return None

    for attempt in range(max_retries):
        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            if resp.status_code in (200, 204):
                return resp.status_code
            elif resp.status_code == 429:
                retry_after = resp.json().get("retry_after", 2.0)
                time.sleep(float(retry_after))
                continue
            elif resp.status_code >= 500:
                time.sleep(1.0 * (attempt + 1))
                continue
            else:
                # 4xx permanent error
                return resp.status_code
        except Exception:
            time.sleep(1.0 * (attempt + 1))
            continue
    return None

def dispatch_post(post: dict) -> Dict[str, bool]:
    """
    Main dispatching coordinator according to CONTRACTS v2.1:
    1. Routes deal posts to exactly ONE channel:
       - is_dealer == 0 -> deal_1
       - is_dealer == 1 -> deal_2
    2. Routes buy posts to buy channel.
    3. Queues all posts for batched delivery to log channel.
    """
    results = {}
    post_id = post.get("post_id")
    if not post_id:
        return results

    post_type = post.get("post_type", "SELL")
    is_deal = bool(post.get("is_deal", 0))

    # 1. Deal Routing (Exclusive 1 Deal Channel per post)
    if is_deal and post_type != "BUY":
        is_dealer = bool(post.get("is_dealer", 0))
        deal_chan_key = "deal_2" if is_dealer else "deal_1"

        if not is_already_delivered(post_id, deal_chan_key):
            chan_cfg = get_channel_config(deal_chan_key)
            if chan_cfg and chan_cfg.get("is_enabled", 1) and chan_cfg.get("webhook_url"):
                min_disc = chan_cfg.get("min_discount", 15.0)
                if post.get("discount_pct", 0.0) >= min_disc:
                    payload = build_deal_payload(post, chan_cfg)
                    status = send_webhook_with_retry(chan_cfg["webhook_url"], payload)
                    if status and 200 <= status < 300:
                        record_delivery(post_id, deal_chan_key, status)
                        results[deal_chan_key] = True
                        state_manager.add_log("INFO", f"Đã gửi bài {post_id} tới kênh {chan_cfg['name']}", "discord")
                    else:
                        results[deal_chan_key] = False

    # 2. Buy Routing
    elif post_type == "BUY":
        if not is_already_delivered(post_id, "buy"):
            chan_cfg = get_channel_config("buy")
            if chan_cfg and chan_cfg.get("is_enabled", 1) and chan_cfg.get("webhook_url"):
                payload = build_buy_payload(post, chan_cfg)
                status = send_webhook_with_retry(chan_cfg["webhook_url"], payload)
                if status and 200 <= status < 300:
                    record_delivery(post_id, "buy", status)
                    results["buy"] = True
                    state_manager.add_log("INFO", f"Đã gửi bài tìm mua {post_id} tới kênh Khách Cần Mua", "discord")
                else:
                    results["buy"] = False

    # 3. Log Channel Routing (Queued with batching)
    queue_post_for_log(post)
    return results

def queue_post_for_log(post: dict) -> None:
    try:
        _log_queue.put_nowait(post)
    except queue.Full:
        pass
    start_log_worker()

def _log_worker_loop():
    while True:
        try:
            batch = []
            # Grab first item (blocking with timeout)
            item = _log_queue.get(timeout=2.0)
            batch.append(item)

            # Collect up to 4 more items without blocking
            while len(batch) < 5:
                try:
                    next_item = _log_queue.get_nowait()
                    batch.append(next_item)
                except queue.Empty:
                    break

            chan_cfg = get_channel_config("log")
            if chan_cfg and chan_cfg.get("is_enabled", 1) and chan_cfg.get("webhook_url"):
                embeds = [build_log_embed(p) for p in batch]
                payload = {"embeds": embeds}
                status = send_webhook_with_retry(chan_cfg["webhook_url"], payload)
                if status and 200 <= status < 300:
                    for p in batch:
                        if p.get("post_id"):
                            record_delivery(p["post_id"], "log", status)

            # Pace sends by at least 1.5s
            time.sleep(1.5)

        except queue.Empty:
            continue
        except Exception:
            time.sleep(2.0)

def start_log_worker():
    global _log_worker_running
    with _log_worker_lock:
        if not _log_worker_running:
            _log_worker_running = True
            t = threading.Thread(target=_log_worker_loop, daemon=True, name="DiscordLogWorker")
            t.start()
