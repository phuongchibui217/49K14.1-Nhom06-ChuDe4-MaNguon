"""
API Endpoints cho Reports - Báo cáo thống kê (JSON)

Chỉ Superuser (Chủ Spa) mới được truy cập.

Author: Spa ANA Team
"""

from datetime import date, timedelta

from django.views.decorators.http import require_http_methods
from django.db.models import Sum, Count
from django.db.models.functions import TruncDate

from appointments.models import Appointment, Invoice
from complaints.models import Complaint
from customers.models import CustomerProfile
from core.api_response import ApiResponse


def _is_owner(user):
    return user.is_authenticated and user.is_superuser


# =====================================================
# API: BÁO CÁO THỐNG KÊ
# GET /api/reports/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
# =====================================================

@require_http_methods(["GET"])
def api_reports(request):
    """
    API: Lấy dữ liệu báo cáo thống kê

    Query params (optional):
    - date_from: YYYY-MM-DD (default: đầu tháng hiện tại)
    - date_to:   YYYY-MM-DD (default: hôm nay)

    Response 200:
    {
        "success": true,
        "date_from": "2026-04-01",
        "date_to": "2026-04-17",
        "kpi": {
            "total_appointments": 42,
            "total_revenue": 15000000,
            "new_customers": 8,
            "total_complaints": 2
        },
        "revenue_chart": {
            "labels": ["01/04", "02/04", ...],
            "data": [500000, 0, 1200000, ...]
        },
        "top_customers": [
            { "full_name": "Nguyễn Văn A", "phone": "0912...", "booking_count": 5 }
        ],
        "top_services": [
            { "name": "Massage thư giãn", "booking_count": 12 }
        ]
    }
    """
    if not _is_owner(request.user):
        return ApiResponse.forbidden('Chỉ Chủ Spa mới được xem báo cáo')

    today = date.today()
    default_from = today.replace(day=1)
    default_to = today

    date_from_str = request.GET.get('date_from', '').strip()
    date_to_str = request.GET.get('date_to', '').strip()

    try:
        date_from = date.fromisoformat(date_from_str) if date_from_str else default_from
    except ValueError:
        return ApiResponse.bad_request('Định dạng date_from không hợp lệ (YYYY-MM-DD)')

    try:
        date_to = date.fromisoformat(date_to_str) if date_to_str else default_to
    except ValueError:
        return ApiResponse.bad_request('Định dạng date_to không hợp lệ (YYYY-MM-DD)')

    if date_from > date_to:
        return ApiResponse.bad_request('Khoảng thời gian không hợp lệ: date_from phải ≤ date_to')

    # ── KPIs ─────────────────────────────────────────────────────────
    appts_qs = Appointment.objects.filter(
        appointment_date__gte=date_from,
        appointment_date__lte=date_to,
        deleted_at__isnull=True,
    )

    total_appointments = appts_qs.exclude(status='CANCELLED').count()

    total_revenue = Invoice.objects.filter(
        appointment__appointment_date__gte=date_from,
        appointment__appointment_date__lte=date_to,
        appointment__deleted_at__isnull=True,
        status__in=['PAID', 'PARTIAL'],
    ).aggregate(total=Sum('final_amount'))['total'] or 0

    new_customers = CustomerProfile.objects.filter(
        created_at__date__gte=date_from,
        created_at__date__lte=date_to,
    ).count()

    total_complaints = Complaint.objects.filter(
        created_at__date__gte=date_from,
        created_at__date__lte=date_to,
    ).count()

    # ── Revenue chart ─────────────────────────────────────────────────
    revenue_by_day = (
        Invoice.objects
        .filter(
            appointment__appointment_date__gte=date_from,
            appointment__appointment_date__lte=date_to,
            appointment__deleted_at__isnull=True,
            status__in=['PAID', 'PARTIAL'],
        )
        .annotate(day=TruncDate('appointment__appointment_date'))
        .values('day')
        .annotate(total=Sum('final_amount'))
        .order_by('day')
    )
    revenue_map = {row['day']: float(row['total']) for row in revenue_by_day}

    chart_labels = []
    chart_data = []
    for i in range((date_to - date_from).days + 1):
        d = date_from + timedelta(days=i)
        chart_labels.append(d.strftime('%d/%m'))
        chart_data.append(revenue_map.get(d, 0))

    # ── Top customers ─────────────────────────────────────────────────
    top_customers = list(
        appts_qs
        .exclude(status='CANCELLED')
        .values('customer__full_name', 'customer__phone')
        .annotate(booking_count=Count('id'))
        .order_by('-booking_count')[:10]
    )

    # ── Top services ──────────────────────────────────────────────────
    top_services = list(
        appts_qs
        .exclude(status='CANCELLED')
        .values('service__name')
        .annotate(booking_count=Count('id'))
        .order_by('-booking_count')[:10]
    )

    return ApiResponse.success(data={
        'date_from': date_from.isoformat(),
        'date_to': date_to.isoformat(),
        'kpi': {
            'total_appointments': total_appointments,
            'total_revenue': float(total_revenue),
            'new_customers': new_customers,
            'total_complaints': total_complaints,
        },
        'revenue_chart': {
            'labels': chart_labels,
            'data': chart_data,
        },
        'top_customers': [
            {
                'full_name': r['customer__full_name'] or '',
                'phone': r['customer__phone'] or '',
                'booking_count': r['booking_count'],
            }
            for r in top_customers
        ],
        'top_services': [
            {
                'name': r['service__name'] or '',
                'booking_count': r['booking_count'],
            }
            for r in top_services
        ],
    })
