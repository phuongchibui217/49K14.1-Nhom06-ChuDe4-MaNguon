from django.db import models
from django.contrib.auth.models import User


class CustomerProfile(models.Model):
    GENDER_CHOICES = [
        ('Nam', 'Nam'),
        ('Nu', 'Nữ'),
        ('Khac', 'Khác'),
    ]

    user = models.OneToOneField(
        User, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='customer_profile',
        verbose_name='User'
    )
    phone = models.CharField(max_length=15, unique=True, verbose_name='Số điện thoại')
    full_name = models.CharField(max_length=100, verbose_name='Họ và tên')
    email = models.CharField(max_length=255, blank=True, null=True, unique=True, verbose_name='Email')
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True, null=True, verbose_name='Giới tính')
    dob = models.DateField(blank=True, null=True, verbose_name='Ngày sinh')
    address = models.CharField(max_length=255, blank=True, null=True, verbose_name='Địa chỉ')
    notes = models.CharField(max_length=1000, blank=True, null=True, verbose_name='Ghi chú')
    contact_channel = models.CharField(max_length=20, blank=True, null=True, verbose_name='Kênh liên hệ')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Thời điểm tạo hồ sơ')
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True, verbose_name='Thời điểm cập nhật gần nhất')

    class Meta:
        db_table = 'customer_profiles'
        verbose_name = 'Khách hàng'
        verbose_name_plural = 'Khách hàng'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['phone'])]
        constraints = [
            models.CheckConstraint(
                check=models.Q(gender__in=['Nam', 'Nu', 'Khac']) | models.Q(gender__isnull=True),
                name='customerprofile_gender_valid'
            )
        ]

    def __str__(self):
        return f"{self.full_name} - {self.phone}"
