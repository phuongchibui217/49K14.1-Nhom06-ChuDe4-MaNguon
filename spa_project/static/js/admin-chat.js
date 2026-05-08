(function () {
    const config = window.adminChatConfig;
    if (!config) {
        return;
    }

    const state = {
        sessions: [],
        selectedSession: null,
        selectedFile: null,
        sessionStream: null,
        messageStream: null,
        sessionReconnectTimer: null,
        messageReconnectTimer: null,
        messageIds: new Set(),
    };

    const dom = {
        emptyState: document.getElementById("adminChatEmptyState"),
        panel: document.getElementById("adminChatPanel"),
        sessionList: document.getElementById("adminChatSessionList"),
        unreadTotal: document.getElementById("adminChatUnreadTotal"),
        searchInput: document.getElementById("adminChatSearch"),
        sessionName: document.getElementById("adminChatSessionName"),
        sessionCode: document.getElementById("adminChatSessionCode"),
        sessionContact: document.getElementById("adminChatSessionContact"),
        sessionStatus: document.getElementById("adminChatSessionStatus"),
        messages: document.getElementById("adminChatMessages"),
        form: document.getElementById("adminChatComposerForm"),
        input: document.getElementById("adminChatInput"),
        sendBtn: document.getElementById("adminChatSendBtn"),
        error: document.getElementById("adminChatErrorMessage"),
        attachBtn: document.getElementById("adminChatAttachBtn"),
        attachmentInput: document.getElementById("adminChatAttachmentInput"),
        selectedFile: document.getElementById("adminChatSelectedFile"),
        selectedFileName: document.getElementById("adminChatSelectedFileName"),
        removeFileBtn: document.getElementById("adminChatRemoveFile"),
    };

    function buildChatUrl(template, chatCode) {
        return template.replace("__CHAT_CODE__", chatCode);
    }

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

    function formatDateTime(value) {
        if (!value) {
            return "";
        }

        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return "";
        }

        return date.toLocaleString("vi-VN", {
            hour: "2-digit",
            minute: "2-digit",
            day: "2-digit",
            month: "2-digit",
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

    function getSessionStatusLabel(status) {
        const normalized = String(status || "").trim().toUpperCase();
        return normalized === "CLOSED" ? "Đã đóng" : "Đang mở";
    }

    function debounce(fn, delay) {
        let timeoutId = null;
        return function (...args) {
            clearTimeout(timeoutId);
            timeoutId = setTimeout(() => fn.apply(this, args), delay);
        };
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
        dom.input.style.height = `${Math.min(dom.input.scrollHeight, 180)}px`;
    }

    function updateSendButtonState() {
        const hasText = dom.input.value.trim().length > 0;
        const hasFile = !!state.selectedFile;
        dom.sendBtn.disabled = !state.selectedSession || (!hasText && !hasFile);
    }

    function setSelectedFile(file) {
        state.selectedFile = file || null;

        if (state.selectedFile) {
            dom.selectedFileName.textContent = state.selectedFile.name;
            dom.selectedFile.classList.remove("d-none");
        } else {
            dom.attachmentInput.value = "";
            dom.selectedFile.classList.add("d-none");
            dom.selectedFileName.textContent = "";
        }

        updateSendButtonState();
    }

    function renderSessions() {
        const unreadCount = state.sessions.reduce((sum, item) => sum + (item.adminUnreadCount || 0), 0);
        dom.unreadTotal.textContent = `${unreadCount} chưa đọc`;

        if (!state.sessions.length) {
            dom.sessionList.innerHTML = `
                <div class="admin-chat-list-empty">
                    <i class="fas fa-comments"></i>
                    <p>Chưa có phiên chat nào.</p>
                </div>
            `;
            return;
        }

        dom.sessionList.innerHTML = state.sessions
            .map((session) => {
                const isActive = state.selectedSession && state.selectedSession.chatCode === session.chatCode;
                const unreadBadge = session.adminUnreadCount
                    ? `<span class="admin-chat-unread-badge">${session.adminUnreadCount}</span>`
                    : "";
                const contactLabel = session.customerPhone || (session.isGuest ? "Khách vãng lai" : "Khách hàng");

                return `
                    <button
                        type="button"
                        class="admin-chat-session-item ${isActive ? "active" : ""}"
                        data-chat-code="${escapeHtml(session.chatCode)}"
                    >
                        <div class="admin-chat-session-top">
                            <div>
                                <p class="admin-chat-session-name">${escapeHtml(session.customerName || "Khách hàng")}</p>
                                <span class="admin-chat-session-code">${escapeHtml(session.chatCode)}</span>
                            </div>
                            <span class="admin-chat-session-time">${escapeHtml(session.lastMessageTimeLabel || "Mới tạo")}</span>
                        </div>
                        <div class="admin-chat-session-preview">${escapeHtml(session.lastMessagePreview || "Chưa có tin nhắn")}</div>
                        <div class="admin-chat-session-bottom">
                            <span class="admin-chat-session-contact">${escapeHtml(contactLabel)}</span>
                            ${unreadBadge}
                        </div>
                    </button>
                `;
            })
            .join("");

        dom.sessionList.querySelectorAll(".admin-chat-session-item").forEach((item) => {
            item.addEventListener("click", function () {
                selectSession(this.dataset.chatCode);
            });
        });
    }

    function renderMessageAttachment(message) {
        if (message.attachmentUrl) {
            if (message.isImage) {
                return `
                    <div class="admin-chat-attachment">
                        <a href="${message.attachmentUrl}" target="_blank" rel="noopener noreferrer">
                            <img
                                src="${message.attachmentUrl}"
                                alt="${escapeHtml(message.attachmentName || "Hình ảnh chat")}"
                                class="admin-chat-attachment-image"
                            >
                        </a>
                    </div>
                `;
            }

            return `
                <div class="admin-chat-attachment">
                    <a
                        href="${message.attachmentUrl}"
                        target="_blank"
                        rel="noopener noreferrer"
                        class="admin-chat-attachment-file"
                    >
                        <i class="fas fa-file-alt"></i>
                        <span>${escapeHtml(message.attachmentName || "Tệp đính kèm")}</span>
                        <small>${escapeHtml(formatFileSize(message.attachmentSize))}</small>
                    </a>
                </div>
            `;
        }

        if (message.attachmentName) {
            return `
                <div class="admin-chat-attachment">
                    <div class="admin-chat-attachment-file">
                        <i class="fas fa-file-alt"></i>
                        <span>${escapeHtml(message.attachmentName)}</span>
                        <small>${escapeHtml(formatFileSize(message.attachmentSize))}</small>
                    </div>
                </div>
            `;
        }

        return "";
    }

    function buildMessageHtml(message) {
        const messageClass = message.senderType === "admin"
            ? "admin"
            : message.senderType === "system"
                ? "system"
                : "customer";

        const displayName = message.senderType === "admin"
            ? (message.staffName || message.senderName || "Nhân viên")
            : (message.senderName || "Khách hàng");

        return `
            <div class="admin-chat-message ${messageClass}" data-message-id="${escapeHtml(message.id)}">
                <div class="admin-chat-message-header">
                    <span class="admin-chat-message-name">${escapeHtml(displayName)}</span>
                    <span class="admin-chat-message-time">${escapeHtml(message.timeLabel || formatDateTime(message.createdAt))}</span>
                </div>
                ${message.content ? `<div class="admin-chat-message-content">${escapeHtml(message.content)}</div>` : ""}
                ${renderMessageAttachment(message)}
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

        dom.messages.innerHTML = messages.length
            ? messages.map(buildMessageHtml).join("")
            : `
                <div class="admin-chat-empty">
                    <i class="fas fa-comment-slash"></i>
                    <p>Phiên chat này chưa có tin nhắn nào.</p>
                </div>
            `;

        scrollMessagesToBottom();
    }

    function appendMessage(message) {
        const numericId = Number(message.id);
        if (Number.isFinite(numericId) && numericId > 0 && state.messageIds.has(numericId)) {
            return;
        }

        if (Number.isFinite(numericId) && numericId > 0) {
            state.messageIds.add(numericId);
        }

        const emptyState = dom.messages.querySelector(".admin-chat-empty");
        if (emptyState) {
            dom.messages.innerHTML = "";
        }

        dom.messages.insertAdjacentHTML("beforeend", buildMessageHtml(message));
        scrollMessagesToBottom();
    }

    function updateSelectedSession(session) {
        state.selectedSession = session;
        dom.emptyState.classList.add("d-none");
        dom.panel.classList.remove("d-none");
        dom.sessionName.textContent = session.customerName || "Khách hàng";
        dom.sessionCode.textContent = session.chatCode || "";
        dom.sessionContact.textContent = session.customerPhone || (session.isGuest ? "Khách vãng lai" : "");
        dom.sessionStatus.textContent = getSessionStatusLabel(session.status);
        updateSendButtonState();
        renderSessions();
    }

    function refreshSelectedSessionFromList() {
        if (!state.selectedSession) {
            return;
        }

        const refreshed = state.sessions.find((item) => item.chatCode === state.selectedSession.chatCode);
        if (refreshed) {
            updateSelectedSession(refreshed);
        }
    }

    function disconnectMessageStream() {
        if (state.messageStream) {
            state.messageStream.onclose = null;
            state.messageStream.close();
            state.messageStream = null;
        }

        if (state.messageReconnectTimer) {
            clearTimeout(state.messageReconnectTimer);
            state.messageReconnectTimer = null;
        }
    }

    function disconnectSessionStream() {
        if (state.sessionStream) {
            state.sessionStream.onclose = null;
            state.sessionStream.close();
            state.sessionStream = null;
        }

        if (state.sessionReconnectTimer) {
            clearTimeout(state.sessionReconnectTimer);
            state.sessionReconnectTimer = null;
        }
    }

    function scheduleSessionReconnect() {
        if (state.sessionReconnectTimer) {
            return;
        }

        state.sessionReconnectTimer = window.setTimeout(function () {
            state.sessionReconnectTimer = null;
            connectSessionStream();
        }, 3000);
    }

    function scheduleMessageReconnect(chatCode) {
        if (state.messageReconnectTimer) {
            return;
        }

        state.messageReconnectTimer = window.setTimeout(function () {
            state.messageReconnectTimer = null;
            if (state.selectedSession && state.selectedSession.chatCode === chatCode) {
                connectMessageStream(chatCode);
            }
        }, 3000);
    }

    function connectSessionStream() {
        disconnectSessionStream();

        const params = new URLSearchParams();
        const search = dom.searchInput.value.trim();
        if (search) {
            params.set("search", search);
        }

        const socket = new WebSocket(buildWebSocketUrl(config.sessionsSocketPath, params));
        state.sessionStream = socket;

        socket.addEventListener("message", function (event) {
            let data;
            try {
                data = JSON.parse(event.data || "{}");
            } catch (error) {
                return;
            }

            if (data.event !== "sessions") {
                return;
            }

            state.sessions = data.sessions || [];
            renderSessions();
            refreshSelectedSessionFromList();
        });

        socket.addEventListener("close", function () {
            if (state.sessionStream === socket) {
                state.sessionStream = null;
                scheduleSessionReconnect();
            }
        });
    }

    function sendMessageAction(payload) {
        if (!state.messageStream || state.messageStream.readyState !== WebSocket.OPEN) {
            setErrorMessage(config.connectionErrorMessage || config.sendErrorMessage);
            return false;
        }

        state.messageStream.send(JSON.stringify(payload));
        return true;
    }

    function sendMarkRead() {
        if (!state.selectedSession) {
            return;
        }

        sendMessageAction({action: "mark_read"});
    }

    function showMessagesLoading() {
        dom.messages.innerHTML = `
            <div class="admin-chat-empty">
                <i class="fas fa-spinner fa-spin"></i>
                <p>Đang tải lịch sử chat...</p>
            </div>
        `;
    }

    function connectMessageStream(chatCode) {
        disconnectMessageStream();
        state.messageIds = new Set();
        showMessagesLoading();

        const socket = new WebSocket(
            buildWebSocketUrl(
                buildChatUrl(config.messageSocketPathTemplate, chatCode)
            )
        );
        state.messageStream = socket;

        socket.addEventListener("message", function (event) {
            let data;
            try {
                data = JSON.parse(event.data || "{}");
            } catch (error) {
                return;
            }

            if (data.event === "bootstrap") {
                if (data.session && data.session.chatCode === chatCode) {
                    updateSelectedSession(data.session);
                }
                renderMessages(data.messages || []);
                setErrorMessage("");
                return;
            }

            if (data.event === "session" && data.session && state.selectedSession && data.session.chatCode === state.selectedSession.chatCode) {
                updateSelectedSession(data.session);
                return;
            }

            if (data.event === "message" && data.message) {
                appendMessage(data.message);

                if (data.session && state.selectedSession && data.session.chatCode === state.selectedSession.chatCode) {
                    updateSelectedSession(data.session);
                }

                if (data.message.senderType === "customer") {
                    sendMarkRead();
                }
                return;
            }

            if (data.event === "error") {
                setErrorMessage(data.message || config.sendErrorMessage);
            }
        });

        socket.addEventListener("close", function () {
            if (state.messageStream === socket) {
                state.messageStream = null;
                scheduleMessageReconnect(chatCode);
            }
        });
    }

    function selectSession(chatCode) {
        const session = state.sessions.find((item) => item.chatCode === chatCode);
        if (!session) {
            return;
        }

        updateSelectedSession(session);
        connectMessageStream(chatCode);
    }

    async function fileToAttachmentPayload(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = function () {
                resolve({
                    name: file.name,
                    contentType: file.type || "application/octet-stream",
                    data: reader.result || "",
                });
            };
            reader.onerror = function () {
                reject(new Error("Không thể đọc tệp đính kèm."));
            };
            reader.readAsDataURL(file);
        });
    }

    async function sendMessage(event) {
        event.preventDefault();
        if (!state.selectedSession) {
            return;
        }

        const content = dom.input.value.trim();
        if (!content && !state.selectedFile) {
            return;
        }

        if (!state.messageStream || state.messageStream.readyState !== WebSocket.OPEN) {
            setErrorMessage(config.connectionErrorMessage || config.sendErrorMessage);
            return;
        }

        if (state.selectedFile && config.maxAttachmentSize && state.selectedFile.size > config.maxAttachmentSize) {
            setErrorMessage("Tệp đính kèm không được vượt quá 10MB.");
            return;
        }

        dom.sendBtn.disabled = true;
        setErrorMessage("");

        const payload = {
            action: "send_message",
            content: content,
            clientMessageId: `admin-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        };

        if (state.selectedFile) {
            try {
                payload.attachment = await fileToAttachmentPayload(state.selectedFile);
            } catch (error) {
                setErrorMessage(error.message || config.sendErrorMessage);
                updateSendButtonState();
                return;
            }
        }

        const sent = sendMessageAction(payload);
        if (!sent) {
            updateSendButtonState();
            return;
        }

        dom.input.value = "";
        autoResizeInput();
        setSelectedFile(null);
        updateSendButtonState();
    }

    function handleSearchInput() {
        connectSessionStream();
    }

    function initialize() {
        connectSessionStream();

        dom.searchInput.addEventListener("input", debounce(handleSearchInput, 350));
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

        dom.form.addEventListener("submit", sendMessage);
        dom.attachBtn.addEventListener("click", function () {
            dom.attachmentInput.click();
        });
        dom.attachmentInput.addEventListener("change", function () {
            const file = this.files && this.files.length ? this.files[0] : null;
            setSelectedFile(file);
        });
        dom.removeFileBtn.addEventListener("click", function () {
            setSelectedFile(null);
        });

        autoResizeInput();
        updateSendButtonState();
    }

    document.addEventListener("DOMContentLoaded", initialize);
    window.addEventListener("beforeunload", function () {
        disconnectMessageStream();
        disconnectSessionStream();
    });
})();
