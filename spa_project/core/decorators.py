"""
Decorators dùng chung cho Spa ANA

File này chứa các decorator để:
- Kiểm tra quyền truy cập
- Giảm lặp code
- Dễ bảo trì
@receptionist_required
Author: Spa ANA Team
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.http import JsonResponse
from functools import wraps


# =====================================================
# STAFF REQUIRED DECORATOR (cho trang admin)
# =====================================================

def staff_required(login_url=None, redirect_on_fail='spa:home'):
    """
    Decorator kiểm tra user có quyền staff/superuser không

    Sử dụng cho: Các trang admin (render template)

    Hành vi:
    - Chưa đăng nhập → Redirect đến trang login
    - Đã đăng nhập nhưng không phải staff → Message lỗi + redirect

    Args:
        login_url: URL trang login (optional, mặc định dùng accounts:login)
        redirect_on_fail: URL redirect khi không có quyền (mặc định: spa:home)

    Usage:
        @staff_required()
        def admin_appointments(request):
            # View code here
            return render(request, 'manage/pages/admin_appointments.html')

        # Hoặc chỉ định login_url riêng
        @staff_required(login_url='accounts:login')
        def admin_services(request):
            return render(request, 'manage/pages/admin_services.html')
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required(login_url=login_url or 'accounts:login')
        def _wrapped_view(request, *args, **kwargs):
            # Kiểm tra quyền staff hoặc superuser
            if request.user.is_staff or request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            # Không có quyền → báo lỗi + redirect
            messages.error(request, 'Bạn không có quyền truy cập trang này.')
            return redirect(redirect_on_fail)

        return _wrapped_view

    return decorator


# =====================================================
# API STAFF REQUIRED DECORATOR (cho API endpoints)
# =====================================================

def api_staff_required():
    """
    Decorator kiểm tra quyền staff/superuser cho API endpoints

    Sử dụng cho: Các API trả về JSON

    Hành vi:
    - Chưa đăng nhập → JsonResponse 401
    - Đã đăng nhập nhưng không phải staff → JsonResponse 403

    Returns:
        JsonResponse với format chuẩn nếu không có quyền

    Usage:
        @api_staff_required()
        def api_services_list(request):
            services = Service.objects.all()
            return JsonResponse({'services': list(services.values())})

        # Kết hợp với @csrf_exempt
        @csrf_exempt
        @api_staff_required()
        def api_service_create(request):
            # API code here
            pass
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            # Kiểm tra đã đăng nhập chưa
            if not request.user.is_authenticated:
                return JsonResponse({
                    'success': False,
                    'error': 'Vui lòng đăng nhập để tiếp tục.'
                }, status=401)

            # Kiểm tra quyền staff hoặc superuser
            if request.user.is_staff or request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            # Không có quyền
            return JsonResponse({
                'success': False,
                'error': 'Bạn không có quyền thực hiện thao tác này.'
            }, status=403)

        return _wrapped_view

    return decorator


# =====================================================
# COMBINED DECORATORS
# =====================================================

def admin_view(login_url=None):
    """
    Shortcut decorator cho admin page views

    Tương đương với:
        @login_required(login_url='accounts:login')
        + check is_staff/is_superuser

    Usage:
        @admin_view()
        def admin_dashboard(request):
            return render(request, 'manage/pages/dashboard.html')
    """
    return staff_required(login_url=login_url or 'accounts:login')


def admin_api():
    """
    Shortcut decorator cho admin API endpoints

    Tương đương với @api_staff_required()

    Usage:
        @admin_api()
        def api_get_data(request):
            return JsonResponse({'data': [...]})
    """
    return api_staff_required()


# =====================================================
# CUSTOMER REQUIRED DECORATOR
# =====================================================

def customer_required(login_url='accounts:login'):
    """
    Decorator bảo vệ các trang dành riêng cho khách hàng.

    Quy tắc:
    - Chưa đăng nhập → redirect login
    - is_staff hoặc is_superuser → redirect về dashboard quản lý (không được vào flow khách)
    - Đã login nhưng không có CustomerProfile → redirect login với thông báo
    - Đã login + có CustomerProfile + không phải staff → cho vào
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.conf import settings
                from urllib.parse import quote
                next_url = quote(request.get_full_path())
                return redirect(f'/{login_url.replace("accounts:login", "login")}/?next={next_url}')

            # Staff/admin không được vào flow khách
            if request.user.is_staff or request.user.is_superuser:
                return redirect('/manage/appointments/')

            # Phải có CustomerProfile
            from customers.models import CustomerProfile
            try:
                request.user.customer_profile
            except CustomerProfile.DoesNotExist:
                messages.error(request, 'Tài khoản chưa được phân quyền. Vui lòng liên hệ quản trị viên.')
                from django.contrib.auth import logout as auth_logout
                auth_logout(request)
                return redirect('accounts:login')

            return view_func(request, *args, **kwargs)

        return _wrapped_view
    return decorator


# =====================================================
# HELPER FUNCTIONS
# =====================================================

def is_staff_user(user):
    """
    Helper function kiểm tra user có phải staff/superuser không

    Dùng cho:
    - Template tags
    - Conditional logic trong view

    Args:
        user: User object

    Returns:
        bool: True nếu là staff hoặc superuser

    Usage:
        if is_staff_user(request.user):
            # Do something
            pass
    """
    return user.is_authenticated and (user.is_staff or user.is_superuser)


def is_customer_user(user):
    """
    Helper function kiểm tra user có phải khách hàng không

    Args:
        user: User object

    Returns:
        bool: True nếu đã đăng nhập và có CustomerProfile
    """
    if not user.is_authenticated:
        return False

    from customers.models import CustomerProfile
    return CustomerProfile.objects.filter(user=user).exists()


# =====================================================
# GROUP-BASED DECORATORS (MỚI)
# =====================================================

def group_required(*group_names):
    """
    Decorator: Check user belongs to specific groups

    Usage:
        @group_required('Lễ tân', 'Chủ Spa')
        def my_view(request):
            pass
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required(login_url='accounts:login')
        def wrapper(request, *args, **kwargs):
            # Check if user belongs to any of the required groups
            user_groups = request.user.groups.values_list('name', flat=True)
            if not any(group in user_groups for group in group_names):
                messages.error(
                    request,
                    f"Bạn cần thuộc về một trong các nhóm: {', '.join(group_names)}"
                )
                return redirect('pages:home')

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def superuser_required(view_func):
    """
    Decorator: Chỉ cho phép Superuser (Chủ Spa)

    Usage:
        @superuser_required
        def my_view(request):
            pass
    """
    @wraps(view_func)
    @login_required(login_url='accounts:login')
    def wrapper(request, *args, **kwargs):
        if not request.user.is_superuser:
            messages.error(request, "Chỉ Quản trị viên mới có quyền truy cập.")
            return redirect('pages:home')

        return view_func(request, *args, **kwargs)
    return wrapper


def permission_or_403(perm, login_url=None):
    """
    Custom version của permission_required decorator
    Raise 403 thay vì redirect nếu không có quyền

    Usage:
        @permission_or_403('appointments.view_all_appointments')
        def my_view(request):
            pass
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required(login_url=login_url or 'accounts:login')
        def wrapper(request, *args, **kwargs):
            if not request.user.has_perm(perm):
                from django.core.exceptions import PermissionDenied
                raise PermissionDenied(f"Bạn cần quyền '{perm}' để truy cập.")
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator

