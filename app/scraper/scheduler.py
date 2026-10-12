import time
import threading
import random
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from app.db import get_connection
from app.config import get_setting
from app.state import state_manager, utc_iso_now
from app.api.sse import sse_manager
from app.api.routes_status import set_scan_trigger
from app.scraper.engine import ScraperEngine
from app.scraper.appraiser import appraise_post, appraise_posts_batch
from app.discord.notifier import dispatch_post

class ScraperScheduler:
    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._scan_now_event = threading.Event()
        self._engine: Optional[ScraperEngine] = None

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._scan_now_event.clear()
        set_scan_trigger(self.trigger_scan_now)
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="ScraperSchedulerWorker")
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        self._scan_now_event.set()
        if self._engine:
            try:
                self._engine.stop()
            except Exception:
                pass

    def trigger_scan_now(self):
        self._scan_now_event.set()

    def _run_loop(self):
        self._engine = ScraperEngine()
        state_manager.add_log("INFO", "Tiến trình Scraper Scheduler đã khởi chạy.", "scheduler")

        while not self._stop_event.is_set():
            state = state_manager.get_state()
            if state.is_paused:
                time.sleep(1.0)
                continue

            # Run a scan iteration
            self._execute_scan_cycle()

            # Calculate next scan time
            interval_mins = max(10, get_setting("scan_interval_minutes", 15))
            next_dt = datetime.now(timezone.utc) + timedelta(minutes=interval_mins)
            state_manager.update(next_scan_time=next_dt.isoformat())
            sse_manager.publish_threadsafe("status", state_manager.to_dict())

            # Wait for interval or scan-now trigger
            wait_seconds = interval_mins * 60
            start_wait = time.time()
            while time.time() - start_wait < wait_seconds:
                if self._stop_event.is_set():
                    break
                if self._scan_now_event.is_set():
                    self._scan_now_event.clear()
                    break
                time.sleep(1.0)

    def _execute_scan_cycle(self):
        conn = get_connection()
        rows = conn.execute("""
        SELECT id, name, url, priority
        FROM monitored_groups
        WHERE is_active = 1
        ORDER BY priority ASC, id ASC
        """).fetchall()
        groups = [dict(r) for r in rows]

        if not groups:
            state_manager.add_log("INFO", "Không có nhóm Facebook nào đang bật theo dõi.", "scheduler")
            return

        state_manager.update(
            is_scanning=True,
            active_groups_count=len(groups)
        )
        sse_manager.publish_threadsafe("status", state_manager.to_dict())
        state_manager.add_log("INFO", f"Bắt đầu chu kỳ quét {len(groups)} nhóm Facebook...", "scheduler")

        total_groups = len(groups)
        for idx, grp in enumerate(groups, start=1):
            if self._stop_event.is_set() or state_manager.get_state().is_paused:
                break

            progress = {
                "current_index": idx,
                "total_groups": total_groups,
                "current_group": grp["name"],
                "percent": round((idx / total_groups) * 100, 1)
            }
            state_manager.update(
                current_group=grp["name"],
                scan_progress=progress
            )
            sse_manager.publish_threadsafe("progress", progress)
            state_manager.add_log("INFO", f"Đang quét nhóm [{idx}/{total_groups}]: {grp['name']}", "scraper")

            try:
                # Scrape group
                scraped_posts = self._engine.scrape_group(grp, max_scrolls=2)
                # Process all scraped posts in batch
                self._process_posts_batch(scraped_posts)

                # Update group's last_scraped_at
                conn.execute("UPDATE monitored_groups SET last_scraped_at = CURRENT_TIMESTAMP WHERE id = ?", (grp["id"],))
                conn.commit()

            except Exception as e:
                state_manager.set_error("scraper", f"Lỗi quét nhóm {grp['name']}: {str(e)}")
                state_manager.add_log("ERROR", f"Lỗi quét nhóm {grp['name']}: {str(e)}", "scraper")

            # Randomized delay between groups
            time.sleep(random.uniform(3.0, 6.0))

        # Scan cycle completed
        now_iso = utc_iso_now()
        state_manager.update(
            is_scanning=False,
            current_group=None,
            scan_progress=None,
            last_scan_time=now_iso
        )
        sse_manager.publish_threadsafe("status", state_manager.to_dict())
        state_manager.add_log("INFO", "Chu kỳ quét hoàn tất thành công.", "scheduler")

    def _process_posts_batch(self, scraped_posts: List[dict]):
        if not scraped_posts:
            return

        conn = get_connection()
        new_posts = []
        for raw_post in scraped_posts:
            post_id = raw_post.get("post_id")
            if not post_id:
                continue

            existing = conn.execute("SELECT 1 FROM posts WHERE post_id = ?", (post_id,)).fetchone()
            if existing:
                continue

            # Insert raw post into SQLite
            media_json = json.dumps(raw_post.get("media_urls", []), ensure_ascii=False)
            conn.execute("""
            INSERT INTO posts (post_id, group_name, group_url, author_name, author_url, post_url, created_time, content, media_urls)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                post_id,
                raw_post.get("group_name", ""),
                raw_post.get("group_url", ""),
                raw_post.get("author_name", ""),
                raw_post.get("author_url", ""),
                raw_post.get("post_url", ""),
                raw_post.get("created_time", ""),
                raw_post.get("content", ""),
                media_json
            ))
            new_posts.append(raw_post)

        if not new_posts:
            return

        conn.commit()

        # Batched appraisal using Gemini / Regex (drastically reduces RPD usage)
        enriched_posts = appraise_posts_batch(new_posts, batch_size=6)

        for enriched in enriched_posts:
            post_id = enriched.get("post_id")
            state = state_manager.get_state()
            state_manager.update(
                total_posts=state.total_posts + 1,
                today_posts=state.today_posts + 1
            )

            # Handle Deal
            if enriched.get("is_deal"):
                state_manager.update(total_deals=state.total_deals + 1)
                deal_data = {
                    "post_id": post_id,
                    "product_name": enriched.get("model", "Màn hình PC"),
                    "deal_price": enriched.get("deal_price", 0),
                    "market_price": enriched.get("market_price", 0),
                    "discount_pct": enriched.get("discount_pct", 0.0),
                    "dealer_buy_price": enriched.get("dealer_buy_price", 0),
                    "profit": enriched.get("profit", 0),
                    "author_name": enriched.get("author_name", ""),
                    "is_dealer": bool(enriched.get("is_dealer", 0)),
                    "thumbnail_url": enriched.get("thumbnail_url", ""),
                    "created_time": enriched.get("created_time", "Vừa xong"),
                    "post_url": enriched.get("post_url", ""),
                    "channel_keys": ["deal_2" if enriched.get("is_dealer") else "deal_1"]
                }
                sse_manager.publish_threadsafe("deal", deal_data)
                state_manager.add_log(
                    "INFO",
                    f"🔥 KÈO THƠM PHÁT HIỆN: {deal_data['product_name']} ({deal_data['discount_pct']}% off) bởi {deal_data['author_name']}",
                    "appraiser"
                )

            elif enriched.get("post_type") == "BUY":
                state_manager.update(total_buys=state.total_buys + 1)

            # Dispatch to Discord
            dispatch_post(enriched)

# Singleton scheduler
scraper_scheduler = ScraperScheduler()
