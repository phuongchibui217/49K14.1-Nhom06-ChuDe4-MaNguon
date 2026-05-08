from django.db import models, transaction
from django.contrib.auth.models import User
from django.utils.text import slugify
from django.core.validators import MinValueValidator


class ServiceCategory(models.Model):
    STATUS_CHOICES = [
        ('ACTIVE', 'Đang hoạt động'),
        ('INACTIVE', 'Ngừng hoạt động'),
    ]

    code = models.CharField(max_length=10, unique=True, verbose_name='Mã danh mục')
    name = models.CharField(max_length=100, unique=True, verbose_name='Tên danh mục')
    slug = models.SlugField(max_length=120, unique=True, blank=True, null=True, verbose_name='Slug')
    description = models.CharField(max_length=255, blank=True, null=True, verbose_name='Mô tả')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE', verbose_name='Trạng thái')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Thứ tự hiển thị')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Thời điểm tạo')
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True, verbose_name='Thời điểm cập nhật')

    class Meta:
        db_table = 'service_categories'
        verbose_name = 'Danh mục dịch vụ'
        verbose_name_plural = 'Danh mục dịch vụ'
        ordering = ['sort_order', 'name']
        constraints = [
            models.CheckConstraint(
                check=models.Q(status__in=['ACTIVE', 'INACTIVE']),
                name='servicecategory_status_valid'
            ),
            models.CheckConstraint(
                check=models.Q(sort_order__gte=0),
                name='servicecategory_sort_order_non_negative'
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.slug and self.name:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Service(models.Model):
    STATUS_CHOICES = [
        ('ACTIVE', 'Đang hoạt động'),
        ('INACTIVE', 'Ngừng hoạt động'),
    ]

    category = models.ForeignKey(
        ServiceCategory, on_delete=models.PROTECT,
        related_name='services', verbose_name='Danh mục'
    )
    code = models.CharField(max_length=10, unique=True, blank=True, verbose_name='Mã dịch vụ')
    name = models.CharField(max_length=150, verbose_name='Tên dịch vụ')
    slug = models.SlugField(max_length=150, unique=True, blank=True, null=True, verbose_name='Slug')
    short_description = models.CharField(max_length=255, blank=True, null=True, verbose_name='Mô tả ngắn')
    description = models.TextField(blank=True, null=True, verbose_name='Mô tả chi tiết')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE', verbose_name='Trạng thái')
    # ImageField tự quản lý upload_to, lưu relative path trong DB (vd: services/abc.jpg)
    # File vật lý được lưu vào MEDIA_ROOT/services/ và serve qua MEDIA_URL
    # KHÔNG dùng CharField để lưu path thủ công — sẽ mất khả năng .url và validation
    image = models.ImageField(
        upload_to='services/',
        blank=False,
        null=False,
        default='',
        verbose_name='Hình ảnh dịch vụ'
    )
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT,
        related_name='services_created', verbose_name='Người tạo'
    )
    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='services_updated', verbose_name='Người cập nhật'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Thời điểm tạo')
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True, verbose_name='Thời điểm cập nhật')

    class Meta:
        db_table = 'services'
        verbose_name = 'Dịch vụ'
        verbose_name_plural = 'Dịch vụ'
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                check=models.Q(status__in=['ACTIVE', 'INACTIVE']),
                name='service_status_valid'
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.slug and self.name:
            self.slug = slugify(self.name)
        if not self.code:
            self.code = self._generate_code()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} - {self.name}"

    def get_category_name(self):
        """Trả về tên danh mục"""
        return self.category.name if self.category else ''

    def get_image_url(self):
        """
        Trả về URL ảnh dịch vụ hoặc ảnh placeholder nếu không có.
        Dùng field.url để Django tự tính đúng MEDIA_URL — không hard-code path.
        """
        if self.image:
            try:
                return self.image.url   # '/media/services/massage.jpg' (MEDIA_URL + name)
            except Exception:
                pass
        return "https://images.unsplash.com/photo-1570172619644-dfd03ed5d881?w=400"

    @classmethod
    def _generate_code(cls):
        prefix = 'DV'
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
        return f"{prefix}{int(time.time()) % 100000:05d}"


class ServiceVariant(models.Model):
    """
    Gói dịch vụ — 1 dịch vụ có thể có nhiều gói khác nhau về thời gian và giá.

    Ví dụ:
        Massage body
          ├── 60 phút - 200,000đ
          ├── 90 phút - 280,000đ
          └── 120 phút - 350,000đ
    """
    service = models.ForeignKey(
        Service, on_delete=models.CASCADE,
        related_name='variants', verbose_name='Dịch vụ'
    )
    label = models.CharField(max_length=100, verbose_name='Tên gói',
                             help_text='Ví dụ: 60 phút, 90 phút, Gói cơ bản...')
    duration_minutes = models.PositiveIntegerField(verbose_name='Thời lượng (phút)')
    price = models.DecimalField(
        max_digits=18, decimal_places=2,
        validators=[MinValueValidator(0)],
        verbose_name='Giá (VNĐ)'
    )
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Thứ tự hiển thị')

    class Meta:
        db_table = 'service_variants'
        verbose_name = 'Gói dịch vụ'
        verbose_name_plural = 'Gói dịch vụ'
        ordering = ['sort_order', 'duration_minutes']
        constraints = [
            models.CheckConstraint(
                check=models.Q(duration_minutes__gt=0),
                name='variant_duration_positive'
            ),
            models.CheckConstraint(
                check=models.Q(price__gte=0),
                name='variant_price_non_negative'
            ),
        ]

    def __str__(self):
        return f"{self.service.name} — {self.label} ({self.duration_minutes} phút)"
