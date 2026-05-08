"""
Views cho Authentication

File này chứa các views cho:
- Đăng nhập, đăng ký, đăng xuất
- Quên mật khẩu / đặt lại mật khẩu

Author: Spa ANA Team
"""

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from customers.models import CustomerProfile
from customers.forms import CustomerRegistrationForm


# =====================================================
# VIEWS - Authentication
# =====================================================


def login_view(request):
    """
    Đăng nhập chung - tự phân luồng theo is_staff sau khi xác thực
    """
    if request.user.is_authenticated:
        return _redirect_by_role(request, request.user)

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            if not user.is_active:
                messages.error(request, 'Tài khoản đã bị vô hiệu hóa.')
                return render(request, 'accounts/login.html')

            login(request, user)

            remember_me = request.POST.get('remember')
            if remember_me:
                request.session.set_expiry(1209600)
            else:
                request.session.set_expiry(0)

            return _redirect_by_role(request, user, show_welcome=True)
        else:
            messages.error(request, 'Tên đăng nhập hoặc mật khẩu không đúng.')

    return render(request, 'accounts/login.html')


def _redirect_by_role(request, user, show_welcome=False):
    """Helper function redirect theo role"""
    if user.is_staff or user.is_superuser:
        # Chủ Spa (superuser) → trang báo cáo thống kê
        if user.is_superuser:
            return redirect('reports:admin_reports')
        return redirect('/manage/appointments/')

    try:
        profile = user.customer_profile
        return redirect('pages:home')
    except CustomerProfile.DoesNotExist:
        pass

    logout(request)
    messages.error(
        request,
        'Tài khoản chưa được phân quyền. Vui lòng liên hệ quản trị viên.'
    )
    return redirect('pages:home')


def register(request):
    """Đăng ký - Tạo User + CustomerProfile"""
    if request.user.is_authenticated:
        return redirect('pages:home')

    if request.method == 'POST':
        form = CustomerRegistrationForm(request.POST)
        if form.is_valid():
            try:
                profile = form.save()
            except ValueError as e:
                messages.error(request, str(e))
                return render(request, 'accounts/register.html', {'form': form})
            except Exception:
                messages.error(request, 'Có lỗi hệ thống khi tạo tài khoản. Vui lòng thử lại.')
                return render(request, 'accounts/register.html', {'form': form})

            # Đăng nhập ngay sau khi tạo tài khoản thành công
            user = authenticate(
                request,
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password1']
            )
            if user is not None:
                login(request, user)
                messages.success(request, f'Đăng ký thành công! Chào mừng {profile.full_name}')
                return redirect('pages:home')
            else:
                # Tài khoản đã tạo nhưng authenticate thất bại (hiếm gặp)
                messages.success(request, f'Đăng ký thành công! Vui lòng đăng nhập.')
                return redirect('accounts:login')
    else:
        form = CustomerRegistrationForm()

    return render(request, 'accounts/register.html', {'form': form})


@login_required
def logout_view(request):
    """Đăng xuất"""
    logout(request)
    return redirect('pages:home')
