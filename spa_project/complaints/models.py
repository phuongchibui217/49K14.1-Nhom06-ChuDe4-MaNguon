from django.db import models, transaction
from django.contrib.auth.models import User


class Complaint(models.Model):
    STATUS_CHOICES = [
        ('NEW', 'Mới tạo'),
        ('IN_PROGRESS', 'Đang xử lý'),
        ('RESOLVED', 'Đã hoàn thành'),
    ]

    code = models.CharField(max_length=10, unique=True, blank=True, verbose_name='Mã khiếu nại')
    customer = models.ForeignKey(
        'customers.CustomerProfile', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='complaints', verbose_name='Khách hàng'
    )
    full_name = models.CharField(max_length=100, verbose_name='Họ và tên')
    phone = models.CharField(max_length=15, verbose_name='Số điện thoại')
    email = models.CharField(max_length=255, blank=True, null=True, verbose_name='Email')
    customer_name_snapshot = models.CharField(max_length=100, blank=True, null=True, verbose_name='Tên KH (snapshot)')
    customer_phone_snapshot = models.CharField(max_length=15, blank=True, null=True, verbose_name='SĐT KH (snapshot)')
    customer_email_snapshot = models.CharField(max_length=255, blank=True, null=True, verbose_name='Email KH (snapshot)')
    title = models.CharField(max_length=200, verbose_name='Tiêu đề khiếu nại')
    content = models.TextField(verbose_name='Nội dung khiếu nại')
    incident_date = models.DateTimeField(blank=True, null=True, verbose_name='Ngày xảy ra sự cố')
    appointment_code = models.CharField(max_length=10, blank=True, null=True, verbose_name='Mã lịch hẹn liên quan')
    related_service = models.ForeignKey(
        'spa_services.Service', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='Dịch vụ liên quan'
    )
    expected_solution = models.CharField(max_length=1000, blank=True, null=True, verbose_name='Giải pháp mong muốn')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='NEW', verbose_name='Trạng thái')
    assigned_to = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assigned_complaints', verbose_name='Người phụ trách'
    )
    resolution = models.TextField(blank=True, null=True, verbose_name='Kết quả xử lý')
    note = models.TextField(blank=True, null=True, verbose_name='Ghi chú nội bộ')
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name='Thời điểm giải quyết xong')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Thời điểm tạo')
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True, verbose_name='Thời điểm cập nhật')

    class Meta:
        db_table = 'complaints'
        verbose_name = 'Khiếu nại'
        verbose_name_plural = 'Khiếu nại'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['assigned_to']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(status__in=['NEW', 'IN_PROGRESS', 'RESOLVED']),
                name='complaint_status_valid'
            ),
            models.CheckConstraint(
                check=models.Q(resolved_at__isnull=True) | models.Q(resolved_at__gte=models.F('created_at')),
                name='complaint_resolved_at_valid'
            ),
        ]

    def __str__(self):
        return f"{self.code} - {self.title}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self._generate_code()
        super().save(*args, **kwargs)

    @classmethod
    def _generate_code(cls):
        prefix = 'KN'
        for attempt in range(100):
            with transaction.atomic():
                last = cls.objects.select_for_update().order_by('-id').first()
                if last and last.code and last.code.startswith(prefix):
                    try:
                        new_number = int(last.code[len(prefix):]) + 1 + attempt
                    except (ValueError, IndexError):
                        new_number = 1 + attempt
                else:
                    new_number = 1 + attempt
                new_code = f"{prefix}{new_number:04d}"
                if not cls.objects.filter(code=new_code).exists():
                    return new_code
        import time
        return f"{prefix}{int(time.time()) % 10000:04d}"


class ComplaintReply(models.Model):
    SENDER_ROLE_CHOICES = [
        ('CUSTOMER', 'Khách hàng'),
        ('STAFF', 'Nhân viên'),
        ('ADMIN', 'Quản trị viên'),
        ('SYSTEM', 'Hệ thống'),
    ]

    complaint = models.ForeignKey(
        Complaint, on_delete=models.CASCADE,
        related_name='replies', verbose_name='Khiếu nại'
    )
    sender = models.ForeignKey(
        User, on_delete=models.PROTECT, verbose_name='Người gửi'
    )
    sender_role = models.CharField(max_length=20, choices=SENDER_ROLE_CHOICES, verbose_name='Vai trò người gửi')
    sender_name = models.CharField(max_length=100, verbose_name='Tên người gửi')
    message = models.TextField(verbose_name='Nội dung phản hồi')
    is_internal = models.BooleanField(default=False, verbose_name='Ghi chú nội bộ')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Thời điểm gửi')

    class Meta:
        db_table = 'complaint_replies'
        verbose_name = 'Phản hồi khiếu nại'
        verbose_name_plural = 'Phản hồi khiếu nại'
        ordering = ['created_at']
        constraints = [
            models.CheckConstraint(
                check=models.Q(sender_role__in=['CUSTOMER', 'STAFF', 'ADMIN', 'SYSTEM']),
                name='complaintreply_sender_role_valid'
            ),
        ]

    def __str__(self):
        return f"Phản hồi {self.complaint.code} - {self.sender_name}"


class ComplaintHistory(models.Model):
    ACTION_CHOICES = [
        ('CREATE', 'Tạo khiếu nại'),
        ('UPDATE', 'Cập nhật'),
        ('ASSIGN', 'Phân công'),
        ('REPLY', 'Phản hồi'),
        ('RESOLVE', 'Hoàn thành'),
    ]

    complaint = models.ForeignKey(
        Complaint, on_delete=models.CASCADE,
        related_name='history', verbose_name='Khiếu nại'
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES, verbose_name='Hành động')
    old_value = models.TextField(blank=True, null=True, verbose_name='Giá trị cũ')
    new_value = models.TextField(blank=True, null=True, verbose_name='Giá trị mới')
    note = models.TextField(blank=True, null=True, verbose_name='Ghi chú')
    performed_by = models.ForeignKey(
        User, on_delete=models.PROTECT, verbose_name='Người thực hiện'
    )
    performed_at = models.DateTimeField(auto_now_add=True, verbose_name='Thời điểm thực hiện')

    class Meta:
        db_table = 'complaint_history'
        verbose_name = 'Lịch sử khiếu nại'
        verbose_name_plural = 'Lịch sử khiếu nại'
        ordering = ['-performed_at']
        indexes = [
            models.Index(fields=['complaint', '-performed_at']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(action__in=['CREATE', 'UPDATE', 'ASSIGN', 'REPLY', 'RESOLVE']),
                name='complainthistory_action_valid'
            ),
        ]

    def __str__(self):
        return f"{self.complaint.code} - {self.get_action_display()}"

    @classmethod
    def log(cls, complaint, action, old_value='', new_value='', note='', performed_by=None):
        return cls.objects.create(
            complaint=complaint,
            action=action,
            old_value=old_value,
            new_value=new_value,
            note=note,
            performed_by=performed_by
        )
