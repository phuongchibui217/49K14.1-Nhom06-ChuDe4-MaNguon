"""
API Endpoints cho Complaints

Tất cả endpoints trả về JSON.

LUỒNG: FE (JavaScript) → Gọi API → File này → Model → Trả JSON → FE render

Author: Spa ANA Team
"""

import json
import time

from django.views.decorators.http import require_http_methods
from django.db.models import Q
from django.http import JsonResponse, StreamingHttpResponse
from django.utils import timezone

from .models import Complaint, ComplaintReply, ComplaintHistory
from .serializers import serialize_complaint, serialize_reply, serialize_history
from core.api_response import ApiResponse, staff_api, safe_api, get_or_404
from core.user_service import get_display_name


# =====================================================
# HELPER
# =====================================================

def _is_authenticated(request):
    return request.user.is_authenticated


def _is_staff(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


# =====================================================
# API: DANH SÁCH KHIẾU NẠI (ADMIN)
# =====================================================

@require_http_methods(["GET"])
def api_complaints_list(request):
    """
    API: Lấy danh sách khiếu nại (admin)

    FE gọi: GET /api/complaints/?status=new&q=nguyen&page=1

    Query params (optional):
    - q: tìm kiếm theo mã, tên, SĐT, email, tiêu đề
    - status: lọc theo trạng thái
    - assigned_to: lọc theo người phụ trách (user id)
    - page: trang (default 1, mỗi trang 20)
    """
    if not _is_staff(request.user):
        return ApiResponse.forbidden()

    complaints = Complaint.objects.select_related('customer', 'assigned_to', 'related_service').all()

    # Tìm kiếm
    search = request.GET.get('q', '').strip()
    if search:
        complaints = complaints.filter(
            Q(code__icontains=search) |
            Q(full_name__icontains=search) |
            Q(phone__icontains=search) |
            Q(email__icontains=search) |
            Q(title__icontains=search)
        )

    # Lọc trạng thái
    status = request.GET.get('status', '')
    if status:
        complaints = complaints.filter(status=status)

    # Lọc người phụ trách
    assigned_to = request.GET.get('assigned_to', '')
    if assigned_to:
        complaints = complaints.filter(assigned_to_id=assigned_to)

    complaints = complaints.order_by('-created_at')

    # Pagination
    try:
        page = int(request.GET.get('page', 1))
    except ValueError:
        page = 1
    per_page = 20
    total = complaints.count()
    start = (page - 1) * per_page
    complaints_page = complaints[start:start + per_page]

    return ApiResponse.success(data={
        'complaints': [serialize_complaint(c) for c in complaints_page],
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page,
    })


# =====================================================
# API: CHI TIẾT KHIẾU NẠI
# =====================================================

@require_http_methods(["GET"])
def api_complaint_detail(request, complaint_id):
    """
    API: Lấy chi tiết 1 khiếu nại

    FE gọi: GET /api/complaints/<id>/

    - Staff: xem tất cả replies (kể cả internal)
    - Customer: chỉ xem replies của mình (is_internal=False)
    """
    if not _is_authenticated(request):
        return ApiResponse.unauthorized()

    complaint, error = get_or_404(Complaint, id=complaint_id)
    if error:
        return error

    # Kiểm tra quyền: staff xem tất cả, customer chỉ xem của mình
    if not _is_staff(request.user):
        if not complaint.customer or complaint.customer.user != request.user:
            return ApiResponse.forbidden()
        replies = complaint.replies.filter(is_internal=False).order_by('created_at')
    else:
        replies = complaint.replies.all().order_by('created_at')

    history = complaint.history.all()[:50]

    return ApiResponse.success(data={
        'complaint': serialize_complaint(complaint),
        'replies': [serialize_reply(r) for r in replies],
        'history': [serialize_history(h) for h in history],
    })


# =====================================================
# API: TẠO KHIẾU NẠI (CUSTOMER)
# =====================================================

@require_http_methods(["POST"])
@safe_api
def api_complaint_create(request):
    """
    API: Khách hàng tạo khiếu nại mới

    FE gọi: POST /api/complaints/create/
    Body JSON: {
        "title": "...",
        "content": "...",
        "incident_date": "2026-04-01",   // optional
        "appointment_code": "APT001",    // optional
        "related_service_id": 1,         // optional
        "expected_solution": "..."       // optional
    }

    Nếu chưa đăng nhập: cần thêm full_name, phone, email
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return ApiResponse.bad_request('Dữ liệu JSON không hợp lệ')

    title = data.get('title', '').strip()
    content = data.get('content', '').strip()

    if not title or len(title) < 5:
        return ApiResponse.bad_request('Tiêu đề phải có ít nhất 5 ký tự')
    if not content or len(content) < 10:
        return ApiResponse.bad_request('Nội dung phải có ít nhất 10 ký tự')

    complaint = Complaint(title=title, content=content)

    # Thông tin liên hệ
    if request.user.is_authenticated:
        from customers.models import CustomerProfile
        customer_profile, _ = CustomerProfile.objects.get_or_create(
            user=request.user,
            defaults={
                'full_name': request.user.get_full_name() or request.user.username,
                'phone': request.user.username,
            }
        )
        complaint.customer = customer_profile
        complaint.full_name = customer_profile.full_name
        complaint.phone = customer_profile.phone
        complaint.email = request.user.email or None
        complaint.customer_name_snapshot = customer_profile.full_name
        complaint.customer_phone_snapshot = customer_profile.phone
        complaint.customer_email_snapshot = request.user.email or ''
    else:
        full_name = data.get('full_name', '').strip()
        phone = data.get('phone', '').strip()
        if not full_name:
            return ApiResponse.bad_request('Vui lòng nhập họ và tên')
        if not phone:
            return ApiResponse.bad_request('Vui lòng nhập số điện thoại')
        complaint.full_name = full_name
        complaint.phone = phone
        complaint.email = data.get('email', '').strip() or None
        complaint.customer_name_snapshot = full_name
        complaint.customer_phone_snapshot = phone
        complaint.customer_email_snapshot = data.get('email', '').strip() or None

    # Thông tin liên quan (optional)
    incident_date = data.get('incident_date')
    if incident_date:
        try:
            from datetime import datetime
            complaint.incident_date = datetime.strptime(incident_date, '%Y-%m-%d').date()
        except ValueError:
            return ApiResponse.bad_request('Định dạng ngày không hợp lệ (YYYY-MM-DD)')

    complaint.appointment_code = data.get('appointment_code', '').strip()
    complaint.expected_solution = data.get('expected_solution', '').strip()

    related_service_id = data.get('related_service_id')
    if related_service_id:
        from spa_services.models import Service
        try:
            complaint.related_service = Service.objects.get(id=related_service_id)
        except Service.DoesNotExist:
            return ApiResponse.bad_request('Dịch vụ không tồn tại')

    complaint.save()

    # Log history - chỉ log khi có user (performed_by không cho phép NULL)
    if request.user.is_authenticated:
        ComplaintHistory.log(
            complaint=complaint,
            action='CREATE',
            note='Tạo qua API',
            performed_by=request.user
        )

    return ApiResponse.created(
        data={'complaint': serialize_complaint(complaint)},
        message=f'Đã gửi khiếu nại thành công! Mã: {complaint.code}'
    )


# =====================================================
# API: GỬI PHẢN HỒI
# =====================================================

@require_http_methods(["POST"])
def api_complaint_reply(request, complaint_id):
    """
    API: Gửi phản hồi cho khiếu nại

    FE gọi: POST /api/complaints/<id>/reply/
    Body JSON: {
        "message": "...",
        "is_internal": false   // chỉ staff dùng
    }
    """
    if not _is_authenticated(request):
        return ApiResponse.unauthorized()

    complaint, error = get_or_404(Complaint, id=complaint_id)
    if error:
        return error

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return ApiResponse.bad_request('Dữ liệu JSON không hợp lệ')

    message = data.get('message', '').strip()
    if not message or len(message) < 3:
        return ApiResponse.bad_request('Nội dung phản hồi phải có ít nhất 3 ký tự')

    is_staff = _is_staff(request.user)

    # Kiểm tra quyền customer
    if not is_staff:
        if not complaint.customer or complaint.customer.user != request.user:
            return ApiResponse.forbidden()

    reply = ComplaintReply(
        complaint=complaint,
        sender=request.user,
        message=message,
    )

    if is_staff:
        reply.sender_role = 'ADMIN' if request.user.is_superuser else 'STAFF'
        reply.sender_name = get_display_name(request.user)
        reply.is_internal = data.get('is_internal', False)
    else:
        if complaint.status == 'RESOLVED':
            return ApiResponse.bad_request('Khiếu nại đã hoàn thành, không thể phản hồi')
        reply.sender_role = 'CUSTOMER'
        reply.sender_name = complaint.customer_name_snapshot or complaint.full_name
        reply.is_internal = False

    reply.save()

    ComplaintHistory.log(
        complaint=complaint,
        action='REPLY',
        note=f'Phản hồi bởi {reply.sender_name}',
        performed_by=request.user
    )

    return ApiResponse.success(
        data={'reply': serialize_reply(reply)},
        message='Đã gửi phản hồi'
    )


# =====================================================
# API: CẬP NHẬT TRẠNG THÁI (ADMIN)
# =====================================================

@require_http_methods(["POST"])
@staff_api
def api_complaint_status(request, complaint_id):
    """
    API: Cập nhật trạng thái khiếu nại

    FE gọi: POST /api/complaints/<id>/status/
    Body JSON: { "status": "processing" }
    """
    complaint, error = get_or_404(Complaint, id=complaint_id)
    if error:
        return error

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return ApiResponse.bad_request('Dữ liệu JSON không hợp lệ')

    new_status = data.get('status', '')
    valid_statuses = dict(Complaint.STATUS_CHOICES)

    if new_status not in valid_statuses:
        return ApiResponse.bad_request(f'Trạng thái không hợp lệ. Các giá trị hợp lệ: {", ".join(valid_statuses.keys())}')

    old_status = complaint.get_status_display()
    complaint.status = new_status
    complaint.save()

    ComplaintHistory.log(
        complaint=complaint,
        action='UPDATE',
        old_value=old_status,
        new_value=complaint.get_status_display(),
        performed_by=request.user
    )

    return ApiResponse.success(
        data={'complaint': serialize_complaint(complaint)},
        message=f'Đã cập nhật trạng thái: {complaint.get_status_display()}'
    )


# =====================================================
# API: PHÂN CÔNG (ADMIN)
# =====================================================

@require_http_methods(["POST"])
@staff_api
def api_complaint_assign(request, complaint_id):
    """
    API: Phân công người phụ trách

    FE gọi: POST /api/complaints/<id>/assign/
    Body JSON: { "user_id": 5 }
    """
    complaint, error = get_or_404(Complaint, id=complaint_id)
    if error:
        return error

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return ApiResponse.bad_request('Dữ liệu JSON không hợp lệ')

    user_id = data.get('user_id')
    if not user_id:
        return ApiResponse.bad_request('Vui lòng cung cấp user_id')

    from django.contrib.auth.models import User
    try:
        assignee = User.objects.get(id=user_id, is_staff=True, is_active=True)
    except User.DoesNotExist:
        return ApiResponse.not_found('Không tìm thấy nhân viên')

    old_assignee = complaint.assigned_to
    complaint.assigned_to = assignee
    complaint.status = 'IN_PROGRESS'
    complaint.save()

    ComplaintHistory.log(
        complaint=complaint,
        action='ASSIGN',
        old_value=old_assignee.get_full_name() if old_assignee else '',
        new_value=assignee.get_full_name() or assignee.username,
        performed_by=request.user
    )

    return ApiResponse.success(
        data={'complaint': serialize_complaint(complaint)},
        message=f'Đã phân công cho {assignee.get_full_name() or assignee.username}'
    )


# =====================================================
# API: NHẬN XỬ LÝ (ADMIN)
# =====================================================

@require_http_methods(["POST"])
@staff_api
def api_complaint_take(request, complaint_id):
    """
    API: Nhân viên tự nhận xử lý khiếu nại

    FE gọi: POST /api/complaints/<id>/take/
    """
    complaint, error = get_or_404(Complaint, id=complaint_id)
    if error:
        return error

    if complaint.assigned_to:
        return ApiResponse.bad_request('Khiếu nại này đã được phân công')

    complaint.assigned_to = request.user
    complaint.status = 'IN_PROGRESS'
    complaint.save()

    ComplaintHistory.log(
        complaint=complaint,
        action='ASSIGN',
        new_value=request.user.get_full_name() or request.user.username,
        note='Nhân viên tự nhận xử lý',
        performed_by=request.user
    )

    return ApiResponse.success(
        data={'complaint': serialize_complaint(complaint)},
        message='Bạn đã nhận xử lý khiếu nại này'
    )


# =====================================================
# API: HOÀN THÀNH (ADMIN)
# =====================================================

@require_http_methods(["POST"])
@staff_api
def api_complaint_complete(request, complaint_id):
    """
    API: Đánh dấu hoàn thành khiếu nại

    FE gọi: POST /api/complaints/<id>/complete/
    Body JSON: { "resolution": "Đã xử lý xong..." }
    """
    complaint, error = get_or_404(Complaint, id=complaint_id)
    if error:
        return error

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return ApiResponse.bad_request('Dữ liệu JSON không hợp lệ')

    resolution = data.get('resolution', '').strip()
    if not resolution:
        return ApiResponse.bad_request('Vui lòng nhập kết quả xử lý')

    if not complaint.assigned_to:
        return ApiResponse.bad_request('Khiếu nại chưa được phân công')

    complaint.resolution = resolution
    complaint.status = 'RESOLVED'
    complaint.resolved_at = timezone.now()
    complaint.save()

    ComplaintHistory.log(
        complaint=complaint,
        action='RESOLVE',
        note=resolution,
        performed_by=request.user
    )

    return ApiResponse.success(
        data={'complaint': serialize_complaint(complaint)},
        message='Đã đánh dấu hoàn thành khiếu nại'
    )


# =====================================================
# API: THỐNG KÊ (ADMIN)
# =====================================================

@require_http_methods(["GET"])
def api_complaints_stats(request):
    """
    API: Thống kê khiếu nại theo trạng thái

    FE gọi: GET /api/complaints/stats/
    Trả về: { success: true, stats: { new: 5, pending: 3, ... }, total: 20 }
    """
    if not _is_staff(request.user):
        return ApiResponse.forbidden()

    stats = {}
    for status_code, _ in Complaint.STATUS_CHOICES:
        stats[status_code] = Complaint.objects.filter(status=status_code).count()

    return ApiResponse.success(data={
        'stats': stats,
        'total': Complaint.objects.count(),
    })


# =====================================================
# API: BADGE — SỐ KHIẾU NẠI MỚI (NEW)
# =====================================================

@require_http_methods(["GET"])
def api_complaints_new_count(request):
    """
    API: Lấy số lượng khiếu nại chưa giải quyết (NEW + IN_PROGRESS)

    FE gọi: GET /api/complaints/new-count/
    Trả về: { "success": true, "count": 3 }
    """
    if not _is_staff(request.user):
        return JsonResponse({'success': False, 'error': 'Không có quyền truy cập'}, status=403)

    try:
        count = Complaint.objects.filter(status__in=['NEW', 'IN_PROGRESS']).count()
        return JsonResponse({'success': True, 'count': count})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e), 'count': 0}, status=500)


def _complaints_new_count_stream_generator():
    """SSE generator — push số khiếu nại NEW + IN_PROGRESS mỗi 15 giây."""
    from datetime import datetime
    while True:
        try:
            count = Complaint.objects.filter(status__in=['NEW', 'IN_PROGRESS']).count()
            yield f"data: {json.dumps({'count': count, 'timestamp': datetime.now().isoformat()})}\n\n"
            time.sleep(15)
        except Exception as e:
            yield f"data: {json.dumps({'count': 0, 'error': str(e)})}\n\n"
            time.sleep(15)


@require_http_methods(["GET"])
def api_complaints_new_count_stream(request):
    """
    SSE Stream: push số khiếu nại NEW real-time

    FE gọi: GET /api/complaints/new-count/stream/
    """
    if not _is_staff(request.user):
        return JsonResponse({'success': False, 'error': 'Không có quyền truy cập'}, status=403)

    response = StreamingHttpResponse(
        _complaints_new_count_stream_generator(),
        content_type='text/event-stream'
    )
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response
