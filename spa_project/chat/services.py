import os
import secrets

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Exists, F, OuterRef, Q, Sum
from django.utils import timezone

from customers.models import CustomerProfile
from core.validators import validate_length, validate_required

from .models import ChatMessage, ChatSession, SessionStaff


CHAT_TEXT_MAX_LENGTH = 1000
CHAT_ATTACHMENT_MAX_SIZE = 10 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
}
ALLOWED_FILE_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain",
    "application/zip",
    "application/x-zip-compressed",
}
ALLOWED_FILE_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".txt",
    ".zip",
}

ADMIN_CHAT_SESSIONS_GROUP = "chat.admin.sessions"
CUSTOMER_VISIBLE_ADMIN_NAME = "Nhân viên"


def get_customer_chat_group(chat_code):
    return f"chat.customer.{chat_code}"


def get_admin_chat_group(chat_code):
    return f"chat.admin.session.{chat_code}"


def normalize_sender_type(sender_type):
    normalized = (sender_type or "").strip().lower()
    if normalized == "staff":
        return "admin"
    return normalized


def get_customer_visible_sender_name(sender_type, sender_name):
    if normalize_sender_type(sender_type) == "admin":
        return CUSTOMER_VISIBLE_ADMIN_NAME
    return (sender_name or "").strip()


def _broadcast_group_event(group_name, event):
    channel_layer = get_channel_layer()
    if not channel_layer:
        return

    async_to_sync(channel_layer.group_send)(group_name, event)


def ensure_customer_profile(user):
    if hasattr(user, "customer_profile"):
        return user.customer_profile

    return CustomerProfile.objects.create(
        user=user,
        phone=user.username,
        full_name=user.get_full_name() or user.username,
    )


def generate_guest_session_key():
    return secrets.token_urlsafe(24)


def normalize_text_message(content):
    content = validate_required(content, "Tin nhắn")
    return validate_length(
        content,
        min_len=1,
        max_len=CHAT_TEXT_MAX_LENGTH,
        field_name="Tin nhắn",
    )


def validate_admin_attachment(attachment):
    if not attachment:
        return "text"

    if attachment.size > CHAT_ATTACHMENT_MAX_SIZE:
        raise ValidationError("Tệp đính kèm không được vượt quá 10MB.")

    content_type = getattr(attachment, "content_type", "").lower()
    extension = os.path.splitext(attachment.name or "")[1].lower()

    if content_type in ALLOWED_IMAGE_TYPES:
        return "image"

    if content_type in ALLOWED_FILE_TYPES or extension in ALLOWED_FILE_EXTENSIONS:
        return "file"

    raise ValidationError("Định dạng tệp không được hỗ trợ.")


def get_existing_customer_chat_session_for_identity(user=None, guest_key=None):
    if user and getattr(user, "is_authenticated", False):
        customer = ensure_customer_profile(user)
        return ChatSession.objects.filter(
            customer=customer,
            customer_type="authenticated",
            status__iexact="open",
        ).order_by("-last_message_at", "-created_at").first()

    if guest_key:
        return ChatSession.objects.filter(
            customer_type="guest",
            guest_session_key=guest_key,
            status__iexact="open",
        ).first()

    return None


def create_customer_chat_session_for_identity(user=None, guest_key=None, source_page=""):
    source_page = (source_page or "")[:255]

    if user and getattr(user, "is_authenticated", False):
        customer = ensure_customer_profile(user)
        session = ChatSession.objects.create(
            customer_type="authenticated",
            customer=customer,
            source_page=source_page,
        )
    else:
        session = ChatSession.objects.create(
            customer_type="guest",
            guest_session_key=guest_key or generate_guest_session_key(),
            source_page=source_page,
        )

    notify_chat_session_changed(session)
    return session


def get_or_create_customer_chat_session_for_identity(user=None, guest_key=None, source_page=""):
    source_page = (source_page or "")[:255]

    existing = get_existing_customer_chat_session_for_identity(user=user, guest_key=guest_key)
    if existing:
        if source_page and not existing.source_page:
            existing.source_page = source_page
            existing.save(update_fields=["source_page", "updated_at"])
            notify_chat_session_changed(existing)
        return existing

    return create_customer_chat_session_for_identity(user=user, guest_key=guest_key, source_page=source_page)


def can_user_access_session(user, session, guest_key=None):
    if session.customer_type == "authenticated":
        return bool(
            getattr(user, "is_authenticated", False)
            and session.customer_id
            and hasattr(user, "customer_profile")
            and session.customer_id == user.customer_profile.id
        )

    return bool(guest_key and session.guest_session_key == guest_key)


def touch_session_from_message(session, message):
    sender_type = normalize_sender_type(message.sender_type)
    update_kwargs = {
        "last_message_at": message.created_at,
        "last_message_preview": message.get_preview_text()[:255],
        "last_sender_type": sender_type,
        "updated_at": timezone.now(),
    }
    if sender_type == "customer":
        update_kwargs["admin_unread_count"] = F("admin_unread_count") + 1
        update_kwargs["customer_unread_count"] = 0
    elif sender_type == "admin":
        update_kwargs["customer_unread_count"] = F("customer_unread_count") + 1
        update_kwargs["admin_unread_count"] = 0

    ChatSession.objects.filter(pk=session.pk).update(**update_kwargs)
    session.refresh_from_db(
        fields=[
            "last_message_at",
            "last_message_preview",
            "last_sender_type",
            "admin_unread_count",
            "customer_unread_count",
            "updated_at",
        ]
    )


def create_chat_message(
    session,
    sender_type,
    sender_user=None,
    sender_name="",
    content="",
    attachment=None,
    client_message_id=None,
):
    sender_type = normalize_sender_type(sender_type)
    sender_name = (sender_name or "").strip()
    content = (content or "").strip()
    client_message_id = (client_message_id or "").strip() or None

    if sender_type == "customer" and attachment:
        raise ValidationError("Khách hàng chỉ được gửi tin nhắn văn bản.")

    message_type = validate_admin_attachment(attachment)

    if content:
        content = normalize_text_message(content)

    if not content and not attachment:
        raise ValidationError("Vui lòng nhập nội dung tin nhắn.")

    with transaction.atomic():
        locked_session = ChatSession.objects.select_for_update().get(pk=session.pk)

        if client_message_id:
            existing = ChatMessage.objects.filter(
                session=locked_session,
                client_message_id=client_message_id,
            ).first()
            if existing:
                session.refresh_from_db()
                return existing, False

        message = ChatMessage(
            session=locked_session,
            sender_type=sender_type,
            sender=sender_user,
            sender_user=sender_user,
            sender_name=sender_name,
            message_type=message_type if attachment else "text",
            content=content,
            client_message_id=client_message_id,
        )

        if attachment:
            message.attachment = attachment
            message.attachment_name = attachment.name
            message.attachment_size = getattr(attachment, "size", 0) or 0
            message.attachment_content_type = getattr(attachment, "content_type", "") or ""

        message.save()
        touch_session_from_message(locked_session, message)
        session.refresh_from_db()

    notify_chat_message_created(message)
    return message, True


def ensure_staff_session_participation(session, staff_user):
    if not staff_user or not getattr(staff_user, "is_authenticated", False):
        return None, False

    return SessionStaff.objects.get_or_create(
        session=session,
        staff=staff_user,
    )


def notify_admin_sessions_changed():
    _broadcast_group_event(
        ADMIN_CHAT_SESSIONS_GROUP,
        {"type": "chat.sessions_refresh"},
    )


def notify_chat_session_changed(session):
    session_payload = serialize_chat_session(session)
    _broadcast_group_event(
        get_customer_chat_group(session.chat_code),
        {
            "type": "chat.session",
            "session": session_payload,
        },
    )
    _broadcast_group_event(
        get_admin_chat_group(session.chat_code),
        {
            "type": "chat.session",
            "session": session_payload,
        },
    )
    notify_admin_sessions_changed()


def notify_chat_message_created(message):
    customer_message_payload = serialize_customer_chat_message(message)
    admin_message_payload = serialize_chat_message(message)
    session_payload = serialize_chat_session(message.session)

    _broadcast_group_event(
        get_customer_chat_group(message.session.chat_code),
        {
            "type": "chat.message",
            "message": customer_message_payload,
            "session": session_payload,
        },
    )
    _broadcast_group_event(
        get_admin_chat_group(message.session.chat_code),
        {
            "type": "chat.message",
            "message": admin_message_payload,
            "session": session_payload,
        },
    )
    notify_admin_sessions_changed()


def mark_session_read_by_admin(session):
    if session.admin_unread_count:
        session.admin_unread_count = 0
        session.updated_at = timezone.now()
        ChatSession.objects.filter(pk=session.pk).update(
            admin_unread_count=0,
            updated_at=session.updated_at,
        )
        notify_chat_session_changed(session)


def mark_session_read_by_customer(session):
    if session.customer_unread_count:
        session.customer_unread_count = 0
        session.updated_at = timezone.now()
        ChatSession.objects.filter(pk=session.pk).update(
            customer_unread_count=0,
            updated_at=session.updated_at,
        )
        notify_chat_session_changed(session)


def get_chat_sessions_queryset(search="", status=""):
    sessions = ChatSession.objects.select_related("customer", "customer__user").filter(
        Exists(ChatMessage.objects.filter(session=OuterRef("pk")))
    )

    if status:
        sessions = sessions.filter(status__iexact=status)

    search = (search or "").strip()
    if search:
        sessions = sessions.filter(
            Q(chat_code__icontains=search)
            | Q(customer__full_name__icontains=search)
            | Q(customer__phone__icontains=search)
            | Q(last_message_preview__icontains=search)
            | Q(source_page__icontains=search)
        )

    return sessions.order_by("-last_message_at", "-created_at")


def get_admin_chat_sessions_data(search="", status="", limit=200):
    sessions_qs = get_chat_sessions_queryset(search=search, status=status)
    unread_total = sessions_qs.order_by().aggregate(total=Sum("admin_unread_count"))["total"] or 0
    return list(sessions_qs[:limit]), unread_total


def _get_attachment_url(message):
    attachment = getattr(message, "attachment", None)
    attachment_name = getattr(attachment, "name", "")

    if attachment and attachment_name:
        storage = getattr(attachment, "storage", None)
        try:
            if storage and storage.exists(attachment_name):
                return attachment.url
        except Exception:
            pass

    return (message.attachment_url or "").strip()


def serialize_chat_message(message, customer_safe=False):
    sender_type = normalize_sender_type(message.sender_type)
    raw_sender_name = (message.sender_name or "").strip()

    if customer_safe:
        sender_name = get_customer_visible_sender_name(sender_type, raw_sender_name)
        staff_name = ""
    else:
        sender_name = raw_sender_name
        staff_name = raw_sender_name if sender_type == "admin" else ""

    return {
        "id": message.id,
        "sessionCode": message.session.chat_code,
        "clientMessageId": message.client_message_id or "",
        "senderType": sender_type,
        "senderName": sender_name,
        "staffName": staff_name,
        "messageType": message.message_type,
        "content": message.content or "",
        "status": message.status,
        "createdAt": message.created_at.isoformat(),
        "timeLabel": timezone.localtime(message.created_at).strftime("%H:%M"),
        "attachmentUrl": _get_attachment_url(message),
        "attachmentName": message.attachment_name or "",
        "attachmentSize": message.attachment_size or 0,
        "attachmentContentType": message.attachment_content_type or "",
        "isImage": message.is_image(),
    }


def serialize_customer_chat_message(message):
    return serialize_chat_message(message, customer_safe=True)


def serialize_chat_messages(messages, customer_safe=False):
    return [serialize_chat_message(message, customer_safe=customer_safe) for message in messages]


def serialize_chat_session(session):
    return {
        "id": session.id,
        "chatCode": session.chat_code,
        "customerType": session.customer_type,
        "customerName": session.get_customer_display_name(),
        "customerPhone": session.get_customer_contact(),
        "status": session.status,
        "sourcePage": session.source_page or "",
        "lastMessagePreview": session.get_last_message_label(),
        "lastSenderType": normalize_sender_type(session.last_sender_type),
        "lastMessageAt": session.last_message_at.isoformat() if session.last_message_at else "",
        "lastMessageTimeLabel": timezone.localtime(session.last_message_at).strftime("%H:%M")
        if session.last_message_at
        else "",
        "adminUnreadCount": session.admin_unread_count,
        "customerUnreadCount": session.customer_unread_count,
        "isGuest": session.customer_type == "guest",
    }


def get_attachment_accept_string():
    return ",".join(sorted(ALLOWED_IMAGE_TYPES | ALLOWED_FILE_TYPES | ALLOWED_FILE_EXTENSIONS))
