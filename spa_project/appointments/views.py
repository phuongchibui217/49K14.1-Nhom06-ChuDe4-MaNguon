"""
Views cho Appointments module.

- booking(): Trang đặt lịch online cho khách hàng → tạo Booking + Appointment
- my_appointments(): Khách xem lịch hẹn của mình
- cancel_appointment(): Khách hủy lịch hẹn
- admin_appointments(): Trang quản lý lịch hẹn (staff/admin)

Author: Spa ANA Team
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required

from .models import Appointment, Booking
from spa_services.models import Service, ServiceVariant
from .forms import BookingOnlineForm
from core.decorators import customer_required


# =====================================================
# TRANG ĐẶT LỊCH (Public — khách hàng)
# =====================================================

@customer_required()
def booking(request):
    """Trang đặt lịch hẹn cho khách hàng (online booking)."""
    customer_profile = request.user.customer_profile

    if request.method == 'POST':
        form = BookingOnlineForm(request.POST, customer_profile=customer_profile)
        if form.is_valid():
            booker_name  = form.cleaned_data['booker_name']
            booker_phone = form.cleaned_data['booker_phone']
            booker_email = customer_profile.user.email
            booker_notes = form.cleaned_data.get('booker_notes', '')

            # Customer snapshot — khách sử dụng dịch vụ
            customer_name_snapshot  = request.POST.get('customer_name_snapshot', '').strip() or booker_name
            _raw_phone              = request.POST.get('customer_phone_snapshot', '').strip()
            customer_phone_snapshot = ''.join(filter(str.isdigit, _raw_phone)) or booker_phone
            customer_email_snapshot = request.POST.get('customer_email_snapshot', '').strip() or None

            # Service variant
            service_variant = form.cleaned_data.get('service_variant')

            try:
                from django.db import transaction
                with transaction.atomic():
                    # Tạo Booking
                    bk = Booking.objects.create(
                        booker_name=booker_name,
                        booker_phone=booker_phone,
                        booker_email=booker_email,
                        booker_notes=booker_notes or None,
                        status='PENDING',
                        payment_status='UNPAID',
                        source='ONLINE',
                        created_by=request.user,
                    )
                    # Tạo Appointment (chưa assign phòng - staff sẽ làm sau)
                    appt = Appointment.objects.create(
                        booking=bk,
                        customer=customer_profile,
                        service_variant=service_variant,
                        customer_name_snapshot=customer_name_snapshot,
                        customer_phone_snapshot=customer_phone_snapshot,
                        customer_email_snapshot=customer_email_snapshot,
                        appointment_date=form.cleaned_data['appointment_date'],
                        appointment_time=form.cleaned_data['appointment_time'],
                        status='NOT_ARRIVED',
                    )
            except Exception:
                import logging
                logging.getLogger(__name__).exception('Booking save failed')
                messages.error(request, 'Đặt lịch thất bại. Vui lòng thử lại hoặc liên hệ trực tiếp.')
                return _render_booking_form(request, form, customer_profile)

            messages.success(request, f'Đặt lịch thành công! Mã đặt lịch: {bk.booking_code}. Vui lòng chờ xác nhận.')
            return redirect('appointments:my_appointments')
    else:
        form = BookingOnlineForm(customer_profile=customer_profile)

    return _render_booking_form(request, form, customer_profile)


"""   
    Mục đích:
    - Lấy tất cả services + variants từ database
    - Format thành JSON để JavaScript dùng cho dropdown
    - Render template với đầy đủ context data
"""
def _render_booking_form(request, form, customer_profile):
    # 1. Lấy tất cả services đang hoạt động
    services = Service.objects.filter(status='ACTIVE').prefetch_related('variants')

    import json as _json
    # chuẩn bị data cho JS
    # 2. Format data cho JavaScript: {service_id: [variants]}
    services_with_variants = {
        str(s.id): [
            {'id': v.id,
             'label': v.label,
             'duration_minutes': v.duration_minutes, 
             'price': float(v.price)
            }
            for v in s.variants.order_by('sort_order', 'duration_minutes')
        ]
        for s in services
    }

    return render(request, 'appointments/booking.html', {
        'form': form,
        'services': services,
        'services_variants_json': _json.dumps(services_with_variants),
        'customer_profile': customer_profile,
    })


# =====================================================
# TRANG LỊCH HẸN CỦA TÔI 
#Hiển thị trang "Lịch hẹn của tôi" cho khách hàng, với bộ lọc trạng thái 
# (Tất cả, Chờ xác nhận, Đã xác nhận, etc.)
# =====================================================

@customer_required()
def my_appointments(request):
    """Trang xem lịch hẹn của khách hàng."""
    # ── Step 1: Lấy input ──
    customer_profile = request.user.customer_profile  # User đang login
    status_filter    = request.GET.get('status', 'all')  # Filter từ URL (?status=pending)

    # ── Step 2: Query tất cả appointments của khách ──
    appointments = Appointment.objects.filter(
        customer=customer_profile,        # Chỉ lấy của user hiện tại
        deleted_at__isnull=True,          # Chỉ lấy chưa xóa
    ).select_related(
        'booking',                        # Join để lấy booking_code, booker_notes
        'service_variant__service'        # Join để lấy tên dịch vụ
    )

    # ── Step 3: Áp dụng bộ lọc (nếu có) ──
    # Map filter URL → điều kiện filter DB
    # Note: 'completed' filter theo appointment.status (vì Booking không có status này)
    FILTER_MAP = {
        'pending':   {'booking__status': 'PENDING'},      # Chờ xác nhận
        'confirmed': {'booking__status': 'CONFIRMED'},    # Đã xác nhận
        'completed': {'status': 'COMPLETED'},             # Hoàn thành
        'cancelled': {'booking__status': 'CANCELLED'},    # Đã hủy
        'rejected':  {'booking__status': 'REJECTED'},     # Đã từ chối
    }

    if status_filter != 'all' and status_filter in FILTER_MAP:
        appointments = appointments.filter(**FILTER_MAP[status_filter])

    # ── Step 4: Sắp xếp ──
    appointments = appointments.order_by('-booking__created_at')  # Mới nhất trước

    # ── Step 5: Đếm số lượng theo từng trạng thái (để hiển thị trên tab filter) ──
    base_qs = Appointment.objects.filter(customer=customer_profile, deleted_at__isnull=True)
    status_counts = {
        'pending':   base_qs.filter(booking__status='PENDING').count(),
        'confirmed': base_qs.filter(booking__status='CONFIRMED').count(),
        'completed': base_qs.filter(status='COMPLETED').count(),
        'cancelled': base_qs.filter(booking__status='CANCELLED').count(),
        'rejected':  base_qs.filter(booking__status='REJECTED').count(),
    }
    status_counts['all'] = base_qs.count()

    # ── Step 6: Render template ──
    return render(request, 'appointments/my_appointments.html', {
        'appointments': appointments,        # Danh sách sau khi lọc
        'status_filter': status_filter,      # Filter hiện tại (để highlight tab)
        'status_counts': status_counts,      # Số lượng mỗi trạng thái
    })


# =====================================================
# HỦY LỊCH HẸN (khách hàng)
# =====================================================

@customer_required()
def cancel_appointment(request, appointment_id):
    """Hủy lịch hẹn (khách hàng tự hủy)."""
    # ── Step 1: Lấy appointment + Kiểm tra quyền ──
    # Chỉ lấy appointment của user đang login (customer=...)
    # Nếu không tìm thấy → 404 Not Found
    # Note: UI đã kiểm soát trạng thái, không cần validate lại ở đây
    appointment = get_object_or_404(
        Appointment,
        id=appointment_id,
        customer=request.user.customer_profile,
        deleted_at__isnull=True
    )
    booking = appointment.booking

    # ── Step 2: Thực hiện hủy (dùng transaction để đảm bảo toàn vẹn dữ liệu) ──
    try:
        from django.utils import timezone
        from django.db import transaction

        with transaction.atomic():  # Transaction: Hoàn thành TẤT CẢ hoặc KHÔNG làm gì cả
            # Nếu có lỗi bất kỳ → tự động rollback (hoàn tác) tất cả thay đổi

            # ── Cập nhật Appointment ──
            appointment.status = 'CANCELLED'  # Đổi trạng thái sang "Đã hủy"
            appointment.save(update_fields=['status', 'updated_at'])  # Chỉ update 2 trường này (tối ưu)

            # ── Cập nhật Booking (nếu có) ──
            if booking:
                booking.status = 'CANCELLED'  # Đổi trạng thái booking sang "Đã hủy"
                booking.cancelled_at = timezone.now()  # Ghi thời điểm hủy
                booking.save(update_fields=['status', 'cancelled_at', 'updated_at'])  # Chỉ update 3 trường này

        messages.success(request, f'Đã hủy lịch hẹn {appointment.appointment_code}.')

    except Exception:
        messages.error(request, 'Hủy lịch thất bại, vui lòng thử lại.')

    # ── Step 3: Redirect về trang lịch hẹn ──
    return redirect('appointments:my_appointments')


# =====================================================
# TRANG QUẢN LÝ LỊCH HẸN (Admin)
# =====================================================

@login_required(login_url='accounts:login')
def admin_appointments(request):
    """Trang quản lý lịch hẹn (staff/admin)."""
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, 'Bạn không có quyền truy cập trang này.')
        return redirect('pages:home')
    return render(request, 'manage/pages/admin_appointments.html')
