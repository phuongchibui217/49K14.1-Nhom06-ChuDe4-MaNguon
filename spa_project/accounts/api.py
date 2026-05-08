"""
API Endpoints cho Accounts - Đăng nhập, Đăng ký, Đăng xuất

Tất cả endpoints trả về JSON.

LUỒNG: FE / Mobile → Gọi API → File này → Model → Trả JSON

Author: Spa ANA Team
"""

import json

from django.views.decorators.http import require_http_methods
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User

from core.api_response import ApiResponse, safe_api, staff_api


# =====================================================
# HELPER
# =====================================================

def _serialize_user(user):
    """Trả về thông tin user cơ bản (không lộ password)."""
    role = 'superuser' if user.is_superuser else ('staff' if user.is_staff else 'customer')
    full_name = ''
    try:
        full_name = user.staff_profile.full_name or ''
    except Exception:
        pass
    if not full_name:
        try:
            full_name = user.customer_profile.full_name or ''
        except Exception:
            pass
    if not full_name:
        full_name = user.get_full_name() or user.username

    return {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'full_name': full_name,
        'role': role,
    }


# =====================================================
# API: ĐĂNG NHẬP
# POST /api/auth/login/
# =====================================================

@require_http_methods(["POST"])
@safe_api
def api_login(request):
    """
    API: Đăng nhập

    Body JSON:
    {
        "username": "nguyenvana",
        "password": "matkhau123"
    }

    Response 200:
    {
        "success": true,
        "message": "Đăng nhập thành công",
        "user": { "id": 1, "username": "...", "role": "customer" }
    }
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return ApiResponse.bad_request('Dữ liệu JSON không hợp lệ')

    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username:
        return ApiResponse.bad_request('Vui lòng nhập tên đăng nhập')
    if not password:
        return ApiResponse.bad_request('Vui lòng nhập mật khẩu')

    user = authenticate(request, username=username, password=password)

    if user is None:
        return ApiResponse.error('Tên đăng nhập hoặc mật khẩu không đúng', status=401)

    if not user.is_active:
        return ApiResponse.error('Tài khoản đã bị vô hiệu hóa', status=403)

    login(request, user)

    return ApiResponse.success(
        data={'user': _serialize_user(user)},
        message='Đăng nhập thành công'
    )


# =====================================================
# API: ĐĂNG KÝ
# POST /api/auth/register/
# =====================================================

@require_http_methods(["POST"])
@safe_api
def api_register(request):
    """
    API: Đăng ký tài khoản khách hàng mới

    Body JSON:
    {
        "username": "nguyenvana",
        "password": "matkhau123",
        "full_name": "Nguyễn Văn A",
        "phone": "0912345678",
        "email": "a@example.com",   // optional
        "gender": "Nam",            // Nam | Nu | Khac
        "dob": "1990-01-15",        // optional, YYYY-MM-DD
        "address": "Hà Nội"         // optional
    }

    Response 201:
    {
        "success": true,
        "message": "Đăng ký thành công",
        "user": { "id": 1, "username": "...", "role": "customer" }
    }
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return ApiResponse.bad_request('Dữ liệu JSON không hợp lệ')

    # Validate bắt buộc
    username = data.get('username', '').strip()
    password = data.get('password', '')
    full_name = data.get('full_name', '').strip()
    phone = data.get('phone', '').strip()
    email = data.get('email', '').strip().lower()

    errors = {}
    if not username:
        errors['username'] = 'Vui lòng nhập tên đăng nhập'
    elif ' ' in username:
        errors['username'] = 'Tên đăng nhập không được chứa khoảng trắng'
    elif not username.isascii():
        errors['username'] = 'Tên đăng nhập chỉ được dùng ký tự không dấu'
    elif User.objects.filter(username=username).exists():
        errors['username'] = 'Tên đăng nhập này đã được sử dụng'

    if not password:
        errors['password'] = 'Vui lòng nhập mật khẩu'
    elif len(password) < 6:
        errors['password'] = 'Mật khẩu phải có ít nhất 6 ký tự'

    if not full_name:
        errors['full_name'] = 'Vui lòng nhập họ và tên'
    elif len(full_name) < 2:
        errors['full_name'] = 'Họ và tên phải có ít nhất 2 ký tự'

    if not phone:
        errors['phone'] = 'Vui lòng nhập số điện thoại'
    else:
        digits = ''.join(filter(str.isdigit, phone))
        if len(digits) < 10 or len(digits) > 11:
            errors['phone'] = 'Số điện thoại phải có 10-11 chữ số'
        else:
            from customers.models import CustomerProfile
            if CustomerProfile.objects.filter(phone=digits).exists():
                errors['phone'] = 'Số điện thoại này đã được đăng ký'
            phone = digits

    if not email:
        errors['email'] = 'Vui lòng nhập địa chỉ Gmail'
    elif not email.endswith('@gmail.com'):
        errors['email'] = 'Vui lòng nhập địa chỉ Gmail hợp lệ (phải kết thúc bằng @gmail.com)'
    elif User.objects.filter(email=email).exists():
        errors['email'] = 'Địa chỉ Gmail này đã được sử dụng'
    if gender and gender not in ('Nam', 'Nu', 'Khac'):
        errors['gender'] = 'Giới tính không hợp lệ (Nam / Nu / Khac)'

    dob = data.get('dob')
    if dob:
        try:
            from datetime import date
            dob_parsed = date.fromisoformat(dob)
            from django.utils import timezone as tz
            if dob_parsed > tz.now().date():
                errors['dob'] = 'Ngày sinh không được lớn hơn ngày hiện tại'
            else:
                dob = dob_parsed
        except ValueError:
            errors['dob'] = 'Định dạng ngày sinh không hợp lệ (YYYY-MM-DD)'
    else:
        dob = None

    if errors:
        return ApiResponse.bad_request('Dữ liệu không hợp lệ', errors=errors)

    # Tạo tài khoản
    try:
        from core.user_service import create_customer_user
        profile = create_customer_user(
            username=username,
            password=password,
            full_name=full_name,
            phone=phone,
            email=email,
            gender=gender or None,
            dob=dob,
            address=data.get('address', '').strip() or None,
        )
    except Exception as e:
        return ApiResponse.server_error(f'Không thể tạo tài khoản: {str(e)}')

    # Tự động đăng nhập sau khi đăng ký
    user = authenticate(request, username=username, password=password)
    if user:
        login(request, user)

    return ApiResponse.created(
        data={'user': _serialize_user(profile.user)},
        message=f'Đăng ký thành công! Chào mừng {full_name}'
    )


# =====================================================
# API: ĐĂNG XUẤT
# POST /api/auth/logout/
# =====================================================

@require_http_methods(["POST"])
@safe_api
def api_logout(request):
    """
    API: Đăng xuất

    Response 200:
    { "success": true, "message": "Đã đăng xuất" }
    """
    if not request.user.is_authenticated:
        return ApiResponse.unauthorized('Bạn chưa đăng nhập')

    logout(request)
    return ApiResponse.success(message='Đã đăng xuất thành công')


# =====================================================
# API: THÔNG TIN USER HIỆN TẠI
# GET /api/auth/me/
# =====================================================

@require_http_methods(["GET"])
def api_me(request):
    """
    API: Lấy thông tin user đang đăng nhập

    Response 200:
    { "success": true, "user": { ... } }
    """
    if not request.user.is_authenticated:
        return ApiResponse.unauthorized()

    return ApiResponse.success(data={'user': _serialize_user(request.user)})
