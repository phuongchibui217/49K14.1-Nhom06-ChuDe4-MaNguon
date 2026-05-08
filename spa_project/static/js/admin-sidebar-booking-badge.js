/**
 * Notification badge cho yêu cầu đặt lịch chờ xác nhận.
 * Dùng polling HTTP — không dùng WebSocket (không có route WS cho endpoint này).
 */
(function () {
    const config = window.adminSidebarBookingBadgeConfig;
    if (!config || !config.countUrl) return;

    const badge = document.getElementById("adminSidebarBookingBadge");
    if (!badge) return;

    let pollingTimer = null;

    function renderBadge(count) {
        const n = Math.max(0, Math.floor(Number(count) || 0));
        if (!n) {
            badge.textContent = "";
            badge.classList.add("d-none");
        } else {
            badge.textContent = n > 99 ? "99+" : String(n);
            badge.classList.remove("d-none");
            badge.setAttribute("aria-label", `${n} yêu cầu đặt lịch online chưa xử lý`);
        }
        window.dispatchEvent(new CustomEvent("booking-pending-count:update", { detail: { count: n } }));
    }

    async function fetchCount() {
        try {
            const res = await fetch(config.countUrl, { credentials: "same-origin" });
            if (!res.ok) return;
            const data = await res.json();
            if (data && data.success) renderBadge(data.count);
        } catch (_) { /* silent */ }
    }

    document.addEventListener("DOMContentLoaded", function () {
        fetchCount();
        pollingTimer = setInterval(fetchCount, 15000);
    });

    window.addEventListener("beforeunload", function () {
        if (pollingTimer) clearInterval(pollingTimer);
    });
})();
