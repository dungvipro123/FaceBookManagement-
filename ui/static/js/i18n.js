export const translations = {
    vi: {
        app_title: "FB Monitor Hunter v2.0",
        tagline: "Hệ thống săn kèo Facebook & định giá thông minh",
        tab_overview: "Tổng Quan",
        tab_groups: "Nhóm Theo Dõi",
        tab_channels: "Kênh Discord",
        tab_settings: "Cài Đặt Hệ Thống",
        status_idle: "Sẵn Sàng",
        status_scanning: "Đang Quét...",
        status_paused: "Đã Tạm Dừng",
        status_error: "Có Lỗi",
        scan_now: "Quét Ngay",
        pause_scan: "Tạm Dừng",
        resume_scan: "Tiếp Tục",
        test_quota: "Kiểm Tra AI",
        stat_total_posts: "Tổng Số Bài Cào",
        stat_total_deals: "Kèo Thơm Đã Bắn",
        stat_today_posts: "Bài Cào Hôm Nay",
        stat_active_groups: "Nhóm Đang Bật",
        recent_deals: "Kèo Thơm Mới Nhất",
        live_logs: "Nhật Ký Thời Gian Thực",
        clear_logs: "Xóa log",
        auto_scroll: "Tự cuộn",
        add_group: "+ Thêm Nhóm Mới",
        save: "Lưu Thay Đổi",
        test_webhook: "Kiểm Tra Webhook",
        save_secrets: "Lưu Khóa Bí Mật",
        rotate_pin: "Đổi Mã PIN Mới",
        save_settings: "Lưu Cài Đặt",
        restart_server: "Khởi Động Lại Server"
    },
    en: {
        app_title: "FB Monitor Hunter v2.0",
        tagline: "Facebook Deal Hunter & AI Valuation Engine",
        tab_overview: "Overview",
        tab_groups: "Monitored Groups",
        tab_channels: "Discord Channels",
        tab_settings: "System Settings",
        status_idle: "Ready / Idle",
        status_scanning: "Scanning...",
        status_paused: "Paused",
        status_error: "Error Alert",
        scan_now: "Scan Now",
        pause_scan: "Pause",
        resume_scan: "Resume",
        test_quota: "Test AI Quota",
        stat_total_posts: "Total Posts",
        stat_total_deals: "Dispatched Deals",
        stat_today_posts: "Today's Posts",
        stat_active_groups: "Active Groups",
        recent_deals: "Recent Hot Deals",
        live_logs: "Realtime Activity Logs",
        clear_logs: "Clear logs",
        auto_scroll: "Auto scroll",
        add_group: "+ Add New Group",
        save: "Save Changes",
        test_webhook: "Test Webhook",
        save_secrets: "Save Secrets",
        rotate_pin: "Rotate LAN PIN",
        save_settings: "Save Settings",
        restart_server: "Restart Server"
    }
};

let currentLang = localStorage.getItem("fb_hunter_lang") || "vi";

export function getLang() {
    return currentLang;
}

export function setLang(lang) {
    if (translations[lang]) {
        currentLang = lang;
        localStorage.setItem("fb_hunter_lang", lang);
        applyTranslations();
    }
}

export function t(key) {
    return translations[currentLang]?.[key] || translations["vi"]?.[key] || key;
}

export function applyTranslations() {
    document.querySelectorAll("[data-i18n]").forEach(el => {
        const key = el.getAttribute("data-i18n");
        if (key && translations[currentLang]?.[key]) {
            el.textContent = translations[currentLang][key];
        }
    });
}
