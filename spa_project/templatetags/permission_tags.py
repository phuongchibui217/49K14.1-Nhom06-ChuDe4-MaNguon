"""
Custom Template Tags cho Spa ANA

Cung cấp các filter và tag để check permissions và roles trong templates

Usage:
    {% load permission_tags %}

    {% if user|is_receptionist %}
        <!-- Show receptionist content -->
    {% endif %}

    {% if user|has_group:'Lễ tân' %}
        <!-- Show group content -->
    {% endif %}
"""

from django import template
from django.core.exceptions import PermissionDenied

register = template.Library()


# =====================================================
# FILTERS - CHECK ROLE
# =====================================================

@register.filter
def is_receptionist(user):
    """
    Check if user is receptionist (is_staff or is_superuser)

    Usage:
        {% if user|is_receptionist %}
            <a href="/manage/appointments/">Quản lý lịch hẹn</a>
        {% endif %}
    """
    if not user.is_authenticated:
        return False
    return user.is_staff or user.is_superuser


@register.filter
def is_customer(user):
    """
    Check if user is customer (has CustomerProfile)

    Usage:
        {% if user|is_customer %}
            <a href="/lich-hen-cua-toi/">Lịch hẹn của tôi</a>
        {% endif %}
    """
    if not user.is_authenticated:
        return False

    try:
        from customers.models import CustomerProfile
        return hasattr(user, 'customer_profile') and user.customer_profile is not None
    except:
        return False


@register.filter
def is_superuser(user):
    """
    Check if user is superuser (Chủ Spa)

    Usage:
        {% if user|is_superuser %}
            <a href="/admin/">Quản trị hệ thống</a>
        {% endif %}
    """
    return user.is_authenticated and user.is_superuser


@register.filter
def has_group(user, group_name):
    """
    Check if user belongs to a specific group

    Usage:
        {% if user|has_group:'Lễ tân' %}
            <button>Quản lý</button>
        {% endif %}
    """
    if not user.is_authenticated:
        return False
    return user.groups.filter(name=group_name).exists()


@register.filter
def has_any_group(user, group_names):
    """
    Check if user belongs to ANY of the specified groups

    Usage:
        {% if user|has_any_group:'Lễ tân,Chủ Spa' %}
            <button>Quản lý</button>
        {% endif %}
    """
    if not user.is_authenticated:
        return False

    groups = group_names.split(',')
    user_groups = user.groups.values_list('name', flat=True)
    return any(group.strip() in user_groups for group in groups)


# =====================================================
# SIMPLE TAGS - CHECK PERMISSIONS
# =====================================================

@register.simple_tag
def can_manage_appointments(user):
    """
    Check if user can manage all appointments

    Usage:
        {% can_manage_appointments user as can_manage %}
        {% if can_manage %}
            <a href="/manage/appointments/">Quản lý lịch hẹn</a>
        {% endif %}
    """
    return user.is_authenticated and user.has_perm('appointments.view_appointment')


@register.simple_tag
def can_view_services(user):
    """
    Check if user can view services

    Usage:
        {% can_view_services user as can_view %}
        {% if can_view %}
            <a href="/services/">Xem dịch vụ</a>
        {% endif %}
    """
    return user.is_authenticated and user.has_perm('spa_services.view_service')


@register.simple_tag
def can_manage_customers(user):
    """
    Check if user can manage customer information

    Usage:
        {% can_manage_customers user as can_manage %}
        {% if can_manage %}
            <a href="/manage/customers/">Quản lý khách hàng</a>
        {% endif %}
    """
    return user.is_authenticated and user.has_perm('accounts.view_customerprofile')


@register.simple_tag
def can_respond_complaints(user):
    """
    Check if user can respond to complaints

    Usage:
        {% can_respond_complaints user as can_respond %}
        {% if can_respond %}
            <a href="/manage/complaints/">Phản hồi khiếu nại</a>
        {% endif %}
    """
    return user.is_authenticated and user.has_perm('complaints.change_complaint')


# =====================================================
# ASSIGNMENT TAGS
# =====================================================

@register.assignment_tag
def get_user_role(user):
    """
    Get user role as string

    Usage:
        {% get_user_role user as role %}
        <p>Bạn đang đăng nhập với vai trò: {{ role }}</p>
    """
    if not user.is_authenticated:
        return "Guest"

    if user.is_superuser:
        return "Quản trị viên"
    elif user.is_staff:
        return "Lễ tân"
    else:
        try:
            from customers.models import CustomerProfile
            if hasattr(user, 'customer_profile'):
                return "Khách hàng"
        except:
            pass

    return "User"


@register.assignment_tag
def get_user_groups(user):
    """
    Get list of user's groups

    Usage:
        {% get_user_groups user as groups %}
        {% for group in groups %}
            <span class="badge">{{ group }}</span>
        {% endfor %}
    """
    if not user.is_authenticated:
        return []

    return list(user.groups.values_list('name', flat=True))


# =====================================================
# CONDITIONAL TAGS
# =====================================================

@register.simple_tag(takes_context=True)
def can_access_manage(context):
    """
    Check if current user can access manage section

    Usage:
        {% can_access_manage as can_manage %}
        {% if can_manage %}
            <a href="/manage/">Quản lý</a>
        {% endif %}
    """
    request = context['request']
    user = request.user

    if not user.is_authenticated:
        return False

    return user.is_staff or user.is_superuser


@register.simple_tag(takes_context=True)
def show_customer_menu(context):
    """
    Check if should show customer menu

    Usage:
        {% show_customer_menu as show_menu %}
        {% if show_menu %}
            <!-- Customer menu items -->
        {% endif %}
    """
    request = context['request']
    user = request.user

    if not user.is_authenticated:
        return False

    try:
        from customers.models import CustomerProfile
        return hasattr(user, 'customer_profile') and user.customer_profile is not None
    except:
        return False
