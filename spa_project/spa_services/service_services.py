"""
Service Services - Business logic cho Service model

File này chứa các hàm xử lý nghiệp vụ liên quan đến Service:
- Validation dữ liệu dịch vụ
- Tạo/Cập nhật dịch vụ
- Helper functions

Tách ra khỏi views.py để:
- Code gọn hơn, dễ đọc
- Dùng lại được ở nhiều nơi (DRY)
- Dễ test riêng biệt
Author: Spa ANA Team
"""

from django.core.exceptions import ValidationError
from django.utils.text import slugify

# Tạm import từ spa.models (CHƯA chuyển model trong phase này)
from .models import Service


# =====================================================
# VALIDATION SERVICES
# =====================================================

def validate_service_name(name, exclude_id=None):
    """
    Validate tên dịch vụ

    Quy tắc:
    - Không được để trống
    - Độ dài 5-200 ký tự
    - Không được trùng (case-insensitive)

    Args:
        name: str - Tên dịch vụ cần validate
        exclude_id: int - ID dịch vụ cần loại trừ (khi update)

    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    if not name:
        return (False, 'Vui lòng nhập tên dịch vụ!')

    name = name.strip()

    if len(name) < 5:
        return (False, 'Tên dịch vụ phải có ít nhất 5 ký tự!')

    if len(name) > 200:
        return (False, 'Tên dịch vụ không được quá 200 ký tự!')

    # Check trùng tên (case-insensitive)
    queryset = Service.objects.filter(name__iexact=name)
    if exclude_id:
        queryset = queryset.exclude(id=exclude_id)

    if queryset.exists():
        return (False, f'Dịch vụ "{name}" đã tồn tại!')

    return (True, '')


def validate_service_price(price_str):
    """
    Validate giá dịch vụ

    Quy tắc:
    - Phải là số hợp lệ
    - Không được âm
    - Không được quá 999,999,999 VNĐ

    Args:
        price_str: str hoặc number - Giá cần validate

    Returns:
        tuple: (is_valid: bool, price: float, error_message: str)
    """
    try:
        price = float(price_str)
    except (ValueError, TypeError):
        return (False, 0, 'Giá không hợp lệ!')

    if price < 0:
        return (False, 0, 'Giá không được âm!')

    if price > 999999999:
        return (False, 0, 'Giá không được quá 999,999,999 VNĐ!')

    return (True, price, '')


def validate_service_duration(duration_str):
    """
    Validate thời lượng dịch vụ

    Quy tắc:
    - Phải là số nguyên hợp lệ
    - Ít nhất 5 phút
    - Không quá 480 phút (8 tiếng)

    Args:
        duration_str: str hoặc number - Thời lượng cần validate

    Returns:
        tuple: (is_valid: bool, duration: int, error_message: str)
    """
    try:
        duration = int(duration_str)
    except (ValueError, TypeError):
        return (False, 0, 'Thời gian không hợp lệ!')

    if duration < 5:
        return (False, 0, 'Thời gian phải ít nhất 5 phút!')

    if duration > 480:
        return (False, 0, 'Thời gian không được quá 480 phút (8 tiếng)!')

    return (True, duration, '')


def validate_service_image(image_file):
    """
    Validate file hình ảnh

    Quy tắc:
    - Tối đa 5MB
    - Chỉ chấp nhận: JPG, PNG, GIF, WebP

    Args:
        image_file: UploadedFile - File cần validate

    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    if not image_file:
        return (True, '')

    # Check file size (max 5MB)
    if image_file.size > 5 * 1024 * 1024:
        return (False, 'Hình ảnh không được quá 5MB!')

    # Check file type
    allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp']
    if image_file.content_type not in allowed_types:
        return (False, 'Chỉ chấp nhận file ảnh (JPG, PNG, GIF, WebP)!')

    return (True, '')


def validate_service_data(data, exclude_id=None):
    """Validate toàn bộ dữ liệu dịch vụ (không còn price/duration — quản lý qua variants)"""
    errors = []
    cleaned_data = {}

    name = data.get('name', '').strip()
    is_valid, error = validate_service_name(name, exclude_id)
    if not is_valid:
        errors.append(error)
    else:
        cleaned_data['name'] = name

    image_file = data.get('image')
    if image_file:
        is_valid, error = validate_service_image(image_file)
        if not is_valid:
            errors.append(error)
        else:
            cleaned_data['image'] = image_file

    from .models import ServiceCategory
    category_input = str(data.get('category', 'CAT01'))
    try:
        cleaned_data['category'] = ServiceCategory.objects.get(code=category_input)
    except ServiceCategory.DoesNotExist:
        cleaned_data['category'] = ServiceCategory.objects.filter(status='ACTIVE').first()

    description = data.get('description', '').strip()
    short_description = data.get('short_description', '').strip()

    # short_description: dùng giá trị riêng nếu có, fallback sang description cắt ngắn
    if short_description:
        cleaned_data['short_description'] = short_description[:255]
    elif description:
        cleaned_data['short_description'] = description[:255]
    else:
        cleaned_data['short_description'] = ''

    cleaned_data['description'] = description

    status = data.get('status', 'active')
    cleaned_data['status'] = status

    return {
        'valid': len(errors) == 0,
        'errors': errors,
        'cleaned_data': cleaned_data
    }


# =====================================================
# CRUD SERVICES
# =====================================================

def create_service(data, created_by=None):
    """
    Tạo dịch vụ mới

    Args:
        data: dict - Dữ liệu dịch vụ (đã validate)
        created_by: User - Người tạo

    Returns:
        tuple: (service: Service|None, error: str|None)
    """
    # Validate data
    validation = validate_service_data(data)
    if not validation['valid']:
        return (None, validation['errors'][0])

    cleaned = validation['cleaned_data']

    # Tạo slug từ name
    slug = slugify(cleaned['name'])

    # Tạo service
    try:
        service = Service.objects.create(
            name=cleaned['name'],
            slug=slug,
            category=cleaned['category'],
            short_description=cleaned['short_description'],
            description=cleaned['description'],
            status=cleaned['status'],
            created_by=created_by,
            updated_by=created_by,
        )

        # Lưu image nếu có
        if 'image' in cleaned:
            service.image = cleaned['image']
            service.save()

        return (service, None)

    except Exception as e:
        return (None, f'Lỗi khi tạo dịch vụ: {str(e)}')


def update_service(service, data, updated_by=None):
    """
    Cập nhật dịch vụ

    Args:
        service: Service - Dịch vụ cần cập nhật
        data: dict - Dữ liệu mới (đã validate)
        updated_by: User - Người cập nhật

    Returns:
        tuple: (service: Service|None, error: str|None)
    """
    # Validate data (exclude current service id)
    validation = validate_service_data(data, exclude_id=service.id)
    if not validation['valid']:
        return (None, validation['errors'][0])

    cleaned = validation['cleaned_data']

    try:
        # Update fields
        service.name = cleaned['name']
        service.category = cleaned['category']
        service.short_description = cleaned['short_description']
        service.description = cleaned['description']
        service.status = cleaned['status']
        service.updated_by = updated_by
        service.slug = slugify(cleaned['name'])

        # Update image nếu có
        if 'image' in cleaned:
            # Xóa image cũ
            if service.image and service.image.name:
                service.image.delete(save=False)
            service.image = cleaned['image']

        service.save()

        return (service, None)

    except Exception as e:
        return (None, f'Lỗi khi cập nhật dịch vụ: {str(e)}')


# =====================================================
# HELPER FUNCTIONS
# =====================================================

def get_service_by_id(service_id):
    """
    Lấy dịch vụ theo ID

    Args:
        service_id: int - ID dịch vụ

    Returns:
        tuple: (service: Service|None, error: JsonResponse|None)
    """
    try:
        service = Service.objects.get(id=service_id)
        return (service, None)
    except Service.DoesNotExist:
        return (None, 'Dịch vụ không tồn tại')
    except ValueError:
        return (None, 'ID dịch vụ không hợp lệ')

# API có thể tạo thêm file Serializer.py 
def serialize_service(service):
    """
    Serialize service thành dict (cho API response)

    Args:
        service: Service - Dịch vụ cần serialize

    Returns:
        dict: Dữ liệu dịch vụ
    """
    return {
        'id': service.id,
        'code': service.code or '',
        'name': service.name,
        'category': service.category,
        'categoryName': service.get_category_name(),
        'description': service.short_description or (service.description[:100] if service.description else ''),
        'short_description': service.short_description or '',
        'detail_description': service.description or '',
        'status': service.status if hasattr(service, 'status') else 'active',
        'image': service.image.url if service.image else 'https://images.unsplash.com/photo-1570172619644-dfd03ed5d881?w=100',
        'variants': [
            {'id': v.id, 'label': v.label, 'duration_minutes': v.duration_minutes, 'price': float(v.price)}
            for v in service.variants.order_by('sort_order', 'duration_minutes')
        ] if hasattr(service, 'variants') else [],
    }
