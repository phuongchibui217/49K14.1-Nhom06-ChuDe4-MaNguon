/**
 * Notification Badge: Khieu nai moi chua xu ly
 *
 * Hien thi so luong khieu nai chua giai quyet.
 * Auto-update dinh ky qua HTTP polling de tranh giu ket noi SSE dai han.
 */
(function () {
    const config = window.adminSidebarComplaintsBadgeConfig;
    if (!config) return;

    const dom = {
        badge: document.getElementById('adminSidebarComplaintsBadge'),
    };
    if (!dom.badge) return;

    const state = {
        pollingTimer: null,
    };

    function normalizeCount(value) {
        const count = Number(value);
        return Number.isFinite(count) && count > 0 ? Math.floor(count) : 0;
    }

    function renderBadge(count) {
        const n = normalizeCount(count);
        if (!n) {
            dom.badge.textContent = '';
            dom.badge.classList.add('d-none');
            return;
        }
        dom.badge.textContent = n > 99 ? '99+' : String(n);
        dom.badge.classList.remove('d-none');
        dom.badge.setAttribute('aria-label', `${n} khieu nai chua giai quyet`);
        dom.badge.classList.add('badge-pulse');
        setTimeout(() => dom.badge.classList.remove('badge-pulse'), 500);
    }

    async function fetchCount() {
        try {
            const res = await fetch(config.countUrl, { credentials: 'same-origin' });
            const ct = res.headers.get('content-type') || '';
            if (!ct.includes('application/json')) return;
            const data = await res.json();
            if (data && data.success) renderBadge(data.count);
        } catch (_) {}
    }

    function disconnect() {
        if (state.pollingTimer) {
            clearInterval(state.pollingTimer);
            state.pollingTimer = null;
        }
    }

    function startPolling() {
        if (state.pollingTimer) return;
        fetchCount();
        state.pollingTimer = setInterval(fetchCount, 15000);
    }

    document.addEventListener('DOMContentLoaded', startPolling);
    window.addEventListener('beforeunload', disconnect);
})();
