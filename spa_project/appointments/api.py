"""
API Endpoints — Lịch hẹn (Organized by Tabs)

Cấu trúc mới: Booking + Appointment
- Booking = 1 lần đặt lịch (1 người đặt, nhiều khách)
- Appointment = từng khách / dịch vụ / phòng / khung giờ

TAB 1: Lịch theo phòng (Room Calendar)
TAB 2: Yêu cầu đặt lịch (Booking Requests)
SHARED: Endpoints dùng chung

Author: Spa ANA Team
"""

import json
import re
import traceback
import logging
from datetime import datetime
from decimal import Decimal

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Q
from django.db import transaction
from django.utils import timezone

from .models import Appointment, Booking, Room, Invoice, InvoiceItem, InvoicePayment
from customers.models import CustomerProfile
from spa_services.models import ServiceVariant

from .serializers import serialize_appointment, serialize_booking
from .services import validate_appointment_create, _get_appt_duration
from core.api_response import staff_api, get_or_404

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')


# ============================================================
# SECTION 2: HELPER FUNCTIONS
# ============================================================

def _is_staff(user):
    """Check if user is staff or superuser."""
    return user.is_authenticated and (user.is_staff or user.is_superuser)


def _deny():
    """Return 403 Forbidden response."""
    return JsonResponse({'success': False, 'error': 'Không có quyền truy cập'}, status=403)


def _get_variant_price(service_variant):
    """Lấy giá từ variant."""
    if service_variant and hasattr(service_variant, 'price'):
        return Decimal(str(service_variant.price))
    return Decimal('0')


# ── Pure-function helpers (no side effects) ──────────────────────────────────

def _normalize_discount_type(dtype):
    """
    Normalize discount type string về một trong {'NONE', 'AMOUNT', 'PERCENT'}.
    Chấp nhận alias cũ 'VND' → 'AMOUNT'.
    Fallback về 'NONE' nếu giá trị không hợp lệ.
    """
    raw = str(dtype or 'NONE').strip().upper()
    if raw == 'VND':
        raw = 'AMOUNT'
    if raw not in {'NONE', 'AMOUNT', 'PERCENT'}:
        raw = 'NONE'
    return raw


def _calc_discount(subtotal, dtype, dvalue):
    """
    Tính discount_amount từ subtotal + type + value.
    Kết quả được clamp về [0, subtotal].

    dtype  : 'NONE' | 'AMOUNT' | 'PERCENT'  (đã normalize)
    dvalue : Decimal
    Returns: (discount_amount: Decimal, effective_dtype: str, effective_dvalue: Decimal)
             effective_dtype/dvalue phản ánh giá trị thực tế sau khi tính
             (NONE nếu kết quả = 0).
    """
    if dtype == 'PERCENT' and dvalue:
        amount = (subtotal * dvalue / Decimal('100')).quantize(Decimal('1'))
        amount = max(Decimal('0'), min(amount, subtotal))
    elif dtype == 'AMOUNT' and dvalue:
        amount = min(dvalue, subtotal)
        amount = max(Decimal('0'), amount)
    else:
        amount = Decimal('0')

    if amount == Decimal('0'):
        return Decimal('0'), 'NONE', Decimal('0')
    return amount, dtype, dvalue


def _calc_payment_status(final_amount, total_paid, has_any_service):
    """
    Tính payment status từ final_amount, total_paid và has_any_service.

    Rules (BUG-06):
    - final == 0 VÀ có dịch vụ → PAID (discount 100%)
    - total_paid <= 0           → UNPAID
    - total_paid >= final       → PAID
    - còn lại                   → PARTIAL
    """
    if final_amount == Decimal('0') and has_any_service:
        return 'PAID'
    if total_paid <= Decimal('0'):
        return 'UNPAID'
    if total_paid >= final_amount:
        return 'PAID'
    return 'PARTIAL'


def _is_valid_vn_phone(phone):
    """
    Kiểm tra phone VN hợp lệ: 10 số, bắt đầu bằng 0.
    phone phải đã được strip về digits trước khi gọi.
    """
    return bool(re.match(r'^0\d{9}$', phone or ''))


def _time_to_minutes(t):
    """Chuyển time object sang số phút từ 00:00."""
    return t.hour * 60 + t.minute


def _count_db_overlaps(room_code, appt_date, start_min, end_min, exclude_codes=None):
    """
    Đếm số Appointment trong DB overlap với slot (room_code, appt_date, start_min, end_min).

    Exclude:
    - status='CANCELLED'
    - booking__status IN ('CANCELLED', 'REJECTED')
    - appointment_code IN exclude_codes (nếu có)

    Returns: int — số lịch overlap trong DB.
    """
    qs = Appointment.objects.filter(
        room__code=room_code,
        appointment_date=appt_date,
        deleted_at__isnull=True,
    ).exclude(
        status='CANCELLED'
    ).exclude(
        booking__status__in=['CANCELLED', 'REJECTED']
    )
    if exclude_codes:
        qs = qs.exclude(appointment_code__in=exclude_codes)

    count = 0
    for ex in qs:
        ex_start = _time_to_minutes(ex.appointment_time)
        ex_end   = ex_start + _get_appt_duration(ex)
        if start_min < ex_end and ex_start < end_min:
            count += 1
    return count


def _check_cross_capacity(slot_list, error_prefix_fn=None, status_code=400, conflict_flag=False,
                          capacity1_msg_fn=None, capacityN_msg_fn=None):
    """
    Kiểm tra capacity tổng hợp cho danh sách slots cùng phòng/ngày.

    slot_list : list of (identifier, room_code, date, start_min, end_min)
                identifier — dùng để exclude DB overlap và nhận diện slot trong req_count.
    error_prefix_fn   : callable(identifier, room_code, capacity) → str prefix (dùng khi
                        không truyền capacity1_msg_fn / capacityN_msg_fn).
    capacity1_msg_fn  : callable(identifier, room_code, capacity) → str message đầy đủ
                        khi capacity == 1. Override error_prefix_fn nếu có.
    capacityN_msg_fn  : callable(identifier, room_code, capacity) → str message đầy đủ
                        khi capacity > 1. Override error_prefix_fn nếu có.
    status_code : HTTP status khi lỗi (400 hoặc 409).
    conflict_flag : nếu True thêm 'conflict': True vào response.

    Returns: JsonResponse (lỗi) hoặc None (pass).
    """
    from collections import defaultdict as _defaultdict

    groups = _defaultdict(list)
    for entry in slot_list:
        _, room_code, appt_date, start_min, end_min = entry
        groups[(room_code, appt_date)].append(entry)

    all_req_identifiers = [entry[0] for entry in slot_list if entry[0]]

    for (room_code, appt_date), slots in groups.items():
        if len(slots) < 2:
            continue
        try:
            room_obj = Room.objects.get(code=room_code, is_active=True)
            capacity = room_obj.capacity
        except Room.DoesNotExist:
            continue

        for identifier, _, _, start_min, end_min in slots:
            db_count = _count_db_overlaps(
                room_code, appt_date, start_min, end_min,
                exclude_codes=all_req_identifiers,
            )
            req_count = sum(
                1 for other_id, _, _, o_start, o_end in slots
                if other_id != identifier and start_min < o_end and o_start < end_min
            )
            total_overlap = db_count + req_count
            if total_overlap >= capacity:
                if capacity == 1:
                    if capacity1_msg_fn:
                        msg = capacity1_msg_fn(identifier, room_code, capacity)
                    else:
                        prefix = error_prefix_fn(identifier, room_code, capacity) if error_prefix_fn else ''
                        msg = f'{prefix}Khung giờ đã có lịch ở phòng {room_code}, vui lòng chọn thời gian khác.'
                else:
                    if capacityN_msg_fn:
                        msg = capacityN_msg_fn(identifier, room_code, capacity)
                    else:
                        prefix = error_prefix_fn(identifier, room_code, capacity) if error_prefix_fn else ''
                        msg = f'{prefix}Phòng {room_code} đã đủ chỗ ở khung giờ này (sức chứa {capacity}), vui lòng chọn phòng hoặc thời gian khác.'
                body = {'success': False, 'error': msg}
                if conflict_flag:
                    body['conflict'] = True
                return JsonResponse(body, status=status_code)
    return None


def _resolve_customer_from_guest(g, cleaned):
    """
    Resolve CustomerProfile từ dữ liệu guest.

    Thứ tự ưu tiên:
    1. g['customerId'] → CustomerProfile.objects.get(id=...) — raise nếu không tìm thấy
    2. cleaned phone/email → _resolve_or_create_customer — raise nếu lỗi
    3. Không có gì → return None

    Exceptions KHÔNG được nuốt — caller tự quyết định xử lý:
    - create_batch: catch DoesNotExist / Exception → append error + continue
    - confirm_online_request: wrap try/except riêng để silent nếu cần
    """
    cust_id = g.get('customerId')
    phone   = cleaned.get('phone') or ''
    email   = cleaned.get('email') or ''
    name    = cleaned.get('customer_name', '')

    if cust_id:
        return CustomerProfile.objects.get(id=cust_id)
    if phone or email:
        return _resolve_or_create_customer(phone=phone, email=email, customer_name=name)
    return None


def _create_invoice_items(invoice, appointments):
    """
    Tạo InvoiceItem cho từng appointment thuộc invoice.
    Dùng chung cho _create_invoice_and_payment và _rebuild_invoice.

    Logic giữ nguyên:
    - unit_price  = _get_variant_price(appt.service_variant)
    - description = "{service.name} — {variant.label}" nếu có service_id,
                    ngược lại = variant.label hoặc ''
    - quantity    = 1
    - line_total  = unit_price
    """
    for appt in appointments:
        unit_price = _get_variant_price(appt.service_variant)
        desc = ''
        if appt.service_variant_id:
            try:
                sv = appt.service_variant
                desc = f"{sv.service.name} — {sv.label}" if sv.service_id else sv.label or ''
            except Exception:
                pass
        InvoiceItem.objects.create(
            invoice=invoice,
            appointment=appt,
            service_variant=appt.service_variant,
            description=desc,
            quantity=1,
            unit_price=unit_price,
            line_total=unit_price,
        )


# ─────────────────────────────────────────────────────────────────────────────

def _resolve_or_create_customer(phone=None, email=None, customer_name=''):
    """
    Tìm CustomerProfile theo phone hoặc email, tạo mới nếu chưa có.

    Thứ tự ưu tiên:
    1. Có phone → tìm theo phone, tạo mới nếu không thấy (email lưu kèm)
    2. Không có phone, có email → tìm theo email (unique), không tạo mới (thiếu phone)
    3. Không có gì → trả None

    Returns: CustomerProfile hoặc None
    """
    from django.contrib.auth.models import User
    import secrets

    phone = ''.join(filter(str.isdigit, phone or ''))
    email = (email or '').strip().lower() or None

    # ── 1. Có phone ──────────────────────────────────────────────────────────
    if phone and len(phone) >= 10:
        try:
            customer = CustomerProfile.objects.get(phone=phone)
            if customer_name and customer.full_name != customer_name:
                customer.full_name = customer_name
                customer.save(update_fields=['full_name'])
            return customer
        except CustomerProfile.DoesNotExist:
            pass

        # Không tìm thấy theo phone → tạo mới
        # Nếu email đã thuộc profile khác thì không gán email (tránh unique violation)
        safe_email = email
        if email and CustomerProfile.objects.filter(email=email).exists():
            safe_email = None

        base_username = f'guest_{phone}'
        username = base_username
        if User.objects.filter(username=username).exists():
            username = f'{base_username}_{secrets.token_hex(3)}'

        name_parts = customer_name.split() if customer_name else []
        user = User.objects.create_user(
            username=username,
            password=secrets.token_hex(16),
            first_name=name_parts[0] if name_parts else '',
            last_name=' '.join(name_parts[1:]) if len(name_parts) > 1 else '',
            email=safe_email or '',
        )
        return CustomerProfile.objects.create(
            phone=phone,
            full_name=customer_name or '',
            email=safe_email,
            user=user,
        )

    # ── 2. Không có phone, chỉ có email ─────────────────────────────────────
    if email:
        try:
            customer = CustomerProfile.objects.get(email=email)
            if customer_name and customer.full_name != customer_name:
                customer.full_name = customer_name
                customer.save(update_fields=['full_name'])
            return customer
        except CustomerProfile.DoesNotExist:
            pass
        # Không tạo mới vì phone là NOT NULL — trả None, dùng snapshot

    return None


def _create_invoice_and_payment(booking, appointments, pay_status, payment_data, created_by,
                                discount_type='NONE', discount_value=None):
    """
    Tạo Invoice + InvoiceItem + InvoicePayment cho 1 Booking.

    BUG-001 FIX: Luôn tính lại payment_status từ total_paid vs final_amount.
    Không dùng pay_status được truyền vào làm invoice.status trực tiếp —
    chỉ dùng để xác định có tạo InvoicePayment hay không.

    booking: Booking instance
    appointments: list of Appointment instances thuộc booking này
    pay_status: trạng thái thanh toán mong muốn ('UNPAID'|'PARTIAL'|'PAID')
    payment_data: dict chứa payment_method, amount, recorded_no, note
    created_by: User
    """
    # Tính tổng từ tất cả appointments
    subtotal = Decimal('0')
    for appt in appointments:
        subtotal += _get_variant_price(appt.service_variant)

    # BUG-001 FIX: Tính discount từ tham số truyền vào (thay vì hardcode 0)
    raw_dtype  = _normalize_discount_type(discount_type)
    raw_dvalue = Decimal(str(discount_value)) if discount_value is not None else Decimal('0')

    discount, raw_dtype, raw_dvalue = _calc_discount(subtotal, raw_dtype, raw_dvalue)

    final = max(subtotal - discount, Decimal('0'))

    # Tạo invoice với status tạm UNPAID — sẽ tính lại sau khi có payment
    invoice = Invoice.objects.create(
        booking=booking,
        subtotal_amount=subtotal,
        discount_type=raw_dtype,
        discount_value=raw_dvalue,
        discount_amount=discount,
        final_amount=final,
        status='UNPAID',
        created_by=created_by,
    )

    # Tạo InvoiceItem cho từng appointment
    _create_invoice_items(invoice, appointments)

    # Tạo InvoicePayment nếu có tiền thu
    if pay_status not in ('UNPAID', 'REFUNDED'):
        if pay_status == 'PAID':
            # PAID: thu đúng bằng final_amount
            pay_amount = final
        else:  # PARTIAL
            pay_amount = Decimal(str(payment_data.get('amount', 0)))

        if pay_amount > 0:
            InvoicePayment.objects.create(
                invoice=invoice,
                amount=pay_amount,
                payment_method=payment_data.get('payment_method', 'CASH'),
                transaction_status='SUCCESS',
                recorded_by=created_by,
                recorded_no=payment_data.get('recorded_no', '') or None,
                note=payment_data.get('note', '') or None,
            )

    # BUG-001 FIX: Tính lại payment_status từ total_paid vs final_amount
    # Không tin vào pay_status được truyền vào — tính từ thực tế
    total_paid = sum(
        p.amount for p in invoice.payments.filter(transaction_status='SUCCESS')
    )
    has_any_service = any(a.service_variant_id for a in appointments)
    actual_status = _calc_payment_status(final, total_paid, has_any_service)

    invoice.status = actual_status
    invoice.save(update_fields=['status'])

    # Đồng bộ booking.payment_status
    booking.payment_status = actual_status
    booking.save(update_fields=['payment_status', 'updated_at'])

    return invoice


def _validate_status_timing(appt_date, appt_time, duration_minutes, new_status):
    """
    Validate thời điểm chuyển trạng thái ARRIVED / COMPLETED.

    Rules:
    - ARRIVED   : now >= appointment_start
    - COMPLETED : now >= appointment_start + duration_minutes

    Trả về (ok: bool, error_msg: str).
    Các status khác (NOT_ARRIVED, CANCELLED) luôn pass.
    """
    if new_status not in ('ARRIVED', 'COMPLETED'):
        return True, ''

    import datetime as _dt

    # Dùng timezone local của server (settings.TIME_ZONE)
    now_local = timezone.localtime(timezone.now())
    now_date  = now_local.date()
    now_time  = now_local.time()

    # Tính start datetime
    start_dt = _dt.datetime.combine(appt_date, appt_time)
    # Tính end datetime
    end_dt   = start_dt + _dt.timedelta(minutes=int(duration_minutes or 60))

    # now datetime (naive, cùng local)
    now_dt = _dt.datetime.combine(now_date, now_time)

    if new_status == 'ARRIVED':
        if now_dt < start_dt:
            return False, 'Chưa đến giờ hẹn, không thể chuyển sang Đã đến'

    if new_status == 'COMPLETED':
        if now_dt < end_dt:
            return False, 'Chưa kết thúc giờ hẹn, không thể hoàn thành lịch'

    return True, ''


def _validate_payment_data(pay_status, payment_data, final_amount=None):
    """Validate payment fields."""
    if pay_status in ('UNPAID', 'REFUNDED'):
        return True, ''

    method = (payment_data.get('payment_method') or '').strip()
    valid_methods = ['CASH', 'CARD', 'BANK_TRANSFER', 'E_WALLET']
    if not method or method not in valid_methods:
        return False, 'Vui lòng chọn phương thức thanh toán'

    if pay_status == 'PARTIAL':
        try:
            amount = Decimal(str(payment_data.get('amount', 0)))
        except Exception:
            return False, 'Số tiền thanh toán không hợp lệ'
        if amount <= 0:
            return False, 'Số tiền thanh toán phải lớn hơn 0'
        if final_amount and amount >= Decimal(str(final_amount)):
            return False, 'Số tiền thanh toán một phần phải nhỏ hơn tổng tiền'

    return True, ''


def _validate_appointment_data(data):
    """Validate dữ liệu appointment (khách/dịch vụ/phòng/giờ) trước khi tạo."""
    errors = []
    cleaned = {}

    # Tên khách (bắt buộc)
    customer_name = data.get('customer_name', '').strip()
    if not customer_name:
        errors.append('Vui lòng nhập tên khách')
    else:
        cleaned['customer_name'] = customer_name

    # SĐT khách (tuỳ chọn — nhưng nếu có phải đúng format VN)
    phone = ''.join(filter(str.isdigit, data.get('phone', '')))
    if phone and not _is_valid_vn_phone(phone):
        errors.append('Số điện thoại khách không hợp lệ (phải có 10 số và bắt đầu bằng 0)')
    else:
        cleaned['phone'] = phone or None

    # Email khách (tuỳ chọn — validate format nếu có)
    guest_email = data.get('email', '').strip()
    if guest_email and not _EMAIL_RE.match(guest_email):
        errors.append('Email không hợp lệ')
    else:
        cleaned['email'] = guest_email or None

    # Dịch vụ (tuỳ chọn — admin có thể tạo lịch không chọn dịch vụ, khách chọn sau khi tới)
    # Logic:
    #   - Không có serviceId VÀ không có variantId → cho phép (lịch chưa chọn dịch vụ)
    #   - Có serviceId nhưng không có variantId → lỗi "Vui lòng chọn gói dịch vụ"
    #   - Có variantId → validate variant tồn tại
    service_id = data.get('service_id') or data.get('serviceId')
    variant_id = data.get('variant_id') or data.get('variantId')

    # Chuẩn hoá: coi '' và None như nhau
    service_id = service_id if service_id else None
    variant_id = variant_id if variant_id else None

    if service_id and not variant_id:
        # Đã chọn dịch vụ nhưng chưa chọn gói → bắt buộc phải chọn gói
        errors.append('Vui lòng chọn gói dịch vụ')
    elif variant_id:
        try:
            variant = ServiceVariant.objects.get(id=variant_id)
            cleaned['service_variant'] = variant
        except ServiceVariant.DoesNotExist:
            errors.append('Gói dịch vụ không tồn tại')
    else:
        # Không chọn dịch vụ lẫn gói → cho phép
        cleaned['service_variant'] = None

    # Trạng thái appointment
    status = str(data.get('status') or 'NOT_ARRIVED').strip().upper()
    valid_statuses = {choice[0] for choice in Appointment.STATUS_CHOICES}
    if status not in valid_statuses:
        errors.append('Trạng thái không hợp lệ')
    cleaned['status'] = status

    # Ngày (bắt buộc)
    date_str = data.get('date_str', '')
    if not date_str:
        errors.append('Vui lòng chọn ngày hẹn')
    else:
        try:
            cleaned['appointment_date'] = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            errors.append('Định dạng ngày không hợp lệ')

    # Giờ (bắt buộc)
    time_str = data.get('time_str', '')
    if not time_str:
        errors.append('Vui lòng chọn giờ hẹn')
    else:
        try:
            cleaned['appointment_time'] = datetime.strptime(time_str, '%H:%M').time()
        except ValueError:
            errors.append('Định dạng giờ không hợp lệ')

    # Duration từ variant hoặc fallback 60
    # Fix: kiểm tra cả service_variant không None trước khi truy cập duration_minutes
    sv = cleaned.get('service_variant')
    if sv is not None:
        try:
            cleaned['duration_minutes'] = sv.duration_minutes
        except Exception:
            cleaned['duration_minutes'] = 60
    else:
        cleaned['duration_minutes'] = 60

    # Phòng (bắt buộc)
    room_id = data.get('room_id')
    if not room_id:
        errors.append('Vui lòng chọn phòng')
    else:
        try:
            cleaned['room'] = Room.objects.get(code=room_id)
        except Room.DoesNotExist:
            errors.append('Phòng không tồn tại')

    # Validate nâng cao: trùng lịch / sức chứa phòng
    if not errors and 'appointment_date' in cleaned and 'appointment_time' in cleaned:
        room_code = cleaned['room'].code if 'room' in cleaned else None
        is_staff_confirm = data.get('is_staff_confirm', False)
        validation_result = validate_appointment_create(
            appointment_date=cleaned['appointment_date'],
            appointment_time=cleaned['appointment_time'],
            duration_minutes=cleaned['duration_minutes'],
            room_code=room_code,
            exclude_appointment_code=None,
            is_staff_confirm=is_staff_confirm,
        )
        if not validation_result['valid']:
            for err_msg in validation_result['errors']:
                lower = err_msg.lower()
                if 'đủ' in lower or 'capacity' in lower or 'chỗ' in lower:
                    errors.append('Phòng đã đủ chỗ ở khung giờ này, vui lòng chọn phòng hoặc thời gian khác.')
                elif 'trùng' in lower or 'conflict' in lower or 'đã có lịch' in lower:
                    errors.append('Khung giờ đã có lịch, vui lòng chọn thời gian khác.')
                else:
                    errors.append(err_msg)

    return {'valid': len(errors) == 0, 'errors': errors, 'cleaned_data': cleaned}


def _rebuild_invoice(booking, appointments=None, discount_type=None, discount_value=None, created_by=None):
    """
    Rebuild InvoiceItem + tính lại subtotal/discount/final/payment_status cho 1 booking.

    Dùng chung cho:
      - api_booking_invoice_pay   (truyền discount_type + discount_value mới từ request)
      - api_booking_update_batch  (giữ nguyên discount đã lưu trong DB)
      - api_confirm_online_request (giữ nguyên discount đã lưu trong DB)

    Params:
      booking        — Booking instance (đã được select_for_update bởi caller)
      appointments   — list[Appointment] để rebuild items; nếu None thì tự query từ DB
      discount_type  — 'NONE' | 'AMOUNT' | 'PERCENT' | None
                       None  → đọc từ invoice.discount_type đã lưu (hoặc 'NONE' nếu chưa có invoice)
      discount_value — Decimal | None
                       None  → đọc từ invoice.discount_value đã lưu (hoặc 0)
      created_by     — User; bắt buộc khi invoice chưa tồn tại (sẽ tạo mới)

    Returns:
      dict {
        'invoice':        Invoice instance (đã save),
        'subtotal':       Decimal,
        'discount_type':  str,
        'discount_value': Decimal,
        'discount_amount':Decimal,
        'final_amount':   Decimal,
        'total_paid':     Decimal,
        'remaining':      Decimal,
        'pay_status':     str,   # 'UNPAID' | 'PARTIAL' | 'PAID'
      }

    Caller phải đảm bảo đang trong transaction.atomic() trước khi gọi.
    """
    # ── 1. Lấy danh sách appointments ────────────────────────────────────────
    if appointments is None:
        appointments = list(
            Appointment.objects
            .filter(booking=booking, deleted_at__isnull=True)
            .select_related('service_variant')
        )

    # ── 2. Tính subtotal ──────────────────────────────────────────────────────
    subtotal = sum(_get_variant_price(a.service_variant) for a in appointments)

    # ── 3. Lấy hoặc tạo Invoice ───────────────────────────────────────────────
    try:
        inv = Invoice.objects.select_for_update().get(booking=booking)
        is_new = False
    except Invoice.DoesNotExist:
        if created_by is None:
            raise ValueError('_rebuild_invoice: created_by bắt buộc khi invoice chưa tồn tại')
        inv = Invoice(
            booking=booking,
            subtotal_amount=Decimal('0'),
            discount_type='NONE',
            discount_value=Decimal('0'),
            discount_amount=Decimal('0'),
            final_amount=Decimal('0'),
            status='UNPAID',
            created_by=created_by,
        )
        is_new = True

    # ── 4. Xác định discount_type / discount_value ────────────────────────────
    # Normalize alias cũ 'VND' → 'AMOUNT' (dù từ request hay từ DB)
    if discount_type is not None:
        raw_dtype = _normalize_discount_type(discount_type)
    else:
        raw_dtype = _normalize_discount_type(inv.discount_type or 'NONE')

    if discount_value is not None:
        raw_dvalue = Decimal(str(discount_value))
    else:
        raw_dvalue = inv.discount_value or Decimal('0')

    # ── 5. Tính discount_amount (clamp) ──────────────────────────────────────
    discount_amount, raw_dtype, raw_dvalue = _calc_discount(subtotal, raw_dtype, raw_dvalue)

    final_amount = max(subtotal - discount_amount, Decimal('0'))

    # ── 6. Rebuild InvoiceItem ────────────────────────────────────────────────
    # BUG-005 FIX: Nếu invoice mới (is_new=True), phải save trước để có pk
    # trước khi tạo InvoiceItem (InvoiceItem.invoice_id cần pk hợp lệ).
    if is_new:
        inv.subtotal_amount = subtotal
        inv.discount_type   = raw_dtype
        inv.discount_value  = raw_dvalue
        inv.discount_amount = discount_amount
        inv.final_amount    = final_amount
        inv.status          = 'UNPAID'  # tạm UNPAID, sẽ cập nhật ở bước 9
        inv.save()

    if not is_new:
        inv.items.all().delete()

    _create_invoice_items(inv, appointments)

    # ── 7. Tính total_paid ────────────────────────────────────────────────────
    if is_new:
        total_paid = Decimal('0')
    else:
        total_paid = sum(
            p.amount for p in inv.payments.filter(transaction_status='SUCCESS')
        )

    # ── 8. Xác định payment_status ────────────────────────────────────────────
    # BUG-06: Chỉ auto-PAID khi final_amount == 0 VÀ có ít nhất 1 dịch vụ
    has_any_service = any(a.service_variant_id for a in appointments)
    pay_status = _calc_payment_status(final_amount, total_paid, has_any_service)

    # ── 9. Save Invoice ───────────────────────────────────────────────────────
    inv.subtotal_amount = subtotal
    inv.discount_type   = raw_dtype
    inv.discount_value  = raw_dvalue
    inv.discount_amount = discount_amount
    inv.final_amount    = final_amount
    inv.status          = pay_status
    # is_new đã được save ở bước 6 (với fields đầy đủ) — chỉ cần update_fields để
    # cập nhật pay_status và các giá trị đã tính xong ở bước 5/8.
    inv.save(update_fields=[
        'subtotal_amount', 'discount_type', 'discount_value',
        'discount_amount', 'final_amount', 'status',
    ])

    # ── 10. Save Booking.payment_status ──────────────────────────────────────
    booking.payment_status = pay_status
    booking.save(update_fields=['payment_status', 'updated_at'])

    remaining = max(final_amount - total_paid, Decimal('0'))

    return {
        'invoice':         inv,
        'subtotal':        subtotal,
        'discount_type':   raw_dtype,
        'discount_value':  raw_dvalue,
        'discount_amount': discount_amount,
        'final_amount':    final_amount,
        'total_paid':      total_paid,
        'remaining':       remaining,
        'pay_status':      pay_status,
    }


# ============================================================
# SECTION 3: SHARED ENDPOINTS
# ============================================================

@require_http_methods(["GET"])
def api_appointments_search(request):
    """
    [SHARED] GET /api/appointments/search/

    Tìm kiếm lịch hẹn toàn hệ thống.
    """
    if not _is_staff(request.user):
        return _deny()

    q          = request.GET.get('q', '').strip()
    name       = request.GET.get('name', '').strip()
    code       = request.GET.get('code', '').strip()
    phone      = request.GET.get('phone', '').strip()
    email      = request.GET.get('email', '').strip()
    status     = request.GET.get('status', '').strip().upper()
    source     = request.GET.get('source', '').strip()
    service_id = request.GET.get('service', '').strip()
    room_code  = request.GET.get('room', '').strip()
    date_from  = request.GET.get('date_from', '').strip()
    date_to    = request.GET.get('date_to', '').strip()

    has_condition = any([q, name, code, phone, email, status, source, service_id, room_code, date_from, date_to])
    if not has_condition:
        return JsonResponse({'success': False, 'error': 'Vui lòng nhập điều kiện tìm kiếm'}, status=400)

    qs = Appointment.objects.filter(deleted_at__isnull=True).select_related('booking', 'customer', 'service_variant__service', 'room')

    if q:
        qs = qs.filter(
            Q(customer_name_snapshot__icontains=q) |
            Q(booking__booker_name__icontains=q) |
            Q(customer__full_name__icontains=q) |
            Q(customer_phone_snapshot__icontains=q) |
            Q(booking__booker_phone__icontains=q) |
            Q(customer_email_snapshot__icontains=q) |
            Q(booking__booker_email__icontains=q) |
            Q(appointment_code__icontains=q) |
            Q(booking__booking_code__icontains=q) |
            Q(customer__phone__icontains=q)
        )
    if name:
        qs = qs.filter(
            Q(customer_name_snapshot__icontains=name) |
            Q(booking__booker_name__icontains=name)
        )
    if code:
        qs = qs.filter(
            Q(appointment_code__icontains=code) |
            Q(booking__booking_code__icontains=code)
        )
    if phone:
        qs = qs.filter(
            Q(customer_phone_snapshot__icontains=phone) |
            Q(booking__booker_phone__icontains=phone) |
            Q(customer__phone__icontains=phone)
        )
    if email:
        qs = qs.filter(
            Q(customer_email_snapshot__icontains=email) |
            Q(booking__booker_email__icontains=email)
        )
    if status:
        # Appointment.status: NOT_ARRIVED, ARRIVED, COMPLETED, CANCELLED
        # Booking.status:     PENDING, CONFIRMED, CANCELLED, REJECTED
        if status in {'NOT_ARRIVED', 'ARRIVED', 'COMPLETED', 'CANCELLED'}:
            # Filter theo appointment.status, loại trừ booking bị từ chối
            # để tránh REJECTED booking cascade CANCELLED vào kết quả sai
            qs = qs.filter(status=status).exclude(booking__status='REJECTED')
        elif status == 'REJECTED':
            # REJECTED chỉ tồn tại ở Booking → lấy tất cả appointment thuộc booking bị từ chối
            qs = qs.filter(booking__status='REJECTED')
        elif status in {'PENDING', 'CONFIRMED'}:
            qs = qs.filter(booking__status=status)
    if source:
        qs = qs.filter(booking__source=source)
    if service_id:
        qs = qs.filter(service_variant__service_id=service_id)
    if room_code:
        qs = qs.filter(room__code=room_code)
    if date_from:
        qs = qs.filter(appointment_date__gte=date_from)
    if date_to:
        qs = qs.filter(appointment_date__lte=date_to)

    results = list(qs.order_by('-appointment_date', '-appointment_time')[:100])

    if name:
        name_lower = name.lower()
        results = [a for a in results if
                   name_lower in (a.customer_name_snapshot or '').lower() or
                   name_lower in (a.booking.booker_name or '').lower() or
                   name_lower in (a.customer.full_name if a.customer_id else '').lower()]

    return JsonResponse({'success': True, 'appointments': [serialize_appointment(a) for a in results]})


@require_http_methods(["GET"])
def api_customer_search(request):
    """
    [SHARED] GET /api/customers/search/?q=...

    Tìm khách hàng theo tên, SĐT hoặc email.

    TAB: Used by both Room Calendar and Booking Requests
    Methods: GET

    Query params:
    - q: Search query (min 2 characters)

    Returns: Max 10 customers with id, fullName, phone, email
    """
    if not _is_staff(request.user):
        return _deny()

    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'success': True, 'customers': []})

    customers = CustomerProfile.objects.filter(
        Q(full_name__icontains=q) | Q(phone__icontains=q) | Q(user__email__icontains=q)
    ).select_related('user')[:10]

    return JsonResponse({
        'success': True,
        'customers': [
            {
                'id':       c.id,
                'fullName': c.full_name,
                'phone':    c.phone,
                'email':    c.user.email if c.user else (c.email or ''),
                'notes':    c.notes or '',
            }
            for c in customers
        ]
    })


# ============================================================
# SECTION 4: TAB 1 - LICH THEO PHONG (ROOM CALENDAR)
# ============================================================

@require_http_methods(["GET"])
def api_rooms_list(request):
    if not _is_staff(request.user):
        return _deny()
    rooms = Room.objects.filter(is_active=True).order_by("code")
    return JsonResponse({
        "success": True,
        "rooms": [{"id": r.code, "name": r.name, "capacity": r.capacity} for r in rooms]
    })


@require_http_methods(["GET"])
def api_appointments_list(request):
    """[TAB 1] GET /api/appointments/ - Danh sach lich hen voi cac bo loc."""
    if not _is_staff(request.user):
        return _deny()
    try:
        # BUG-07: Không exclude ONLINE PENDING nữa — hiển thị trên grid với flag isPending
        # Chỉ exclude ONLINE CANCELLED/REJECTED (không cần hiện trên grid lịch phòng)
        qs = Appointment.objects.filter(deleted_at__isnull=True).select_related(
            'booking', 'customer', 'service_variant__service', 'room'
        ).exclude(
            booking__source='ONLINE',
            booking__status__in=['CANCELLED', 'REJECTED']
        )
        if date_filter := request.GET.get('date'):
            qs = qs.filter(appointment_date=date_filter)
        if status_filter := request.GET.get('status', '').strip().upper():
            qs = qs.filter(status=status_filter)
        if source_filter := request.GET.get('source'):
            qs = qs.filter(booking__source=source_filter)
        if service_filter := request.GET.get('service'):
            qs = qs.filter(service_variant__service_id=service_filter)
        if search := request.GET.get('q', '').strip():
            # BUG-09: Thêm tìm kiếm theo booking_code
            qs = qs.filter(
                Q(customer_name_snapshot__icontains=search) |
                Q(customer_phone_snapshot__icontains=search) |
                Q(customer_email_snapshot__icontains=search) |
                Q(booking__booker_name__icontains=search) |
                Q(booking__booker_phone__icontains=search) |
                Q(appointment_code__icontains=search) |
                Q(booking__booking_code__icontains=search) |
                Q(booking__booker_notes__icontains=search) |
                Q(customer__full_name__icontains=search) |
                Q(customer__phone__icontains=search)
            )
        qs = qs.order_by('appointment_date', 'appointment_time')
        return JsonResponse({'success': True, 'appointments': [serialize_appointment(a) for a in qs]})
    except Exception:
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': 'Không thể tải lịch hẹn. Vui lòng thử lại sau.'}, status=500)


@require_http_methods(["GET"])
def api_appointment_detail(request, appointment_code):
    """[TAB 1] GET /api/appointments/<code>/ - Chi tiet lich hen."""
    if not _is_staff(request.user):
        return _deny()
    try:
        appt = Appointment.objects.select_related('booking', 'customer', 'service_variant__service', 'room').get(
            appointment_code=appointment_code, deleted_at__isnull=True
        )
    except Appointment.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Không tìm thấy lịch hẹn'}, status=404)
    return JsonResponse({'success': True, 'appointment': serialize_appointment(appt)})

@require_http_methods(["POST", "DELETE"])
@staff_api
def api_booking_delete(request, booking_code):
    """
    [TAB 1] POST /api/bookings/<booking_code>/delete/
    Xóa toàn bộ booking và các lịch hẹn bên trong.
    """
    try:
        booking = Booking.objects.get(booking_code=booking_code, deleted_at__isnull=True)
    except Booking.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Không tìm thấy booking'}, status=404)

    if not _is_staff(request.user):
        return _deny()

    try:
        with transaction.atomic():
            booking = Booking.objects.select_for_update().get(id=booking.id)
            booking_pay_status = booking.payment_status or ''
            if booking_pay_status in ('PAID', 'PARTIAL', 'REFUNDED'):
                if booking_pay_status == 'PAID':
                    err_msg = 'Không thể xóa booking đã thanh toán. Vui lòng hoàn tiền trước nếu cần hủy.'
                elif booking_pay_status == 'PARTIAL':
                    err_msg = 'Không thể xóa booking đang có thanh toán một phần. Vui lòng hoàn tiền trước nếu cần hủy.'
                else:
                    err_msg = 'Không thể xóa booking đã hoàn tiền. Vui lòng giữ lại để đối soát.'
                return JsonResponse({'success': False, 'error': err_msg}, status=400)
            
            appointments = Appointment.objects.filter(booking=booking, deleted_at__isnull=True)
            if appointments.filter(status='COMPLETED').exists():
                return JsonResponse({'success': False, 'error': 'Không thể xóa booking có lịch hẹn đã hoàn thành.'}, status=400)

            now = timezone.now()
            for appt in appointments:
                appt.deleted_at = now
                appt.deleted_by_user = request.user
                appt.save(update_fields=['deleted_at', 'deleted_by_user', 'updated_at'])
            
            booking.deleted_at = now
            booking.deleted_by_user = request.user
            booking.save(update_fields=['deleted_at', 'deleted_by_user', 'updated_at'])

        return JsonResponse({
            'success': True,
            'message': 'Đã xóa toàn bộ booking',
            'booking_deleted': True,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Lỗi khi xóa booking: {str(e)}'}, status=400)


@require_http_methods(["GET"])
def api_booking_detail(request, booking_code):
    """
    [TAB 1] GET /api/bookings/<booking_code>/
    Trả về toàn bộ appointments thuộc 1 booking để edit modal hiển thị đủ khách.
    """
    if not _is_staff(request.user):
        return _deny()
    try:
        booking = Booking.objects.get(booking_code=booking_code, deleted_at__isnull=True)
    except Booking.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Không tìm thấy booking'}, status=404)

    appointments = (
        Appointment.objects
        .filter(booking=booking, deleted_at__isnull=True)
        .select_related('booking', 'customer', 'service_variant__service', 'room')
        .order_by('appointment_date', 'appointment_time')
    )
    return JsonResponse({
        'success': True,
        'booking': serialize_booking(booking),
        'appointments': [serialize_appointment(a) for a in appointments],
    })


@require_http_methods(["GET"])
@staff_api
def api_booking_invoice(request, booking_code):
    """
    [TAB 1] GET /api/bookings/<booking_code>/invoice/
    Trả về dữ liệu hóa đơn đầy đủ cho popup Invoice Modal.
    """
    try:
        booking = Booking.objects.get(booking_code=booking_code, deleted_at__isnull=True)
    except Booking.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Không tìm thấy booking'}, status=404)

    appointments = list(
        Appointment.objects
        .filter(booking=booking, deleted_at__isnull=True)
        .select_related('service_variant__service', 'customer')
        .order_by('appointment_date', 'appointment_time')
    )

    # Tính subtotal từ appointments hiện tại (giá variant thực tế)
    subtotal = Decimal('0')
    lines = []
    for appt in appointments:
        unit_price = _get_variant_price(appt.service_variant)
        subtotal += unit_price
        svc_name = variant_label = ''
        duration_min = None
        if appt.service_variant_id:
            try:
                sv = appt.service_variant
                svc_name     = sv.service.name if sv.service_id else ''
                variant_label = sv.label or ''
                duration_min  = sv.duration_minutes
            except Exception:
                pass
        lines.append({
            'apptCode':     appt.appointment_code,
            'customerName': appt.customer_name_snapshot or '',
            'serviceName':  svc_name,
            'variantLabel': variant_label,
            'durationMin':  duration_min,
            'unitPrice':    str(unit_price),
            'quantity':     1,
            'lineTotal':    str(unit_price),
        })

    # Lấy invoice nếu đã có — đọc discount_type / discount_value từ DB
    discount_type   = 'NONE'
    discount_value  = Decimal('0')
    discount_amount = Decimal('0')
    paid_amount     = Decimal('0')
    invoice_code    = ''
    try:
        inv = booking.invoice
        discount_type   = inv.discount_type   or 'NONE'
        discount_value  = inv.discount_value  or Decimal('0')
        invoice_code    = inv.code or ''
        paid_amount     = sum(
            p.amount for p in inv.payments.filter(transaction_status='SUCCESS')
        )
    except Invoice.DoesNotExist:
        pass

    # Luôn recalculate discount_amount từ discount_type + discount_value + subtotal hiện tại
    # (không dùng discount_amount cũ trong DB — subtotal có thể đã thay đổi do đổi variant)
    discount_amount, _, _ = _calc_discount(subtotal, discount_type, discount_value)

    # Tính lại final từ subtotal hiện tại — không được âm
    final     = max(subtotal - discount_amount, Decimal('0'))
    remaining = max(final - paid_amount, Decimal('0'))

    return JsonResponse({
        'success': True,
        'invoice': {
            'invoiceCode':    invoice_code,
            'bookingCode':    booking.booking_code,
            'bookerName':     booking.booker_name or '',
            'bookerPhone':    booking.booker_phone or '',
            'paymentStatus':  booking.payment_status,
            'lines':          lines,
            'subtotal':       str(subtotal),
            'discountType':   discount_type,
            'discountValue':  str(discount_value),
            'discountAmount': str(discount_amount),
            'finalAmount':    str(final),
            'paidAmount':     str(paid_amount),
            'remaining':      str(remaining),
        }
    })


@require_http_methods(["POST"])
@staff_api
def api_booking_invoice_pay(request, booking_code):
    """
    [TAB 1] POST /api/bookings/<booking_code>/invoice/pay/
    Xử lý thanh toán hóa đơn từ Invoice Modal.

    Body JSON:
    {
        "discountType":   "NONE" | "AMOUNT" | "PERCENT"
        "discountValue":  <number>,   // số tiền (AMOUNT) hoặc % (PERCENT)
        "payAmount":      <number>,   // số tiền thu lần này (0 = chỉ lưu discount)
        "paymentMethod":  "CASH" | "CARD" | "BANK_TRANSFER" | "E_WALLET"
    }

    Công thức:
        subtotal       = tổng giá variant hiện tại
        discount_amount:
            NONE/0     → 0
            AMOUNT     → min(discount_value, subtotal)
            PERCENT    → round(subtotal * discount_value / 100)
        final_amount   = subtotal - discount_amount
        payment_status:
            total_paid == 0          → UNPAID
            0 < total_paid < final   → PARTIAL
            total_paid >= final      → PAID
    """
    try:
        booking = Booking.objects.get(booking_code=booking_code, deleted_at__isnull=True)
    except Booking.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Không tìm thấy booking'}, status=404)

    try:
        raw = json.loads(request.body)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Dữ liệu không hợp lệ'}, status=400)

    # ── Đọc & validate input ─────────────────────────────────────────────────
    raw_dtype = _normalize_discount_type(raw.get('discountType') or 'NONE')

    try:
        discount_value = Decimal(str(raw.get('discountValue') or 0))
    except Exception:
        return JsonResponse({'success': False, 'error': 'Giá trị chiết khấu không hợp lệ'}, status=400)

    try:
        pay_amount = Decimal(str(raw.get('payAmount') or 0))
    except Exception:
        return JsonResponse({'success': False, 'error': 'Số tiền thanh toán không hợp lệ'}, status=400)

    pay_method = (raw.get('paymentMethod') or '').strip()
    valid_methods = {'CASH', 'CARD', 'BANK_TRANSFER', 'E_WALLET'}

    if pay_amount < 0:
        return JsonResponse({'success': False, 'error': 'Số tiền thanh toán không được âm'}, status=400)
    if pay_amount > 0 and pay_method not in valid_methods:
        return JsonResponse({'success': False, 'error': 'Vui lòng chọn phương thức thanh toán'}, status=400)
    if discount_value < 0:
        return JsonResponse({'success': False, 'error': 'Chiết khấu không được âm'}, status=400)
    if raw_dtype == 'PERCENT' and discount_value > 100:
        return JsonResponse({'success': False, 'error': 'Chiết khấu % không được vượt quá 100'}, status=400)

    # ── Rebuild invoice + ghi nhận thanh toán ────────────────────────────────
    with transaction.atomic():
        locked_booking = Booking.objects.select_for_update().get(pk=booking.pk)

        # _rebuild_invoice: tạo/cập nhật invoice, rebuild items, tính lại subtotal/discount/final
        # Truyền discount_type + discount_value mới từ request (override giá trị cũ trong DB)
        inv_result = _rebuild_invoice(
            booking=locked_booking,
            discount_type=raw_dtype,
            discount_value=discount_value,
            created_by=request.user,
        )
        inv          = inv_result['invoice']
        final_amount = inv_result['final_amount']
        discount_amount = inv_result['discount_amount']

        # ── Ghi nhận thanh toán lần này ──────────────────────────────────────
        if pay_amount > 0:
            # BUG-A04 FIX: Chặn overpay — pay_amount không được vượt quá số tiền còn lại
            # Dùng total_paid từ _rebuild_invoice (đã tính trong cùng transaction) thay vì
            # query lại để tránh inconsistency khi final_amount = 0 (chưa có dịch vụ).
            already_paid = inv_result['total_paid']
            remaining_before = inv_result['remaining']
            if pay_amount > remaining_before:
                # Thông báo rõ hơn khi final_amount = 0 (chưa có dịch vụ)
                if final_amount == Decimal('0'):
                    err_msg = (
                        'Hóa đơn chưa có dịch vụ nào (tổng tiền = 0đ). '
                        'Vui lòng lưu lịch hẹn với dịch vụ trước khi thanh toán.'
                    )
                else:
                    err_msg = (
                        f'Số tiền thanh toán ({pay_amount:,.0f}đ) vượt quá số tiền còn lại '
                        f'({remaining_before:,.0f}đ). Vui lòng kiểm tra lại.'
                    )
                return JsonResponse({'success': False, 'error': err_msg}, status=400)
            InvoicePayment.objects.create(
                invoice=inv,
                amount=pay_amount,
                payment_method=pay_method,
                transaction_status='SUCCESS',
                recorded_by=request.user,
            )

        # ── Tính lại pay_status sau khi có payment mới ───────────────────────
        # (payment vừa tạo chưa được tính trong inv_result vì tạo sau _rebuild_invoice)
        total_paid = sum(
            p.amount for p in inv.payments.filter(transaction_status='SUCCESS')
        )
        has_any_service = any(
            a.service_variant_id
            for a in Appointment.objects.filter(booking=locked_booking, deleted_at__isnull=True)
        )
        new_pay_status = _calc_payment_status(final_amount, total_paid, has_any_service)

        inv.status = new_pay_status
        inv.save(update_fields=['status'])
        locked_booking.payment_status = new_pay_status
        locked_booking.save(update_fields=['payment_status', 'updated_at'])

    remaining = max(final_amount - total_paid, Decimal('0'))

    return JsonResponse({
        'success':        True,
        'paymentStatus':  new_pay_status,
        'paidAmount':     str(total_paid),
        'finalAmount':    str(final_amount),
        'discountAmount': str(discount_amount),
        'remaining':      str(remaining),
        'message':        'Cập nhật thanh toán thành công',
    })


@require_http_methods(["POST"])
@staff_api
def api_booking_invoice_refund(request, booking_code):
    """
    [TAB 1] POST /api/bookings/<booking_code>/invoice/refund/
    Hoàn tiền hóa đơn: đổi tất cả InvoicePayment SUCCESS → REFUNDED,
    set Invoice.status = REFUNDED, Booking.payment_status = REFUNDED.

    BUG-012 FIX: Cho phép hoàn tiền cả khi PARTIAL (đã thu một phần).
    Điều kiện: phải có ít nhất 1 InvoicePayment SUCCESS với amount > 0.
    """
    try:
        booking = Booking.objects.get(booking_code=booking_code, deleted_at__isnull=True)
    except Booking.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Không tìm thấy booking'}, status=404)

    try:
        inv = booking.invoice
    except Invoice.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Không tìm thấy hóa đơn'}, status=404)

    if inv.status == 'REFUNDED':
        return JsonResponse({'success': False, 'error': 'Hóa đơn đã được hoàn tiền trước đó'}, status=400)

    if inv.status == 'UNPAID':
        return JsonResponse({'success': False, 'error': 'Hóa đơn chưa có thanh toán để hoàn'}, status=400)

    # Chỉ hoàn tiền khi thực sự có tiền đã thu (paidAmount > 0)
    # BUG-012 FIX: Cho phép cả PARTIAL — khách đã trả một phần và muốn hủy
    paid_amount = sum(
        p.amount for p in inv.payments.filter(transaction_status='SUCCESS')
    )
    if paid_amount <= 0:
        return JsonResponse({'success': False, 'error': 'Không có khoản thanh toán nào để hoàn'}, status=400)

    with transaction.atomic():
        # Đổi tất cả payment SUCCESS → REFUNDED
        inv.payments.filter(transaction_status='SUCCESS').update(transaction_status='REFUNDED')

        # Cập nhật invoice và booking
        inv.status = 'REFUNDED'
        inv.save(update_fields=['status'])

        booking.payment_status = 'REFUNDED'
        booking.save(update_fields=['payment_status', 'updated_at'])

    return JsonResponse({
        'success':       True,
        'paymentStatus': 'REFUNDED',
        'paidAmount':    str(paid_amount),
        'message':       'Đã hoàn tiền hóa đơn',
    })


@require_http_methods(["POST"])
@staff_api
def api_appointment_create_batch(request):
    """
    [TAB 1] POST /api/appointments/create-batch/
    Tao nhieu lich hen cung luc (1 nguoi dat, nhieu khach).
    Tao 1 Booking + N Appointment + 1 Invoice cho toan bo.
    """
    try:
        raw = json.loads(request.body)
        booker = raw.get('booker', {})
        guests = raw.get('guests', [])

        if not guests:
            return JsonResponse({'success': False, 'error': 'Vui lòng thêm ít nhất 1 khách'}, status=400)

        booker_name  = booker.get('name', '').strip()
        booker_phone = ''.join(filter(str.isdigit, booker.get('phone', '')))
        booker_email = booker.get('email', '').strip()
        booker_notes = booker.get('notes', '').strip()
        source       = booker.get('source', 'DIRECT')

        if not booker_name:
            return JsonResponse({'success': False, 'error': 'Vui lòng nhập họ tên người đặt'}, status=400)
        if not booker_phone or not _is_valid_vn_phone(booker_phone):
            return JsonResponse({'success': False, 'error': 'Số điện thoại người đặt không hợp lệ (phải có 10 số và bắt đầu bằng 0)'}, status=400)
        if booker_email:
            if not _EMAIL_RE.match(booker_email):
                return JsonResponse({'success': False, 'error': 'Email không hợp lệ'}, status=400)

        valid_sources = {'DIRECT', 'ONLINE', 'PHONE', 'FACEBOOK', 'ZALO'}
        if source not in valid_sources:
            source = 'DIRECT'

        # Xác định booking status:
        # - Admin tạo/rebook (fromAdmin=True hoặc source != ONLINE) → CONFIRMED
        # - Khách đặt online → PENDING (cần xác nhận)
        from_admin = bool(booker.get('fromAdmin', False))
        # Nếu admin tạo mà source vô tình là ONLINE → đổi về DIRECT để tránh hiển thị sai
        if from_admin and source == 'ONLINE':
            source = 'DIRECT'
        booking_status = 'CONFIRMED' if (from_admin or source != 'ONLINE') else 'PENDING'

        # Lay pay_status chung tu booker (hoac tu guest dau tien)
        booking_pay_status = booker.get('payStatus', 'UNPAID') or 'UNPAID'
        valid_pay = {'UNPAID', 'PARTIAL', 'PAID', 'REFUNDED'}
        if booking_pay_status not in valid_pay:
            booking_pay_status = 'UNPAID'

        # BUG-001 FIX: Đọc discount từ booker payload (FE gửi từ _createModePayment)
        booking_discount_type  = _normalize_discount_type(booker.get('discountType') or 'NONE')
        try:
            booking_discount_value = Decimal(str(booker.get('discountValue') or 0))
        except Exception:
            booking_discount_value = Decimal('0')

        created_appts = []
        errors = []

        # Validate tat ca guests truoc
        validated_guests = []
        for idx, g in enumerate(guests):
            label = f"Khach {idx + 1}"
            data = {
                'customer_name': g.get('name', '').strip(),
                'phone':         ''.join(filter(str.isdigit, g.get('phone', ''))),
                'email':         g.get('email', '').strip(),
                'service_id':    g.get('serviceId'),   # để validate "chọn dịch vụ nhưng chưa chọn gói"
                'variant_id':    g.get('variantId'),
                'room_id':       g.get('roomId'),
                'date_str':      g.get('date', ''),
                'time_str':      g.get('time', ''),
                'status':        g.get('apptStatus', 'NOT_ARRIVED'),
            }
            validation = _validate_appointment_data(data)
            if not validation['valid']:
                errors.append(f"{label}: {validation['errors'][0]}")
                continue
            validated_guests.append((idx, g, validation['cleaned_data']))

        if not validated_guests and errors:
            return JsonResponse({'success': False, 'error': '; '.join(errors)}, status=400)


        # BUG-002 FIX: Capacity check tổng hợp — DB slots + request slots cùng phòng/giờ
        # validate_appointment_create chỉ check từng khách riêng lẻ với DB, không tính
        # các khách khác trong cùng request (chưa được lưu). Cần cộng dồn thủ công.
        _slot_list_create = []
        for idx_g, (_, _, cleaned) in enumerate(validated_guests):
            room = cleaned.get('room')
            appt_date = cleaned.get('appointment_date')
            appt_time = cleaned.get('appointment_time')
            dur = cleaned.get('duration_minutes', 60)
            if not room or not appt_date or not appt_time:
                continue
            start_min = _time_to_minutes(appt_time)
            end_min   = start_min + dur
            _slot_list_create.append((idx_g + 1, room.code, appt_date, start_min, end_min))

        if _slot_list_create:
            _cap_err = _check_cross_capacity(
                _slot_list_create,
                error_prefix_fn=lambda id, room, cap: f'Khách {id}: ',
                status_code=400,
                conflict_flag=False,
                capacity1_msg_fn=lambda id, room, cap: f'Khách {id}: Khung giờ đã có lịch, vui lòng chọn thời gian khác.',
                capacityN_msg_fn=lambda id, room, cap: f'Khách {id}: Phòng đã đủ chỗ ở khung giờ này (sức chứa {cap}), vui lòng chọn phòng hoặc thời gian khác.',
            )
            if _cap_err:
                return _cap_err

        # Validate payment chung
        g_payment_data = {
            'payment_method': booker.get('paymentMethod', ''),
            'amount':         booker.get('paymentAmount', 0),
            'recorded_no':    booker.get('paymentRecordedNo', ''),
            'note':           booker.get('paymentNote', ''),
        }
        if validated_guests:
            total_price = sum(_get_variant_price(c.get('service_variant')) for _, _, c in validated_guests)
            pay_valid, pay_error = _validate_payment_data(booking_pay_status, g_payment_data, total_price)
            if not pay_valid:
                return JsonResponse({'success': False, 'error': pay_error}, status=400)

        with transaction.atomic():
            # Tao Booking
            booking = Booking.objects.create(
                booker_name=booker_name,
                booker_phone=booker_phone,
                booker_email=booker_email or None,
                booker_notes=booker_notes or None,
                status=booking_status,
                payment_status=booking_pay_status,
                source=source,
                created_by=request.user,
            )

            for idx, g, cleaned in validated_guests:
                label = f"Khach {idx + 1}"
                guest_name = cleaned.get('customer_name', '')

                customer = None
                try:
                    customer = _resolve_customer_from_guest(g, cleaned)
                except CustomerProfile.DoesNotExist:
                    errors.append(f"{label}: Không tìm thấy khách hàng")
                    continue
                except Exception as e:
                    errors.append(f"{label}: Lỗi xác định khách hàng - {str(e)}")
                    continue

                try:
                    appt_status_val = cleaned['status']
                    if appt_status_val == 'COMPLETED' and booking_pay_status not in ('PAID',):
                        errors.append(f"{label}: Không thể hoàn thành lịch khi chưa thanh toán đủ")
                        continue
                    # Validate thời điểm chuyển trạng thái
                    timing_ok, timing_err = _validate_status_timing(
                        cleaned['appointment_date'], cleaned['appointment_time'],
                        cleaned['duration_minutes'], appt_status_val
                    )
                    if not timing_ok:
                        errors.append(f"{label}: {timing_err}")
                        continue
                    appt = Appointment.objects.create(
                        booking=booking,
                        customer=customer,
                        service_variant=cleaned.get('service_variant'),
                        room=cleaned['room'],
                        customer_name_snapshot=cleaned['customer_name'],
                        customer_phone_snapshot=cleaned.get('phone'),
                        customer_email_snapshot=g.get('email', '').strip() or None,
                        appointment_date=cleaned['appointment_date'],
                        appointment_time=cleaned['appointment_time'],
                        status=appt_status_val,
                    )
                    created_appts.append(appt)
                except Exception as e:
                    errors.append(f"{label}: {str(e)}")

            if not created_appts:
                raise Exception('; '.join(errors) or 'Không tạo được lịch hẹn nào')

            # Tao Invoice cho toan bo Booking
            _create_invoice_and_payment(
                booking, created_appts, booking_pay_status, g_payment_data, request.user,
                discount_type=booking_discount_type,
                discount_value=booking_discount_value,
            )
            # BUG-A01 FIX: Không ghi đè booking.payment_status sau _create_invoice_and_payment.
            # _create_invoice_and_payment đã tính actual_status từ total_paid vs final_amount
            # và save vào booking.payment_status. Ghi đè ở đây sẽ phá vỡ kết quả đó.

        return JsonResponse({
            'success': True,
            'message': f'Đã tạo {len(created_appts)} lịch hẹn',
            'appointments': [serialize_appointment(a) for a in created_appts],
            'bookingCode': booking.booking_code,
            'errors': errors,
        })

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e) or 'Không thể tạo lịch hẹn. Vui lòng thử lại sau'}, status=400)


@require_http_methods(["POST"])
@staff_api
def api_booking_update_batch(request, booking_code):
    """
    [TAB 1] POST /api/bookings/<booking_code>/update-batch/

    BUG-02: Cập nhật toàn bộ booking + tất cả appointments trong 1 transaction atomic.
    Nếu bất kỳ appointment nào fail → rollback toàn bộ.

    BUG-13: Mỗi appointment nhận apptStatus riêng (không dùng shared status nữa).

    Body JSON:
    {
        "bookerName":  "...",
        "bookerPhone": "...",
        "bookerEmail": "...",
        "bookerNotes": "...",
        "guests": [
            {
                "appointmentCode": "APP0001",
                "customerName":    "...",
                "phone":           "...",
                "email":           "...",
                "variantId":       1,
                "roomId":          "P01",
                "date":            "2026-05-01",   // chỉ gửi khi thay đổi
                "time":            "10:00",         // chỉ gửi khi thay đổi
                "apptStatus":      "ARRIVED",       // trạng thái riêng từng khách
                "customerId":      123
            },
            ...
        ]
    }
    """
    try:
        booking = Booking.objects.get(booking_code=booking_code, deleted_at__isnull=True)
    except Booking.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Không tìm thấy booking'}, status=404)

    # Chặn sửa khi booking đã CANCELLED hoặc REJECTED
    if booking.status in ('CANCELLED', 'REJECTED'):
        return JsonResponse(
            {'success': False, 'error': f'Không thể sửa booking đã {booking.get_status_display().lower()}.'},
            status=400
        )

    try:
        raw = json.loads(request.body)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Dữ liệu không hợp lệ'}, status=400)

    guests = raw.get('guests', [])
    if not guests:
        return JsonResponse({'success': False, 'error': 'Không có dữ liệu khách để cập nhật'}, status=400)

    # ── Validate booker fields ────────────────────────────────────────────────
    new_booker_name  = raw.get('bookerName', '').strip()
    new_booker_phone = ''.join(filter(str.isdigit, raw.get('bookerPhone', '')))
    new_booker_email = raw.get('bookerEmail', '').strip()
    new_booker_notes = raw.get('bookerNotes', '').strip()

    if not new_booker_name:
        return JsonResponse({'success': False, 'error': 'Vui lòng nhập họ tên người đặt'}, status=400)
    if not new_booker_phone or not _is_valid_vn_phone(new_booker_phone):
        return JsonResponse({'success': False, 'error': 'Số điện thoại người đặt không hợp lệ (phải có 10 số và bắt đầu bằng 0)'}, status=400)

    valid_appt_statuses = {choice[0] for choice in Appointment.STATUS_CHOICES}

    all_req_identifiers = [g.get('appointmentCode').strip() for g in guests if g.get('appointmentCode')]

    # ── Pre-validate tất cả guests trước khi vào transaction ─────────────────
    # Tránh rollback giữa chừng do lỗi validate đơn giản
    pre_errors = []
    for i, g in enumerate(guests):
        label = f'Khách {i + 1}: ' if len(guests) > 1 else ''
        appt_code = (g.get('appointmentCode') or '').strip()

        # Guest không có appointmentCode → là khách mới thêm vào booking
        # Validate như create: bắt buộc room + date + time
        if not appt_code:
            if not g.get('roomId'):
                pre_errors.append(f'{label}Vui lòng chọn phòng')
            if not g.get('date'):
                pre_errors.append(f'{label}Vui lòng chọn ngày hẹn')
            if not g.get('time'):
                pre_errors.append(f'{label}Vui lòng chọn giờ hẹn')
            # Validate service/variant cho guest mới
            service_id_new = g.get('serviceId') or g.get('service_id')
            variant_id_new = g.get('variantId') or g.get('variant_id')
            service_id_new = service_id_new if service_id_new else None
            variant_id_new = variant_id_new if variant_id_new else None
            if service_id_new and not variant_id_new:
                pre_errors.append(f'{label}Vui lòng chọn gói dịch vụ')
            continue  # bỏ qua các validate dành cho appointment đã có

        # Validate apptStatus nếu có
        appt_status = (g.get('apptStatus') or '').strip().upper()
        if appt_status and appt_status not in valid_appt_statuses:
            pre_errors.append(f'{label}Trạng thái không hợp lệ ({appt_status})')

        # Validate phone nếu có
        phone = ''.join(filter(str.isdigit, g.get('phone', '')))
        if phone and not _is_valid_vn_phone(phone):
            pre_errors.append(f'{label}Số điện thoại khách không hợp lệ (phải có 10 số và bắt đầu bằng 0)')

        # Validate email nếu có
        email = g.get('email', '').strip()
        if email and not _EMAIL_RE.match(email):
            pre_errors.append(f'{label}Email không hợp lệ')

        # Validate service/variant: có serviceId nhưng không có variantId → lỗi
        service_id = g.get('serviceId') or g.get('service_id')
        variant_id = g.get('variantId') or g.get('variant_id')
        service_id = service_id if service_id else None
        variant_id = variant_id if variant_id else None
        if service_id and not variant_id:
            pre_errors.append(f'{label}Vui lòng chọn gói dịch vụ')

    if pre_errors:
        return JsonResponse({'success': False, 'error': pre_errors[0], 'errors': pre_errors}, status=400)

    # ── BUG-003 FIX: Cross-guest capacity check trước khi vào transaction ────
    # validate_appointment_create chỉ check từng appointment riêng lẻ với DB.
    # Khi edit nhiều khách đổi sang cùng phòng cùng giờ, mỗi khách pass riêng lẻ
    # nhưng tổng có thể vượt capacity. Cần check tổng hợp giống create-batch.
    #
    # Chỉ check các guest có date/time/roomId thay đổi (gửi trong payload).
    # Với mỗi slot mới, đếm: DB slots (exclude chính appointment đó) + các guest
    # khác trong request cùng phòng cùng giờ overlap.
    try:
        from collections import defaultdict as _defaultdict
        import datetime as _dt_mod

        # Thu thập thông tin slot mới của từng guest (chỉ những guest có thay đổi)
        _slot_list = []  # list of (appt_code, room_code, date, start_min, end_min)
        for g in guests:
            appt_code   = (g.get('appointmentCode') or '').strip()
            new_room_id = g.get('roomId')
            new_date_str = g.get('date', '')
            new_time_str = g.get('time', '')
            variant_id   = g.get('variantId') or g.get('variant_id')
            variant_id   = variant_id if variant_id else None

            # Chỉ xử lý khi có đủ thông tin phòng + ngày + giờ
            if not new_room_id or not new_date_str or not new_time_str:
                # Nếu thiếu một trong ba, lấy giá trị hiện tại từ DB để check
                try:
                    existing_appt = Appointment.objects.get(
                        appointment_code=appt_code, deleted_at__isnull=True
                    )
                    room_code = new_room_id or (existing_appt.room.code if existing_appt.room_id else None)
                    try:
                        appt_date = _dt_mod.datetime.strptime(new_date_str, '%Y-%m-%d').date() if new_date_str else existing_appt.appointment_date
                    except ValueError:
                        continue
                    try:
                        appt_time = _dt_mod.datetime.strptime(new_time_str, '%H:%M').time() if new_time_str else existing_appt.appointment_time
                    except ValueError:
                        continue
                    if variant_id:
                        try:
                            dur = ServiceVariant.objects.get(id=variant_id).duration_minutes
                        except ServiceVariant.DoesNotExist:
                            dur = _get_appt_duration(existing_appt)
                    else:
                        dur = _get_appt_duration(existing_appt)
                except Appointment.DoesNotExist:
                    continue
            else:
                room_code = new_room_id
                try:
                    appt_date = _dt_mod.datetime.strptime(new_date_str, '%Y-%m-%d').date()
                    appt_time = _dt_mod.datetime.strptime(new_time_str, '%H:%M').time()
                except ValueError:
                    continue
                if variant_id:
                    try:
                        dur = ServiceVariant.objects.get(id=variant_id).duration_minutes
                    except ServiceVariant.DoesNotExist:
                        dur = 60
                else:
                    dur = 60

            if not room_code:
                continue
            start_min = _time_to_minutes(appt_time)
            end_min   = start_min + dur
            _slot_list.append((appt_code, room_code, appt_date, start_min, end_min))

        # Nhóm theo (room_code, date) và check capacity qua helper
        _cap_resp = _check_cross_capacity(_slot_list, status_code=400, conflict_flag=False)
        if _cap_resp:
            return _cap_resp
    except Exception as _cap_err:
        logger.warning('update-batch capacity pre-check error: %s', _cap_err)
        # Không block request nếu pre-check lỗi — validate_appointment_create trong transaction vẫn chạy

    # ── Thực hiện trong 1 transaction atomic ─────────────────────────────────
    try:
        with transaction.atomic():
            # Lock booking
            locked_booking = Booking.objects.select_for_update().get(pk=booking.pk)

            # Cập nhật booker info
            locked_booking.booker_name  = new_booker_name
            locked_booking.booker_phone = new_booker_phone
            if 'bookerEmail' in raw:
                locked_booking.booker_email = new_booker_email or None
            if 'bookerNotes' in raw:
                locked_booking.booker_notes = new_booker_notes or None
            locked_booking.save(update_fields=['booker_name', 'booker_phone', 'booker_email', 'booker_notes', 'updated_at'])

            updated_appts = []

            for i, g in enumerate(guests):
                label = f'Khách {i + 1}: ' if len(guests) > 1 else ''
                appt_code = (g.get('appointmentCode') or '').strip()

                # ── Guest mới (không có appointmentCode) → tạo appointment mới ──
                if not appt_code:
                    new_name  = g.get('customerName', '').strip()
                    new_phone = ''.join(filter(str.isdigit, g.get('phone', '')))
                    new_email = g.get('email', '').strip() or None
                    new_room_id   = g.get('roomId', '')
                    new_date_str  = g.get('date', '')
                    new_time_str  = g.get('time', '')
                    variant_id    = g.get('variantId') or g.get('variant_id')
                    variant_id    = variant_id if variant_id else None
                    new_cust_id   = g.get('customerId')

                    # Resolve room
                    try:
                        new_room = Room.objects.get(code=new_room_id)
                    except Room.DoesNotExist:
                        raise ValueError(f'{label}Phòng không tồn tại')

                    # Parse date/time
                    try:
                        new_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
                    except (ValueError, TypeError):
                        raise ValueError(f'{label}Định dạng ngày không hợp lệ')
                    try:
                        new_time = datetime.strptime(new_time_str, '%H:%M').time()
                    except (ValueError, TypeError):
                        raise ValueError(f'{label}Định dạng giờ không hợp lệ')

                    # Resolve variant
                    new_variant = None
                    if variant_id:
                        try:
                            new_variant = ServiceVariant.objects.get(id=variant_id)
                        except ServiceVariant.DoesNotExist:
                            raise ValueError(f'{label}Gói dịch vụ không tồn tại')

                    duration = new_variant.duration_minutes if new_variant else 60

                    # Validate conflict/capacity
                    val_result = validate_appointment_create(
                        appointment_date=new_date,
                        appointment_time=new_time,
                        duration_minutes=duration,
                        room_code=new_room_id,
                        exclude_appointment_code=None,
                        is_staff_confirm=False,
                    )
                    if not val_result['valid']:
                        raise ValueError(f'{label}{val_result["errors"][0]}')

                    # Resolve customer
                    new_customer = None
                    if new_cust_id:
                        try:
                            new_customer = CustomerProfile.objects.get(id=int(new_cust_id))
                        except (CustomerProfile.DoesNotExist, ValueError, TypeError):
                            pass
                    elif new_phone and len(new_phone) >= 10:
                        try:
                            new_customer = CustomerProfile.objects.get(phone=new_phone)
                        except CustomerProfile.DoesNotExist:
                            new_customer = _resolve_or_create_customer(
                                phone=new_phone, email=new_email, customer_name=new_name
                            )

                    # Tạo appointment mới gắn vào booking hiện có
                    new_appt = Appointment.objects.create(
                        booking=locked_booking,
                        room=new_room,
                        appointment_date=new_date,
                        appointment_time=new_time,
                        service_variant=new_variant,
                        status='NOT_ARRIVED',
                        customer=new_customer,
                        customer_name_snapshot=new_name or '',
                        customer_phone_snapshot=new_phone or None,
                        customer_email_snapshot=new_email or None,
                    )
                    updated_appts.append(new_appt)
                    continue  # bỏ qua phần update bên dưới

                # Lock appointment — phải thuộc booking này
                try:
                    locked_appt = Appointment.objects.select_for_update().get(
                        appointment_code=appt_code,
                        booking=locked_booking,
                        deleted_at__isnull=True,
                    )
                except Appointment.DoesNotExist:
                    raise ValueError(f'{label}Không tìm thấy lịch hẹn {appt_code} trong booking này')

                if locked_appt.status == 'CANCELLED':
                    raise ValueError(f'{label}Không thể sửa lịch đã hủy')
                if locked_appt.status == 'COMPLETED':
                    raise ValueError(f'{label}Không thể sửa lịch đã hoàn thành')

                # ── Cập nhật snapshot fields ──────────────────────────────────
                new_name = g.get('customerName', '').strip()
                if new_name:
                    locked_appt.customer_name_snapshot = new_name

                phone = ''.join(filter(str.isdigit, g.get('phone', '')))
                if 'phone' in g:
                    locked_appt.customer_phone_snapshot = phone or None

                if 'email' in g:
                    locked_appt.customer_email_snapshot = g.get('email', '').strip() or None

                # ── Resolve CustomerProfile ───────────────────────────────────
                new_customer_id = g.get('customerId')
                if new_customer_id:
                    try:
                        locked_appt.customer = CustomerProfile.objects.get(id=int(new_customer_id))
                    except (CustomerProfile.DoesNotExist, ValueError, TypeError):
                        pass
                elif 'phone' in g:
                    if phone and len(phone) >= 10:
                        try:
                            locked_appt.customer = CustomerProfile.objects.get(phone=phone)
                        except CustomerProfile.DoesNotExist:
                            locked_appt.customer = None
                    elif not phone:
                        locked_appt.customer = None

                # ── Variant ───────────────────────────────────────────────────
                variant_id = g.get('variantId') or g.get('variant_id')
                variant_id = variant_id if variant_id else None
                if variant_id:
                    try:
                        locked_appt.service_variant = ServiceVariant.objects.get(id=variant_id)
                    except ServiceVariant.DoesNotExist:
                        raise ValueError(f'{label}Gói dịch vụ không tồn tại')
                elif 'variantId' in g and not variant_id:
                    locked_appt.service_variant = None

                # ── Room ──────────────────────────────────────────────────────
                new_room_id = g.get('roomId')
                if new_room_id is not None:
                    current_room_code = locked_appt.room.code if locked_appt.room_id else None
                    if new_room_id != current_room_code:
                        if new_room_id:
                            try:
                                locked_appt.room = Room.objects.get(code=new_room_id)
                            except Room.DoesNotExist:
                                raise ValueError(f'{label}Phòng không tồn tại')

                # ── Date / Time — validate nếu thay đổi ──────────────────────
                new_date_str = g.get('date', '')
                new_time_str = g.get('time', '')
                datetime_changed = False
                # Luôn validate khi variant đổi (duration mới có thể gây overlap dù room không đổi)
                needs_validation = bool(new_date_str or new_time_str or new_room_id is not None or variant_id)

                current_date = locked_appt.appointment_date
                current_time = locked_appt.appointment_time
                val_date = current_date
                val_time = current_time
                val_duration = _get_appt_duration(locked_appt)
                # Luôn dùng room hiện tại trên instance (có thể vừa được đổi ở bước Room)
                val_room = locked_appt.room.code if locked_appt.room_id else None

                if new_date_str:
                    try:
                        parsed_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
                        if parsed_date != current_date:
                            datetime_changed = True
                        val_date = parsed_date
                    except ValueError:
                        raise ValueError(f'{label}Định dạng ngày không hợp lệ')

                if new_time_str:
                    try:
                        parsed_time = datetime.strptime(new_time_str, '%H:%M').time()
                        if parsed_time != current_time:
                            datetime_changed = True
                        val_time = parsed_time
                    except ValueError:
                        raise ValueError(f'{label}Định dạng giờ không hợp lệ')

                if new_room_id is not None:
                    val_room = new_room_id if new_room_id else None

                # Cập nhật duration từ variant mới để validate đúng end time + overlap
                if variant_id:
                    try:
                        val_duration = ServiceVariant.objects.get(id=variant_id).duration_minutes
                    except Exception:
                        pass

                if needs_validation:
                    val_result = validate_appointment_create(
                        appointment_date=val_date,
                        appointment_time=val_time,
                        duration_minutes=val_duration,
                        room_code=val_room,
                        exclude_appointment_code=appt_code,
                        exclude_appointment_codes=all_req_identifiers,
                        is_staff_confirm=(not datetime_changed),
                    )
                    if not val_result['valid']:
                        raise ValueError(f'{label}{val_result["errors"][0]}')

                if new_date_str:
                    locked_appt.appointment_date = val_date
                if new_time_str:
                    locked_appt.appointment_time = val_time

                # ── BUG-13: apptStatus riêng từng khách ──────────────────────
                appt_status = (g.get('apptStatus') or '').strip().upper()
                if appt_status and appt_status in valid_appt_statuses:
                    # BUG-006: dùng service_variant đã gán trên instance (có thể vừa được set
                    # ở bước Variant phía trên), không dùng service_variant_id từ DB cũ.
                    effective_variant = locked_appt.service_variant
                    if appt_status == 'COMPLETED' and not effective_variant:
                        raise ValueError('Không thể hoàn thành khi chưa có dịch vụ')
                    # BUG-A12 FIX: Chặn cancel appointment khi booking đã có payment.
                    # Nếu cancel khi PAID/PARTIAL → tiền đã thu không được hoàn tự động,
                    # staff phải hoàn tiền trước qua invoice/refund.
                    if appt_status == 'CANCELLED' and locked_booking.payment_status in ('PAID', 'PARTIAL'):
                        raise ValueError(
                            f'Không thể hủy lịch khi booking đã có thanh toán '
                            f'(trạng thái: {locked_booking.payment_status}). '
                            'Vui lòng hoàn tiền trước.'
                        )
                    # NOTE: check COMPLETED + PAID được thực hiện SAU khi invoice rebuild
                    # (xem bên dưới) để dùng payment_status mới nhất, không dùng state cũ.
                    # Validate thời điểm chuyển trạng thái
                    # Trạng thái là shared cho toàn booking → không dùng label (không phải lỗi riêng 1 khách)
                    timing_ok, timing_err = _validate_status_timing(
                        val_date, val_time, val_duration, appt_status
                    )
                    if not timing_ok:
                        raise ValueError(timing_err)
                    locked_appt.status = appt_status

                locked_appt.save()
                updated_appts.append(locked_appt)

            # ── BUG-012: Recalculate invoice khi variant thay đổi ────────────
            # Chạy trong cùng transaction để đảm bảo atomic.
            # Chỉ recalculate khi booking đã có invoice — không tạo invoice mới ở đây.
            try:
                Invoice.objects.get(booking=locked_booking)  # kiểm tra tồn tại
                # _rebuild_invoice: giữ nguyên discount đã lưu trong DB (không truyền discount_type/value)
                # BUG-005 FIX: Truyền created_by để tránh ValueError nếu invoice bị xóa thủ công
                _rebuild_invoice(booking=locked_booking, created_by=request.user)
            except Invoice.DoesNotExist:
                # Booking chưa có invoice → không làm gì, invoice sẽ được tạo khi thanh toán
                pass

            # ── Post-rebuild: validate COMPLETED + PAID dùng payment_status mới nhất ──
            # Phải chạy sau invoice rebuild để payment_status phản ánh đúng trạng thái
            # (ví dụ: discount 100% → PAID ngay trong cùng batch)
            effective_pay_status = locked_booking.payment_status  # đã được cập nhật bởi _rebuild_invoice
            for appt in updated_appts:
                if appt.status == 'COMPLETED' and effective_pay_status not in ('PAID',):
                    raise ValueError(
                        f'Không thể hoàn thành lịch khi chưa thanh toán đủ '
                        f'(trạng thái thanh toán hiện tại: {effective_pay_status})'
                    )

        # Serialize kết quả sau transaction
        return JsonResponse({
            'success':      True,
            'message':      f'Đã cập nhật {len(updated_appts)} lịch hẹn',
            'appointments': [serialize_appointment(a) for a in updated_appts],
            'bookingCode':  booking_code,
        })

    except ValueError as ve:
        return JsonResponse({'success': False, 'error': str(ve)}, status=400)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': f'Lỗi: {str(e)}'}, status=500)


@require_http_methods(["POST"])
@staff_api
def api_appointment_status(request, appointment_code):
    """
    [TAB 1+2] POST /api/appointments/<code>/status/
    Doi trang thai lich hen.
    Appointment.status: NOT_ARRIVED, ARRIVED, COMPLETED, CANCELLED
    Booking.status: PENDING, CONFIRMED, CANCELLED, REJECTED
    """
    appointment, error = get_or_404(Appointment, appointment_code=appointment_code, deleted_at__isnull=True)
    if error:
        return error

    try:
        data = json.loads(request.body)
        new_status = str(data.get('status', '')).strip().upper()

        # Map status: frontend co the gui Booking status hoac Appointment status
        BOOKING_STATUSES = {'PENDING', 'CONFIRMED', 'CANCELLED', 'REJECTED'}
        APPT_STATUSES    = {'NOT_ARRIVED', 'ARRIVED', 'COMPLETED', 'CANCELLED'}

        booking = appointment.booking

        if new_status in BOOKING_STATUSES:
            # Doi Booking status

            # BUG-003: chỉ cho phép REJECT booking ONLINE đang PENDING
            # Tránh staff vô tình REJECT booking DIRECT qua endpoint này
            if new_status == 'REJECTED':
                if not booking or booking.source != 'ONLINE' or booking.status != 'PENDING':
                    return JsonResponse(
                        {'success': False, 'error': 'Chỉ có thể từ chối yêu cầu đặt lịch online đang chờ xác nhận'},
                        status=400,
                    )
                booking.appointments.filter(
                    deleted_at__isnull=True
                ).exclude(status='COMPLETED').update(status='CANCELLED')
                booking.status = 'REJECTED'
                booking.save(update_fields=['status', 'updated_at'])
                return JsonResponse({
                    'success': True,
                    'message': 'Đã từ chối yêu cầu đặt lịch',
                })

            if new_status == 'CONFIRMED':
                # Xac nhan: kiem tra trung lich cho tung appointment trong booking
                all_appts = list(booking.appointments.filter(deleted_at__isnull=True))
                for appt_to_check in all_appts:
                    duration  = _get_appt_duration(appt_to_check)
                    room_code = appt_to_check.room.code if appt_to_check.room_id else None
                    validation = validate_appointment_create(
                        appointment_date=appt_to_check.appointment_date,
                        appointment_time=appt_to_check.appointment_time,
                        duration_minutes=duration,
                        room_code=room_code,
                        exclude_appointment_code=appt_to_check.appointment_code,
                        is_staff_confirm=True,
                    )
                    if not validation['valid']:
                        return JsonResponse({
                            'success': False,
                            'error': f'Lịch {appt_to_check.appointment_code}: {validation["errors"][0]}',
                            'conflict': True,
                        }, status=409)

                # CAP-01 FIX: Cross-capacity check toan bo appointments trong booking.
                # validate_appointment_create o tren chi check tung appointment rieng le
                # voi DB — khong tinh cac appointments khac trong cung booking nay (vi
                # chung dang PENDING nen bi exclude khoi DB count).
                # Vi du: capacity=2, DB co 1 confirmed, booking nay co 2 guests cung phong/gio
                # -> moi guest check rieng thay DB=1 < 2 -> pass, nhung sau confirm tong = 3 > 2.
                _confirm_slot_list = []
                for appt_to_check in all_appts:
                    if not appt_to_check.room_id:
                        continue
                    dur       = _get_appt_duration(appt_to_check)
                    start_min = _time_to_minutes(appt_to_check.appointment_time)
                    end_min   = start_min + dur
                    _confirm_slot_list.append((
                        appt_to_check.appointment_code,
                        appt_to_check.room.code,
                        appt_to_check.appointment_date,
                        start_min,
                        end_min,
                    ))

                if _confirm_slot_list:
                    _cap_resp = _check_cross_capacity(
                        _confirm_slot_list,
                        status_code=409,
                        conflict_flag=True,
                        capacity1_msg_fn=lambda code, room, cap: (
                            f'Lich {code}: Khung gio da co lich o phong {room}, vui long chon thoi gian khac.'
                        ),
                        capacityN_msg_fn=lambda code, room, cap: (
                            f'Lich {code}: Phong {room} da du cho o khung gio nay '
                            f'(suc chua {cap}), vui long chon phong hoac thoi gian khac.'
                        ),
                    )
                    if _cap_resp:
                        return _cap_resp

                # Xac nhan OK: chuyen tat ca appointment chua hoan thanh sang NOT_ARRIVED
                booking.appointments.filter(
                    deleted_at__isnull=True
                ).exclude(status='COMPLETED').update(status='NOT_ARRIVED')

            if new_status == 'CANCELLED':
                booking.cancelled_at = timezone.now()
                # Huy tat ca appointment chua hoan thanh
                booking.appointments.filter(
                    deleted_at__isnull=True
                ).exclude(status='COMPLETED').update(status='CANCELLED')
                # BUG-010 FIX: Nếu booking đang UNPAID → giữ UNPAID (không có tiền để đối soát).
                # Nếu đang PARTIAL/PAID → giữ nguyên để đối soát, nhưng ghi nhận vào response
                # để FE biết cần hoàn tiền. Không tự động đổi sang REFUNDED vì chưa thực sự hoàn.
                # payment_status KHÔNG thay đổi ở đây — staff phải chủ động bấm Hoàn tiền.

            booking.status = new_status
            booking.save(update_fields=['status', 'cancelled_at', 'updated_at'] if new_status == 'CANCELLED' else ['status', 'updated_at'])

            # BUG-010 FIX: Trả về payment_status hiện tại để FE hiển thị cảnh báo nếu cần hoàn tiền
            response_data = {
                'success': True,
                'message': f'Đã cập nhật trạng thái đặt lịch: {booking.get_status_display()}',
            }
            if new_status == 'CANCELLED':
                response_data['paymentStatus'] = booking.payment_status
                if booking.payment_status in ('PAID', 'PARTIAL'):
                    response_data['needsRefund'] = True
                    response_data['warning'] = (
                        'Booking đã hủy nhưng còn tiền đã thu. '
                        'Vui lòng hoàn tiền nếu cần.'
                    )
            return JsonResponse(response_data)

        elif new_status in APPT_STATUSES:
            # Doi Appointment status
            if new_status == 'COMPLETED':
                if not appointment.service_variant_id:
                    return JsonResponse({'success': False, 'error': 'Không thể hoàn thành khi chưa có dịch vụ'}, status=400)
                booking_pay = booking.payment_status if booking else 'UNPAID'
                if booking_pay not in ('PAID',):
                    return JsonResponse({'success': False, 'error': 'Không thể hoàn thành lịch khi chưa thanh toán đủ'}, status=400)

            # Validate thời điểm chuyển trạng thái
            duration = _get_appt_duration(appointment)
            timing_ok, timing_err = _validate_status_timing(
                appointment.appointment_date, appointment.appointment_time, duration, new_status
            )
            if not timing_ok:
                return JsonResponse({'success': False, 'error': timing_err}, status=400)

            appointment.status = new_status
            appointment.save(update_fields=['status', 'updated_at'])

            return JsonResponse({
                'success': True,
                'message': f'Đã cập nhật trạng thái: {appointment.get_status_display()}'
            })

        else:
            return JsonResponse({'success': False, 'error': 'Trạng thái không hợp lệ'}, status=400)

    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Lỗi: {str(e)}'}, status=400)


@require_http_methods(["POST", "DELETE"])
@staff_api
def api_appointment_delete(request, appointment_code):
    """[TAB 1] POST /api/appointments/<code>/delete/ - Xoa mem lich hen."""
    try:
        appointment = Appointment.objects.get(appointment_code=appointment_code, deleted_at__isnull=True)
    except Appointment.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Không tìm thấy lịch hẹn'}, status=404)

    if not _is_staff(request.user):
        return _deny()

    if appointment.status == 'COMPLETED':
        return JsonResponse({'success': False, 'error': 'Không thể xóa lịch hẹn đã hoàn thành dịch vụ.'}, status=400)

    try:
        customer_name  = appointment.customer_name_snapshot or 'Khach hang'
        appointment_id = appointment.id
        booking_id     = appointment.booking_id

        with transaction.atomic():
            # BUG-04 & Race condition fix: Lock booking before checking payment status
            booking = None
            if booking_id:
                booking = Booking.objects.select_for_update().get(id=booking_id)
                booking_pay_status = booking.payment_status or ''
                if booking_pay_status in ('PAID', 'PARTIAL', 'REFUNDED'):
                    if booking_pay_status == 'PAID':
                        err_msg = 'Không thể xóa lịch đã thanh toán. Vui lòng hoàn tiền trước nếu cần hủy.'
                    elif booking_pay_status == 'PARTIAL':
                        err_msg = 'Không thể xóa lịch khi booking đang có thanh toán một phần. Vui lòng hoàn tiền trước nếu cần hủy.'
                    else:
                        err_msg = 'Không thể xóa lịch đã hoàn tiền. Vui lòng giữ lại để đối soát.'
                    return JsonResponse({'success': False, 'error': err_msg}, status=400)

            appointment.deleted_at      = timezone.now()
            appointment.deleted_by_user = request.user
            appointment.save(update_fields=['deleted_at', 'deleted_by_user', 'updated_at'])

            # BUG-003 FIX: Nếu booking không còn appointment nào → soft-delete booking luôn
            # để tránh booking rỗng tồn tại trong DB gây nhầm lẫn.
            booking_deleted = False
            if booking:
                remaining_count = Appointment.objects.filter(
                    booking=booking,
                    deleted_at__isnull=True,
                ).count()
                if remaining_count == 0:
                    booking.deleted_at      = timezone.now()
                    booking.deleted_by_user = request.user
                    booking.save(update_fields=['deleted_at', 'deleted_by_user', 'updated_at'])
                    booking_deleted = True
                else:
                    # BUG-A06 FIX: Booking còn appointment khác → rebuild invoice để
                    # subtotal/final/payment_status phản ánh đúng appointments còn lại.
                    try:
                        Invoice.objects.get(booking=booking)  # chỉ rebuild nếu invoice đã tồn tại
                        _rebuild_invoice(booking=booking)
                    except Invoice.DoesNotExist:
                        pass

        return JsonResponse({
            'success':        True,
            'message':        'Đã xóa lịch hẹn',
            'deleted_id':     appointment_id,
            'customer_name':  customer_name,
            'booking_deleted': booking_deleted,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Không thể xóa: {str(e)}'}, status=400)


# ============================================================
# SECTION 5: TAB 2 - YEU CAU DAT LICH (BOOKING REQUESTS)
# ============================================================


@require_http_methods(["GET"])
def api_booking_requests(request):
    """
    [TAB 2] GET /api/booking-requests/
    Danh sach yeu cau dat lich online (Booking.source=ONLINE, status PENDING).

    Query Parameters:
        - date:     Lọc theo ngày hẹn (YYYY-MM-DD)
        - q:        Tìm kiếm tự do (code, tên, SĐT)
        - service:  Lọc theo dịch vụ

    Returns:
        JSON với danh sách appointments (đã serialize)
    """
    # ── STEP 1: Kiểm tra quyền truy cập ────────────────────────────────────────
    # Chỉ staff mới được xem danh sách yêu cầu đặt lịch online
    if not _is_staff(request.user):
        return _deny()

    # ── STEP 2: Query cơ bản - Lấy appointments từ booking online PENDING ───────────
    # TẠI SAO query Appointment thay vì Booking?
    #   - Booking là "đơn đặt" (1 booking có N appointments)
    #   - Appointment là "lịch hẹn" từng khách riêng lẻ
    #   - Frontend hiển thị theo từng khách → query appointments trực tiếp
    #   - Tránh việc query 2 lần (bookings → appointments)
    # CHỈ hiển thị PENDING - không hiển thị CANCELLED/REJECTED
    qs = Appointment.objects.filter(
        booking__source='ONLINE',                      # Chỉ lấy booking đặt online
        booking__status='PENDING',                     # CHỈ hiển thị chờ xác nhận
        deleted_at__isnull=True,                       # Loại bỏ appointment đã xóa (soft delete)
    ).select_related(
        'booking',                    # JOIN với bảng bookings (tránh N+1 queries)
        'customer',                   # JOIN với bảng customers
        'service_variant__service',   # JOIN với services qua variants
        'room'                        # JOIN với bảng rooms
    )


    # ── STEP 3: Áp dụng filters từ query parameters ─────────────────────────────
    # Mỗi filter là OPTIONAL - chỉ áp dụng khi có giá trị

    # Filter 1: Theo ngày hẹn
    # Ví dụ: GET /api/booking-requests/?date=2024-01-15
    if date_filter := request.GET.get('date'):
        qs = qs.filter(appointment_date=date_filter)

    # Filter 2: Tìm kiếm tự do (full-text search trên nhiều fields)
    # Ví dụ: GET /api/booking-requests/?q=0123456789
    #       → Tìm trong: booking_code, booker_name, booker_phone, appointment_code, customer_name
    # 💡 TIP: search_norm = loại bỏ tất cả ký tự không phải số (để search SĐT)
    if search := request.GET.get('q', '').strip():
        search_norm = ''.join(filter(str.isdigit, search))
        qs = qs.filter(
            Q(booking__booking_code__icontains=search) |           # Mã booking: BK0001
            Q(booking__booker_name__icontains=search) |            # Tên người đặt
            Q(booking__booker_phone__icontains=search_norm) |       # SĐT người đặt (chỉ số)
            Q(appointment_code__icontains=search) |                # Mã lịch hẹn: APP0001
            Q(customer_name_snapshot__icontains=search)             # Tên khách hàng
        )
    # 💡 TIP: Q() objects cho phép OR queries (|)
    #         icontains = case-insensitive contains (không phân biệt hoa thường)

    # Filter 3: Theo dịch vụ
    # Ví dụ: GET /api/booking-requests/?service=1
    #       → Chỉ hiển thị booking của dịch vụ có id=1
    if service_id := request.GET.get('service', '').strip():
        qs = qs.filter(service_variant__service_id=service_id)

    # ── STEP 4: Sắp xếp kết quả (Ordering) ───────────────────────────────────────
    # Sắp xếp: mới nhất trước (theo created_at), sau đó theo ngày giờ hẹn
    qs = qs.order_by(
        '-booking__created_at',     # Mới nhất trước (dấu - = DESC)
        'appointment_date',          # Ngày hẹn tăng dần
        'appointment_time',          # Giờ hẹn tăng dần
    )

    # ── STEP 5: Serialize & Return ───────────────────────────────────────────────
    # 💡 TIP: qs được EVALUATE ở đây (query thực sự chạy DB)
    #         Django ORM là lazy - chỉ query khi cần dữ liệu
    return JsonResponse({
        'success': True,
        'appointments': [serialize_appointment(a) for a in qs]
    })


@require_http_methods(["POST"])
@staff_api
def api_confirm_online_request(request, booking_code):
    """
    [TAB 2] POST /api/booking-requests/<booking_code>/confirm/
    Xac nhan yeu cau dat lich online: cap nhat phong/gio/dich vu vao appointment goc
    roi confirm booking. KHONG tao Booking moi.
    
    API endpoint nhận POST request để xác nhận yêu cầu đặt lịch online
    Cập nhật phòng/giờ/dịch vụ vào appointment gốc, sau đó confirm booking 
    KHÔNG tạo booking mới (update booking đã có từ request online)

    Payload:
    {
      "guests": [{
        "name": "...", "phone": "...", "email": "...",
        "serviceId": ..., "variantId": ...,
        "roomId": "...", "date": "YYYY-MM-DD", "time": "HH:MM"
      }]
    }
    """
    try:
        booking = Booking.objects.get(
            booking_code=booking_code,
            source='ONLINE',
            status='PENDING',
            deleted_at__isnull=True,
        )
    except Booking.DoesNotExist:
        return JsonResponse(
            {'success': False, 'error': 'Không tìm thấy yêu cầu đặt lịch hoặc đã được xử lý'},
            status=404,
        )

    try:
        raw = json.loads(request.body)
        guests = raw.get('guests', [])
        if not guests:
            return JsonResponse({'success': False, 'error': 'Vui lòng thêm ít nhất 1 khách'}, status=400)

        # Lay danh sach appointment hien tai cua booking goc (chua bi xoa)
        existing_appts = list(
            booking.appointments.filter(deleted_at__isnull=True).order_by('id')
        )

        # Validate tung guest — is_staff_confirm=True để cho phép ngày quá khứ
        validated = []
        for idx, g in enumerate(guests):
            label = f'Khách {idx + 1}: ' if len(guests) > 1 else ''
            data = {
                'customer_name': g.get('name', '').strip(),
                'phone':         ''.join(filter(str.isdigit, g.get('phone', ''))),
                'email':         g.get('email', '').strip(),
                'service_id':    g.get('serviceId'),
                'variant_id':    g.get('variantId'),
                'room_id':       g.get('roomId'),
                'date_str':      g.get('date', ''),
                'time_str':      g.get('time', ''),
                'status':        'NOT_ARRIVED',
                'is_staff_confirm': True,
            }
            result = _validate_appointment_data(data)
            if not result['valid']:
                return JsonResponse(
                    {'success': False, 'error': f'{label}{result["errors"][0]}',
                     'conflict': any('trùng' in e or 'đủ chỗ' in e or 'khả dụng' in e for e in result['errors'])},
                    status=409 if any('trùng' in e or 'đủ chỗ' in e for e in result['errors']) else 400,
                )
            validated.append((idx, g, result['cleaned_data']))

        # BUG-004 FIX: Cross-guest capacity check — giống create-batch
        # validate_appointment_data chỉ check từng guest riêng lẻ với DB.
        # Khi confirm với nhiều guests mới cùng phòng cùng giờ, cần check tổng hợp.
        if len(validated) > 1:
            _slot_list_confirm = []
            for idx, g, cleaned in validated:
                room_obj  = cleaned.get('room')
                appt_date = cleaned.get('appointment_date')
                appt_time = cleaned.get('appointment_time')
                dur       = cleaned.get('duration_minutes', 60)
                if not room_obj or not appt_date or not appt_time:
                    continue
                start_min = _time_to_minutes(appt_time)
                end_min   = start_min + dur
                orig_code = existing_appts[idx].appointment_code if idx < len(existing_appts) else None
                _slot_list_confirm.append((orig_code, room_obj.code, appt_date, start_min, end_min))

            _cap_resp = _check_cross_capacity(
                _slot_list_confirm,
                status_code=409,
                conflict_flag=True,
            )
            if _cap_resp:
                return _cap_resp

        with transaction.atomic():
            updated_appts = []

            for idx, g, cleaned in validated:
                if idx < len(existing_appts):
                    # Cap nhat appointment da co
                    appt = existing_appts[idx]
                    appt.service_variant        = cleaned.get('service_variant')
                    appt.room                   = cleaned['room']
                    appt.appointment_date       = cleaned['appointment_date']
                    appt.appointment_time       = cleaned['appointment_time']
                    appt.customer_name_snapshot = cleaned['customer_name']
                    appt.customer_phone_snapshot = cleaned.get('phone') or appt.customer_phone_snapshot
                    appt.customer_email_snapshot = (g.get('email', '').strip() or None) or appt.customer_email_snapshot
                    appt.status                 = 'NOT_ARRIVED'

                    # Resolve customer profile
                    try:
                        resolved = _resolve_customer_from_guest(g, cleaned)
                    except Exception:
                        resolved = None
                    appt.customer = resolved or appt.customer

                    appt.save(update_fields=[
                        'service_variant', 'room', 'appointment_date', 'appointment_time',
                        'customer_name_snapshot', 'customer_phone_snapshot', 'customer_email_snapshot',
                        'status', 'customer', 'updated_at',
                    ])
                    updated_appts.append(appt)
                else:
                    # Tao them appointment moi neu guest nhieu hon appointment goc
                    try:
                        customer = _resolve_customer_from_guest(g, cleaned)
                    except Exception:
                        customer = None

                    appt = Appointment.objects.create(
                        booking=booking,
                        customer=customer,
                        service_variant=cleaned.get('service_variant'),
                        room=cleaned['room'],
                        customer_name_snapshot=cleaned['customer_name'],
                        customer_phone_snapshot=cleaned.get('phone'),
                        customer_email_snapshot=g.get('email', '').strip() or None,
                        appointment_date=cleaned['appointment_date'],
                        appointment_time=cleaned['appointment_time'],
                        status='NOT_ARRIVED',
                    )
                    updated_appts.append(appt)

            # Soft-delete cac appointment goc thua (neu guest it hon appointment goc)
            for extra_appt in existing_appts[len(validated):]:
                extra_appt.deleted_at = timezone.now()
                extra_appt.deleted_by_user = request.user
                extra_appt.save(update_fields=['deleted_at', 'deleted_by_user'])

            # Tao/cap nhat Invoice cho booking
            try:
                existing_invoice = booking.invoice
                # Invoice đã tồn tại → rebuild items + tính lại discount/final/payment_status
                # Giữ nguyên discount đã lưu trong DB (không truyền discount_type/value)
                _rebuild_invoice(booking=booking, appointments=updated_appts)
            except Invoice.DoesNotExist:
                # Invoice chưa có → tạo mới với UNPAID
                _create_invoice_and_payment(booking, updated_appts, 'UNPAID', {}, request.user)

            # Confirm booking
            booking.status = 'CONFIRMED'
            booking.save(update_fields=['status', 'updated_at'])

        return JsonResponse({
            'success': True,
            'message': 'Xác nhận yêu cầu đặt lịch thành công',
            'appointments': [serialize_appointment(a) for a in updated_appts],
            'bookingCode': booking.booking_code,
        })

    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e) or 'Không thể xác nhận yêu cầu'}, status=400)


@require_http_methods(["GET"])
def api_booking_pending_count(request):
    """[TAB 2] GET /api/booking/pending-count/ - So luong booking dang cho xac nhan."""
    if not _is_staff(request.user):
        return _deny()
    try:
        count = Booking.objects.filter(
            source='ONLINE',
            status='PENDING',
            deleted_at__isnull=True,
        ).count()
        return JsonResponse({'success': True, 'count': count, 'timestamp': timezone.now().isoformat()})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Không thể lấy số lượng: {str(e)}', 'count': 0}, status=500)


@require_http_methods(["GET"])
def api_customer_cancelled_recent(request):
    """
    [TAB 2] GET /api/appointments/customer-cancelled-recent/
    Danh sach cac lich bi khach huy gan day (Booking.status=CANCELLED, source=ONLINE).
    """
    if not _is_staff(request.user):
        return _deny()

    from datetime import timedelta
    minutes = int(request.GET.get('minutes', 10))
    since   = timezone.now() - timedelta(minutes=minutes)

    bookings = Booking.objects.filter(
        source='ONLINE',
        status='CANCELLED',
        cancelled_at__gte=since,
        deleted_at__isnull=True,
    ).order_by('-cancelled_at')[:20]

    return JsonResponse({
        'success': True,
        'appointments': [
            {
                'code':         b.booking_code,
                'customerName': b.booker_name or 'Khach',
                'cancelledAt':  b.cancelled_at.isoformat() if b.cancelled_at else '',
            }
            for b in bookings
        ]
    })


# ============================================================
# SECTION 6: CUSTOMER NOTE UPDATE
# ============================================================

@require_http_methods(["POST"])
@staff_api
def api_customer_note_update(request, phone):
    """
    [SHARED] POST /api/customers/<phone>/note/
    Cập nhật ghi chú hồ sơ khách theo SĐT.

    TODO: endpoint này không còn được FE sử dụng (FE đã chuyển sang
          POST /api/customers/id/<id>/note/). Cân nhắc xóa sau khi kiểm tra logs.

    Body JSON:
        { "note": "..." }

    Chỉ update field notes trên CustomerProfile.
    Không ảnh hưởng đến booking hay appointment.
    """
    phone_digits = ''.join(filter(str.isdigit, phone or ''))
    if not phone_digits or not _is_valid_vn_phone(phone_digits):
        return JsonResponse({'success': False, 'error': 'Số điện thoại không hợp lệ (phải có 10 số và bắt đầu bằng 0)'}, status=400)

    try:
        raw = json.loads(request.body)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Dữ liệu không hợp lệ'}, status=400)

    note = (raw.get('note') or '').strip()

    try:
        customer = CustomerProfile.objects.get(phone=phone_digits)
    except CustomerProfile.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Không tìm thấy hồ sơ khách'}, status=404)

    customer.notes = note or None
    customer.save(update_fields=['notes', 'updated_at'])

    return JsonResponse({'success': True, 'message': 'Đã cập nhật ghi chú hồ sơ khách'})


@require_http_methods(["POST"])
@staff_api
def api_customer_note_update_by_id(request, customer_id):
    """
    [SHARED] POST /api/customers/id/<customer_id>/note/
    Cập nhật ghi chú hồ sơ khách theo ID (an toàn hơn theo phone).

    Body JSON:
        { "note": "..." }

    Chỉ update field notes trên CustomerProfile.
    Không ảnh hưởng đến booking hay appointment.
    """
    try:
        cid = int(customer_id)
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'ID không hợp lệ'}, status=400)

    try:
        raw = json.loads(request.body)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Dữ liệu không hợp lệ'}, status=400)

    note = (raw.get('note') or '').strip()

    try:
        customer = CustomerProfile.objects.get(id=cid)
    except CustomerProfile.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Không tìm thấy hồ sơ khách'}, status=404)

    customer.notes = note or None
    customer.save(update_fields=['notes', 'updated_at'])

    return JsonResponse({'success': True, 'message': 'Đã cập nhật ghi chú hồ sơ khách'})
