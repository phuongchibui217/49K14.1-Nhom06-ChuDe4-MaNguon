"""
Services cho Appointment Validation

Tách logic nghiệp vụ ra khỏi views/api để dùng lại và dễ test.
"""

from datetime import datetime, timedelta, date, time as time_type
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Q
from .models import Appointment, Booking, Room


# =====================================================
# CONSTANTS
# =====================================================

SPA_CLOSE_TIME = time_type(21, 0)       # 21:00
SPA_OPEN_TIME  = time_type(9, 0)        # 09:00
DEFAULT_APPOINTMENT_DURATION_MINUTES = 60


# =====================================================
# APPOINTMENT VALIDATION SERVICES
# =====================================================

def validate_appointment_date(appointment_date, is_staff_confirm=False):
    """
    Kiểm tra ngày hẹn hợp lệ.
    Staff xác nhận booking cũ được phép dùng ngày quá khứ.
    """
    if is_staff_confirm:
        return

    today = timezone.localtime(timezone.now()).date()
    if appointment_date < today:
        raise ValidationError('Ngày hẹn không được nhỏ hơn ngày hôm nay.')


def validate_appointment_time(appointment_time, appointment_date, duration_minutes=None, is_staff_confirm=False):
    """
    Kiểm tra giờ hẹn hợp lệ.
    - Phải trong 09:00 – 21:00.
    - Giờ kết thúc (start + duration) không được vượt quá 21:00.
    - Nếu là ngày hôm nay, giờ phải >= giờ hiện tại.
    - is_staff_confirm=True: bỏ qua check giờ đã qua (dùng khi staff edit lịch cũ không đổi giờ).
    """
    if duration_minutes is None:
        duration_minutes = DEFAULT_APPOINTMENT_DURATION_MINUTES

    if appointment_time < SPA_OPEN_TIME:
        raise ValidationError('Giờ làm việc từ 09:00 đến 21:00.')

    if appointment_time >= SPA_CLOSE_TIME:
        raise ValidationError('Giờ hẹn phải trước 21:00.')

    # Kiểm tra giờ kết thúc không vượt 21:00
    end_time = _calc_end_time(appointment_time, duration_minutes)
    if end_time > SPA_CLOSE_TIME:
        latest_start = _calc_end_time(SPA_CLOSE_TIME, -duration_minutes)
        raise ValidationError(
            f'Gói {duration_minutes} phút sẽ kết thúc sau 21:00. '
            f'Giờ trễ nhất có thể đặt: {latest_start.strftime("%H:%M")}.'
        )

    # Chặn giờ đã qua trong ngày hôm nay — bỏ qua khi staff confirm lịch cũ
    if not is_staff_confirm:
        now = timezone.localtime(timezone.now())
        if appointment_date == now.date() and appointment_time <= now.time():
            raise ValidationError(f'Giờ hẹn phải sau giờ hiện tại ({now.strftime("%H:%M")}).')


def check_room_availability(
    room_code,
    appointment_date,
    start_time,
    duration_minutes,
    exclude_appointment_code=None,
    exclude_appointment_codes=None,
):
    """
    Kiểm tra phòng có trống trong khung giờ đã chọn không.

    Mỗi appointment = 1 khách = 1 slot.
    Phòng có capacity N → cho phép N lịch trùng giờ.

    Returns:
        (is_available: bool, conflict: Appointment|None, message: str)
        message phân biệt rõ 2 trường hợp:
        - 'CONFLICT': khung giờ đã có lịch (capacity = 1, bị trùng)
        - 'CAPACITY': phòng đã đủ chỗ (capacity > 1, vượt giới hạn)
    """
    # ── Step 1: Guard clause - nếu không có room_code → coi như available
    # Lý do: Một số flow (tạo pending, xác nhận request) chưa chọn phòng ngay
    if not room_code:
        return (True, None, '')

    # ── Step 2: Lấy room object từ DB
    try:
        room = Room.objects.get(code=room_code, is_active=True)
    except Room.DoesNotExist:
        return (False, None, f'Phòng {room_code} không tồn tại.')

    # ── Step 3: Tính giờ kết thúc của appointment đang check
    end_time = _calc_end_time(start_time, duration_minutes)

    # ── Step 4: Query appointments CẦN CHECK TRỪNG LỊCH
    # Chỉ lấy appointments:
    #   - Cùng phòng
    #   - Cùng ngày
    #   - Chưa bị xóa (deleted_at is null)
    #   - KHÔNG phải CANCELLED
    #   - KHÔNG phải booking CANCELLED/REJECTED/PENDING
    # Lý do exclude PENDING: Booking mới tạo (PENDING) chưa được confirm → chưa chiếm slot
    queryset = Appointment.objects.filter(
        room=room,                           # Cùng phòng
        appointment_date=appointment_date,   # Cùng ngày
        deleted_at__isnull=True,             # Chưa bị xóa
    ).exclude(
        status='CANCELLED'                   # Bỏ qua appointments đã hủy
    ).exclude(
        booking__status__in=['CANCELLED', 'REJECTED', 'PENDING']  # Bỏ qua booking không hiệu lực
    )

    # ── Step 5: Exclude appointment đang được update (tránh check với chính nó)
    # VD: Update appointment A, đổi thời gian → không conflict với A cũ
    if exclude_appointment_codes:
        queryset = queryset.exclude(appointment_code__in=exclude_appointment_codes)
    elif exclude_appointment_code:
        queryset = queryset.exclude(appointment_code=exclude_appointment_code)

    # ── Step 6: Đếm số lượng appointments trùng khung giờ
    overlapping_count = 0
    first_conflict = None

    for existing in queryset:
        # Tính giờ kết thúc của appointment existing
        dur = _get_appt_duration(existing)
        existing_end = _calc_end_time(existing.appointment_time, dur)

        # Check overlap: 2 khung giờ giao nhau?
        # Formula: (start1 < end2) AND (end1 > start2)
        if start_time < existing_end and end_time > existing.appointment_time:
            overlapping_count += 1
            if first_conflict is None:
                first_conflict = existing  # Lưu appointment đầu tiên bị conflict (để báo lỗi chi tiết)

    # ── Step 7: Kiểm tra có vượt quá capacity không?
    if overlapping_count >= room.capacity:
        # Phân biệt rõ 2 trường hợp để error message thân thiện
        if room.capacity == 1:
            # Phòng 1 người: trùng giờ = CONFLICT
            return (False, first_conflict, 'CONFLICT')
        # Phòng nhiều người: đã đủ chỗ = CAPACITY
        return (False, first_conflict, 'CAPACITY')

    # ── Step 8: Pass mọi check → phòng available
    return (True, None, '')


def validate_appointment_create(
    appointment_date,
    appointment_time,
    duration_minutes,
    room_code=None,
    exclude_appointment_code=None,
    exclude_appointment_codes=None,
    is_staff_confirm=False,
):
    """
    Validate toàn bộ trước khi tạo/sửa lịch hẹn.

    Returns:
        {'valid': bool, 'errors': list}
    """
    errors = []

    try:
        validate_appointment_date(appointment_date, is_staff_confirm=is_staff_confirm)
    except ValidationError as e:
        errors.append(str(e.message))

    try:
        validate_appointment_time(appointment_time, appointment_date, duration_minutes, is_staff_confirm=is_staff_confirm)
    except ValidationError as e:
        errors.append(str(e.message))

    if room_code:
        is_available, _, message = check_room_availability(
            room_code=room_code,
            appointment_date=appointment_date,
            start_time=appointment_time,
            duration_minutes=duration_minutes,
            exclude_appointment_code=exclude_appointment_code,
            exclude_appointment_codes=exclude_appointment_codes,
        )
        if not is_available:
            if message == 'CONFLICT':
                errors.append('Khung giờ đã có lịch, vui lòng chọn thời gian khác')
            elif message == 'CAPACITY':
                errors.append('Phòng đã đủ chỗ ở khung giờ này, vui lòng chọn phòng hoặc thời gian khác')
            else:
                errors.append(message)

    return {'valid': len(errors) == 0, 'errors': errors}


# =====================================================
# HELPER FUNCTIONS
# =====================================================

def _calc_end_time(start_time, duration_minutes):
    """Tính giờ kết thúc từ giờ bắt đầu và thời lượng (có thể âm để tính ngược)."""
    base = date.today()
    start_dt = datetime.combine(base, start_time)
    return (start_dt + timedelta(minutes=duration_minutes)).time()


def _get_appt_duration(appointment):
    """
    Lấy thời lượng của 1 appointment.
    Ưu tiên service_variant.duration_minutes, fallback 60 phút.
    """
    try:
        if appointment.service_variant_id and appointment.service_variant:
            return appointment.service_variant.duration_minutes
    except Exception:
        pass
    return 60


