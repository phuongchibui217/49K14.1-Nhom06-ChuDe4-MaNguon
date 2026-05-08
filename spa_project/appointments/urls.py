"""
URL configuration cho appointments app

Phan tich ro rang:
- views.py  -> Trang web (HTML)   -> import views
- api.py    -> API endpoints (JSON) -> import api

Author: Spa ANA Team
"""

from django.urls import path

from . import api, views

app_name = 'appointments'

urlpatterns = [
    # ========== HTML PAGES ==========
    path('booking/', views.booking, name='booking'),
    path('lich-hen-cua-toi/', views.my_appointments, name='my_appointments'),
    path('lich-hen/cancel/<int:appointment_id>/', views.cancel_appointment, name='cancel_appointment'),
    path('manage/appointments/', views.admin_appointments, name='admin_appointments'),

    # ========== API: TAB "Lá»‹ch Theo PhÃ²ng" (Appointments) ==========
    # Láº¥y danh sÃ¡ch phÃ²ng
    path('api/rooms/', api.api_rooms_list, name='api_rooms_list'),

    # Appointment CRUD Operations
    path('api/appointments/', api.api_appointments_list, name='api_appointments_list'),  # Danh sÃ¡ch vá»›i filters
    path('api/appointments/search/', api.api_appointments_search, name='api_appointments_search'),  # TÃ¬m kiáº¿m / share
    path('api/appointments/create-batch/', api.api_appointment_create_batch, name='api_appointment_create_batch'),  # Táº¡o nhiá»u / share
    path('api/appointments/customer-cancelled-recent/', api.api_customer_cancelled_recent, name='api_customer_cancelled_recent'),  # KhÃ¡ch há»§y gáº§n Ä‘Ã¢y
    path('api/appointments/<str:appointment_code>/', api.api_appointment_detail, name='api_appointment_detail'),  # Chi tiáº¿t
    # path('api/appointments/<str:appointment_code>/update/', api.api_appointment_update, name='api_appointment_update'),  # [REMOVED] tráº£ 410 â€” dÃ¹ng update-batch
    path('api/appointments/<str:appointment_code>/status/', api.api_appointment_status, name='api_appointment_status'),  # Äá»•i tráº¡ng thÃ¡i
    path('api/appointments/<str:appointment_code>/delete/', api.api_appointment_delete, name='api_appointment_delete'),  # XÃ³a

    # ========== API: TAB "YÃªu Cáº§u Äáº·t Lá»‹ch" (Booking Requests) ==========
    path('api/booking-requests/', api.api_booking_requests, name='api_booking_requests'),  # Danh sÃ¡ch requests
    path('api/booking-requests/<str:booking_code>/confirm/', api.api_confirm_online_request, name='api_confirm_online_request'),  # XÃ¡c nháº­n/Reject
    path('api/booking/pending-count/', api.api_booking_pending_count, name='api_booking_pending_count'),  # Äáº¿m sá»‘ pending

    # ========== API: Booking Management ==========
    path('api/bookings/<str:booking_code>/', api.api_booking_detail, name='api_booking_detail'),  # Chi tiáº¿t booking
    path('api/bookings/<str:booking_code>/delete/', api.api_booking_delete, name='api_booking_delete'),  # Xóa toàn bộ booking
    path('api/bookings/<str:booking_code>/update-batch/', api.api_booking_update_batch, name='api_booking_update_batch'),  # Cáº­p nháº­t batch
    path('api/bookings/<str:booking_code>/invoice/', api.api_booking_invoice, name='api_booking_invoice'),  # HÃ³a Ä‘Æ¡n
    path('api/bookings/<str:booking_code>/invoice/pay/', api.api_booking_invoice_pay, name='api_booking_invoice_pay'),  # Thanh toÃ¡n
    path('api/bookings/<str:booking_code>/invoice/refund/', api.api_booking_invoice_refund, name='api_booking_invoice_refund'),  # HoÃ n tiá»n

    # ========== API: Customers ==========
    path('api/customers/search/', api.api_customer_search, name='api_customer_search'),  # TÃ¬m khÃ¡ch hÃ ng
    path('api/customers/<str:phone>/note/', api.api_customer_note_update, name='api_customer_note_update'),  # Cáº­p nháº­t note
    path('api/customers/id/<int:customer_id>/note/', api.api_customer_note_update_by_id, name='api_customer_note_update_by_id'),  # Note theo ID
]

