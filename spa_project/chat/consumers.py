import base64
import binascii
from urllib.parse import parse_qs

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from channels.generic.websocket import JsonWebsocketConsumer

from .models import ChatSession
from .services import (
    ADMIN_CHAT_SESSIONS_GROUP,
    can_user_access_session,
    create_chat_message,
    ensure_staff_session_participation,
    get_admin_chat_group,
    get_admin_chat_sessions_data,
    get_customer_chat_group,
    get_existing_customer_chat_session_for_identity,
    get_or_create_customer_chat_session_for_identity,
    mark_session_read_by_admin,
    mark_session_read_by_customer,
    serialize_customer_chat_message,
    serialize_chat_message,
    serialize_chat_messages,
    serialize_chat_session,
)

User = get_user_model()


def format_exception_message(exc):
    if isinstance(exc, ValidationError):
        if hasattr(exc, "messages") and exc.messages:
            return " ".join(str(message) for message in exc.messages)
        if hasattr(exc, "message") and exc.message:
            return str(exc.message)

    message = str(exc).strip()
    return message or "Không thể xử lý yêu cầu."


def get_customer_warning_message(is_authenticated):
    if is_authenticated:
        return ""
    return "Lịch sử chat sẽ không được lưu khi bạn rời khỏi website."


def get_admin_session_meta(chat_code):
    session = ChatSession.objects.only("id", "chat_code").get(chat_code=chat_code)
    return {
        "session_id": session.id,
        "chat_code": session.chat_code,
    }


def record_staff_participation(session_id, user_id):
    if not user_id:
        return

    session = ChatSession.objects.get(pk=session_id)
    user = User.objects.get(pk=user_id)
    ensure_staff_session_participation(session, user)


def get_session_messages_payload(session, customer_safe=False):
    messages = session.messages.select_related("session", "sender").order_by("created_at", "id")
    return serialize_chat_messages(messages, customer_safe=customer_safe)


def get_admin_sessions_snapshot(search, status):
    sessions, unread_total = get_admin_chat_sessions_data(search=search, status=status)
    return [serialize_chat_session(session) for session in sessions], unread_total


class BaseChatConsumer(JsonWebsocketConsumer):
    def get_query_params(self):
        raw_query = self.scope.get("query_string", b"").decode("utf-8")
        return parse_qs(raw_query)

    def get_query_param(self, key, default=""):
        values = self.get_query_params().get(key)
        if not values:
            return default
        return values[0]

    def get_action(self, content):
        return (content.get("action") or content.get("event") or "").strip().lower()

    def get_scope_user(self):
        user = self.scope.get("user")
        if user and getattr(user, "is_authenticated", False):
            return user
        return None

    def send_event(self, event, **payload):
        data = {"event": event}
        data.update(payload)
        self.send_json(data)

    def send_error(self, message, **payload):
        data = {"message": message}
        data.update(payload)
        self.send_event("error", **data)

    def chat_message(self, event):
        self.send_event(
            "message",
            message=event.get("message"),
            session=event.get("session"),
        )

    def chat_session(self, event):
        self.send_event("session", session=event.get("session"))

    def chat_sessions_refresh(self, event):
        return None

    def disconnect_group(self):
        group_name = getattr(self, "group_name", "")
        if group_name:
            async_to_sync(self.channel_layer.group_discard)(group_name, self.channel_name)
            self.group_name = ""

    def disconnect(self, close_code):
        self.disconnect_group()


class CustomerChatConsumer(BaseChatConsumer):
    def connect(self):
        self.group_name = ""
        self.session_id = None
        self.chat_code = ""
        self.guest_key = (self.get_query_param("guestKey", "") or "").strip()

        user = self.get_scope_user()
        session = get_existing_customer_chat_session_for_identity(user=user, guest_key=self.guest_key)

        self.accept()

        if session:
            self.bind_session(session)

        self.send_bootstrap(session)

        if session:
            mark_session_read_by_customer(session)

    def chat_session(self, event):
        payload = {"session": event.get("session")}
        if self.guest_key:
            payload["guestKey"] = self.guest_key
        self.send_event("session", **payload)

    def bind_session(self, session):
        next_group_name = get_customer_chat_group(session.chat_code)
        if self.group_name and self.group_name != next_group_name:
            self.disconnect_group()

        self.session_id = session.id
        self.chat_code = session.chat_code
        self.group_name = next_group_name

        if session.customer_type == "guest" and session.guest_session_key:
            self.guest_key = session.guest_session_key

        async_to_sync(self.channel_layer.group_add)(self.group_name, self.channel_name)

    def send_bootstrap(self, session):
        user = self.get_scope_user()
        is_authenticated = bool(user)
        history_preserved = bool(session and session.customer_type == "authenticated")
        guest_key = self.guest_key

        if session and session.customer_type == "guest":
            guest_key = session.guest_session_key or guest_key

        self.send_event(
            "bootstrap",
            session=serialize_chat_session(session) if session else None,
            messages=get_session_messages_payload(session, customer_safe=True) if session else [],
            guestKey=guest_key,
            historyPreserved=history_preserved,
            isNewSession=not bool(session),
            warningMessage=get_customer_warning_message(is_authenticated),
        )

    def get_bound_session(self):
        if not self.session_id:
            return None
        return ChatSession.objects.select_related("customer", "customer__user").get(pk=self.session_id)

    def receive_json(self, content, **kwargs):
        action = self.get_action(content)
        if action == "send_message":
            self.handle_send_message(content)
            return

        if action == "mark_read":
            self.handle_mark_read()
            return

        self.send_error("Sự kiện WebSocket không hợp lệ.")

    def handle_send_message(self, content):
        if content.get("attachment"):
            self.send_error(
                "Khách hàng chỉ được gửi tin nhắn văn bản.",
                clientMessageId=(content.get("clientMessageId") or "").strip(),
            )
            return

        user = self.get_scope_user()
        guest_key = (content.get("guestKey") or self.guest_key or "").strip()
        source_page = (content.get("sourcePage") or "").strip()[:255]
        client_message_id = (content.get("clientMessageId") or "").strip()

        try:
            session = self.get_bound_session()
            if session and not can_user_access_session(user, session, guest_key):
                self.send_error("Bạn không có quyền truy cập phiên chat này.", clientMessageId=client_message_id)
                return

            if not session:
                session = get_or_create_customer_chat_session_for_identity(
                    user=user,
                    guest_key=guest_key,
                    source_page=source_page,
                )
                self.bind_session(session)
                self.send_event(
                    "session",
                    session=serialize_chat_session(session),
                    guestKey=self.guest_key,
                )

            message, created = create_chat_message(
                session=session,
                sender_type="customer",
                sender_user=user,
                sender_name=session.get_customer_display_name() if user else "Khách vãng lai",
                content=content.get("content", ""),
                client_message_id=client_message_id,
            )
        except Exception as exc:
            self.send_error(format_exception_message(exc), clientMessageId=client_message_id)
            return

        if not created:
            self.send_event(
                "message",
                message=serialize_customer_chat_message(message),
                session=serialize_chat_session(message.session),
            )

    def handle_mark_read(self):
        try:
            session = self.get_bound_session()
            if not session:
                return

            user = self.get_scope_user()
            if not can_user_access_session(user, session, self.guest_key):
                self.send_error("Bạn không có quyền truy cập phiên chat này.")
                return

            mark_session_read_by_customer(session)
        except Exception as exc:
            self.send_error(format_exception_message(exc))


class AdminChatSessionsConsumer(BaseChatConsumer):
    def connect(self):
        user = self.get_scope_user()
        if not user or not (user.is_staff or user.is_superuser):
            self.close(code=4403)
            return

        self.search = (self.get_query_param("search", "") or "").strip()
        self.status = (self.get_query_param("status", "") or "").strip()
        self.group_name = ADMIN_CHAT_SESSIONS_GROUP
        async_to_sync(self.channel_layer.group_add)(self.group_name, self.channel_name)
        self.accept()
        self.send_sessions_snapshot()

    def receive_json(self, content, **kwargs):
        action = self.get_action(content)
        if action != "set_filters":
            self.send_error("Sự kiện WebSocket không hợp lệ.")
            return

        self.search = (content.get("search") or "").strip()
        self.status = (content.get("status") or "").strip()
        self.send_sessions_snapshot()

    def send_sessions_snapshot(self):
        sessions, unread_total = get_admin_sessions_snapshot(self.search, self.status)
        self.send_event(
            "sessions",
            sessions=sessions,
            unreadTotal=unread_total,
        )

    def chat_sessions_refresh(self, event):
        self.send_sessions_snapshot()


class AdminChatSessionConsumer(BaseChatConsumer):
    def connect(self):
        user = self.get_scope_user()
        if not user or not (user.is_staff or user.is_superuser):
            self.close(code=4403)
            return

        chat_code = self.scope["url_route"]["kwargs"]["chat_code"]

        try:
            session_meta = get_admin_session_meta(chat_code)
        except ChatSession.DoesNotExist:
            self.close(code=4404)
            return

        self.chat_code = session_meta["chat_code"]
        self.session_id = session_meta["session_id"]
        record_staff_participation(self.session_id, getattr(user, "id", None))

        self.group_name = get_admin_chat_group(self.chat_code)
        async_to_sync(self.channel_layer.group_add)(self.group_name, self.channel_name)
        self.accept()
        self.send_bootstrap()
        mark_session_read_by_admin(ChatSession.objects.get(pk=self.session_id))

    def get_session(self):
        return ChatSession.objects.select_related("customer", "customer__user").get(pk=self.session_id)

    def send_bootstrap(self):
        session = self.get_session()
        self.send_event(
            "bootstrap",
            session=serialize_chat_session(session),
            messages=get_session_messages_payload(session),
        )

    def receive_json(self, content, **kwargs):
        action = self.get_action(content)
        if action == "send_message":
            self.handle_send_message(content)
            return

        if action == "mark_read":
            self.handle_mark_read()
            return

        self.send_error("Sự kiện WebSocket không hợp lệ.")

    def build_attachment_from_payload(self, payload):
        if not payload:
            return None

        attachment_name = (payload.get("name") or "").strip()
        attachment_content_type = (payload.get("contentType") or "").strip()
        encoded_content = (payload.get("data") or "").strip()

        if not attachment_name or not attachment_content_type or not encoded_content:
            raise ValidationError("Thông tin tệp đính kèm không hợp lệ.")

        if "," in encoded_content:
            encoded_content = encoded_content.split(",", 1)[1]

        try:
            file_bytes = base64.b64decode(encoded_content, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValidationError("Không thể đọc tệp đính kèm.") from exc

        return SimpleUploadedFile(
            attachment_name,
            file_bytes,
            content_type=attachment_content_type,
        )

    def handle_send_message(self, content):
        user = self.get_scope_user()
        if not user:
            self.send_error("Bạn không có quyền thực hiện thao tác này.")
            return

        client_message_id = (content.get("clientMessageId") or "").strip()

        try:
            session = self.get_session()
            ensure_staff_session_participation(session, user)
            attachment = self.build_attachment_from_payload(content.get("attachment"))
            message, created = create_chat_message(
                session=session,
                sender_type="admin",
                sender_user=user,
                sender_name=user.get_full_name() or user.username,
                content=content.get("content", ""),
                attachment=attachment,
                client_message_id=client_message_id,
            )
        except Exception as exc:
            self.send_error(format_exception_message(exc), clientMessageId=client_message_id)
            return

        if not created:
            self.send_event(
                "message",
                message=serialize_chat_message(message),
                session=serialize_chat_session(message.session),
            )

    def handle_mark_read(self):
        try:
            mark_session_read_by_admin(self.get_session())
        except Exception as exc:
            self.send_error(format_exception_message(exc))
