(function () {
    const config = window.adminSidebarChatBadgeConfig;
    if (!config) {
        return;
    }

    const dom = {
        badge: document.getElementById("adminSidebarChatBadge"),
    };

    if (!dom.badge) {
        return;
    }

    const state = {
        stream: null,
        reconnectTimer: null,
    };

    function buildWebSocketUrl(path) {
        const protocol = window.location.protocol === "https:" ? "wss" : "ws";
        return `${protocol}://${window.location.host}${path}`;
    }

    function normalizeCount(value) {
        const count = Number(value);
        if (!Number.isFinite(count) || count <= 0) {
            return 0;
        }
        return Math.floor(count);
    }

    function formatCount(count) {
        return count > 99 ? "99+" : String(count);
    }

    function renderBadge(count) {
        const normalizedCount = normalizeCount(count);

        if (!normalizedCount) {
            dom.badge.textContent = "";
            dom.badge.classList.add("d-none");
            return;
        }

        dom.badge.textContent = formatCount(normalizedCount);
        dom.badge.classList.remove("d-none");
        dom.badge.setAttribute(
            "aria-label",
            `${normalizedCount} tin nhắn chat khách hàng chưa đọc`
        );
    }

    function disconnectStream() {
        if (state.stream) {
            state.stream.onclose = null;
            state.stream.close();
            state.stream = null;
        }

        if (state.reconnectTimer) {
            clearTimeout(state.reconnectTimer);
            state.reconnectTimer = null;
        }
    }

    function scheduleReconnect() {
        if (state.reconnectTimer) {
            return;
        }

        state.reconnectTimer = window.setTimeout(function () {
            state.reconnectTimer = null;
            connectStream();
        }, 3000);
    }

    function connectStream() {
        disconnectStream();

        const socket = new WebSocket(buildWebSocketUrl(config.sessionsSocketPath));
        state.stream = socket;

        socket.addEventListener("message", function (event) {
            try {
                const data = JSON.parse(event.data || "{}");
                if (data.event !== "sessions") {
                    return;
                }
                renderBadge(data.unreadTotal);
            } catch (error) {
                // Bỏ qua payload lỗi và chờ event tiếp theo.
            }
        });

        socket.addEventListener("close", function () {
            if (state.stream === socket) {
                state.stream = null;
            }
            scheduleReconnect();
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        connectStream();
    });

    window.addEventListener("beforeunload", disconnectStream);
})();
