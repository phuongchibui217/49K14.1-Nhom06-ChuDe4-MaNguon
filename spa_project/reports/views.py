"""
Views cho Reports - Báo cáo thống kê

Chỉ Chủ Spa / Superuser mới được truy cập.

Author: Spa ANA Team
"""

from datetime import date, timedelta
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count, Q, F


from appointments.models import Appointment, Invoice
from complaints.models import Complaint
from customers.models import CustomerProfile


def _is_owner(user):
    """Chỉ superuser (Chủ Spa) mới được xem báo cáo."""
    return user.is_authenticated and user.is_superuser


@login_required(login_url='accounts:login')
def admin_reports(request):
    """
    Trang báo cáo thống kê.

    BR-UC11-01: Chỉ superuser mới được xem.
    BR-UC11-02: Lọc theo khoảng thời gian.
    BR-UC11-03: Doanh thu chỉ tính hóa đơn PAID / PARTIAL.
    BR-UC11-04: Khách hàng mới tính theo ngày tạo CustomerProfile.
    BR-UC11-05: Top khách theo số lần đặt lịch.
    BR-UC11-06: Top dịch vụ theo số lượt đặt.
    """
    if not _is_owner(request.user):
        messages.error(request, 'Bạn không có quyền truy cập trang này.')
        return redirect('pages:home')

    # ── Khoảng thời gian mặc định: đầu tháng → hôm nay ──────────────
    today = date.today()
    default_from = today.replace(day=1)
    default_to = today

    date_from_str = request.GET.get('date_from', '').strip()
    date_to_str = request.GET.get('date_to', '').strip()

    error_msg = None
    no_data = False

    # Parse ngày
    try:
        date_from = date.fromisoformat(date_from_str) if date_from_str else default_from
    except ValueError:
        date_from = default_from

    try:
        date_to = date.fromisoformat(date_to_str) if date_to_str else default_to
    except ValueError:
        date_to = default_to

    # Exception 5a: từ ngày > đến ngày
    if date_from > date_to:
        error_msg = 'Khoảng thời gian không hợp lệ. Từ ngày phải nhỏ hơn hoặc bằng Đến ngày.'
        # Reset về default để tránh query sai
        date_from = default_from
        date_to = default_to

    # ── Queries ───────────────────────────────────────────────────────
    appts_qs = Appointment.objects.filter(
        appointment_date__gte=date_from,
        appointment_date__lte=date_to,
        deleted_at__isnull=True,
    )

    # KPI 1: Tổng số lịch hẹn (không tính CANCELLED)
    total_appointments = appts_qs.exclude(status='CANCELLED').count()

    # KPI 2: Tổng doanh thu (hóa đơn PAID hoặc PARTIAL)
    # Invoice → Booking (1-1) → Appointment (FK), lọc theo ngày hẹn của appointment
    revenue_qs = Invoice.objects.filter(
        booking__appointments__appointment_date__gte=date_from,
        booking__appointments__appointment_date__lte=date_to,
        booking__appointments__deleted_at__isnull=True,
        status__in=['PAID', 'PARTIAL'],
    ).distinct()
    total_revenue = revenue_qs.aggregate(total=Sum('final_amount'))['total'] or 0

    # KPI 3: Khách hàng mới (tính theo ngày tạo CustomerProfile)
    new_customers = CustomerProfile.objects.filter(
        created_at__date__gte=date_from,
        created_at__date__lte=date_to,
    ).count()

    # KPI 4: Số khiếu nại
    total_complaints = Complaint.objects.filter(
        created_at__date__gte=date_from,
        created_at__date__lte=date_to,
    ).count()

    # Biểu đồ doanh thu theo ngày
    # Dùng ngày hẹn của appointment đầu tiên trong booking để nhóm theo ngày
    revenue_by_day = (
        Invoice.objects
        .filter(
            booking__appointments__appointment_date__gte=date_from,
            booking__appointments__appointment_date__lte=date_to,
            booking__appointments__deleted_at__isnull=True,
            status__in=['PAID', 'PARTIAL'],
        )
        .distinct()
        .values(day=F('booking__appointments__appointment_date'))
        .annotate(total=Sum('final_amount'))
        .order_by('day')
    )

    # Tạo dict ngày → doanh thu để fill đủ các ngày trong khoảng
    revenue_map = {row['day']: float(row['total']) for row in revenue_by_day}
    chart_labels = []
    chart_data = []
    delta = (date_to - date_from).days
    for i in range(delta + 1):
        d = date_from + timedelta(days=i)
        chart_labels.append(d.strftime('%d/%m'))
        chart_data.append(revenue_map.get(d, 0))

    # Top khách hàng (số lần đặt lịch, không tính CANCELLED)
    # Dùng snapshot để luôn có tên/SĐT kể cả khi customer bị NULL
    top_customers = (
        appts_qs
        .exclude(status='CANCELLED')
        .values('customer_name_snapshot', 'customer_phone_snapshot')
        .annotate(booking_count=Count('id'))
        .order_by('-booking_count')[:10]
    )

    # Top dịch vụ (số lượt đặt, không tính CANCELLED, không tính lịch chưa chọn dịch vụ)
    top_services = (
        appts_qs
        .exclude(status='CANCELLED')
        .exclude(service_variant__isnull=True)
        .values('service_variant__service__name')
        .annotate(booking_count=Count('id'))
        .order_by('-booking_count')[:5]
    )

    # Exception 6a: không có dữ liệu
    if not error_msg and total_appointments == 0 and total_revenue == 0 and new_customers == 0 and total_complaints == 0:
        no_data = True

    context = {
        'date_from': date_from.isoformat(),
        'date_to': date_to.isoformat(),
        'error_msg': error_msg,
        'no_data': no_data,
        # KPIs
        'total_appointments': total_appointments,
        'total_revenue': total_revenue,
        'new_customers': new_customers,
        'total_complaints': total_complaints,
        # Chart
        'chart_labels': chart_labels,
        'chart_data': chart_data,
        # Tables
        'top_customers': top_customers,
        'top_services': top_services,
    }
    return render(request, 'manage/pages/admin_reports.html', context)
