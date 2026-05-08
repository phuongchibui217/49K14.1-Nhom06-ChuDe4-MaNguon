from django.contrib import admin

from .models import ChatMessage, ChatSession, SessionStaff


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    readonly_fields = ['sender_type', 'sender_user', 'content', 'attachment_url', 'sent_at']
    fields = ['sender_type', 'sender_user', 'content', 'attachment_url', 'sent_at']


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ['id', 'customer', 'guest_name', 'status', 'last_message_at', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['customer__full_name', 'customer__phone', 'guest_name', 'guest_phone']
    readonly_fields = ['started_at', 'last_message_at', 'created_at', 'updated_at', 'closed_at']
    inlines = [ChatMessageInline]


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ['session', 'sender_type', 'sender_user', 'delivery_status', 'sent_at']
    list_filter = ['sender_type', 'delivery_status', 'sent_at']
    search_fields = ['session__id', 'content']
    readonly_fields = ['session', 'sender_user', 'sender_type', 'content', 'attachment_url', 'sent_at', 'created_at', 'updated_at']


@admin.register(SessionStaff)
class SessionStaffAdmin(admin.ModelAdmin):
    list_display = ['session', 'staff', 'join_at']
