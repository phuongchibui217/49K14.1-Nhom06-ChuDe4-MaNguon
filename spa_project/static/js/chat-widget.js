(function () {
    const config = window.chatWidgetConfig;
    if (!config) {
        return;
    }

    const STORAGE_KEYS = {
        guestKey: "spa_ana_guest_chat_key",
    };

    const state = {
        isOpen: false,
        isBootstrapped: false,
        session: null,
        guestKey: sessionStorage.getItem(STORAGE_KEYS.guestKey) || "",
        messageIds: new Set(),
        unreadCount: 0,
        stream: null,
        reconnectTimer: null,
        bootstrapPromise: null,
        resolveBootstrap: null,
        rejectBootstrap: null,
    };

    const dom = {
        widget: document.getElementById("chatWidgetContainer"),
        warning: document.getElementById("chatGuestWarning"),
        messages: document.getElementById("chatMessages"),
        emptyState: document.getElementById("chatEmptyState"),
        form: document.getElementById("chatForm"),
        input: document.getElementById("chatInput"),
        sendBtn: document.getElementById("chatSendBtn"),
        error: document.getElementById("chatErrorMessage"),
        floatingBadge: document.getElementById("chatFloatingBadge"),
    };

    function buildWebSocketUrl(path, params) {
        const protocol = window.location.protocol === "https:" ? "wss" : "ws";
        const queryString = params && params.toString() ? `?${params.toString()}` : "";
        return `${protocol}://${window.location.host}${path}${queryString}`;
    }

    function escapeHtml(value) {
        const div = document.createElement("div");
        div.textContent = value || "";
        return div.innerHTML;
    }

    function escapeSelectorValue(value) {
        if (window.CSS && typeof window.CSS.escape === "function") {
            return window.CSS.escape(value);
        }
        return String(value || "").replace(/\\/g, "\\\\").replace(/"/g, '\\"');
    }

    function formatTime(value) {
        if (!value) {
            return "";
        }

        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return "";
        }

        return date.toLocaleTimeString("vi-VN", {
            hour: "2-digit",
            minute: "2-digit",
        });
    }

    function formatFileSize(size) {
        const value = Number(size || 0);
        if (!value) {
            return "";
        }

        if (value >= 1024 * 1024) {
            return `${(value / (1024 * 1024)).toFixed(1)} MB`;
        }

        return `${Math.ceil(value / 1024)} KB`;
    }

    function hasOpenStream() {
        return !!state.stream && state.stream.readyState === WebSocket.OPEN;
    }

    function hasPendingStream() {
        return !!state.stream && (
            state.stream.readyState === WebSocket.OPEN
            || state.stream.readyState === WebSocket.CONNECTING
        );
    }

    function createBootstrapPromise() {
        state.bootstrapPromise = new Promise((resolve, reject) => {
            state.resolveBootstrap = resolve;
            state.rejectBootstrap = reject;
        });
        return state.bootstrapPromise;
    }

    function resolveBootstrap(data) {
        if (state.resolveBootstrap) {
            state.resolveBootstrap(data);
        }
        state.bootstrapPromise = null;
        state.resolveBootstrap = null;
        state.rejectBootstrap = null;
    }

    function rejectBootstrap(error) {
        if (state.rejectBootstrap) {
            state.rejectBootstrap(error);
        }
        state.bootstrapPromise = null;
        state.resolveBootstrap = null;
        state.rejectBootstrap = null;
    }

    function setErrorMessage(message) {
        if (!message) {
            dom.error.classList.add("d-none");
            dom.error.textContent = config.sendErrorMessage;
            return;
        }

        dom.error.textContent = message;
        dom.error.classList.remove("d-none");
    }

    function autoResizeInput() {
        dom.input.style.height = "52px";
        dom.input.style.height = `${Math.min(dom.input.scrollHeight, 132)}px`;
    }

    function updateSendButtonState() {
        dom.sendBtn.disabled = !dom.input.value.trim();
    }

    function clearGuestStorage() {
        sessionStorage.removeItem(STORAGE_KEYS.guestKey);
        state.guestKey = "";
    }

    function persistGuestStorage() {
        if (config.isAuthenticated) {
            clearGuestStorage();
            return;
        }

        if (state.guestKey) {
            sessionStorage.setItem(STORAGE_KEYS.guestKey, state.guestKey);
            return;
        }

        sessionStorage.removeItem(STORAGE_KEYS.guestKey);
    }

    function updateFloatingBadge() {
        if (!dom.floatingBadge) {
            return;
        }

        if (state.unreadCount > 0) {
            dom.floatingBadge.textContent = state.unreadCount > 9 ? "9+" : String(state.unreadCount);
            dom.floatingBadge.classList.remove("d-none");
        } else {
            dom.floatingBadge.textContent = "";
            dom.floatingBadge.classList.add("d-none");
        }
    }

    function renderWarning(message) {
        if (!config.isAuthenticated) {
            dom.warning.querySelector("span").textContent = message || config.guestWarningMessage;
            dom.warning.classList.remove("d-none");
        } else {
            dom.warning.classList.add("d-none");
        }
    }

    function buildAttachmentHtml(message) {
        if (!message.attachmentUrl) {
            return "";
        }

        if (message.isImage) {
            return `
                <div class="chat-attachment">
                    <a href="${message.attachmentUrl}" target="_blank" rel="noopener noreferrer">
                        <img src="${message.attachmentUrl}" alt="${escapeHtml(message.attachmentName || "Hình ảnh")}">
                    </a>
                </div>
            `;
        }

        return `
            <div class="chat-attachment">
                <a
                    class="chat-attachment-file"
                    href="${message.attachmentUrl}"
                    target="_blank"
                    rel="noopener noreferrer"
                >
                    <i class="fas fa-file-alt"></i>
                    <span>${escapeHtml(message.attachmentName || "Tệp đính kèm")}</span>
                    <small>${escapeHtml(formatFileSize(message.attachmentSize))}</small>
                </a>
            </div>
        `;
    }

    function buildMessageHtml(message, deliveryState) {
        const senderClass = message.senderType === "customer"
            ? "customer"
            : message.senderType === "system"
                ? "system"
                : "admin";

        const displayName = message.senderType === "customer"
            ? "Bạn"
            : senderClass === "admin"
                ? "Nhân viên"
                : message.senderName || "Spa ANA";

        const headerHtml = senderClass === "system"
            ? ""
            : `
                <div class="chat-message-header">
                    <span class="chat-message-name">${escapeHtml(displayName)}</span>
                    <span class="chat-message-time">${escapeHtml(message.timeLabel || formatTime(message.createdAt))}</span>
                </div>
            `;

        const deliveryHtml = message.senderType === "customer" && deliveryState
            ? `<div class="chat-message-status">${escapeHtml(deliveryState)}</div>`
            : "";

        return `
            <div class="chat-message ${senderClass}" data-message-id="${escapeHtml(message.id)}">
                ${headerHtml}
                ${message.content ? `<div class="chat-message-body">${escapeHtml(message.content)}</div>` : ""}
                ${buildAttachmentHtml(message)}
                ${deliveryHtml}
            </div>
        `;
    }

    function scrollMessagesToBottom() {
        dom.messages.scrollTop = dom.messages.scrollHeight;
    }

    function renderMessages(messages) {
        state.messageIds = new Set(
            messages
                .map((message) => Number(message.id))
                .filter((id) => Number.isFinite(id) && id > 0)
        );

        if (!messages.length) {
            dom.messages.innerHTML = "";
            dom.messages.appendChild(dom.emptyState);
            dom.emptyState.classList.remove("d-none");
            return;
        }

        dom.messages.innerHTML = messages
            .map((message) => buildMessageHtml(message, message.senderType === "customer" ? "Đã gửi" : ""))
            .join("");
        scrollMessagesToBottom();
    }

    function appendMessage(message, deliveryState) {
        const numericId = Number(message.id);
        if (Number.isFinite(numericId) && numericId > 0 && state.messageIds.has(numericId)) {
            return;
        }

        if (Number.isFinite(numericId) && numericId > 0) {
            state.messageIds.add(numericId);
        }

        if (dom.emptyState.parentNode === dom.messages) {
            dom.messages.innerHTML = "";
        }

        dom.messages.insertAdjacentHTML("beforeend", buildMessageHtml(message, deliveryState));
        scrollMessagesToBottom();
    }

    function updatePendingMessage(pendingId, message, deliveryState, failed) {
        const selector = `[data-message-id="${escapeSelectorValue(pendingId)}"]`;
        const element = dom.messages.querySelector(selector);
        if (!element) {
            appendMessage(message, deliveryState);
            return;
        }

        const wrapper = document.createElement("div");
        wrapper.innerHTML = buildMessageHtml(message, deliveryState);
        const nextElement = wrapper.firstElementChild;
        if (failed) {
            nextElement.classList.add("failed");
        }
        element.replaceWith(nextElement);

        const numericId = Number(message.id);
        if (Number.isFinite(numericId) && numericId > 0) {
            state.messageIds.add(numericId);
        }

        scrollMessagesToBottom();
    }

    function markPendingMessageFailed(pendingId) {
        const selector = `[data-message-id="${escapeSelectorValue(pendingId)}"]`;
        const element = dom.messages.querySelector(selector);
        if (!element) {
            return;
        }

        element.classList.add("failed");
        const statusElement = element.querySelector(".chat-message-status");
        if (statusElement) {
            statusElement.textContent = "Lỗi gửi";
            return;
        }

        element.insertAdjacentHTML("beforeend", '<div class="chat-message-status">Lỗi gửi</div>');
    }

    function applySessionState(session, guestKey) {
        state.session = session || null;

        if (!config.isAuthenticated && typeof guestKey !== "undefined") {
            state.guestKey = guestKey || "";
            persistGuestStorage();
        }

        if (config.isAuthenticated) {
            clearGuestStorage();
        }
    }

    function handleBootstrap(data) {
        applySessionState(data.session || null, data.guestKey);
        state.isBootstrapped = true;
        renderWarning(data.warningMessage || config.guestWarningMessage);
        renderMessages(data.messages || []);

        if (state.session) {
            state.unreadCount = state.isOpen ? 0 : Number(state.session.customerUnreadCount || 0);
        } else {
            state.unreadCount = 0;
        }
        updateFloatingBadge();
        setErrorMessage("");

        if (state.isOpen && state.session) {
            sendMarkRead();
        }
    }

    function handleSessionEvent(data) {
        if (!data.session) {
            return;
        }

        applySessionState(data.session, data.guestKey);

        if (!state.isOpen && state.session) {
            state.unreadCount = Number(state.session.customerUnreadCount || 0);
            updateFloatingBadge();
        }
    }

    function handleIncomingMessage(data) {
        const message = data.message;
        if (!message) {
            return;
        }

        if (data.session) {
            applySessionState(data.session, data.guestKey);
        }

        const pendingId = (message.clientMessageId || "").trim();
        if (pendingId) {
            const selector = `[data-message-id="${escapeSelectorValue(pendingId)}"]`;
            if (dom.messages.querySelector(selector)) {
                updatePendingMessage(
                    pendingId,
                    message,
                    message.senderType === "customer" ? "Đã gửi" : "",
                    false
                );
            } else {
                appendMessage(message, message.senderType === "customer" ? "Đã gửi" : "");
            }
        } else {
            appendMessage(message, message.senderType === "customer" ? "Đã gửi" : "");
        }

        if (message.senderType === "admin") {
            if (state.isOpen) {
                state.unreadCount = 0;
                updateFloatingBadge();
                sendMarkRead();
            } else if (data.session) {
                state.unreadCount = Number(data.session.customerUnreadCount || 0);
                updateFloatingBadge();
            } else {
                state.unreadCount += 1;
                updateFloatingBadge();
            }
        }
    }

    function handleSocketError(data) {
        if (data.clientMessageId) {
            markPendingMessageFailed(data.clientMessageId);
        }

        setErrorMessage(data.message || config.sendErrorMessage);
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

        rejectBootstrap(new Error("Socket closed"));
    }

    function scheduleReconnect() {
        if (state.reconnectTimer || !state.isBootstrapped) {
            return;
        }

        state.reconnectTimer = window.setTimeout(function () {
            state.reconnectTimer = null;
            connectStream().catch(function () {
                setErrorMessage(config.connectionErrorMessage || config.sendErrorMessage);
            });
        }, 3000);
    }

    function connectStream() {
        if (hasOpenStream() && state.isBootstrapped) {
            return Promise.resolve();
        }

        if (state.bootstrapPromise) {
            return state.bootstrapPromise;
        }

        if (hasPendingStream()) {
            return state.bootstrapPromise || Promise.resolve();
        }

        if (state.reconnectTimer) {
            clearTimeout(state.reconnectTimer);
            state.reconnectTimer = null;
        }

        const params = new URLSearchParams();
        if (!config.isAuthenticated && state.guestKey) {
            params.set("guestKey", state.guestKey);
        }

        const socket = new WebSocket(buildWebSocketUrl(config.socketPath, params));
        state.stream = socket;
        const promise = createBootstrapPromise();

        socket.addEventListener("message", function (event) {
            let data;
            try {
                data = JSON.parse(event.data || "{}");
            } catch (error) {
                return;
            }

            if (data.event === "bootstrap") {
                handleBootstrap(data);
                resolveBootstrap(data);
                return;
            }

            if (data.event === "session") {
                handleSessionEvent(data);
                return;
            }

            if (data.event === "message") {
                handleIncomingMessage(data);
                return;
            }

            if (data.event === "error") {
                handleSocketError(data);
            }
        });

        socket.addEventListener("close", function () {
            if (state.stream === socket) {
                state.stream = null;
                rejectBootstrap(new Error("Socket closed"));
                scheduleReconnect();
            }
        });

        socket.addEventListener("error", function () {
            if (state.stream === socket && !hasOpenStream()) {
                rejectBootstrap(new Error("Socket error"));
            }
        });

        return promise;
    }

    async function ensureStreamReady() {
        if (hasOpenStream() && state.isBootstrapped) {
            return;
        }

        await connectStream();
    }

    function sendAction(payload) {
        if (!hasOpenStream()) {
            setErrorMessage(config.connectionErrorMessage || config.sendErrorMessage);
            return false;
        }

        state.stream.send(JSON.stringify(payload));
        return true;
    }

    function sendMarkRead() {
        if (!state.session || !hasOpenStream()) {
            return;
        }

        state.unreadCount = 0;
        updateFloatingBadge();
        sendAction({action: "mark_read"});
    }

    async function handleSend(event) {
        event.preventDefault();

        const content = dom.input.value.trim();
        if (!content) {
            return;
        }

        try {
            await ensureStreamReady();
        } catch (error) {
            setErrorMessage(config.connectionErrorMessage || config.sendErrorMessage);
            return;
        }

        const clientMessageId = `temp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        const tempMessage = {
            id: clientMessageId,
            clientMessageId: clientMessageId,
            senderType: "customer",
            senderName: "Bạn",
            messageType: "text",
            content: content,
            createdAt: new Date().toISOString(),
            timeLabel: formatTime(new Date().toISOString()),
        };

        appendMessage(tempMessage, "Đang gửi...");
        dom.input.value = "";
        autoResizeInput();
        updateSendButtonState();
        setErrorMessage("");

        const sent = sendAction({
            action: "send_message",
            content: content,
            clientMessageId: clientMessageId,
            sourcePage: window.location.pathname,
        });

        if (!sent) {
            updatePendingMessage(clientMessageId, tempMessage, "Lỗi gửi", true);
        }
    }

    function openChat() {
        state.isOpen = true;
        dom.widget.classList.add("active");
        setTimeout(function () {
            dom.input.focus();
            scrollMessagesToBottom();
        }, 120);

        connectStream()
            .then(function () {
                if (state.session) {
                    sendMarkRead();
                }
            })
            .catch(function () {
                setErrorMessage(config.connectionErrorMessage || config.sendErrorMessage);
            });
    }

    function closeChat() {
        state.isOpen = false;
        dom.widget.classList.remove("active");
    }

    function toggleChat() {
        if (state.isOpen) {
            closeChat();
        } else {
            openChat();
        }
    }

    function initialize() {
        renderWarning(config.guestWarningMessage);
        autoResizeInput();
        updateSendButtonState();
        updateFloatingBadge();

        dom.input.addEventListener("input", function () {
            autoResizeInput();
            updateSendButtonState();
        });

        dom.input.addEventListener("keydown", function (event) {
            if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                if (!dom.sendBtn.disabled) {
                    dom.form.requestSubmit();
                }
            }
        });

        dom.form.addEventListener("submit", handleSend);
    }

    window.toggleChat = toggleChat;
    document.addEventListener("DOMContentLoaded", initialize);
    window.addEventListener("beforeunload", disconnectStream);
})();
