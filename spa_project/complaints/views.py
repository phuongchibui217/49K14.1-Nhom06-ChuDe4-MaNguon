"""
Views cho Complaint Management

File này chứa các views cho:
- Khách hàng tạo, xem danh sách, chi tiết, phản hồi khiếu nại
- Admin quản lý, phân công, phản hồi, đổi trạng thái, hoàn thành khiếu nại

Author: Spa ANA Team
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone

from .models import Complaint, ComplaintReply, ComplaintHistory
from customers.models import CustomerProfile
from core.user_service import get_display_name
from .forms import (
    CustomerComplaintForm,
    ComplaintReplyForm,
    ComplaintStatusForm,
    ComplaintAssignForm,
)
from core.decorators import customer_required


# =====================================================
# CUSTOMER COMPLAINT VIEWS
# =====================================================

@customer_required()
def customer_complaint_create(request):
    """Khách hàng gửi khiếu nại"""
    customer_profile = request.user.customer_profile

    if request.method == 'POST':
        form = CustomerComplaintForm(request.POST)

        if form.is_valid():
            complaint = form.save(commit=False)
            complaint.customer = customer_profile
            complaint.full_name = customer_profile.full_name
            complaint.phone = customer_profile.phone
            complaint.email = request.user.email or None
            complaint.customer_name_snapshot = customer_profile.full_name
            complaint.customer_phone_snapshot = customer_profile.phone
            complaint.customer_email_snapshot = request.user.email or ''
            complaint.save()

            # Log history (bọc trong try để không ảnh hưởng luồng chính)
            try:
                ComplaintHistory.log(
                    complaint=complaint,
                    action='CREATE',
                    note='Khách hàng tạo khiếu nại',
                    performed_by=request.user
                )
            except Exception as e:
                print(f"Warning: Could not log complaint history: {e}")

            messages.success(request, f'Đã gửi khiếu nại thành công! Mã khiếu nại: {complaint.code}')
            return redirect('complaints:customer_complaint_list')
    else:
        # GET request - luôn dùng CustomerComplaintForm
        form = CustomerComplaintForm()

    return render(request, 'complaints/customer_complaint_create.html', {
        'form': form,
        'customer_profile': customer_profile,
    })


@customer_required()
def customer_complaint_list(request):
    """Danh sách khiếu nại của khách hàng"""
    customer_profile = request.user.customer_profile
    complaints = customer_profile.complaints.all().order_by('-created_at')

    return render(request, 'complaints/customer_complaint_list.html', {
        'complaints': complaints,
        'customer_profile': customer_profile,
    })


@customer_required()
def customer_complaint_detail(request, complaint_id):
    """Chi tiết khiếu nại của khách hàng"""
    complaint = get_object_or_404(Complaint, id=complaint_id)

    # Kiểm tra quyền: chỉ chủ khiếu nại mới xem được
    if complaint.customer and complaint.customer.user != request.user:
        messages.error(request, 'Bạn không có quyền xem khiếu nại này.')
        return redirect('complaints:customer_complaint_list')

    replies = complaint.replies.filter(is_internal=False).order_by('created_at')
    history = complaint.history.all()[:20]

    reply_form = ComplaintReplyForm()

    context = {
        'complaint': complaint,
        'replies': replies,
        'history': history,
        'reply_form': reply_form,
    }
    return render(request, 'complaints/customer_complaint_detail.html', context)


@customer_required()
def customer_complaint_reply(request, complaint_id):
    """Khách hàng phản hồi khiếu nại"""
    complaint = get_object_or_404(Complaint, id=complaint_id)

    if complaint.customer and complaint.customer.user != request.user:
        messages.error(request, 'Bạn không có quyền phản hồi khiếu nại này.')
        return redirect('complaints:customer_complaint_list')

    if request.method == 'POST':
        if complaint.status == 'RESOLVED':
            messages.error(request, 'Khiếu nại đã được giải quyết, không thể phản hồi thêm.')
            return redirect('complaints:customer_complaint_detail', complaint_id=complaint_id)

        message_text = request.POST.get('message', '').strip()
        if not message_text:
            messages.error(request, 'Vui lòng nhập nội dung phản hồi.')
            return redirect('complaints:customer_complaint_detail', complaint_id=complaint_id)

        ComplaintReply.objects.create(
            complaint=complaint,
            sender=request.user,
            sender_role='CUSTOMER',
            sender_name=complaint.customer_name_snapshot or complaint.full_name,
            message=message_text,
            is_internal=False,
        )

        ComplaintHistory.log(
            complaint=complaint,
            action='REPLY',
            note='Khách hàng phản hồi bổ sung',
            performed_by=request.user
        )
        messages.success(request, 'Đã gửi phản hồi thành công.')

    return redirect('complaints:customer_complaint_detail', complaint_id=complaint_id)


# =====================================================
# ADMIN COMPLAINT MANAGEMENT VIEWS
# =====================================================

@login_required(login_url='accounts:login')
def admin_complaints(request):
    """Quản lý khiếu nại - Danh sách"""
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, 'Bạn không có quyền truy cập trang này.')
        return redirect('pages:home')

    complaints_list = Complaint.objects.all().order_by('-created_at')

    # Search
    search = request.GET.get('search', '')
    if search:
        complaints_list = complaints_list.filter(
            Q(code__icontains=search) |
            Q(customer_name_snapshot__icontains=search) |
            Q(customer_email_snapshot__icontains=search) |
            Q(customer_phone_snapshot__icontains=search) |
            Q(title__icontains=search)
        )

    # Filter by status
    status = request.GET.get('status', '')
    if status:
        complaints_list = complaints_list.filter(status=status)

    # Pagination
    paginator = Paginator(complaints_list, 10)
    page = request.GET.get('page', 1)
    complaints = paginator.get_page(page)

    context = {
        'complaints': complaints,
        'search': search,
        'status_filter': status,
    }
    return render(request, 'manage/pages/admin_complaints.html', context)


@login_required(login_url='accounts:login')
def admin_complaint_detail(request, complaint_id):
    """Chi tiết khiếu nại"""
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, 'Bạn không có quyền truy cập trang này.')
        return redirect('pages:home')

    complaint = get_object_or_404(Complaint, id=complaint_id)
    replies = complaint.replies.filter(is_internal=False).order_by('created_at')
    all_replies = complaint.replies.all().order_by('created_at')
    history = complaint.history.all()[:50]

    reply_form = ComplaintReplyForm()
    status_form = ComplaintStatusForm(instance=complaint)
    assign_form = ComplaintAssignForm(instance=complaint)

    context = {
        'complaint': complaint,
        'replies': replies,
        'all_replies': all_replies,
        'history': history,
        'reply_form': reply_form,
        'status_form': status_form,
        'assign_form': assign_form,
    }
    return render(request, 'manage/pages/admin_complaint_detail.html', context)


@login_required(login_url='accounts:login')
def admin_complaint_take(request, complaint_id):
    """Nhận xử lý khiếu nại"""
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, 'Bạn không có quyền truy cập trang này.')
        return redirect('pages:home')

    complaint = get_object_or_404(Complaint, id=complaint_id)

    if complaint.assigned_to:
        messages.warning(request, 'Khiếu nại này đã được phân công.')
    else:
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
        messages.success(request, 'Bạn đã nhận xử lý khiếu nại này.')

    return redirect('complaints:admin_complaint_detail', complaint_id=complaint_id)


@login_required(login_url='accounts:login')
def admin_complaint_assign(request, complaint_id):
    """Phân công người phụ trách"""
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, 'Bạn không có quyền truy cập trang này.')
        return redirect('pages:home')

    complaint = get_object_or_404(Complaint, id=complaint_id)

    if request.method == 'POST':
        form = ComplaintAssignForm(request.POST, instance=complaint)
        if form.is_valid():
            old_assignee = complaint.assigned_to
            complaint = form.save(commit=False)
            complaint.status = 'IN_PROGRESS'
            complaint.save()

            ComplaintHistory.log(
                complaint=complaint,
                action='ASSIGN',
                old_value=old_assignee.get_full_name() if old_assignee else '',
                new_value=complaint.assigned_to.get_full_name() or complaint.assigned_to.username,
                performed_by=request.user
            )
            messages.success(request, f'Đã phân công cho {complaint.assigned_to.get_full_name() or complaint.assigned_to.username}.')
    return redirect('complaints:admin_complaint_detail', complaint_id=complaint_id)


@login_required(login_url='accounts:login')
def admin_complaint_reply(request, complaint_id):
    """Phản hồi khiếu nại"""
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, 'Bạn không có quyền truy cập trang này.')
        return redirect('pages:home')

    complaint = get_object_or_404(Complaint, id=complaint_id)

    if request.method == 'POST':
        form = ComplaintReplyForm(request.POST)
        if form.is_valid():
            reply = form.save(commit=False)
            reply.complaint = complaint
            reply.sender = request.user
            reply.sender_role = 'ADMIN' if request.user.is_superuser else 'STAFF'
            reply.sender_name = get_display_name(request.user)
            reply.is_internal = request.POST.get('is_internal') == 'on'
            reply.save()

            ComplaintHistory.log(
                complaint=complaint,
                action='REPLY',
                note=f'Phản hồi bởi {reply.sender_name}',
                performed_by=request.user
            )
            messages.success(request, 'Đã gửi phản hồi.')

    return redirect('complaints:admin_complaint_detail', complaint_id=complaint_id)


@login_required(login_url='accounts:login')
def admin_complaint_status(request, complaint_id):
    """Cập nhật trạng thái khiếu nại"""
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, 'Bạn không có quyền truy cập trang này.')
        return redirect('pages:home')

    complaint = get_object_or_404(Complaint, id=complaint_id)

    if request.method == 'POST':
        old_status = complaint.get_status_display()
        new_status_code = request.POST.get('status')

        if new_status_code in dict(Complaint.STATUS_CHOICES):
            complaint.status = new_status_code
            complaint.save()

            ComplaintHistory.log(
                complaint=complaint,
                action='UPDATE',
                old_value=old_status,
                new_value=complaint.get_status_display(),
                performed_by=request.user
            )
            messages.success(request, f'Đã cập nhật trạng thái: {complaint.get_status_display()}')

    return redirect('complaints:admin_complaint_detail', complaint_id=complaint_id)


@login_required(login_url='accounts:login')
def admin_complaint_complete(request, complaint_id):
    """Đánh dấu hoàn thành"""
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, 'Bạn không có quyền truy cập trang này.')
        return redirect('pages:home')

    complaint = get_object_or_404(Complaint, id=complaint_id)

    if request.method == 'POST':
        resolution = request.POST.get('resolution', '').strip()

        if not resolution:
            messages.error(request, 'Vui lòng nhập kết quả xử lý.')
        elif not complaint.assigned_to:
            messages.error(request, 'Khiếu nại chưa được phân công.')
        else:
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
            messages.success(request, 'Đã đánh dấu hoàn thành khiếu nại.')

    return redirect('complaints:admin_complaint_detail', complaint_id=complaint_id)
