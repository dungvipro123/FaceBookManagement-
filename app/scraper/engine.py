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
    # Check multiple possible locations for cookies
    candidate_paths = [
        get_app_dir() / "data" / "facebook_cookies.json",
        get_app_dir() / "data" / "cookies.json",
        Path.cwd() / "cookies.json",
        Path.cwd() / "facebook_cookies.json"
    ]
    for p in candidate_paths:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    cookies = json.load(f)
                    if isinstance(cookies, list) and cookies:
                        return cookies
            except Exception:
                pass
    return []

def dismiss_fb_popups(page: Page) -> None:
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass

    close_selectors = [
        'div[aria-label="Đóng"][role="button"]',
        'div[aria-label="Close"][role="button"]',
        'div[aria-label="Đóng"]',
        'div[aria-label="Close"]',
        'div[role="dialog"] div[aria-label="Đóng"]',
        'div[role="dialog"] div[aria-label="Close"]',
        'div[role="dialog"] svg',
    ]
    for sel in close_selectors:
        try:
            loc = page.locator(sel)
            if loc.count() > 0:
                loc.first.click(timeout=600)
                break
        except Exception:
            pass

def expand_see_more(page: Page) -> None:
    try:
        see_more_buttons = page.locator('div[role="button"]:has-text("Xem thêm"), span:has-text("Xem thêm"), div[role="button"]:has-text("See more"), span:has-text("See more")')
        count = see_more_buttons.count()
        for i in range(min(count, 5)):
            try:
                btn = see_more_buttons.nth(i)
                if btn.is_visible():
                    btn.click(timeout=400)
            except Exception:
                continue
    except Exception:
        pass

def check_fb_security_state(page: Page) -> str:
    """
    Checks if page has encountered hard blocking checkpoint.
    Avoids false positives from minified JavaScript bundles containing captcha keywords.
    """
    url = page.url.lower()
    if "/checkpoint/" in url:
        return "checkpoint"
    return "ok"

class ScraperEngine:
    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._has_cookies = False

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
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="vi-VN",
            timezone_id="Asia/Ho_Chi_Minh"
        )
        cookies = load_cookies()
        if cookies:
            try:
                self._context.add_cookies(cookies)
                self._has_cookies = True
                state_manager.add_log("INFO", f"Đã nạp {len(cookies)} cookies phiên Facebook.", "scraper")
            except Exception:
                self._has_cookies = False
        else:
            self._has_cookies = False
            state_manager.add_log("INFO", "Không tìm thấy cookies. Đang quét nhóm công khai ở chế độ Khách (Guest Mode).", "scraper")

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
        Handles both logged-in sessions and public guest mode.
        """
        if not self._context:
            self.start()

        page = self._context.new_page()
        posts = []
        try:
            target_url = format_chronological_url(group["url"])
            page.goto(target_url, timeout=35000, wait_until="domcontentloaded")
            time.sleep(random.uniform(2.5, 3.5))

            # Detect Facebook checkpoint status
            fb_stat = check_fb_security_state(page)
            if fb_stat != "ok":
                state_manager.update(fb_status=fb_stat)
                state_manager.set_error("scraper", f"Facebook alert: {fb_stat}")
                state_manager.add_log("WARNING", f"Phát hiện trạng thái Facebook bất thường: {fb_stat}", "scraper")
                return []
            else:
                state_manager.update(fb_status="ok")

            dismiss_fb_popups(page)

            # Scroll loop
            for scroll_idx in range(max_scrolls):
                dismiss_fb_popups(page)
                expand_see_more(page)
                page.evaluate("window.scrollBy(0, 1000);")
                time.sleep(random.uniform(1.5, 2.5))

            dismiss_fb_popups(page)
            expand_see_more(page)

            # Extract posts using full robust JS evaluator
            js_code = """
            () => {
                const posts = [];
                const articles = document.querySelectorAll('div[role="article"], div[role="feed"] > div');
                
                articles.forEach(art => {
                    let postLinkEl = art.querySelector('a[href*="/posts/"], a[href*="/permalink/"], a[href*="multi_permalinks="]');
                    if (!postLinkEl) return;
                    
                    const rawHref = postLinkEl.getAttribute('href') || '';
                    let cleanPostUrl = rawHref.split('?')[0];
                    if (rawHref.startsWith('/')) cleanPostUrl = 'https://www.facebook.com' + cleanPostUrl;

                    let postId = '';
                    const m1 = cleanPostUrl.match(/posts\\/(\\d+)/);
                    const m2 = rawHref.match(/permalink\\/(\\d+)/);
                    const m3 = rawHref.match(/multi_permalinks=(\\d+)/);
                    if (m1) postId = m1[1];
                    else if (m2) postId = m2[1];
                    else if (m3) postId = m3[1];
                    if (!postId) return;

                    let authorName = '';
                    let authorUrl = '';
                    const headerEl = art.querySelector('h2, h3, h4, [role="heading"]');
                    const headerText = headerEl ? headerEl.innerText.trim() : '';
                    if (headerText.includes('Người tham gia ẩn danh') || headerText.includes('Thành viên ẩn danh') || headerText.includes('Anonymous participant')) {
                        authorName = 'Thành viên ẩn danh';
                    } else {
                        const userLink = art.querySelector('h2 a[href*="/user/"], h3 a[href*="/user/"], h4 a[href*="/user/"], a[href*="/user/"], a[href*="profile.php"]');
                        if (userLink && userLink.innerText.trim().length > 1) {
                            authorName = userLink.innerText.trim();
                            const rawH = userLink.getAttribute('href') || '';
                            authorUrl = rawH.startsWith('/') ? 'https://www.facebook.com' + rawH.split('?')[0] : rawH.split('?')[0];
                        }
                        if (!authorName && headerEl) {
                            const links = headerEl.querySelectorAll('a');
                            for (let l of links) {
                                const href = l.getAttribute('href') || '';
                                const txt = l.innerText.trim();
                                if (txt && !href.includes('/posts/') && !href.includes('/permalink/') && txt !== 'Facebook' && txt.length > 1) {
                                    authorName = txt;
                                    authorUrl = href.startsWith('/') ? 'https://www.facebook.com' + href.split('?')[0] : href.split('?')[0];
                                    break;
                                }
                            }
                        }
                    }
                    if (!authorName) authorName = 'Thành viên';

                    let createdTime = postLinkEl.innerText.trim() || 'Vừa xong';

                    // Extract content
                    let content = '';
                    const messageContainers = art.querySelectorAll('div[dir="auto"]');
                    const contentParts = [];
                    messageContainers.forEach(div => {
                        const txt = div.innerText.trim();
                        if (txt && txt !== authorName && txt !== createdTime && txt !== 'Thích' && txt !== 'Bình luận' && txt !== 'Chia sẻ') {
                            let isDup = false;
                            for (let ex of contentParts) {
                                if (ex.includes(txt) || txt.includes(ex)) {
                                    isDup = true;
                                    break;
                                }
                            }
                            if (!isDup && txt.length > 5) {
                                contentParts.push(txt);
                            }
                        }
                    });
                    content = contentParts.join('\\n').trim();

                    // Media URLs
                    const mediaUrls = [];
                    art.querySelectorAll('img').forEach(img => {
                        const src = img.getAttribute('src') || '';
                        const width = img.naturalWidth || img.width || 0;
                        if (src.includes('fbcdn.net') && !src.includes('/static.xx/') && width > 120) {
                            if (!mediaUrls.includes(src)) mediaUrls.push(src);
                        }
                    });

                    posts.push({
                        post_id: postId,
                        author_name: authorName,
                        author_url: authorUrl,
                        post_url: cleanPostUrl,
                        created_time: createdTime,
                        content: content,
                        media_urls: mediaUrls
                    });
                });
                return posts;
            }
            """
            extracted = page.evaluate(js_code)
            clean_group_base = group["url"].split("?")[0].rstrip("/")
            seen_ids = set()

            for item in extracted:
                pid = item.get("post_id")
                if pid and pid not in seen_ids:
                    seen_ids.add(pid)
                    item["group_name"] = group["name"]
                    item["group_url"] = group["url"]
                    item["post_url"] = f"{clean_group_base}/posts/{pid}/"
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
