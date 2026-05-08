"""
Validators dùng chung cho Spa ANA

File này chứa các hàm validation có thể tái sử dụng ở:
- Forms (forms.py)
- API views (views.py)
- Services (services.py)

Mục đích:
- Tránh lặp code (DRY - Don't Repeat Yourself)
- Dễ bảo trì: sửa 1 chỗ, cập nhật everywhere
- Nhất quán: message lỗi giống nhau ở mọi nơi

Author: Spa ANA Team
"""

import re
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile


# =====================================================
# SERVICE VALIDATORS
# =====================================================

def validate_service_name(name, exclude_id=None):
    """
    Validate tên dịch vụ

    Quy tắc:
    - Không được rỗng
    - Không được chỉ chứa số
    - Độ dài: 5-200 ký tự
    - Không được trùng (case-insensitive)

    Args:
        name: str - tên dịch vụ cần validate
        exclude_id: int - ID dịch vụ cần loại trừ (khi edit)

    Returns:
        str - tên đã được chuẩn hóa

    Raises:
        ValidationError: Nếu không hợp lệ
    """
    from spa_services.models import Service

    # Chuẩn hóa: strip và collapse spaces
    name = ' '.join(name.strip().split()) if name else ''

    # Check rỗng
    if not name:
        raise ValidationError('Vui lòng nhập tên dịch vụ.')

    # Check độ dài tối thiểu
    if len(name) < 5:
        raise ValidationError('Tên dịch vụ phải có ít nhất 5 ký tự.')

    # Check độ dài tối đa
    if len(name) > 200:
        raise ValidationError('Tên dịch vụ không được quá 200 ký tự.')

    # Check không được chỉ chứa số
    if name.isdigit():
        raise ValidationError('Tên dịch vụ không được chỉ chứa số.')

    # Check trùng (case-insensitive)
    existing = Service.objects.filter(name__iexact=name)
    if exclude_id:
        existing = existing.exclude(id=exclude_id)

    if existing.exists():
        raise ValidationError(f'Dịch vụ "{name}" đã tồn tại.')

    return name


def validate_service_price(price):
    """
    Validate giá dịch vụ

    Quy tắc:
    - Phải là số dương
    - Không được âm
    - Tối đa 999,999,999 VNĐ

    Args:
        price: số (int/float/Decimal)

    Returns:
        số - giá đã validate

    Raises:
        ValidationError: Nếu không hợp lệ
    """
    if price is None:
        raise ValidationError('Vui lòng nhập giá dịch vụ.')

    try:
        price = float(price)
    except (ValueError, TypeError):
        raise ValidationError('Giá dịch vụ không hợp lệ.')

    if price < 0:
        raise ValidationError('Giá dịch vụ không được âm.')

    if price > 999999999:
        raise ValidationError('Giá dịch vụ không được quá 999,999,999 VNĐ.')

    return price


def validate_service_duration(duration):
    """
    Validate thời lượng dịch vụ

    Quy tắc:
    - Tối thiểu: 5 phút
    - Tối đa: 480 phút (8 tiếng)

    Args:
        duration: int - số phút

    Returns:
        int - thời lượng đã validate

    Raises:
        ValidationError: Nếu không hợp lệ
    """
    if duration is None:
        raise ValidationError('Vui lòng nhập thời gian dịch vụ.')

    try:
        duration = int(duration)
    except (ValueError, TypeError):
        raise ValidationError('Thời gian không hợp lệ.')

    if duration < 5:
        raise ValidationError('Thời gian phải ít nhất 5 phút.')

    if duration > 480:
        raise ValidationError('Thời gian không được quá 480 phút (8 tiếng).')

    return duration


def validate_service_image(image):
    """
    Validate hình ảnh dịch vụ

    Quy tắc:
    - File type: JPG, JPEG, PNG, WEBP
    - Max size: 5MB
    - Min dimension: 300x300px

    Args:
        image: UploadedFile - file ảnh

    Returns:
        UploadedFile - file đã validate

    Raises:
        ValidationError: Nếu không hợp lệ
    """
    if not image:
        raise ValidationError('Vui lòng chọn hình ảnh dịch vụ.')

    # Check file size (max 5MB)
    if image.size > 5 * 1024 * 1024:
        raise ValidationError('Hình ảnh không được quá 5MB.')

    # Check file type
    allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp']
    if image.content_type not in allowed_types:
        raise ValidationError('Chỉ chấp nhận file ảnh (JPG, PNG, WebP).')

    # Check image dimensions
    try:
        from PIL import Image
        img = Image.open(image)
        width, height = img.size

        if width < 300 or height < 300:
            raise ValidationError('Kích thước ảnh tối thiểu là 300x300px.')

        # Reset file pointer sau khi PIL đọc
        image.seek(0)

    except Exception as e:
        raise ValidationError(f'Có lỗi khi đọc hình ảnh: {str(e)}')

    return image


def validate_service_description(description):
    """
    Validate mô tả dịch vụ

    Quy tắc:
    - Không được rỗng

    Args:
        description: str

    Returns:
        str - mô tả đã chuẩn hóa

    Raises:
        ValidationError: Nếu không hợp lệ
    """
    description = description.strip() if description else ''

    if not description:
        raise ValidationError('Vui lòng nhập mô tả dịch vụ.')

    return description


# =====================================================
# CUSTOMER VALIDATORS
# =====================================================

def is_valid_vn_phone(phone_digits: str) -> bool:
    """
    Kiểm tra định dạng SĐT Việt Nam.
    Quy tắc: đúng 10 chữ số, bắt đầu bằng 0.
    """
    return bool(re.match(r'^0\d{9}$', phone_digits))


def validate_phone_number(phone, check_exists=False, exclude_phone=None):
    """
    Validate số điện thoại

    Quy tắc:
    - Không được rỗng
    - Chỉ chứa số
    - Đúng 10 số, bắt đầu bằng 0 (format SĐT Việt Nam)
    - (Optional) Check đã tồn tại trong DB

    Args:
        phone: str - số điện thoại
        check_exists: bool - có check trùng trong DB không
        exclude_phone: str - số điện thoại cần loại trừ (khi edit)

    Returns:
        str - số điện thoại đã chuẩn hóa (chỉ còn số)

    Raises:
        ValidationError: Nếu không hợp lệ
    """
    from customers.models import CustomerProfile

    if not phone:
        raise ValidationError('Vui lòng nhập số điện thoại.')

    # Chuẩn hóa: chỉ giữ lại số
    phone_clean = ''.join(filter(str.isdigit, str(phone)))

    if not is_valid_vn_phone(phone_clean):
        raise ValidationError('Số điện thoại không hợp lệ (phải có 10 số và bắt đầu bằng 0).')

    # Check trùng trong DB (nếu yêu cầu)
    if check_exists:
        existing = CustomerProfile.objects.filter(phone=phone_clean)
        if exclude_phone:
            existing = existing.exclude(phone=exclude_phone)

        if existing.exists():
            raise ValidationError('Số điện thoại này đã được đăng ký.')

    return phone_clean


def validate_customer_name(name):
    """
    Validate tên khách hàng

    Quy tắc:
    - Không được rỗng
    - Độ dài: 2-200 ký tự

    Args:
        name: str

    Returns:
        str - tên đã chuẩn hóa

    Raises:
        ValidationError: Nếu không hợp lệ
    """
    name = ' '.join(name.strip().split()) if name else ''

    if not name:
        raise ValidationError('Vui lòng nhập tên khách hàng.')

    if len(name) < 2:
        raise ValidationError('Tên phải có ít nhất 2 ký tự.')

    if len(name) > 200:
        raise ValidationError('Tên không được quá 200 ký tự.')

    return name


# =====================================================
# APPOINTMENT VALIDATORS
# =====================================================

def validate_appointment_notes(notes, max_length=500):
    """
    Validate ghi chú lịch hẹn

    Args:
        notes: str
        max_length: int - độ dài tối đa

    Returns:
        str - ghi chú đã chuẩn hóa
    """
    notes = notes.strip() if notes else ''

    if len(notes) > max_length:
        raise ValidationError(f'Ghi chú không được quá {max_length} ký tự.')

    return notes


def validate_guests_count(guests, max_guests=10):
    """
    Validate số lượng khách

    Args:
        guests: int
        max_guests: int - số khách tối đa

    Returns:
        int - số khách đã validate

    Raises:
        ValidationError: Nếu không hợp lệ
    """
    try:
        guests = int(guests)
    except (ValueError, TypeError):
        raise ValidationError('Số khách không hợp lệ.')

    if guests < 1:
        raise ValidationError('Số khách phải ít nhất là 1.')

    if guests > max_guests:
        raise ValidationError(f'Số khách không được quá {max_guests} người.')

    return guests


# =====================================================
# COMPLAINT VALIDATORS
# =====================================================

def validate_complaint_title(title):
    """
    Validate tiêu đề khiếu nại

    Quy tắc:
    - Không rỗng
    - Độ dài: 5-200 ký tự

    Args:
        title: str

    Returns:
        str - tiêu đề đã chuẩn hóa

    Raises:
        ValidationError: Nếu không hợp lệ
    """
    title = ' '.join(title.strip().split()) if title else ''

    if not title:
        raise ValidationError('Vui lòng nhập tiêu đề khiếu nại.')

    if len(title) < 5:
        raise ValidationError('Tiêu đề phải có ít nhất 5 ký tự.')

    if len(title) > 200:
        raise ValidationError('Tiêu đề không được quá 200 ký tự.')

    return title


def validate_complaint_content(content):
    """
    Validate nội dung khiếu nại

    Quy tắc:
    - Không rỗng
    - Độ dài: 10-2000 ký tự

    Args:
        content: str

    Returns:
        str - nội dung đã chuẩn hóa

    Raises:
        ValidationError: Nếu không hợp lệ
    """
    content = content.strip() if content else ''

    if not content:
        raise ValidationError('Vui lòng nhập nội dung khiếu nại.')

    if len(content) < 10:
        raise ValidationError('Nội dung phải có ít nhất 10 ký tự.')

    if len(content) > 2000:
        raise ValidationError('Nội dung không được quá 2000 ký tự.')

    return content


def validate_reply_message(message):
    """
    Validate nội dung phản hồi

    Quy tắc:
    - Không rỗng
    - Độ dài: 3-1000 ký tự

    Args:
        message: str

    Returns:
        str - nội dung đã chuẩn hóa

    Raises:
        ValidationError: Nếu không hợp lệ
    """
    message = message.strip() if message else ''

    if not message:
        raise ValidationError('Vui lòng nhập nội dung phản hồi.')

    if len(message) < 3:
        raise ValidationError('Nội dung phản hồi phải có ít nhất 3 ký tự.')

    if len(message) > 1000:
        raise ValidationError('Nội dung phản hồi không được quá 1000 ký tự.')

    return message


# =====================================================
# HELPER FUNCTIONS
# =====================================================

def validate_required(value, field_name='Trường này'):
    """
    Validate trường bắt buộc

    Args:
        value: giá trị cần check
        field_name: str - tên trường để hiển thị trong message

    Returns:
        value - giá trị đã strip (nếu là string)

    Raises:
        ValidationError: Nếu rỗng
    """
    if value is None:
        raise ValidationError(f'{field_name} không được để trống.')

    if isinstance(value, str):
        value = value.strip()
        if not value:
            raise ValidationError(f'{field_name} không được để trống.')

    return value


def validate_length(value, min_len=None, max_len=None, field_name='Trường này'):
    """
    Validate độ dài chuỗi

    Args:
        value: str
        min_len: int - độ dài tối thiểu (optional)
        max_len: int - độ dài tối đa (optional)
        field_name: str - tên trường

    Returns:
        str - giá trị đã validate

    Raises:
        ValidationError: Nếu không hợp lệ
    """
    value = str(value).strip() if value else ''

    if min_len is not None and len(value) < min_len:
        raise ValidationError(f'{field_name} phải có ít nhất {min_len} ký tự.')

    if max_len is not None and len(value) > max_len:
        raise ValidationError(f'{field_name} không được quá {max_len} ký tự.')

    return value


def validate_integer(value, min_val=None, max_val=None, field_name='Giá trị'):
    """
    Validate số nguyên

    Args:
        value: giá trị cần check
        min_val: int - giá trị tối thiểu (optional)
        max_val: int - giá trị tối đa (optional)
        field_name: str - tên trường

    Returns:
        int - giá trị đã validate

    Raises:
        ValidationError: Nếu không hợp lệ
    """
    try:
        value = int(value)
    except (ValueError, TypeError):
        raise ValidationError(f'{field_name} phải là số nguyên.')

    if min_val is not None and value < min_val:
        raise ValidationError(f'{field_name} phải lớn hơn hoặc bằng {min_val}.')

    if max_val is not None and value > max_val:
        raise ValidationError(f'{field_name} phải nhỏ hơn hoặc bằng {max_val}.')

    return value


# =====================================================
# VALIDATION RESULT HELPER
# =====================================================

class ValidationResult:
    """
    Class helper để trả kết quả validation

    Thay vì raise exception, có thể dùng class này để:
    - Gom nhiều lỗi cùng lúc
    - Dễ dùng trong API (trả về JSON)

    Usage:
        result = ValidationResult()
        result.add_error('name', 'Tên không hợp lệ')
        result.add_error('price', 'Giá phải dương')

        if not result.is_valid:
            return JsonResponse({'errors': result.errors}, status=400)
    """

    def __init__(self):
        self.errors = {}

    def add_error(self, field, message):
        """Thêm lỗi cho một field"""
        if field not in self.errors:
            self.errors[field] = []
        self.errors[field].append(message)

    @property
    def is_valid(self):
        """Check có hợp lệ không"""
        return len(self.errors) == 0

    def get_first_error(self):
        """Lấy lỗi đầu tiên (dùng cho API trả 1 lỗi)"""
        if self.errors:
            first_field = list(self.errors.keys())[0]
            return self.errors[first_field][0]
        return None

    def to_dict(self):
        """Convert thành dict"""
        return {
            'valid': self.is_valid,
            'errors': self.errors
        }
