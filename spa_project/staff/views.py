"""
Views cho Staff Management

File này chứa các views cho:
- Quản lý nhân viên từ Admin Panel (chỉ Superuser)

Author: Spa ANA Team
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse

from .models import StaffProfile


@login_required(login_url='accounts:login')
def admin_staff(request):
    """Quản lý nhân viên - Chỉ dành cho Superuser"""
    if not request.user.is_superuser:
        messages.error(request, 'Bạn không có quyền truy cập trang này. Chỉ Superuser mới được quản lý nhân viên.')
        return redirect('appointments:admin_appointments')

    if request.method == 'POST':
        action = request.POST.get('action', '').strip()

        # THÊM
        if action == 'create':
            username = request.POST.get('username', '').strip()
            full_name = request.POST.get('full_name', '').strip()
            password = request.POST.get('password', '')
            confirm_password = request.POST.get('confirm_password', '')
            phone = request.POST.get('phone', '').strip()
            email = request.POST.get('email', '').strip()
            gender = request.POST.get('gender', '').strip()
            dob = request.POST.get('dob', '').strip()
            address = request.POST.get('address', '').strip()
            notes = request.POST.get('notes', '').strip()

            if not all([username, full_name, password, confirm_password, phone, email]):
                messages.error(request, 'Vui lòng nhập đầy đủ thông tin bắt buộc.')
                return redirect('staff:admin_staff')

            if password != confirm_password:
                messages.error(request, 'Mật khẩu xác nhận không khớp.')
                return redirect('staff:admin_staff')

            # Validate format trước khi check trùng
            if not phone.isdigit():
                messages.error(request, 'Số điện thoại chỉ được chứa chữ số.')
                return redirect('staff:admin_staff')

            # Kiểm tra trùng dữ liệu
            if User.objects.filter(username=username).exists():
                messages.error(request, 'Tên đăng nhập đã tồn tại.')
                return redirect('staff:admin_staff')

            if User.objects.filter(email=email).exists():
                messages.error(request, 'Email đã tồn tại.')
                return redirect('staff:admin_staff')

            if StaffProfile.objects.filter(phone=phone).exists():
                messages.error(request, 'Số điện thoại đã tồn tại.')
                return redirect('staff:admin_staff')

            try:
                from core.user_service import create_staff_user
                create_staff_user(
                    username=username,
                    password=password,
                    full_name=full_name,
                    phone=phone,
                    email=email,
                    gender=gender or None,
                    dob=dob or None,
                    address=address or None,
                    notes=notes or None,
                )
            except ValueError as e:
                messages.error(request, str(e))
                return redirect('staff:admin_staff')

            messages.success(request, 'Thêm nhân viên thành công!')
            return redirect('staff:admin_staff')

        # SỬA
        elif action == 'update':
            staff_id = request.POST.get('staff_id', '').strip()

            if not staff_id:
                messages.error(request, 'Không tìm thấy nhân viên cần cập nhật.')
                return redirect('staff:admin_staff')

            staff = get_object_or_404(StaffProfile, pk=staff_id)

            full_name = request.POST.get('full_name', '').strip()
            phone = request.POST.get('phone', '').strip()
            email = request.POST.get('email', '').strip()
            status = request.POST.get('status', '').strip()
            gender = request.POST.get('gender', '').strip()
            dob = request.POST.get('dob', '').strip()
            address = request.POST.get('address', '').strip()
            notes = request.POST.get('notes', '').strip()

            if not all([full_name, phone, email, status]):
                messages.error(request, 'Vui lòng nhập đầy đủ thông tin bắt buộc.')
                return redirect('staff:admin_staff')

            if StaffProfile.objects.exclude(pk=staff.pk).filter(phone=phone).exists():
                messages.error(request, 'Số điện thoại đã tồn tại.')
                return redirect('staff:admin_staff')

            if User.objects.exclude(pk=staff.user.pk).filter(email=email).exists():
                messages.error(request, 'Email đã tồn tại.')
                return redirect('staff:admin_staff')

            staff.full_name = full_name
            staff.phone = phone
            staff.gender = gender or None
            staff.dob = dob or None
            staff.address = address or None
            staff.notes = notes or None
            staff.save()

            staff.user.email = email
            staff.user.is_active = (status == 'active')
            staff.user.is_staff = True
            staff.user.save()

            # Đảm bảo StaffProfile tồn tại sau khi update (idempotent)
            from core.user_service import ensure_staff_profile
            ensure_staff_profile(staff.user)

            messages.success(request, 'Cập nhật nhân viên thành công!')
            return redirect('staff:admin_staff')

        # KHÓA
        elif action == 'lock':
            staff_id = request.POST.get('staff_id', '').strip()

            if not staff_id:
                messages.error(request, 'Không tìm thấy nhân viên cần khóa.')
                return redirect('staff:admin_staff')

            staff = get_object_or_404(StaffProfile, pk=staff_id)

            # Không cho khóa nếu tài khoản đã bị khóa rồi
            if not staff.user.is_active:
                messages.warning(request, 'Tài khoản này đã bị khóa trước đó.')
                return redirect('staff:admin_staff')

            staff.user.is_active = False
            staff.user.save()
            messages.success(request, f'Đã khóa tài khoản "{staff.full_name}".')
            return redirect('staff:admin_staff')

        # MỞ KHÓA
        elif action == 'unlock':
            staff_id = request.POST.get('staff_id', '').strip()

            if not staff_id:
                messages.error(request, 'Không tìm thấy nhân viên cần mở khóa.')
                return redirect('staff:admin_staff')

            staff = get_object_or_404(StaffProfile, pk=staff_id)

            # Không cho mở khóa nếu tài khoản đang hoạt động
            if staff.user.is_active:
                messages.warning(request, 'Tài khoản này đang hoạt động, không cần mở khóa.')
                return redirect('staff:admin_staff')

            staff.user.is_active = True
            staff.user.save()
            messages.success(request, f'Đã mở khóa tài khoản "{staff.full_name}".')
            return redirect('staff:admin_staff')

        else:
            messages.error(request, 'Thao tác không hợp lệ.')
            return redirect('staff:admin_staff')

    staffs = StaffProfile.objects.select_related('user').order_by('-created_at')
    return render(request, 'manage/pages/admin_staff.html', {
        'staffs': staffs,
    })


@login_required(login_url='accounts:login')
def check_username(request):
    """API nhanh kiểm tra username đã tồn tại chưa — dùng cho realtime check ở frontend"""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    username = request.GET.get('username', '').strip()
    if not username:
        return JsonResponse({'exists': False})

    exists = User.objects.filter(username=username).exists()
    return JsonResponse({'exists': exists})