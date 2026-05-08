from django.contrib import admin
from .models import Room, Booking, Appointment, Invoice, InvoiceItem, InvoicePayment


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    search_fields = ['code', 'name']
    list_display  = ['code', 'name', 'capacity', 'is_active', 'created_at']
    list_filter   = ['is_active']
    list_editable = ['is_active', 'capacity']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display  = ['booking_code', 'booker_name', 'booker_phone', 'status', 'payment_status', 'source', 'created_at']
    list_filter   = ['status', 'payment_status', 'source', 'created_at']
    search_fields = ['booking_code', 'booker_name', 'booker_phone', 'booker_email']
    readonly_fields = ['booking_code', 'created_at', 'updated_at']
    fieldsets = (
        ('Mã đặt lịch', {'fields': ('booking_code',)}),
        ('Người đặt', {'fields': ('booker_name', 'booker_phone', 'booker_email', 'booker_notes', 'source')}),
        ('Trạng thái', {'fields': ('status', 'payment_status')}),
        ('Audit', {'fields': ('created_by', 'created_at', 'updated_at', 'deleted_at', 'deleted_by_user', 'cancelled_at'), 'classes': ('collapse',)}),
    )


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display  = ['appointment_code', 'booking', 'customer', 'service_variant', 'room', 'appointment_date', 'appointment_time', 'status']
    list_filter   = ['status', 'appointment_date']
    search_fields = ['appointment_code', 'customer__full_name', 'customer__phone', 'customer_name_snapshot', 'booking__booking_code', 'booking__booker_name']
    readonly_fields = ['appointment_code', 'created_at', 'updated_at']
    date_hierarchy = 'appointment_date'
    fieldsets = (
        ('Mã lịch hẹn', {'fields': ('appointment_code',)}),
        ('Đặt lịch', {'fields': ('booking',)}),
        ('Khách sử dụng dịch vụ', {'fields': ('customer', 'customer_name_snapshot', 'customer_phone_snapshot', 'customer_email_snapshot')}),
        ('Dịch vụ & Phòng', {'fields': ('service_variant', 'room')}),
        ('Thời gian', {'fields': ('appointment_date', 'appointment_time')}),
        ('Trạng thái', {'fields': ('status',)}),
        ('Audit', {'fields': ('created_at', 'updated_at', 'deleted_at', 'deleted_by_user'), 'classes': ('collapse',)}),
    )


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0
    readonly_fields = ['line_total']


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display  = ['code', 'booking', 'subtotal_amount', 'discount_amount', 'final_amount', 'status', 'created_at']
    list_filter   = ['status']
    search_fields = ['code', 'booking__booking_code', 'booking__booker_name']
    readonly_fields = ['code', 'created_at']
    inlines = [InvoiceItemInline]
