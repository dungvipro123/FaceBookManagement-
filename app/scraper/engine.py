import os
import json
import time
import random
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from pathlib import Path
from playwright.sync_api import sync_playwright, Page, BrowserContext
from app.config import get_setting
from app.state import state_manager
from app.paths import get_app_dir

def format_chronological_url(group_url: str) -> str:
    clean_url = group_url.strip().rstrip("/")
    parsed = urlparse(clean_url)
    query_params = parse_qs(parsed.query)
    query_params["sorting_setting"] = ["CHRONOLOGICAL"]
    new_query = urlencode(query_params, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))

def load_cookies() -> List[dict]:
    # Check %APPDATA%/FBMonitorHunter/data/facebook_cookies.json first, then workspace
    app_cookie = get_app_dir() / "data" / "facebook_cookies.json"
    if app_cookie.exists():
        try:
            with open(app_cookie, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
            
    ws_cookie = Path.cwd() / "facebook_cookies.json"
    if ws_cookie.exists():
        try:
            with open(ws_cookie, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def dismiss_popups(page: Page) -> None:
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    for sel in [
        'div[aria-label="Đóng"][role="button"]',
        'div[aria-label="Close"][role="button"]',
        'div[aria-label="Đóng"]',
        'div[role="dialog"] div[aria-label="Đóng"]',
    ]:
        try:
            loc = page.locator(sel)
            if loc.count() > 0:
                loc.first.click(timeout=500)
                break
        except Exception:
            pass

def check_fb_security_state(page: Page) -> str:
    """
    Checks if page has encountered checkpoint, captcha, or logout.
    Returns: 'ok' | 'checkpoint' | 'captcha' | 'logged_out'
    """
    url = page.url.lower()
    if "/checkpoint" in url:
        return "checkpoint"
    if "/login" in url or "login.php" in url:
        return "logged_out"
        
    try:
        content = page.content().lower()
        if "captcha" in content or "recaptcha" in content:
            return "captcha"
        if "tài khoản của bạn đã bị khóa" in content or "account locked" in content:
            return "checkpoint"
    except Exception:
        pass
    return "ok"

class ScraperEngine:
    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None

    def start(self):
        if self._playwright is not None:
            return
        self._playwright = sync_playwright().start()
        headless = get_setting("headless", True)
        self._browser = self._playwright.chromium.launch(
            headless=headless,
            args=["--disable-notifications", "--disable-blink-features=AutomationControlled"]
        )
        self._context = self._browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        cookies = load_cookies()
        if cookies:
            try:
                self._context.add_cookies(cookies)
            except Exception:
                pass

    def stop(self):
        if self._context:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    def scrape_group(self, group: dict, max_scrolls: int = 3) -> List[dict]:
        """
        Scrapes a single Facebook group.
        Updates AppState fb_status accordingly.
        """
        if not self._context:
            self.start()

        page = self._context.new_page()
        posts = []
        try:
            target_url = format_chronological_url(group["url"])
            page.goto(target_url, timeout=30000, wait_until="domcontentloaded")
            time.sleep(random.uniform(2.0, 3.5))

            # Detect Facebook status
            fb_stat = check_fb_security_state(page)
            state_manager.update(fb_status=fb_stat)
            if fb_stat != "ok":
                state_manager.set_error("scraper", f"Facebook status alert: {fb_stat}")
                state_manager.add_log("WARNING", f"Phát hiện trạng thái Facebook bất thường: {fb_stat}", "scraper")
                return []

            dismiss_popups(page)

            # Scroll loop
            for scroll_idx in range(max_scrolls):
                dismiss_popups(page)
                page.evaluate("window.scrollBy(0, 1000);")
                time.sleep(random.uniform(1.5, 2.5))

            # Extract posts using JS
            extracted = page.evaluate("""
            () => {
                const results = [];
                const articles = document.querySelectorAll('div[role="article"], div[role="feed"] > div');
                articles.forEach(art => {
                    let linkEl = art.querySelector('a[href*="/posts/"], a[href*="/permalink/"], a[href*="multi_permalinks="]');
                    if (!linkEl) return;
                    let rawHref = linkEl.getAttribute('href') || '';
                    let cleanUrl = rawHref.split('?')[0];
                    if (rawHref.startsWith('/')) cleanUrl = 'https://www.facebook.com' + cleanUrl;

                    let postId = '';
                    const m1 = cleanUrl.match(/posts\\/(\\d+)/);
                    const m2 = rawHref.match(/permalink\\/(\\d+)/);
                    const m3 = rawHref.match(/multi_permalinks=(\\d+)/);
                    if (m1) postId = m1[1];
                    else if (m2) postId = m2[1];
                    else if (m3) postId = m3[1];
                    if (!postId) return;

                    let authorName = 'Thành viên';
                    let authorUrl = '';
                    const userLink = art.querySelector('h2 a, h3 a, h4 a, a[role="link"]');
                    if (userLink && userLink.innerText.trim().length > 1) {
                        authorName = userLink.innerText.trim();
                        authorUrl = userLink.getAttribute('href') || '';
                    }

                    let content = art.innerText.trim();
                    let createdTime = linkEl.innerText.trim() || 'Vừa xong';

                    let mediaUrls = [];
                    art.querySelectorAll('img').forEach(img => {
                        let src = img.getAttribute('src');
                        if (src && src.includes('fbcdn.net') && !src.includes('emoji') && !src.includes('rsrc.php')) {
                            mediaUrls.push(src);
                        }
                    });

                    results.push({
                        post_id: postId,
                        post_url: cleanUrl,
                        author_name: authorName,
                        author_url: authorUrl,
                        content: content,
                        created_time: createdTime,
                        media_urls: mediaUrls
                    });
                });
                return results;
            }
            """)

            for item in extracted:
                item["group_name"] = group["name"]
                item["group_url"] = group["url"]
                posts.append(item)

        except Exception as e:
            state_manager.set_error("scraper", f"Lỗi cào nhóm {group['name']}: {str(e)}")
            state_manager.add_log("ERROR", f"Lỗi cào nhóm {group['name']}: {str(e)}", "scraper")
        finally:
            try:
                page.close()
            except Exception:
                pass

        return posts
