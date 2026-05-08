from django.db import models
from django.contrib.auth.models import User


class StaffProfile(models.Model):
    GENDER_CHOICES = [
        ('Nam', 'Nam'),
        ('Nu', 'Nữ'),
        ('Khac', 'Khác'),
    ]

    user = models.OneToOneField(
        User, on_delete=models.CASCADE,
        related_name='staff_profile',
        verbose_name='Tài khoản người dùng'
    )
    phone = models.CharField(max_length=15, unique=True, verbose_name='Số điện thoại')
    full_name = models.CharField(max_length=100, verbose_name='Họ và tên')
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True, null=True, verbose_name='Giới tính')
    dob = models.DateField(blank=True, null=True, verbose_name='Ngày sinh')
    address = models.CharField(max_length=255, blank=True, null=True, verbose_name='Địa chỉ')
    notes = models.CharField(max_length=1000, blank=True, null=True, verbose_name='Ghi chú')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Thời điểm tạo hồ sơ')
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True, verbose_name='Thời điểm cập nhật gần nhất')

    class Meta:
        db_table = 'staff_profiles'
        verbose_name = 'Hồ sơ nhân viên'
        verbose_name_plural = 'Hồ sơ nhân viên'
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                check=models.Q(gender__in=['Nam', 'Nu', 'Khac']) | models.Q(gender__isnull=True),
                name='staffprofile_gender_valid'
            )
        ]

    def __str__(self):
        return f"{self.full_name} - {self.phone}"
