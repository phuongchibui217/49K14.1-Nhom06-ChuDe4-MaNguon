from django.contrib.auth.models import User
from django.db import models, transaction


class ChatSession(models.Model):
    STATUS_CHOICES = [
        ('OPEN', 'Đang mở'),
        ('PENDING', 'Chờ xử lý'),
        ('CLOSED', 'Đã đóng'),
    ]

    customer = models.ForeignKey(
        'customers.CustomerProfile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='chat_sessions',
        verbose_name='Khách hàng',
    )
    guest_name = models.CharField(max_length=100, blank=True, null=True, verbose_name='Tên khách vãng lai')
    guest_phone = models.CharField(max_length=15, blank=True, null=True, verbose_name='SĐT khách vãng lai')
    guest_email = models.CharField(max_length=255, blank=True, null=True, verbose_name='Email khách vãng lai')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='OPEN', verbose_name='Trạng thái')
    started_at = models.DateTimeField(auto_now_add=True, verbose_name='Thời điểm bắt đầu phiên')
    closed_at = models.DateTimeField(null=True, blank=True, verbose_name='Thời điểm đóng phiên')
    last_message_at = models.DateTimeField(null=True, blank=True, verbose_name='Thời điểm tin nhắn cuối')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Thời điểm tạo')
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True, verbose_name='Thời điểm cập nhật')

    chat_code = models.CharField(max_length=20, unique=True, blank=True, verbose_name='Mã phiên chat')
    customer_type = models.CharField(max_length=20, default='guest', verbose_name='Loại khách')
    guest_session_key = models.CharField(max_length=64, null=True, blank=True, unique=True, verbose_name='Khóa phiên khách')
    source_page = models.CharField(max_length=255, blank=True, verbose_name='Trang bắt đầu chat')
    last_message_preview = models.CharField(max_length=255, blank=True, verbose_name='Xem trước tin nhắn cuối')
    last_sender_type = models.CharField(max_length=20, blank=True, verbose_name='Loại người gửi cuối')
    admin_unread_count = models.PositiveIntegerField(default=0, verbose_name='Tin chưa đọc phía admin')
    customer_unread_count = models.PositiveIntegerField(default=0, verbose_name='Tin chưa đọc phía khách')

    class Meta:
        db_table = 'chat_sessions'
        verbose_name = 'Phiên chat'
        verbose_name_plural = 'Phiên chat'
        ordering = ['-last_message_at', '-created_at']
        constraints = [
            models.CheckConstraint(
                check=models.Q(status__in=['OPEN', 'PENDING', 'CLOSED']),
                name='chatsession_status_valid',
            ),
            models.CheckConstraint(
                check=models.Q(closed_at__isnull=True) | models.Q(closed_at__gte=models.F('started_at')),
                name='chatsession_closed_at_valid',
            ),
            models.CheckConstraint(
                check=models.Q(last_message_at__isnull=True) | models.Q(last_message_at__gte=models.F('started_at')),
                name='chatsession_last_message_at_valid',
            ),
        ]

    def __str__(self):
        return f"{self.chat_code or self.pk} - {self.status}"

    def save(self, *args, **kwargs):
        if not self.chat_code:
            self.chat_code = self._generate_chat_code()
        super().save(*args, **kwargs)

    def get_customer_display_name(self):
        if self.customer and self.customer.full_name:
            return self.customer.full_name
        if self.customer and self.customer.phone:
            return self.customer.phone
        if self.guest_name:
            return self.guest_name
        return 'Khách vãng lai'

    def get_customer_contact(self):
        if self.customer and self.customer.phone:
            return self.customer.phone
        return self.guest_phone or ''

    def get_last_message_label(self):
        return self.last_message_preview or 'Chưa có tin nhắn'

    @classmethod
    def _generate_chat_code(cls):
        prefix = 'CHAT'
        for attempt in range(100):
            with transaction.atomic():
                last = cls.objects.select_for_update().filter(
                    chat_code__startswith=prefix,
                ).order_by('-id').first()
                if last and last.chat_code:
                    try:
                        new_number = int(last.chat_code[len(prefix):]) + 1 + attempt
                    except (TypeError, ValueError, IndexError):
                        new_number = 1 + attempt
                else:
                    new_number = 1 + attempt
                new_code = f'{prefix}{new_number:04d}'
                if not cls.objects.filter(chat_code=new_code).exists():
                    return new_code
        import time
        return f'{prefix}{int(time.time()) % 10000:04d}'


class ChatMessage(models.Model):
    SENDER_TYPE_CHOICES = [
        ('CUSTOMER', 'Khách hàng'),
        ('STAFF', 'Nhân viên'),
        ('SYSTEM', 'Hệ thống'),
        ('customer', 'Khách hàng (legacy)'),
        ('admin', 'Nhân viên (legacy)'),
        ('system', 'Hệ thống (legacy)'),
    ]
    DELIVERY_STATUS_CHOICES = [
        ('SENT', 'Đã gửi'),
        ('DELIVERED', 'Đã nhận'),
        ('READ', 'Đã đọc'),
        ('FAILED', 'Thất bại'),
        ('sent', 'Đã gửi (legacy)'),
    ]
    MESSAGE_TYPE_CHOICES = [
        ('text', 'Văn bản'),
        ('image', 'Hình ảnh'),
        ('file', 'Tệp tin'),
    ]

    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name='messages',
        verbose_name='Phiên chat',
    )
    sender_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='chat_messages_sent',
        verbose_name='Người gửi',
    )
    sender = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='chat_messages_sent_legacy',
        verbose_name='Người gửi (legacy)',
    )
    sender_type = models.CharField(max_length=20, verbose_name='Loại người gửi')
    sender_name = models.CharField(max_length=200, blank=True, verbose_name='Tên người gửi')
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPE_CHOICES, default='text', verbose_name='Loại tin nhắn')
    content = models.TextField(blank=True, null=True, verbose_name='Nội dung tin nhắn')
    attachment_url = models.CharField(max_length=500, blank=True, null=True, verbose_name='URL tệp đính kèm')
    attachment = models.FileField(upload_to='chat/attachments/', null=True, blank=True, verbose_name='Tệp đính kèm')
    attachment_name = models.CharField(max_length=255, blank=True, verbose_name='Tên file')
    attachment_size = models.PositiveBigIntegerField(default=0, verbose_name='Kích thước file')
    attachment_content_type = models.CharField(max_length=120, blank=True, verbose_name='Kiểu file')
    client_message_id = models.CharField(max_length=64, null=True, blank=True, verbose_name='Mã tin nhắn client')
    sent_at = models.DateTimeField(auto_now_add=True, verbose_name='Thời điểm gửi')
    delivery_status = models.CharField(max_length=20, default='SENT', verbose_name='Trạng thái gửi')
    status = models.CharField(max_length=20, default='sent', verbose_name='Trạng thái (legacy)')
    is_read = models.BooleanField(default=False, verbose_name='Đã đọc')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Thời điểm tạo')
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True, verbose_name='Thời điểm cập nhật')

    class Meta:
        db_table = 'chat_messages'
        verbose_name = 'Tin nhắn chat'
        verbose_name_plural = 'Tin nhắn chat'
        ordering = ['created_at', 'id']

    def __str__(self):
        return f"Session #{self.session_id} - {self.sender_type}"

    def is_image(self):
        return self.message_type == 'image'

    def get_preview_text(self):
        if self.message_type == 'image':
            return self.attachment_name or 'Hình ảnh'
        if self.message_type == 'file':
            return self.attachment_name or 'Tệp đính kèm'
        return (self.content or '').strip()


class SessionStaff(models.Model):
    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name='session_staff',
        verbose_name='Phiên chat',
    )
    staff = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='chat_sessions_joined',
        verbose_name='Nhân viên',
    )
    join_at = models.DateTimeField(auto_now_add=True, verbose_name='Thời điểm tham gia')

    class Meta:
        db_table = 'session_staff'
        verbose_name = 'Nhân viên phiên chat'
        verbose_name_plural = 'Nhân viên phiên chat'
        constraints = [
            models.UniqueConstraint(
                fields=['session', 'staff'],
                name='sessionstaff_session_staff_unique',
            ),
        ]

    def __str__(self):
        return f"Session #{self.session_id} - Staff #{self.staff_id}"
