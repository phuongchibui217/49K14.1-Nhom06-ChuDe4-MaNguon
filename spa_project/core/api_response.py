"""
API Response Helper cho Spa ANA

File này chuẩn hóa cách trả response cho tất cả API endpoints.
Mục tiêu:
- Format thống nhất, dễ predictable cho frontend
- Dễ debug, dễ log
- Message tiếng Việt rõ ràng
- CSRF protection cho API POST/PUT/DELETE

Author: Spa ANA Team
"""

from django.http import JsonResponse
from django.core.exceptions import ValidationError
from django.middleware.csrf import rotate_token
from django.views.decorators.csrf import ensure_csrf_cookie
import traceback
import functools


# =====================================================
# HTTP STATUS CODES
# =====================================================

class HttpStatus:
    """Các HTTP status code thường dùng"""
    OK = 200           # Thành công
    CREATED = 201      # Tạo mới thành công
    BAD_REQUEST = 400  # Lỗi dữ liệu đầu vào
    UNAUTHORIZED = 401 # Chưa đăng nhập
    FORBIDDEN = 403    # Không có quyền
    NOT_FOUND = 404    # Không tìm thấy
    SERVER_ERROR = 500 # Lỗi server


# =====================================================
# API RESPONSE CLASS
# =====================================================

class ApiResponse:
    """
    Helper class để tạo API response chuẩn hóa

    FORMAT CHUẨN:
    {
        "success": true/false,
        "message": "Thông báo (optional)",
        "data": { ... },           // Dữ liệu trả về (optional)
        "errors": { ... }          // Chi tiết lỗi (optional)
    }

    USAGE:
        # Thành công
        return ApiResponse.success(data={'services': [...]})
        return ApiResponse.success(message='Tạo thành công', data={'id': 1})

        # Lỗi
        return ApiResponse.error('Tên không hợp lệ')
        return ApiResponse.bad_request('Dữ liệu không hợp lệ', errors={'name': ['Required']})
        return ApiResponse.not_found('Không tìm thấy dịch vụ')
        return ApiResponse.forbidden()
    """

    # =====================================================
    # SUCCESS RESPONSES
    # =====================================================

    @staticmethod
    def success(data=None, message=None, status=HttpStatus.OK):
        """
        Response thành công

        Args:
            data: dict - Dữ liệu trả về (optional)
            message: str - Thông báo thành công (optional)
            status: int - HTTP status code (default: 200)

        Returns:
            JsonResponse với format chuẩn
        """
        response = {'success': True}

        if message:
            response['message'] = message

        if data:
            # Merge data vào response
            response.update(data)

        return JsonResponse(response, status=status)

    @staticmethod
    def created(data=None, message='Tạo thành công'):
        """
        Response khi tạo mới thành công (HTTP 201)

        Args:
            data: dict - Dữ liệu object vừa tạo
            message: str - Thông báo

        Returns:
            JsonResponse với status 201
        """
        return ApiResponse.success(data=data, message=message, status=HttpStatus.CREATED)

    # =====================================================
    # ERROR RESPONSES
    # =====================================================

    @staticmethod
    def error(message, status=HttpStatus.BAD_REQUEST, errors=None):
        """
        Response lỗi chung

        Args:
            message: str - Thông báo lỗi
            status: int - HTTP status code (default: 400)
            errors: dict - Chi tiết lỗi từng field (optional)

        Returns:
            JsonResponse với format chuẩn
        """
        response = {
            'success': False,
            'error': message  # Dùng 'error' để tương thích với code cũ
        }

        if errors:
            response['errors'] = errors

        return JsonResponse(response, status=status)

    @staticmethod
    def bad_request(message='Dữ liệu không hợp lệ', errors=None):
        """
        Response lỗi dữ liệu đầu vào (HTTP 400)

        Args:
            message: str - Thông báo lỗi
            errors: dict - Chi tiết lỗi từng field

        Returns:
            JsonResponse với status 400
        """
        return ApiResponse.error(message, status=HttpStatus.BAD_REQUEST, errors=errors)

    @staticmethod
    def unauthorized(message='Vui lòng đăng nhập để tiếp tục'):
        """
        Response chưa đăng nhập (HTTP 401)

        Args:
            message: str - Thông báo

        Returns:
            JsonResponse với status 401
        """
        return ApiResponse.error(message, status=HttpStatus.UNAUTHORIZED)

    @staticmethod
    def forbidden(message='Bạn không có quyền thực hiện thao tác này'):
        """
        Response không có quyền (HTTP 403)

        Args:
            message: str - Thông báo

        Returns:
            JsonResponse với status 403
        """
        return ApiResponse.error(message, status=HttpStatus.FORBIDDEN)

    @staticmethod
    def not_found(message='Không tìm thấy dữ liệu'):
        """
        Response không tìm thấy (HTTP 404)

        Args:
            message: str - Thông báo

        Returns:
            JsonResponse với status 404
        """
        return ApiResponse.error(message, status=HttpStatus.NOT_FOUND)

    @staticmethod
    def server_error(message='Đã có lỗi xảy ra, vui lòng thử lại sau'):
        """
        Response lỗi server (HTTP 500)

        Args:
            message: str - Thông báo

        Returns:
            JsonResponse với status 500
        """
        return ApiResponse.error(message, status=HttpStatus.SERVER_ERROR)

    # =====================================================
    # SPECIAL RESPONSES
    # =====================================================

    @staticmethod
    def validation_error(errors, message='Dữ liệu không hợp lệ'):
        """
        Response lỗi validation

        Args:
            errors: dict/list - Chi tiết lỗi validation
            message: str - Thông báo chung

        Returns:
            JsonResponse với status 400
        """
        # Nếu errors là list, convert thành dict
        if isinstance(errors, list) and errors:
            return ApiResponse.bad_request(message, errors=errors)

        # Nếu errors là dict (từ form.errors)
        if isinstance(errors, dict):
            # Lấy lỗi đầu tiên nếu chỉ có 1 lỗi
            if len(errors) == 1:
                first_field = list(errors.keys())[0]
                first_error = errors[first_field]
                if isinstance(first_error, list) and first_error:
                    return ApiResponse.bad_request(first_error[0])
                return ApiResponse.bad_request(str(first_error))

            return ApiResponse.bad_request(message, errors=errors)

        return ApiResponse.bad_request(str(errors))

    @staticmethod
    def from_exception(exception, include_traceback=False):
        """
        Tạo response từ exception

        Args:
            exception: Exception - Exception xảy ra
            include_traceback: bool - Có kèm traceback không (chỉ dùng khi debug)

        Returns:
            JsonResponse phù hợp
        """
        # ValidationError từ Django
        if isinstance(exception, ValidationError):
            messages = exception.messages if hasattr(exception, 'messages') else [str(exception)]
            return ApiResponse.validation_error(messages)

        # Lỗi khác
        message = str(exception) if str(exception) else 'Đã có lỗi xảy ra'

        response_data = {'success': False, 'error': message}

        if include_traceback:
            response_data['traceback'] = traceback.format_exc()

        return JsonResponse(response_data, status=HttpStatus.BAD_REQUEST)


# =====================================================
# DECORATOR CHO API VIEWS
# =====================================================

def api_view(func):
    """
    Decorator để wrap API view và xử lý exception tự động

    Usage:
        @api_view
        def api_get_service(request, service_id):
            service = Service.objects.get(id=service_id)
            return ApiResponse.success(data={'service': service.to_dict()})

    Tự động:
        - Catch exception và trả về error response
        - Log error (nếu configured)
    """
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # Log error
            print(f"[API ERROR] {func.__name__}: {str(e)}")
            traceback.print_exc()

            # Return error response
            return ApiResponse.from_exception(e)

    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper


# =====================================================
# HELPER FUNCTIONS
# =====================================================

def check_staff_permission(request):
    """
    Kiểm tra quyền staff/admin

    Args:
        request: HttpRequest

    Returns:
        None nếu có quyền, hoặc JsonResponse lỗi nếu không
    """
    if not request.user.is_authenticated:
        return ApiResponse.unauthorized()

    if not (request.user.is_staff or request.user.is_superuser):
        return ApiResponse.forbidden()

    return None  # Có quyền


def get_or_404(model, **kwargs):
    """
    Lấy object hoặc trả về 404 response

    Args:
        model: Model class
        **kwargs: Filter conditions

    Returns:
        tuple: (object, None) hoặc (None, error_response)

    Usage:
        service, error = get_or_404(Service, id=service_id)
        if error:
            return error
    """
    try:
        obj = model.objects.get(**kwargs)
        return obj, None
    except model.DoesNotExist:
        model_name = model.__name__
        message = f'Không tìm thấy {model_name._meta.verbose_name}' if hasattr(model, '_meta') else f'Không tìm thấy {model_name}'
        return None, ApiResponse.not_found(message)


# =====================================================
# BACKWARD COMPATIBILITY
# =====================================================

def api_success(data=None, message=None):
    """
    Helper function cho backward compatibility

    Giữ lại để code cũ vẫn chạy được
    """
    return ApiResponse.success(data=data, message=message)


def api_error(message, status=400):
    """
    Helper function cho backward compatibility

    Giữ lại để code cũ vẫn chạy được
    """
    return ApiResponse.error(message, status=status)


# =====================================================
# CSRF PROTECTION HELPERS
# =====================================================

def get_csrf_token(request):
    """
    Lấy CSRF token từ request

    Args:
        request: HttpRequest

    Returns:
        str: CSRF token hoặc None
    """
    return request.META.get('HTTP_X_CSRFTOKEN') or request.POST.get('csrfmiddlewaretoken')


def validate_csrf_token(request):
    """
    Validate CSRF token cho API POST/PUT/DELETE

    CÁCH HOẠT ĐỘNG:
    1. Lấy token từ header (X-CSRFToken) hoặc POST data (csrfmiddlewaretoken)
    2. So sánh với token trong cookie
    3. Trả về (True, None) nếu hợp lệ, (False, error_response) nếu không

    Args:
        request: HttpRequest

    Returns:
        tuple: (is_valid, error_response)
        - (True, None) nếu CSRF hợp lệ
        - (False, JsonResponse) nếu CSRF không hợp lệ
    """
    from django.middleware.csrf import CsrfViewMiddleware

    # Lấy token từ header hoặc POST data
    csrf_token = get_csrf_token(request)

    if not csrf_token:
        return False, ApiResponse.forbidden(
            'Thiếu CSRF token. Vui lòng làm mới trang và thử lại.'
        )

    # Sử dụng Django's CSRF middleware để validate
    middleware = CsrfViewMiddleware(lambda x: None)

    # Process request để check CSRF
    try:
        result = middleware.process_view(request, None, (), {})
        if result is not None:
            # CSRF validation failed
            return False, ApiResponse.forbidden(
                'CSRF token không hợp lệ. Vui lòng làm mới trang và thử lại.'
            )
    except Exception as e:
        return False, ApiResponse.forbidden(
            f'Lỗi xác thực CSRF: {str(e)}'
        )

    return True, None


def require_csrf_validation(view_func):
    """
    Decorator yêu cầu CSRF validation cho API view

    USAGE:
        @require_http_methods(["POST"])
        @require_csrf_validation
        def api_create_service(request):
            # CSRF đã được validate ở đây
            ...

    GIẢI THÍCH:
        - Tự động check CSRF token trước khi chạy view
        - Trả về 403 Forbidden nếu token không hợp lệ
        - Giúp bảo vệ chống lại CSRF attack

    Args:
        view_func: Function view cần bảo vệ

    Returns:
        Wrapped function với CSRF validation
    """
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Chỉ validate CSRF cho method cần bảo vệ
        if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
            is_valid, error_response = validate_csrf_token(request)
            if not is_valid:
                return error_response

        # CSRF hợp lệ, chạy view bình thường
        return view_func(request, *args, **kwargs)

    return wrapper


def csrf_protected_api(view_func):
    """
    Alias cho require_csrf_validation - ngắn gọn hơn

    USAGE:
        @require_http_methods(["POST"])
        @csrf_protected_api
        def api_create_service(request):
            ...
    """
    return require_csrf_validation(view_func)


# =====================================================
# COMBINED DECORATORS
# =====================================================

def staff_api(view_func):
    """
    Decorator kết hợp: Login required + Staff permission + CSRF validation

    USAGE:
        @require_http_methods(["POST"])
        @staff_api
        def api_create_service(request):
            # Đã đảm bảo:
            # 1. User đã đăng nhập
            # 2. User là staff/admin
            # 3. CSRF token hợp lệ (nếu POST/PUT/DELETE)
            ...

    Args:
        view_func: Function view cần bảo vệ

    Returns:
        Wrapped function với đầy đủ protection
    """
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # 1. Check authentication
        if not request.user.is_authenticated:
            return ApiResponse.unauthorized()

        # 2. Check staff permission
        if not (request.user.is_staff or request.user.is_superuser):
            return ApiResponse.forbidden()

        # 3. Check CSRF cho method cần bảo vệ
        if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
            is_valid, error_response = validate_csrf_token(request)
            if not is_valid:
                return error_response

        # Tất cả check passed, chạy view
        return view_func(request, *args, **kwargs)

    return wrapper


def safe_api(view_func):
    """
    Decorator cho API công khai - chỉ cần CSRF validation (không cần login)

    Dùng cho các API mà guest cũng có thể gọi (ví dụ: đặt lịch không cần login)

    USAGE:
        @require_http_methods(["POST"])
        @safe_api
        def api_public_booking(request):
            # CSRF đã được validate
            ...
    """
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Check CSRF cho method cần bảo vệ
        if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
            is_valid, error_response = validate_csrf_token(request)
            if not is_valid:
                return error_response

        return view_func(request, *args, **kwargs)

    return wrapper
