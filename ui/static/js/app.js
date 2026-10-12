import { initBackground, initStatusCore, updateCoreHealth, triggerDealBurst } from "./scene3d.js";
import { t, setLang, getLang, applyTranslations } from "./i18n.js";

let eventSource = null;
let isAutoScroll = true;
let currentState = {};

document.addEventListener("DOMContentLoaded", () => {
    // 1. Initialize 3D Scenes
    initBackground(document.getElementById("bg-canvas"));
    initStatusCore(document.getElementById("core-canvas"));

    // 2. Setup Tabs
    setupTabs();

    // 3. Connect SSE Stream
    connectSSE();

    // 4. Initial REST Fetches
    fetchStatus();
    fetchDeals();
    fetchGroups();
    fetchChannels();
    fetchSettings();

    // 5. Setup Action Listeners
    setupActions();
    setupLanguageToggle();
});

function setupTabs() {
    document.querySelectorAll(".tab-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
            document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));
            btn.classList.add("active");
            const targetId = btn.getAttribute("data-tab");
            const targetPane = document.getElementById(targetId);
            if (targetPane) targetPane.classList.add("active");
        });
    });
}

function connectSSE() {
    if (eventSource) {
        eventSource.close();
    }
    eventSource = new EventSource("/api/logs/stream");

    eventSource.addEventListener("init", (e) => {
        try {
            const data = JSON.parse(e.data);
            if (data.replay_logs) {
                const term = document.getElementById("terminal-logs");
                term.innerHTML = "";
                data.replay_logs.forEach(appendLog);
            }
            if (data.state) {
                applyState(data.state);
            }
        } catch (err) {
            console.error("Init SSE error:", err);
        }
    });

    eventSource.addEventListener("log", (e) => {
        try {
            const logData = JSON.parse(e.data);
            appendLog(logData);
        } catch (err) {}
    });

    eventSource.addEventListener("status", (e) => {
        try {
            const stateData = JSON.parse(e.data);
            applyState(stateData);
        } catch (err) {}
    });

    eventSource.addEventListener("progress", (e) => {
        try {
            const prog = JSON.parse(e.data);
            updateProgress(prog);
        } catch (err) {}
    });

    eventSource.addEventListener("deal", (e) => {
        try {
            const deal = JSON.parse(e.data);
            prependDeal(deal);
            triggerDealBurst();
            incrementStat("stat-deals");
        } catch (err) {}
    });

    eventSource.onerror = () => {
        // SSE reconnects automatically
    };
}

function appendLog(log) {
    const term = document.getElementById("terminal-logs");
    if (!term) return;

    const row = document.createElement("div");
    row.className = "log-row";
    const time = (log.timestamp || "").split("T")[1]?.slice(0, 8) || "";
    row.innerHTML = `
        <span class="log-time">[${time}]</span>
        <span class="log-level ${log.level}">${log.level}</span>
        <span class="log-msg">${log.message}</span>
    `;
    term.appendChild(row);

    if (isAutoScroll) {
        term.scrollTop = term.scrollHeight;
    }
}

function applyState(state) {
    currentState = state;
    const healthBadge = document.getElementById("health-badge");
    const healthText = document.getElementById("health-text");
    const coreStatus = document.getElementById("core-status-title");
    const coreDesc = document.getElementById("core-status-desc");

    const color = state.health_color || "amber";
    healthBadge.className = `health-badge ${color}`;
    updateCoreHealth(color);

    if (state.status === "error") {
        healthText.textContent = t("status_error");
        coreStatus.textContent = "CẢNH BÁO";
        coreDesc.textContent = state.last_error?.message || "Phát hiện lỗi an ninh hoặc hạn mức";
    } else if (state.status === "scanning") {
        healthText.textContent = t("status_scanning");
        coreStatus.textContent = "ĐANG QUÉT BÀI...";
        coreDesc.textContent = state.current_group ? `Nhóm: ${state.current_group}` : "Đang kiểm tra nhóm";
    } else if (state.status === "paused") {
        healthText.textContent = t("status_paused");
        coreStatus.textContent = "TẠM DỪNG";
        coreDesc.textContent = "Hệ thống đang ở trạng thái nghỉ";
    } else {
        healthText.textContent = t("status_idle");
        coreStatus.textContent = "SẴN SÀNG";
        coreDesc.textContent = "Hệ thống hoạt động bình thường";
    }

    // Update stats counters
    if (state.total_posts !== undefined) setStat("stat-posts", state.total_posts);
    if (state.total_deals !== undefined) setStat("stat-deals", state.total_deals);
    if (state.today_posts !== undefined) setStat("stat-today", state.today_posts);
    if (state.active_groups_count !== undefined) setStat("stat-groups", state.active_groups_count);

    // Update pause/resume button text
    const pauseBtn = document.getElementById("btn-pause");
    if (pauseBtn) {
        pauseBtn.textContent = state.is_paused ? t("resume_scan") : t("pause_scan");
        pauseBtn.className = state.is_paused ? "btn btn-primary" : "btn btn-warning";
    }
}

function setStat(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
}

function incrementStat(id) {
    const el = document.getElementById(id);
    if (el) el.textContent = parseInt(el.textContent || "0") + 1;
}

function updateProgress(prog) {
    const coreDesc = document.getElementById("core-status-desc");
    if (coreDesc) {
        coreDesc.textContent = `[${prog.current_index}/${prog.total_groups}] ${prog.current_group} (${prog.percent}%)`;
    }
}

function prependDeal(deal) {
    const list = document.getElementById("deals-list");
    if (!list) return;

    const item = document.createElement("div");
    item.className = "deal-item";
    const isDealer = deal.is_dealer;
    const badgeClass = isDealer ? "dealer" : "user";
    const badgeText = isDealer ? "Thợ / Shop" : "Người dùng";
    const priceStr = (deal.deal_price || 0).toLocaleString("vi-VN") + " đ";
    const profitStr = "+" + (deal.profit || 0).toLocaleString("vi-VN") + " đ";

    item.innerHTML = `
        <img class="deal-thumb" src="${deal.thumbnail_url || 'data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><rect fill=%22%231e293b%22 width=%22100%22 height=%22100%22/><text fill=%22%2364748b%22 font-size=%2220%22 x=%2225%22 y=%2255%22>IMG</text></svg>'}" alt="Thumb" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><rect fill=%22%231e293b%22 width=%22100%22 height=%22100%22/><text fill=%22%2364748b%22 font-size=%2220%22 x=%2225%22 y=%2255%22>IMG</text></svg>'">
        <div class="deal-content">
            <div class="deal-header">
                <span class="deal-title">${deal.product_name}</span>
                <span class="deal-badge ${badgeClass}">${badgeText}</span>
            </div>
            <div class="deal-meta">
                <span>👤 ${deal.author_name}</span> • <span>${deal.created_time || 'Vừa xong'}</span>
            </div>
            <div class="deal-prices">
                <span class="price-deal">💰 ${priceStr}</span>
                <span class="price-profit">📈 Lãi ${profitStr} (${deal.discount_pct}%)</span>
                <a href="${deal.post_url}" target="_blank" style="margin-left:auto;color:#06B6D4;text-decoration:none;font-weight:600;">Xem bài ↗</a>
            </div>
        </div>
    `;
    list.insertBefore(item, list.firstChild);
}

// REST API calls
async function fetchStatus() {
    try {
        const res = await fetch("/api/status");
        const json = await res.json();
        if (json.success) applyState(json.data);
    } catch (e) {}
}

async function fetchDeals() {
    try {
        const res = await fetch("/api/deals?limit=15");
        const json = await res.json();
        if (json.success && json.data.deals) {
            const list = document.getElementById("deals-list");
            list.innerHTML = "";
            json.data.deals.forEach(d => {
                prependDeal({
                    product_name: d.model || "Màn hình PC",
                    deal_price: d.deal_price,
                    market_price: d.market_price,
                    discount_pct: d.discount_pct,
                    profit: d.profit,
                    is_dealer: d.is_dealer,
                    author_name: d.author_name,
                    post_url: d.post_url,
                    thumbnail_url: d.thumbnail_url,
                    created_time: d.created_time
                });
            });
        }
    } catch (e) {}
}

async function fetchGroups() {
    try {
        const res = await fetch("/api/groups");
        const json = await res.json();
        if (json.success) {
            const tbody = document.getElementById("groups-tbody");
            tbody.innerHTML = "";
            json.data.forEach(g => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td style="padding:12px;font-weight:600;">${g.name}</td>
                    <td style="padding:12px;"><a href="${g.url}" target="_blank" style="color:#06B6D4;text-decoration:none;">${g.url.slice(0, 38)}...</a></td>
                    <td style="padding:12px;text-align:center;"><span style="padding:2px 8px;border-radius:999px;background:rgba(255,255,255,0.1);">${g.priority}</span></td>
                    <td style="padding:12px;text-align:center;">
                        <button class="btn btn-outline" style="padding:4px 10px;font-size:12px;" onclick="toggleGroup(${g.id})">${g.is_active ? '✅ Bật' : '⏸️ Tắt'}</button>
                    </td>
                    <td style="padding:12px;text-align:center;">
                        <button class="btn btn-danger" style="padding:4px 10px;font-size:12px;" onclick="deleteGroup(${g.id})">Xóa</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        }
    } catch (e) {}
}

window.toggleGroup = async function(id) {
    try {
        await fetch(`/api/groups/${id}/toggle`, { method: "PATCH" });
        fetchGroups();
    } catch (e) {}
};

window.deleteGroup = async function(id) {
    if (!confirm("Bạn có chắc muốn xóa nhóm này khỏi danh sách theo dõi?")) return;
    try {
        await fetch(`/api/groups/${id}`, { method: "DELETE" });
        fetchGroups();
    } catch (e) {}
};

async function fetchChannels() {
    try {
        const res = await fetch("/api/channels");
        const json = await res.json();
        if (json.success) {
            const container = document.getElementById("channels-container");
            container.innerHTML = "";
            json.data.forEach(c => {
                const card = document.createElement("div");
                card.className = "card";
                card.style.marginBottom = "16px";
                card.innerHTML = `
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
                        <h3 style="font-size:16px;">${c.name} (${c.channel_key})</h3>
                        <label class="toggle-switch">
                            <span class="switch"><input type="checkbox" id="chan-${c.channel_key}-enabled" ${c.is_enabled ? 'checked' : ''}><span class="slider"></span></span>
                        </label>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Discord Webhook URL</label>
                        <input type="text" class="form-control" id="chan-${c.channel_key}-wh" placeholder="https://discord.com/api/webhooks/..." value="${c.webhook_url_masked || ''}">
                    </div>
                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
                        <div class="form-group">
                            <label class="form-label">Ngưỡng Giảm Giá Tối Thiểu (%)</label>
                            <input type="number" class="form-control" id="chan-${c.channel_key}-min" min="0" max="99" value="${c.min_discount}">
                        </div>
                        <div class="form-group">
                            <label class="form-label">Mention Tag (@everyone, @here)</label>
                            <input type="text" class="form-control" id="chan-${c.channel_key}-tag" value="${c.mention_tag || ''}">
                        </div>
                    </div>
                    <div style="display:flex;gap:10px;margin-top:10px;">
                        <button class="btn btn-primary" onclick="saveChannel('${c.channel_key}')">Lưu Kênh</button>
                        <button class="btn btn-outline" onclick="testChannel('${c.channel_key}')">Test Webhook</button>
                    </div>
                `;
                container.appendChild(card);
            });
        }
    } catch (e) {}
}

window.saveChannel = async function(key) {
    const isEnabled = document.getElementById(`chan-${key}-enabled`).checked;
    const whVal = document.getElementById(`chan-${key}-wh`).value.trim();
    const minVal = parseFloat(document.getElementById(`chan-${key}-min`).value);
    const tagVal = document.getElementById(`chan-${key}-tag`).value.trim();

    const payload = {
        is_enabled: isEnabled,
        min_discount: minVal,
        mention_tag: tagVal
    };
    if (whVal && !whVal.includes("••••••••")) {
        payload.webhook_url = whVal;
    }

    try {
        const res = await fetch(`/api/channels/${key}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const json = await res.json();
        if (json.success) {
            alert(`Đã lưu cấu hình kênh ${key} thành công!`);
            fetchChannels();
        } else {
            alert("Lỗi: " + json.error.message);
        }
    } catch (e) {
        alert("Lỗi kết nối");
    }
};

window.testChannel = async function(key) {
    try {
        const res = await fetch(`/api/channels/${key}/test`, { method: "POST" });
        const json = await res.json();
        if (json.success) {
            alert(json.data.message);
        } else {
            alert("Lỗi: " + json.error.message);
        }
    } catch (e) {
        alert("Lỗi kết nối kiểm tra webhook");
    }
};

async function fetchSettings() {
    try {
        const res = await fetch("/api/settings");
        const json = await res.json();
        if (json.success) {
            const data = json.data;
            if (data.scan_interval_minutes) document.getElementById("set-interval").value = data.scan_interval_minutes.value;
            if (data.headless) document.getElementById("set-headless").checked = data.headless.value;
            if (data.gemini_model) document.getElementById("set-model").value = data.gemini_model.value;
            if (data.lan_access_enabled) document.getElementById("set-lan").checked = data.lan_access_enabled.value;
            if (data.web_port) document.getElementById("set-port").value = data.web_port.value;
            if (data.autostart) document.getElementById("set-autostart").checked = data.autostart.value;

            if (data.secrets) {
                document.getElementById("sec-gemini").value = data.secrets.GEMINI_API_KEY || "";
                document.getElementById("sec-discord-token").value = data.secrets.DISCORD_BOT_TOKEN || "";
            }
        }
    } catch (e) {}
}

function setupActions() {
    document.getElementById("btn-scan")?.addEventListener("click", async () => {
        const res = await fetch("/api/actions/scan-now", { method: "POST" });
        const json = await res.json();
        if (json.success) {
            alert(json.data.message);
        } else {
            alert("Lỗi: " + json.error.message);
        }
    });

    document.getElementById("btn-pause")?.addEventListener("click", async () => {
        const endpoint = currentState.is_paused ? "/api/actions/resume" : "/api/actions/pause";
        await fetch(endpoint, { method: "POST" });
        fetchStatus();
    });

    document.getElementById("btn-test-quota")?.addEventListener("click", async () => {
        const res = await fetch("/api/actions/test-quota", { method: "POST" });
        const json = await res.json();
        if (json.success) {
            alert(`Kết quả kiểm tra AI: [${json.data.status}] ${json.data.latency_ms ? json.data.latency_ms + 'ms' : json.data.message}`);
        }
    });

    document.getElementById("btn-clear-logs")?.addEventListener("click", () => {
        document.getElementById("terminal-logs").innerHTML = "";
    });

    document.getElementById("chk-autoscroll")?.addEventListener("change", (e) => {
        isAutoScroll = e.target.checked;
    });

    // Add group form
    document.getElementById("form-add-group")?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const name = document.getElementById("group-name").value.trim();
        const url = document.getElementById("group-url").value.trim();
        const priority = parseInt(document.getElementById("group-priority").value);

        const res = await fetch("/api/groups", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name, url, priority })
        });
        const json = await res.json();
        if (json.success) {
            alert("Đã thêm nhóm thành công!");
            document.getElementById("form-add-group").reset();
            fetchGroups();
        } else {
            alert("Lỗi: " + json.error.message);
        }
    });

    // Save System Settings
    document.getElementById("btn-save-settings")?.addEventListener("click", async () => {
        const payload = {
            scan_interval_minutes: parseInt(document.getElementById("set-interval").value),
            headless: document.getElementById("set-headless").checked,
            gemini_model: document.getElementById("set-model").value.trim(),
            lan_access_enabled: document.getElementById("set-lan").checked,
            web_port: parseInt(document.getElementById("set-port").value),
            autostart: document.getElementById("set-autostart").checked
        };
        const res = await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const json = await res.json();
        if (json.success) {
            if (json.data.requires_restart) {
                alert("Đã lưu cài đặt! Cần khởi động lại ứng dụng để áp dụng đổi Cổng hoặc Mạng LAN.");
            } else {
                alert("Đã lưu cài đặt thành công!");
            }
        }
    });

    // Save Secrets
    document.getElementById("btn-save-secrets")?.addEventListener("click", async () => {
        const gemini = document.getElementById("sec-gemini").value.trim();
        const discord = document.getElementById("sec-discord-token").value.trim();
        const payload = {};
        if (gemini && !gemini.includes("••••••••")) payload.gemini_api_key = gemini;
        if (discord && !discord.includes("••••••••")) payload.discord_bot_token = discord;

        const res = await fetch("/api/secrets", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const json = await res.json();
        if (json.success) {
            alert("Đã lưu khóa bảo mật vào .env thành công!");
            fetchSettings();
        }
    });

    // Rotate PIN
    document.getElementById("btn-rotate-pin")?.addEventListener("click", async () => {
        if (!confirm("Xoay vòng PIN sẽ hủy toàn bộ các phiên đăng nhập LAN hiện có. Tiếp tục?")) return;
        const res = await fetch("/api/auth/rotate-pin", { method: "POST" });
        const json = await res.json();
        if (json.success) {
            alert(`MÃ PIN MỚI CỦA BẠN LÀ: ${json.data.pin}\n(Hãy lưu lại ngay, mã này chỉ hiển thị một lần duy nhất!)`);
        } else {
            alert("Lỗi: " + json.error.message);
        }
    });

    // Restart server
    document.getElementById("btn-restart-server")?.addEventListener("click", async () => {
        const res = await fetch("/api/actions/restart-server", { method: "POST" });
        const json = await res.json();
        if (json.success) {
            alert(json.data.message);
        }
    });
}

function setupLanguageToggle() {
    const langBtn = document.getElementById("btn-lang");
    if (!langBtn) return;
    langBtn.textContent = getLang().toUpperCase();
    langBtn.addEventListener("click", () => {
        const nextLang = getLang() === "vi" ? "en" : "vi";
        setLang(nextLang);
        langBtn.textContent = nextLang.toUpperCase();
        applyTranslations();
        fetchStatus();
    });
}
