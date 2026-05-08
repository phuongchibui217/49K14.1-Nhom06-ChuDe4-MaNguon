"""
Forms cho Service Management

File này chứa các forms cho:
- Tạo/cập nhật dịch vụ spa

"""

from django import forms
from PIL import Image

# Tạm import từ spa.models (CHƯA chuyển model trong phase này)
from .models import Service


# =====================================================
# SERVICE FORMS
# =====================================================

class ServiceForm(forms.ModelForm):
    """
    Form tạo/cập nhật dịch vụ

    VALIDATION RULES:
    - Mã dịch vụ: tự động sinh (DV0001, DV0002, ...)
    - Danh mục: bắt buộc chọn
    - Tên dịch vụ: bắt buộc, không chỉ số, không trùng
    - Mô tả: bắt buộc
    - Giá: bắt buộc, số dương
    - Thời gian: bắt buộc, số nguyên dương
    - Trạng thái: mặc định active
    - Hình ảnh: bắt buộc, chỉ jpg/jpeg/png/webp, max 5MB, min 300x300px
    """
    category_number = forms.ChoiceField(
        label='Danh mục',
        choices=[],  # load từ DB trong __init__
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'}),
        error_messages={'required': 'Vui lòng chọn danh mục'}
    )

    code = forms.CharField(
        label='Mã dịch vụ',
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nhập mã dịch vụ'
        }),
    )

    name = forms.CharField(
        label='Tên dịch vụ',
        max_length=200,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nhập tên dịch vụ...'
        }),
        error_messages={'required': 'Tên dịch vụ không hợp lệ'}
    )

    description = forms.CharField(
        label='Mô tả ngắn',
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Mô tả ngắn hiển thị ở trang danh sách (tối đa 255 ký tự)...',
            'maxlength': '255',
        }),
        help_text='Hiển thị ở trang danh sách dịch vụ. Để trống sẽ tự sinh từ mô tả chi tiết.',
    )

    detail_description = forms.CharField(
        label='Mô tả chi tiết',
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 5,
            'placeholder': 'Mô tả chi tiết hiển thị ở trang chi tiết dịch vụ. Để trống sẽ tự sinh.',
        }),
        help_text='Hiển thị ở trang chi tiết dịch vụ. Để trống sẽ tự sinh từ tên, danh mục và gói dịch vụ.',
    )

    status = forms.ChoiceField(
        label='Trạng thái',
        choices=[
            ('ACTIVE', 'Đang hoạt động'),
            ('INACTIVE', 'Ngừng hoạt động'),
        ],
        initial='ACTIVE',
        required=True,
        widget=forms.Select(attrs={
            'class': 'form-select'
        }),
        error_messages={'required': 'Vui lòng chọn trạng thái dịch vụ'}
    )

    image = forms.ImageField(
        label='Hình ảnh',
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': 'image/jpeg,image/jpg,image/png,image/webp'
        })
    )

    class Meta:
        model = Service
        fields = []
        # Không dùng trực tiếp fields từ model, ta đã định nghĩa ở trên

    def __init__(self, *args, **kwargs):
        """Load danh mục từ DB và set choices cho category_number field"""
        super().__init__(*args, **kwargs)
        from .models import ServiceCategory
        self.fields['category_number'].choices = [('', 'Chọn danh mục')] + [
            (cat.code, cat.name)
            for cat in ServiceCategory.objects.filter(status='ACTIVE').order_by('sort_order')
        ]

    def clean_code(self):
        """Validate mã dịch vụ: bắt buộc, unique (case-insensitive khi edit)"""
        code = self.cleaned_data.get('code', '').strip().upper()
        if not code:
            raise forms.ValidationError('Vui lòng nhập mã dịch vụ')
        qs = Service.objects.filter(code=code)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f'Mã dịch vụ "{code}" đã tồn tại')
        return code

    def clean_name(self):
        """Validate tên dịch vụ: không rỗng, không chỉ số, unique (case-insensitive)"""
        name = self.cleaned_data.get('name', '').strip()

        # Check if name is not empty
        if not name:
            raise forms.ValidationError('Tên dịch vụ không hợp lệ')

        # Check if name contains only numbers
        if name.isdigit():
            raise forms.ValidationError('Tên dịch vụ không hợp lệ')

        # Check if name already exists (case-insensitive, ignore extra spaces)
        normalized_name = ' '.join(name.split())
        existing_services = Service.objects.filter(name__iexact=normalized_name)

        # If editing, exclude current instance
        if self.instance and self.instance.pk:
            existing_services = existing_services.exclude(pk=self.instance.pk)

        if existing_services.exists():
            raise forms.ValidationError('Dịch vụ đã tồn tại')

        return name

    def clean_description(self):
        """Cắt short_description tối đa 255 ký tự (trả về chuỗi rỗng nếu null)"""
        value = self.cleaned_data.get('description', '').strip()
        return value[:255] if value else ''

    def clean_detail_description(self):
        """Return detail_description as-is (không validate, chỉ strip spaces)"""
        return self.cleaned_data.get('detail_description', '').strip()

    def clean_image(self):
        """Validate hình ảnh: bắt buộc khi tạo, optional khi edit, max 5MB, min 300x300px"""
        image = self.cleaned_data.get('image')

        # Nếu không upload ảnh mới
        if not image:
            # Đang edit và instance đã có ảnh → giữ nguyên (trả về False để Django không xóa)
            if self.instance and self.instance.pk and self.instance.image:
                return False  # False = "không thay đổi" với ImageField trong ModelForm
            raise forms.ValidationError('Vui lòng chọn hình ảnh dịch vụ')

        # Check file size (max 5MB)
        if image.size > 5 * 1024 * 1024:
            raise forms.ValidationError('Hình ảnh không được quá 5MB')

        # Check file type
        allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp']
        if image.content_type not in allowed_types:
            raise forms.ValidationError('Chỉ chấp nhận file ảnh (JPG, PNG, WebP)')

        # Check image dimensions (min 300x300)
        try:
            img = Image.open(image)
            width, height = img.size
            if width < 300 or height < 300:
                raise forms.ValidationError('Kích thước ảnh tối thiểu là 300x300px')
            image.seek(0)  # reset file pointer sau khi PIL đọc
        except forms.ValidationError:
            raise
        except Exception:
            raise forms.ValidationError('Có lỗi khi đọc hình ảnh')

        return image

    def clean_category_number(self):
        """Validate category được chọn và map code -> ServiceCategory object"""
        category_code = self.cleaned_data.get('category_number')
        if not category_code:
            raise forms.ValidationError('Vui lòng chọn danh mục')
        from .models import ServiceCategory
        try:
            return ServiceCategory.objects.get(code=category_code)
        except ServiceCategory.DoesNotExist:
            raise forms.ValidationError('Danh mục không tồn tại trong hệ thống')

    def save(self, commit=True):
        """Override save: map category_number->object, sinh mã code, xử lý descriptions"""
        service = super().save(commit=False)

        # Map category_number to ServiceCategory object
        service.category = self.cleaned_data.get('category_number')

        # Map status
        service.status = self.cleaned_data.get('status', 'ACTIVE')

        # Dùng mã do user nhập, hoặc tự sinh nếu để trống
        custom_code = self.cleaned_data.get('code', '').strip()
        if custom_code:
            service.code = custom_code
        elif not service.code:
            service.code = Service._generate_code()

        # short_description: từ field 'description' trong form
        short_desc = self.cleaned_data.get('description', '').strip()
        # detail description: từ field 'detail_description' trong form
        detail_desc = self.cleaned_data.get('detail_description', '').strip()

        # Nếu short_description trống, fallback sang detail_description cắt ngắn
        service.short_description = short_desc or (detail_desc[:255] if detail_desc else '')

        service.description = detail_desc

        if commit:
            service.save()

        return service
