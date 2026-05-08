from django.contrib import admin
from .models import Complaint, ComplaintReply, ComplaintHistory


class ComplaintReplyInline(admin.TabularInline):
    """Inline cho phản hồi khiếu nại"""
    model = ComplaintReply
    extra = 0
    readonly_fields = ['sender', 'sender_role', 'sender_name', 'message', 'created_at']
    fields = ['sender_name', 'sender_role', 'message', 'is_internal', 'created_at']


class ComplaintHistoryInline(admin.TabularInline):
    """Inline cho lịch sử khiếu nại"""
    model = ComplaintHistory
    extra = 0
    readonly_fields = ['action', 'old_value', 'new_value', 'note', 'performed_by', 'performed_at']
    fields = ['action', 'old_value', 'new_value', 'note', 'performed_by', 'performed_at']


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    """Admin cho khiếu nại - Quản lý đầy đủ"""
    list_display = ['code', 'title', 'customer', 'status', 'assigned_to', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['code', 'title', 'customer__full_name', 'customer__phone', 'content']
    readonly_fields = ['code', 'created_at', 'updated_at', 'resolved_at']
    inlines = [ComplaintReplyInline, ComplaintHistoryInline]
    date_hierarchy = 'created_at'
    list_select_related = ['customer', 'assigned_to']
    fieldsets = (
        ('Thông tin khiếu nại', {
            'fields': ('code', 'customer', 'title', 'content')
        }),
        ('Thông tin liên hệ', {
            'fields': ('customer_name_snapshot', 'customer_phone_snapshot', 'customer_email_snapshot')
        }),
        ('Thông tin liên quan', {
            'fields': ('incident_date', 'appointment_code', 'related_service', 'expected_solution')
        }),
        ('Xử lý', {
            'fields': ('status', 'assigned_to', 'resolution', 'resolved_at')
        }),
        ('Thời gian', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('customer', 'assigned_to')


@admin.register(ComplaintReply)
class ComplaintReplyAdmin(admin.ModelAdmin):
    """Admin cho phản hồi khiếu nại"""
    list_display = ['complaint', 'sender_name', 'sender_role', 'is_internal', 'created_at']
    list_filter = ['sender_role', 'is_internal', 'created_at']
    search_fields = ['complaint__code', 'sender_name', 'message']
    readonly_fields = ['sender_name', 'created_at']


@admin.register(ComplaintHistory)
class ComplaintHistoryAdmin(admin.ModelAdmin):
    """Admin cho lịch sử khiếu nại"""
    list_display = ['complaint', 'action', 'old_value', 'new_value', 'performed_by', 'performed_at']
    list_filter = ['action', 'performed_at']
    search_fields = ['complaint__code', 'note']
    readonly_fields = ['complaint', 'action', 'old_value', 'new_value', 'note', 'performed_by', 'performed_at']
