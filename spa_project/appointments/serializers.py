"""
Serializers — chuyển Booking/Appointment model thành dict/JSON cho frontend.

Author: Spa ANA Team
"""

from .models import Appointment, Booking
from .services import _get_appt_duration, _calc_end_time


def _resolve_customer_note(appointment):
    """
    Trả về ghi chú hồ sơ của đúng khách sử dụng dịch vụ trong dòng này.

    Quy tắc:
    - Chỉ lấy customer.notes khi customer.phone khớp với customer_phone_snapshot
      (tức là profile được gán đúng là khách sử dụng dịch vụ, không phải người đặt).
    - Nếu không có customer_phone_snapshot → trả về '' để tránh lấy nhầm ghi chú người đặt.
    - Nếu customer_phone_snapshot có nhưng không khớp customer.phone
      → thử lookup profile theo snapshot phone, lấy notes từ đó.
    """
    if not appointment.customer_id:
        return ''

    guest_phone = (appointment.customer_phone_snapshot or '').strip()
    if not guest_phone:
        return ''

    try:
        customer = appointment.customer
        if customer.phone == guest_phone:
            return customer.notes or ''
        else:
            from customers.models import CustomerProfile
            try:
                guest_profile = CustomerProfile.objects.get(phone=guest_phone)
                return guest_profile.notes or ''
            except CustomerProfile.DoesNotExist:
                return ''
    except Exception:
        return ''


def serialize_booking(booking):
    """Chuyển 1 Booking thành dict."""
    return {
        'bookingCode':    booking.booking_code,
        'bookerName':     booking.booker_name or '',
        'bookerPhone':    booking.booker_phone or '',
        'bookerEmail':    booking.booker_email or '',
        'bookerNotes':    booking.booker_notes or '',
        'status':         booking.status,
        'paymentStatus':  booking.payment_status,
        'source':         booking.source,
        'createdAt':      booking.created_at.isoformat() if booking.created_at else '',
        'createdBy': {
            'id':       booking.created_by.id,
            'username': booking.created_by.username,
            'fullName': f"{booking.created_by.first_name} {booking.created_by.last_name}".strip(),
        } if booking.created_by_id else None,
    }


def serialize_appointment(appointment):
    """
    Chuyển 1 Appointment thành dict.
    Bao gồm thông tin Booking cha (booker info, payment, source).
    """
    booking = appointment.booking

    # Người đặt lịch — lấy từ Booking
    booker_name  = booking.booker_name  if booking else ''
    booker_phone = booking.booker_phone if booking else ''
    booker_email = booking.booker_email if booking else ''

    # Khách sử dụng dịch vụ (snapshot)
    customer_name  = appointment.customer_name_snapshot  or ''
    customer_phone = appointment.customer_phone_snapshot or ''
    customer_email = appointment.customer_email_snapshot or ''

    # Thời lượng và end_time tính từ service_variant
    duration_min = _get_appt_duration(appointment)
    end_str = ''
    if appointment.appointment_time:
        end_time = _calc_end_time(appointment.appointment_time, duration_min)
        end_str = end_time.strftime('%H:%M')

    # Service info từ variant
    service_name  = ''
    service_id    = None
    service_code  = ''
    variant_label = ''
    if appointment.service_variant_id:
        try:
            sv = appointment.service_variant
            if sv.service_id:
                service_name = sv.service.name
                service_id   = sv.service_id
                service_code = sv.service.code or ''
            variant_label = sv.label or ''
        except Exception:
            pass

    return {
        'id':          appointment.appointment_code,
        'bookingCode': booking.booking_code if booking else '',
        'customerId':  appointment.customer_id,
        # Người đặt lịch (từ Booking)
        'bookerName':  booker_name,
        'bookerPhone': booker_phone,
        'bookerEmail': booker_email,
        'bookerNotes': booking.booker_notes if booking else '',
        # Khách sử dụng dịch vụ (snapshot)
        'customerName':  customer_name,
        'phone':         customer_phone,
        'email':         customer_email,
        # Dịch vụ / gói
        'service':      service_name,
        'serviceCode':  service_code,
        'serviceId':    service_id,
        'variantId':    appointment.service_variant_id,
        'variantLabel': variant_label,
        # Phòng
        'roomCode': appointment.room.code if appointment.room_id else '',
        'roomName': appointment.room.name if appointment.room_id else '',
        # Thời gian
        'date':        appointment.appointment_date.strftime('%Y-%m-%d') if appointment.appointment_date else '',
        'start':       appointment.appointment_time.strftime('%H:%M') if appointment.appointment_time else '',
        'end':         end_str,
        'durationMin': duration_min,
        # Trạng thái appointment
        'apptStatus':  appointment.status,
        # Trạng thái booking (payment, source)
        'payStatus':   booking.payment_status if booking else 'UNPAID',
        'source':      booking.source if booking else 'DIRECT',
        # Booking status riêng để frontend phân biệt PENDING/CONFIRMED/CANCELLED/REJECTED
        'bookingStatus': booking.status if booking else '',
        # Ghi chú khách: chỉ lấy từ profile nếu profile đó đúng là khách sử dụng dịch vụ
        'customerNote': _resolve_customer_note(appointment),
    }
