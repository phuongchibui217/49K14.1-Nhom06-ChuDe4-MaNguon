"""
Models cho Appointments module.

Cấu trúc:
- Room: Phòng dịch vụ
- Booking: 1 lần đặt lịch (1 người đặt, có thể nhiều khách)
- Appointment: Từng khách / dịch vụ / phòng / khung giờ trong Booking
- Invoice: Hóa đơn của Booking
- InvoiceItem: Chi tiết từng dịch vụ trong hóa đơn
- InvoicePayment: Giao dịch thanh toán

Author: Spa ANA Team
"""

from django.db import models, transaction
from django.contrib.auth.models import User


# ============================================================
# ROOM
# ============================================================

class Room(models.Model):
    code = models.CharField(max_length=10, unique=True, verbose_name='Mã phòng')
    name = models.CharField(max_length=100, unique=True, verbose_name='Tên phòng')
    capacity = models.PositiveIntegerField(verbose_name='Sức chứa')
    is_active = models.BooleanField(default=True, verbose_name='Đang hoạt động')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Thời điểm tạo')
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True, verbose_name='Thời điểm cập nhật')

    class Meta:
        db_table = 'rooms'
        verbose_name = 'Phòng'
        verbose_name_plural = 'Phòng'
        ordering = ['code']
        constraints = [
            models.CheckConstraint(check=models.Q(capacity__gt=0), name='room_capacity_positive')
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"


# ============================================================
# BOOKING — 1 lần đặt lịch / 1 đơn đặt của người đặt
# ============================================================

class Booking(models.Model):
    STATUS_CHOICES = [
        ('PENDING',    'Chờ xác nhận'),
        ('CONFIRMED',  'Đã xác nhận'),
        ('CANCELLED',  'Đã hủy'),
        ('REJECTED',   'Đã từ chối'),
    ]
    PAYMENT_STATUS_CHOICES = [
        ('UNPAID',   'Chưa thanh toán'),
        ('PARTIAL',  'Thanh toán một phần'),
        ('PAID',     'Đã thanh toán'),
        ('REFUNDED', 'Đã hoàn tiền'),
    ]
    SOURCE_CHOICES = [
        ('DIRECT',   'Trực tiếp'),
        ('ONLINE',   'Đặt online'),
        ('PHONE',    'Điện thoại'),
        ('FACEBOOK', 'Facebook'),
        ('ZALO',     'Zalo'),
    ]

    # ── Mã đặt lịch ──────────────────────────────────────────────────────────
    booking_code = models.CharField(
        max_length=30, unique=True, db_index=True,
        verbose_name='Mã đặt lịch'
    )

    # ── Thông tin người đặt ───────────────────────────────────────────────────
    booker_name = models.CharField(max_length=100, verbose_name='Tên người đặt')
    booker_phone = models.CharField(max_length=15, verbose_name='SĐT người đặt')
    booker_email = models.CharField(
        max_length=255, blank=True, null=True, verbose_name='Email người đặt'
    )
    booker_notes = models.CharField(
        max_length=1000, blank=True, null=True, verbose_name='Ghi chú lần đặt lịch'
    )

    # ── Trạng thái ────────────────────────────────────────────────────────────
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='PENDING',
        db_index=True, verbose_name='Trạng thái'
    )
    payment_status = models.CharField(
        max_length=20, choices=PAYMENT_STATUS_CHOICES, default='UNPAID',
        verbose_name='Trạng thái thanh toán'
    )
    source = models.CharField(
        max_length=20, choices=SOURCE_CHOICES, default='DIRECT',
        verbose_name='Nguồn đặt lịch'
    )

    # ── Audit ─────────────────────────────────────────────────────────────────
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='bookings_created', verbose_name='Người tạo'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Thời điểm tạo')
    updated_at = models.DateTimeField(
        auto_now=True, null=True, blank=True, verbose_name='Thời điểm cập nhật'
    )

    # ── Soft delete / cancel ──────────────────────────────────────────────────
    deleted_at = models.DateTimeField(
        null=True, blank=True, verbose_name='Thời điểm xóa'
    )
    deleted_by_user = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='bookings_deleted', verbose_name='Người xóa'
    )
    cancelled_at = models.DateTimeField(
        null=True, blank=True, verbose_name='Thời điểm hủy'
    )

    class Meta:
        db_table = 'bookings'
        verbose_name = 'Đặt lịch'
        verbose_name_plural = 'Đặt lịch'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['booking_code'], name='booking_code_idx'),
            models.Index(fields=['status', 'source'], name='booking_status_source_idx'),
            models.Index(fields=['created_at'], name='booking_created_at_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(status__in=['PENDING', 'CONFIRMED', 'CANCELLED', 'REJECTED']),
                name='booking_status_valid'
            ),
            models.CheckConstraint(
                check=models.Q(payment_status__in=['UNPAID', 'PARTIAL', 'PAID', 'REFUNDED']),
                name='booking_payment_status_valid'
            ),
            models.CheckConstraint(
                check=models.Q(source__in=['DIRECT', 'ONLINE', 'PHONE', 'FACEBOOK', 'ZALO']),
                name='booking_source_valid'
            ),
        ]

    def __str__(self):
        return f"{self.booking_code} - {self.booker_name}"

    def save(self, *args, **kwargs):
        if not self.booking_code:
            self.booking_code = self._generate_code()
        super().save(*args, **kwargs)

    @classmethod
    def _generate_code(cls):
        """Tạo booking_code mới dạng BKxxxx.
        BUG-14: attempt chỉ dùng để retry khi race condition, không cộng vào số thứ tự.
        """
        prefix = 'BK'
        for attempt in range(100):
            with transaction.atomic():
                last = cls.objects.select_for_update().filter(
                    booking_code__startswith=prefix
                ).order_by('-booking_code').first()
                if last and last.booking_code:
                    try:
                        new_number = int(last.booking_code[len(prefix):]) + 1
                    except (ValueError, IndexError):
                        new_number = 1
                else:
                    new_number = 1
                new_code = f'{prefix}{new_number:04d}'
                if not cls.objects.filter(booking_code=new_code).exists():
                    return new_code
                # Code đã tồn tại (race condition) → thử lại với số tiếp theo
        import time
        return f'{prefix}{int(time.time()) % 10000:04d}'


# ============================================================
# APPOINTMENT — Từng khách / dịch vụ / phòng / khung giờ
# ============================================================

class Appointment(models.Model):
    STATUS_CHOICES = [
        ('NOT_ARRIVED', 'Chưa đến'),
        ('ARRIVED',     'Đã đến'),
        ('COMPLETED',   'Đã hoàn thành'),
        ('CANCELLED',   'Đã hủy'),
    ]

    # ── Mã lịch hẹn ──────────────────────────────────────────────────────────
    appointment_code = models.CharField(
        max_length=30, unique=True, blank=True, verbose_name='Mã lịch hẹn'
    )

    # ── Booking (đơn đặt lịch cha) ────────────────────────────────────────────
    booking = models.ForeignKey(
        Booking, on_delete=models.PROTECT,
        related_name='appointments', verbose_name='Đặt lịch'
    )

    # ── Khách hàng (nullable — khách đặt dùm có thể không có profile riêng) ──
    customer = models.ForeignKey(
        'customers.CustomerProfile', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='appointments', verbose_name='Khách hàng'
    )

    # ── Gói dịch vụ (nullable — khách có thể chọn sau khi tới) ───────────────
    service_variant = models.ForeignKey(
        'spa_services.ServiceVariant', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='appointments', verbose_name='Gói dịch vụ'
    )

    # ── Phòng ─────────────────────────────────────────────────────────────────
    room = models.ForeignKey(
        Room, on_delete=models.PROTECT,
        null=True, blank=True,
        verbose_name='Phòng'
    )

    # ── Snapshot thông tin khách tại thời điểm đặt ───────────────────────────
    customer_name_snapshot = models.CharField(
        max_length=100, verbose_name='Tên khách (snapshot)'
    )
    customer_phone_snapshot = models.CharField(
        max_length=15, blank=True, null=True, verbose_name='SĐT khách (snapshot)'
    )
    customer_email_snapshot = models.CharField(
        max_length=255, blank=True, null=True, verbose_name='Email khách (snapshot)'
    )

    # ── Ngày giờ ─────────────────────────────────────────────────────────────
    appointment_date = models.DateField(db_index=True, verbose_name='Ngày hẹn')
    appointment_time = models.TimeField(verbose_name='Giờ bắt đầu')

    # ── Trạng thái ────────────────────────────────────────────────────────────
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='NOT_ARRIVED',
        db_index=True, verbose_name='Trạng thái'
    )

    # ── Audit ─────────────────────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Thời điểm tạo')
    updated_at = models.DateTimeField(
        auto_now=True, null=True, blank=True, verbose_name='Thời điểm cập nhật'
    )

    # ── Soft delete ───────────────────────────────────────────────────────────
    deleted_at = models.DateTimeField(
        null=True, blank=True, verbose_name='Thời điểm xóa'
    )
    deleted_by_user = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='appointments_deleted', verbose_name='Người xóa'
    )

    class Meta:
        db_table = 'appointments'
        verbose_name = 'Lịch hẹn'
        verbose_name_plural = 'Lịch hẹn'
        ordering = ['-appointment_date', '-appointment_time']
        indexes = [
            models.Index(fields=['appointment_code'], name='appt_code_idx'),
            models.Index(fields=['booking'], name='appt_booking_idx'),
            models.Index(fields=['customer', 'appointment_date'], name='appt_customer_date_idx'),
            models.Index(fields=['status', 'appointment_date'], name='appt_status_date_idx'),
            models.Index(fields=['room', 'appointment_date'], name='appt_room_date_idx'),
            models.Index(fields=['appointment_date', 'appointment_time'], name='appt_datetime_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(status__in=[
                    'NOT_ARRIVED', 'ARRIVED', 'COMPLETED', 'CANCELLED',
                ]),
                name='appointment_status_valid'
            ),
        ]

    # ── Customer-facing status labels ─────────────────────────────────────────
    # Hiển thị dựa trên Booking.status + Appointment.status kết hợp
    CUSTOMER_STATUS_LABELS = {
        'NOT_ARRIVED': 'Đã xác nhận',
        'ARRIVED':     'Đã xác nhận',
        'COMPLETED':   'Hoàn thành',
        'CANCELLED':   'Đã hủy',
    }
    CUSTOMER_STATUS_CSS = {
        'NOT_ARRIVED': 'confirmed',
        'ARRIVED':     'confirmed',
        'COMPLETED':   'completed',
        'CANCELLED':   'cancelled',
    }

    @property
    def customer_status_label(self):
        """
        Trả về label hiển thị cho khách hàng.
        Ưu tiên Booking.status để phân biệt PENDING vs CONFIRMED.
        """
        if self.booking_id:
            try:
                bk_status = self.booking.status
                if bk_status == 'PENDING':
                    return 'Chờ xác nhận'
                if bk_status == 'REJECTED':
                    return 'Đã từ chối'
                if bk_status == 'CANCELLED':
                    return 'Đã hủy'
            except Exception:
                pass
        return self.CUSTOMER_STATUS_LABELS.get(self.status, self.get_status_display())

    @property
    def customer_status_css(self):
        """
        Trả về CSS class cho badge trạng thái.
        """
        if self.booking_id:
            try:
                bk_status = self.booking.status
                if bk_status == 'PENDING':
                    return 'pending'
                if bk_status in ('REJECTED', 'CANCELLED'):
                    return 'cancelled'
            except Exception:
                pass
        return self.CUSTOMER_STATUS_CSS.get(self.status, 'pending')

    @property
    def duration_minutes(self):
        """Lấy thời lượng từ service_variant nếu có, không lưu vào DB."""
        if self.service_variant_id:
            try:
                return self.service_variant.duration_minutes
            except Exception:
                pass
        return None

    def __str__(self):
        return f"{self.appointment_code} - {self.customer_name_snapshot}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.status == 'COMPLETED' and not self.service_variant_id:
            raise ValidationError('Không thể hoàn thành lịch hẹn khi chưa có dịch vụ')

    def save(self, *args, **kwargs):
        if not self.appointment_code:
            self.appointment_code = self._generate_code()
        super().save(*args, **kwargs)

    @classmethod
    def _generate_code(cls):
        """Tạo appointment_code mới dạng APPxxxx.
        BUG-14: attempt chỉ dùng để retry khi race condition, không cộng vào số thứ tự.
        """
        prefix = 'APP'
        for attempt in range(100):
            with transaction.atomic():
                last = cls.objects.select_for_update().filter(
                    appointment_code__startswith=prefix
                ).order_by('-appointment_code').first()
                if last:
                    try:
                        new_number = int(last.appointment_code[len(prefix):]) + 1
                    except (ValueError, IndexError):
                        new_number = 1
                else:
                    new_number = 1
                new_code = f'{prefix}{new_number:04d}'
                if not cls.objects.filter(appointment_code=new_code).exists():
                    return new_code
                # Code đã tồn tại (race condition) → thử lại với số tiếp theo
        import time
        return f'{prefix}{int(time.time()) % 10000:04d}'


# ============================================================
# INVOICE — Hóa đơn của Booking
# ============================================================

class Invoice(models.Model):
    STATUS_CHOICES = [
        ('UNPAID',    'Chưa thanh toán'),
        ('PARTIAL',   'Thanh toán một phần'),
        ('PAID',      'Đã thanh toán'),
        ('CANCELLED', 'Đã hủy'),
        ('REFUNDED',  'Đã hoàn tiền'),
    ]
    DISCOUNT_TYPE_CHOICES = [
        ('NONE',    'Không chiết khấu'),
        ('AMOUNT',  'Số tiền cố định (VNĐ)'),
        ('PERCENT', 'Phần trăm (%)'),
    ]

    code = models.CharField(max_length=10, unique=True, blank=True, verbose_name='Mã hóa đơn')
    booking = models.OneToOneField(
        Booking, on_delete=models.CASCADE,
        related_name='invoice', verbose_name='Đặt lịch'
    )
    subtotal_amount = models.DecimalField(
        max_digits=18, decimal_places=2, default=0,
        verbose_name='Tổng tiền trước chiết khấu'
    )
    # ── Chiết khấu ────────────────────────────────────────────────────────────
    discount_type = models.CharField(
        max_length=10, choices=DISCOUNT_TYPE_CHOICES, default='NONE',
        verbose_name='Loại chiết khấu'
    )
    discount_value = models.DecimalField(
        max_digits=18, decimal_places=2, default=0,
        verbose_name='Giá trị chiết khấu (số tiền hoặc %)'
    )
    discount_amount = models.DecimalField(
        max_digits=18, decimal_places=2, default=0,
        verbose_name='Số tiền chiết khấu thực tế'
    )
    # ─────────────────────────────────────────────────────────────────────────
    final_amount = models.DecimalField(
        max_digits=18, decimal_places=2, default=0,
        verbose_name='Thành tiền'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='UNPAID', verbose_name='Trạng thái')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Thời điểm tạo')
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT,
        related_name='invoices_created', verbose_name='Người tạo'
    )

    class Meta:
        db_table = 'invoices'
        verbose_name = 'Hóa đơn'
        verbose_name_plural = 'Hóa đơn'
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(check=models.Q(subtotal_amount__gte=0), name='invoice_subtotal_non_negative'),
            models.CheckConstraint(check=models.Q(discount_amount__gte=0), name='invoice_discount_non_negative'),
            models.CheckConstraint(check=models.Q(discount_value__gte=0),  name='invoice_discount_value_non_negative'),
            models.CheckConstraint(check=models.Q(final_amount__gte=0),    name='invoice_final_non_negative'),
            models.CheckConstraint(
                check=models.Q(discount_amount__lte=models.F('subtotal_amount')),
                name='invoice_discount_lte_subtotal'
            ),
            models.CheckConstraint(
                check=models.Q(status__in=['UNPAID', 'PARTIAL', 'PAID', 'CANCELLED', 'REFUNDED']),
                name='invoice_status_valid'
            ),
            models.CheckConstraint(
                check=models.Q(discount_type__in=['NONE', 'AMOUNT', 'PERCENT']),
                name='invoice_discount_type_valid'
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self._generate_code()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} - {self.booking.booking_code}"

    @classmethod
    def _generate_code(cls):
        """Tạo invoice code mới dạng INVxxxxx.
        BUG-14: attempt chỉ dùng để retry khi race condition, không cộng vào số thứ tự.
        """
        prefix = 'INV'
        for attempt in range(100):
            with transaction.atomic():
                last = cls.objects.select_for_update().order_by('-id').first()
                if last and last.code and last.code.startswith(prefix):
                    try:
                        new_number = int(last.code[len(prefix):]) + 1
                    except (ValueError, IndexError):
                        new_number = 1
                else:
                    new_number = 1
                new_code = f"{prefix}{new_number:05d}"
                if not cls.objects.filter(code=new_code).exists():
                    return new_code
                # Code đã tồn tại (race condition) → thử lại với số tiếp theo
        import time
        return f"{prefix}{int(time.time()) % 100000:05d}"


# ============================================================
# INVOICE ITEM — Chi tiết từng dịch vụ trong hóa đơn
# ============================================================

class InvoiceItem(models.Model):
    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE,
        related_name='items', verbose_name='Hóa đơn'
    )
    appointment = models.ForeignKey(
        Appointment, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='invoice_items', verbose_name='Lịch hẹn'
    )
    service_variant = models.ForeignKey(
        'spa_services.ServiceVariant', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='invoice_items', verbose_name='Gói dịch vụ'
    )
    description = models.CharField(max_length=500, blank=True, verbose_name='Mô tả')
    quantity = models.PositiveIntegerField(default=1, verbose_name='Số lượng')
    unit_price = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name='Đơn giá')
    line_total = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name='Thành tiền dòng')

    class Meta:
        db_table = 'invoice_items'
        verbose_name = 'Chi tiết hóa đơn'
        verbose_name_plural = 'Chi tiết hóa đơn'
        ordering = ['id']
        constraints = [
            models.CheckConstraint(check=models.Q(quantity__gt=0), name='invoice_item_quantity_positive'),
            models.CheckConstraint(check=models.Q(unit_price__gte=0), name='invoice_item_unit_price_non_negative'),
            models.CheckConstraint(check=models.Q(line_total__gte=0), name='invoice_item_line_total_non_negative'),
        ]

    def save(self, *args, **kwargs):
        self.line_total = self.unit_price * self.quantity
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.invoice.code} - {self.description or self.service_variant}"


# ============================================================
# INVOICE PAYMENT — Giao dịch thanh toán
# ============================================================

class InvoicePayment(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ('CASH',          'Tiền mặt'),
        ('CARD',          'Thẻ'),
        ('BANK_TRANSFER', 'Chuyển khoản'),
        ('E_WALLET',      'Ví điện tử'),
    ]
    TRANSACTION_STATUS_CHOICES = [
        ('PENDING',  'Chờ xử lý'),
        ('SUCCESS',  'Thành công'),
        ('FAILED',   'Thất bại'),
        ('REFUNDED', 'Đã hoàn tiền'),
    ]

    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE,
        related_name='payments', verbose_name='Hóa đơn'
    )
    amount = models.DecimalField(max_digits=18, decimal_places=2, verbose_name='Số tiền')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, verbose_name='Phương thức thanh toán')
    transaction_status = models.CharField(max_length=20, choices=TRANSACTION_STATUS_CHOICES, default='SUCCESS', verbose_name='Trạng thái giao dịch')
    paid_at = models.DateTimeField(auto_now_add=True, verbose_name='Thời điểm thanh toán')
    recorded_by = models.ForeignKey(
        User, on_delete=models.PROTECT,
        related_name='payments_recorded', verbose_name='Người ghi nhận'
    )
    recorded_no = models.CharField(max_length=100, blank=True, null=True, verbose_name='Mã giao dịch tham chiếu')
    note = models.CharField(max_length=500, blank=True, null=True, verbose_name='Ghi chú')

    class Meta:
        db_table = 'invoice_payments'
        verbose_name = 'Thanh toán'
        verbose_name_plural = 'Thanh toán'
        ordering = ['-paid_at']
        constraints = [
            models.CheckConstraint(check=models.Q(amount__gt=0), name='payment_amount_positive'),
            models.CheckConstraint(
                check=models.Q(payment_method__in=['CASH', 'CARD', 'BANK_TRANSFER', 'E_WALLET']),
                name='payment_method_valid'
            ),
            models.CheckConstraint(
                check=models.Q(transaction_status__in=['PENDING', 'SUCCESS', 'FAILED', 'REFUNDED']),
                name='payment_transaction_status_valid'
            ),
        ]

    def __str__(self):
        return f"{self.invoice.code} - {self.amount:,}đ"
