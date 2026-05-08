"""
Tests cho Appointments app — covers models, APIs, views.
Cấu trúc mới: Booking + Appointment
"""
import json
from datetime import date, time

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils.crypto import get_random_string

from customers.models import CustomerProfile
from spa_services.models import Service, ServiceCategory, ServiceVariant
from .models import Appointment, Booking, Room


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def make_staff(username="staff1"):
    return User.objects.create_user(username=username, password="pass1234", is_staff=True)


def make_customer_user(username="cust1", phone="0911111111"):
    user = User.objects.create_user(username=username, password="pass1234")
    profile = CustomerProfile.objects.create(user=user, phone=phone, full_name="Khach Hang")
    return user, profile


def make_room(code="P01", capacity=2):
    return Room.objects.create(code=code, name=f"Phong {code}", capacity=capacity)


def make_category():
    cat, _ = ServiceCategory.objects.get_or_create(code="MS", defaults={"name": "Massage", "status": "ACTIVE"})
    return cat


def make_service(category, created_by):
    svc = Service.objects.create(
        category=category, name="Massage Body", status="ACTIVE",
        image="", created_by=created_by,
    )
    ServiceVariant.objects.create(service=svc, label="60 phut", duration_minutes=60, price=200000)
    return svc


def make_booking(booker_name="Khach Hang", booker_phone="0911111111",
                 source="DIRECT", status="CONFIRMED", created_by=None,
                 payment_status="UNPAID"):
    """Tạo Booking mới."""
    return Booking.objects.create(
        booker_name=booker_name,
        booker_phone=booker_phone,
        status=status,
        payment_status=payment_status,
        source=source,
        created_by=created_by,
    )


def make_appointment(customer, service, room, booking, appt_date=None,
                     appt_time=None, status="NOT_ARRIVED"):
    """Tạo Appointment thuộc 1 Booking."""
    appt_date = appt_date or date.today()
    appt_time = appt_time or time(10, 0)
    variant = service.variants.first()
    return Appointment.objects.create(
        booking=booking,
        customer=customer,
        service_variant=variant,
        room=room,
        customer_name_snapshot=customer.full_name,
        customer_phone_snapshot=customer.phone,
        appointment_date=appt_date,
        appointment_time=appt_time,
        status=status,
    )


# ─────────────────────────────────────────────
# MODEL TESTS
# ─────────────────────────────────────────────

class BookingModelTests(TestCase):
    def setUp(self):
        self.staff = make_staff()

    def test_booking_code_auto_generated(self):
        bk = make_booking(created_by=self.staff)
        self.assertTrue(bk.booking_code.startswith("BK"))

    def test_booking_code_unique(self):
        bk1 = make_booking(created_by=self.staff)
        bk2 = make_booking(created_by=self.staff)
        self.assertNotEqual(bk1.booking_code, bk2.booking_code)

    def test_booking_status_choices(self):
        for status in ["PENDING", "CONFIRMED", "CANCELLED", "REJECTED"]:
            bk = make_booking(status=status, created_by=self.staff)
            self.assertEqual(bk.status, status)


class AppointmentModelTests(TestCase):
    def setUp(self):
        self.staff = make_staff()
        self.cat = make_category()
        self.svc = make_service(self.cat, self.staff)
        self.room = make_room()
        _, self.profile = make_customer_user()
        self.booking = make_booking(
            booker_name=self.profile.full_name,
            booker_phone=self.profile.phone,
            created_by=self.staff,
        )

    def test_appointment_code_auto_generated(self):
        appt = make_appointment(self.profile, self.svc, self.room, self.booking)
        self.assertTrue(appt.appointment_code.startswith("APP"))

    def test_snapshot_fields_filled(self):
        appt = make_appointment(self.profile, self.svc, self.room, self.booking)
        self.assertEqual(appt.customer_name_snapshot, self.profile.full_name)
        self.assertEqual(appt.customer_phone_snapshot, self.profile.phone)

    def test_appointment_linked_to_booking(self):
        appt = make_appointment(self.profile, self.svc, self.room, self.booking)
        self.assertEqual(appt.booking.booking_code, self.booking.booking_code)

    def test_status_choices_valid(self):
        for status in ["NOT_ARRIVED", "ARRIVED", "COMPLETED", "CANCELLED"]:
            appt = make_appointment(self.profile, self.svc, self.room, self.booking, status=status)
            self.assertEqual(appt.status, status)

    def test_invalid_status_raises(self):
        with self.assertRaises(Exception):
            make_appointment(self.profile, self.svc, self.room, self.booking, status="INVALID")

    def test_room_str(self):
        self.assertIn("P01", str(self.room))


# ─────────────────────────────────────────────
# API TESTS
# ─────────────────────────────────────────────

class AppointmentAPITests(TestCase):
    def setUp(self):
        self.staff = make_staff()
        self.cat = make_category()
        self.svc = make_service(self.cat, self.staff)
        self.room = make_room()
        _, self.profile = make_customer_user()
        self.booking = make_booking(
            booker_name=self.profile.full_name,
            booker_phone=self.profile.phone,
            created_by=self.staff,
        )
        self.appt = make_appointment(self.profile, self.svc, self.room, self.booking)
        self.client = Client(enforce_csrf_checks=False)
        self.client.force_login(self.staff)

    def post_json(self, url, data):
        if "csrftoken" not in self.client.cookies:
            self.client.cookies["csrftoken"] = get_random_string(32)
        csrf_token = self.client.cookies["csrftoken"].value
        return self.client.post(
            url, json.dumps(data), content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

    # --- Rooms ---
    def test_api_rooms_list_staff(self):
        resp = self.client.get("/api/rooms/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertGreaterEqual(len(data["rooms"]), 1)

    def test_api_rooms_list_anonymous_denied(self):
        c = Client()
        resp = c.get("/api/rooms/")
        self.assertEqual(resp.status_code, 403)

    # --- Appointments list ---
    def test_api_appointments_list(self):
        resp = self.client.get("/api/appointments/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])

    def test_api_appointments_filter_status(self):
        resp = self.client.get("/api/appointments/?status=NOT_ARRIVED")
        self.assertEqual(resp.status_code, 200)
        appts = resp.json()["appointments"]
        for a in appts:
            self.assertEqual(a["apptStatus"], "NOT_ARRIVED")

    def test_api_appointments_search_by_name(self):
        resp = self.client.get("/api/appointments/?q=Khach")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()["appointments"]), 1)

    def test_api_appointments_search_no_result(self):
        resp = self.client.get("/api/appointments/?q=XYZNOTEXIST")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["appointments"]), 0)

    # --- Appointment detail ---
    def test_api_appointment_detail(self):
        resp = self.client.get(f"/api/appointments/{self.appt.appointment_code}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["appointment"]["id"], self.appt.appointment_code)

    def test_api_appointment_detail_not_found(self):
        resp = self.client.get("/api/appointments/NOTEXIST/")
        self.assertEqual(resp.status_code, 404)

    # --- Status update ---
    def test_api_appointment_status_update(self):
        resp = self.post_json(
            f"/api/appointments/{self.appt.appointment_code}/status/",
            {"status": "ARRIVED"}
        )
        self.assertEqual(resp.status_code, 200)
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, "ARRIVED")

    def test_api_appointment_status_invalid(self):
        resp = self.post_json(
            f"/api/appointments/{self.appt.appointment_code}/status/",
            {"status": "INVALID_STATUS"}
        )
        self.assertEqual(resp.status_code, 400)

    def test_api_booking_status_cancel(self):
        """Hủy Booking → Booking.status=CANCELLED, Appointment.status=CANCELLED."""
        resp = self.post_json(
            f"/api/appointments/{self.appt.appointment_code}/status/",
            {"status": "CANCELLED"}
        )
        self.assertEqual(resp.status_code, 200)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "CANCELLED")
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, "CANCELLED")

    def test_api_appointment_rebook_post_returns_410(self):
        """POST /rebook/ → 410 Gone (endpoint đã bị loại bỏ, không reset dữ liệu cũ)."""
        self.booking.status = "CANCELLED"
        self.booking.save()
        self.appt.status = "CANCELLED"
        self.appt.save()

        resp = self.post_json(f"/api/appointments/{self.appt.appointment_code}/rebook/", {})
        self.assertEqual(resp.status_code, 410)
        payload = resp.json()
        self.assertFalse(payload["success"])
        self.assertTrue(payload.get("deprecated"))
        # Booking và Appointment KHÔNG bị reset
        self.booking.refresh_from_db()
        self.appt.refresh_from_db()
        self.assertEqual(self.booking.status, "CANCELLED")
        self.assertEqual(self.appt.status, "CANCELLED")

    def test_api_appointment_rebook_get_returns_410(self):
        """GET /rebook/ → 410 Gone (endpoint đã bị loại bỏ)."""
        self.booking.status = "CANCELLED"
        self.booking.save()
        self.appt.status = "CANCELLED"
        self.appt.save()

        resp = self.client.get(f"/api/appointments/{self.appt.appointment_code}/rebook/")
        self.assertEqual(resp.status_code, 410)
        payload = resp.json()
        self.assertFalse(payload["success"])
        self.assertTrue(payload.get("deprecated"))

    def test_api_appointment_rebook_active_also_returns_410(self):
        """POST /rebook/ với lịch đang active cũng trả 410 (không phân biệt trạng thái)."""
        resp = self.post_json(f"/api/appointments/{self.appt.appointment_code}/rebook/", {})
        self.assertEqual(resp.status_code, 410)
        self.assertFalse(resp.json()["success"])

    # --- Delete ---
    def test_api_appointment_delete(self):
        code = self.appt.appointment_code
        resp = self.post_json(f"/api/appointments/{code}/delete/", {})
        self.assertEqual(resp.status_code, 200)
        self.appt.refresh_from_db()
        self.assertIsNotNone(self.appt.deleted_at)

    # --- Pending count ---
    def test_api_pending_count(self):
        resp = self.client.get("/api/booking/pending-count/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("count", resp.json())

    # --- Create batch ---
    def test_api_create_batch_creates_booking_and_appointment(self):
        """POST create-batch tạo 1 Booking + 1 Appointment."""
        from datetime import timedelta
        tomorrow = str(date.today() + timedelta(days=1))
        variant = self.svc.variants.first()
        payload = {
            "booker": {
                "name": "Nguyen Van A",
                "phone": "0912345678",
                "source": "DIRECT",
            },
            "guests": [{
                "name": "Nguyen Van A",
                "phone": "0912345678",
                "variantId": variant.id,
                "roomId": self.room.code,
                "date": tomorrow,
                "time": "10:00",
                "apptStatus": "NOT_ARRIVED",
            }]
        }
        resp = self.post_json("/api/appointments/create-batch/", payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIn("bookingCode", data)
        self.assertEqual(len(data["appointments"]), 1)

    def test_api_create_batch_multiple_guests_same_booking(self):
        """1 người đặt cho 2 khách → cùng bookingCode."""
        from datetime import timedelta
        tomorrow = str(date.today() + timedelta(days=1))
        room2 = Room.objects.create(code="P02", name="Phong P02", capacity=1)
        variant = self.svc.variants.first()
        payload = {
            "booker": {"name": "Tran Thi B", "phone": "0987654321", "source": "DIRECT"},
            "guests": [
                {"name": "Khach 1", "phone": "0911000001", "variantId": variant.id,
                 "roomId": self.room.code, "date": tomorrow, "time": "14:00", "apptStatus": "NOT_ARRIVED"},
                {"name": "Khach 2", "phone": "0911000002", "variantId": variant.id,
                 "roomId": room2.code, "date": tomorrow, "time": "14:00", "apptStatus": "NOT_ARRIVED"},
            ]
        }
        resp = self.post_json("/api/appointments/create-batch/", payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(len(data["appointments"]), 2)
        # Cả 2 appointment phải cùng bookingCode
        codes = [a["bookingCode"] for a in data["appointments"]]
        self.assertEqual(codes[0], codes[1])

    def test_api_create_batch_admin_fromAdmin_flag_sets_confirmed(self):
        """Admin tạo với fromAdmin=True → Booking.status = CONFIRMED (xuất hiện ngay trên lịch)."""
        from datetime import timedelta
        tomorrow = str(date.today() + timedelta(days=1))
        variant = self.svc.variants.first()
        payload = {
            "booker": {
                "name": "Admin Tao Lich",
                "phone": "0912000001",
                "source": "DIRECT",
                "fromAdmin": True,
            },
            "guests": [{
                "name": "Khach Rebook",
                "phone": "0912000002",
                "variantId": variant.id,
                "roomId": self.room.code,
                "date": tomorrow,
                "time": "11:00",
                "apptStatus": "NOT_ARRIVED",
            }]
        }
        resp = self.post_json("/api/appointments/create-batch/", payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        bk = Booking.objects.get(booking_code=data["bookingCode"])
        self.assertEqual(bk.status, "CONFIRMED")

    def test_api_create_batch_online_source_without_fromAdmin_stays_pending(self):
        """Source=ONLINE, không có fromAdmin → Booking.status = PENDING (cần xác nhận)."""
        from datetime import timedelta
        tomorrow = str(date.today() + timedelta(days=1))
        variant = self.svc.variants.first()
        payload = {
            "booker": {
                "name": "Khach Online",
                "phone": "0912000003",
                "source": "ONLINE",
            },
            "guests": [{
                "name": "Khach Online",
                "phone": "0912000003",
                "variantId": variant.id,
                "roomId": self.room.code,
                "date": tomorrow,
                "time": "12:00",
                "apptStatus": "NOT_ARRIVED",
            }]
        }
        resp = self.post_json("/api/appointments/create-batch/", payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        bk = Booking.objects.get(booking_code=data["bookingCode"])
        self.assertEqual(bk.status, "PENDING")

    def test_api_create_batch_direct_source_without_flag_also_confirmed(self):
        """Source=DIRECT (không phải ONLINE) → CONFIRMED dù không có fromAdmin."""
        from datetime import timedelta
        tomorrow = str(date.today() + timedelta(days=1))
        variant = self.svc.variants.first()
        payload = {
            "booker": {
                "name": "Khach Direct",
                "phone": "0912000004",
                "source": "DIRECT",
            },
            "guests": [{
                "name": "Khach Direct",
                "phone": "0912000004",
                "variantId": variant.id,
                "roomId": self.room.code,
                "date": tomorrow,
                "time": "13:00",
                "apptStatus": "NOT_ARRIVED",
            }]
        }
        resp = self.post_json("/api/appointments/create-batch/", payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        bk = Booking.objects.get(booking_code=data["bookingCode"])
        self.assertEqual(bk.status, "CONFIRMED")


# ─────────────────────────────────────────────
# BOOKING PENDING COUNT TESTS
# ─────────────────────────────────────────────

class BookingPendingCountApiTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username="booking-admin", password="testpass123", is_staff=True,
        )
        self.customer_user = User.objects.create_user(username="0900000001", password="testpass123")
        self.customer = CustomerProfile.objects.create(
            user=self.customer_user, phone="0900000001", full_name="Khach Hang 1",
        )
        self.room = Room.objects.create(code="R01", name="Phong 1", capacity=2)
        self.category = ServiceCategory.objects.order_by("id").first()
        if not self.category:
            self.category = ServiceCategory.objects.create(
                code=f"CAT-{get_random_string(6)}", name=f"Category {get_random_string(6)}", status="ACTIVE",
            )
        self.service = Service.objects.create(
            category=self.category, name=f"Tri lieu da {get_random_string(6)}",
            status="ACTIVE", image="/media/services/test.jpg", created_by=self.admin_user,
        )
        self.variant = ServiceVariant.objects.create(
            service=self.service, label="60 phut", duration_minutes=60, price=100000,
        )

    def _make_booking_with_appt(self, source="ONLINE", booking_status="PENDING"):
        bk = Booking.objects.create(
            booker_name=self.customer.full_name,
            booker_phone=self.customer.phone,
            status=booking_status,
            payment_status="UNPAID",
            source=source,
            created_by=self.admin_user,
        )
        Appointment.objects.create(
            booking=bk,
            customer=self.customer,
            service_variant=self.variant,
            room=self.room,
            customer_name_snapshot=self.customer.full_name,
            customer_phone_snapshot=self.customer.phone,
            appointment_date=date(2026, 4, 15),
            appointment_time=time(10, 0),
            status="NOT_ARRIVED",
        )
        return bk

    def test_pending_count_only_includes_online_pending_bookings(self):
        self._make_booking_with_appt(source="ONLINE", booking_status="PENDING")
        self._make_booking_with_appt(source="DIRECT", booking_status="PENDING")
        self._make_booking_with_appt(source="ONLINE", booking_status="CANCELLED")
        self._make_booking_with_appt(source="ONLINE", booking_status="REJECTED")

        client = Client()
        client.force_login(self.admin_user)
        response = client.get(reverse("appointments:api_booking_pending_count"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["count"], 1)


# ─────────────────────────────────────────────
# VIEW TESTS (HTML pages)
# ─────────────────────────────────────────────

class AppointmentViewTests(TestCase):
    def setUp(self):
        self.staff = make_staff()
        self.cat = make_category()
        self.svc = make_service(self.cat, self.staff)
        self.room = make_room()
        self.user, self.profile = make_customer_user()
        self.client = Client()

    def test_admin_appointments_requires_staff(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse("appointments:admin_appointments"))
        self.assertEqual(resp.status_code, 302)

    def test_admin_appointments_staff_ok(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("appointments:admin_appointments"))
        self.assertEqual(resp.status_code, 200)

    def test_my_appointments_requires_login(self):
        resp = self.client.get(reverse("appointments:my_appointments"))
        self.assertEqual(resp.status_code, 302)

    def test_my_appointments_customer_ok(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse("appointments:my_appointments"))
        self.assertEqual(resp.status_code, 200)

    def test_booking_page_customer_ok(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse("appointments:booking"))
        self.assertEqual(resp.status_code, 200)

    def test_cancel_appointment_wrong_owner(self):
        bk = make_booking(booker_name=self.profile.full_name, booker_phone=self.profile.phone, created_by=self.staff)
        appt = make_appointment(self.profile, self.svc, self.room, bk)
        other_user, _ = make_customer_user(username="other", phone="0922222222")
        self.client.force_login(other_user)
        resp = self.client.post(reverse("appointments:cancel_appointment", args=[appt.id]))
        # 404 vì get_object_or_404 lọc theo customer=other_user.customer_profile
        self.assertEqual(resp.status_code, 404)
        appt.refresh_from_db()
        self.assertNotEqual(appt.status, "CANCELLED")

    def test_cancel_appointment_success(self):
        bk = make_booking(booker_name=self.profile.full_name, booker_phone=self.profile.phone,
                          status="CONFIRMED", created_by=self.staff)
        appt = make_appointment(self.profile, self.svc, self.room, bk, status="NOT_ARRIVED")
        self.client.force_login(self.user)
        resp = self.client.post(reverse("appointments:cancel_appointment", args=[appt.id]))
        self.assertEqual(resp.status_code, 302)
        appt.refresh_from_db()
        bk.refresh_from_db()
        self.assertEqual(appt.status, "CANCELLED")
        self.assertEqual(bk.status, "CANCELLED")


class BookingBadgeTemplateTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username="booking-admin", password="testpass123", is_staff=True,
        )

    def test_admin_appointments_page_loads(self):
        client = Client()
        client.force_login(self.admin_user)
        response = client.get(reverse("appointments:admin_appointments"))
        self.assertEqual(response.status_code, 200)


# ─────────────────────────────────────────────
# BOOKING DETAIL API TESTS (edit modal bug fix)
# ─────────────────────────────────────────────

class BookingDetailApiTests(TestCase):
    """
    Test case bắt buộc:
    1 booking có 2 khách khác phòng/khác giờ →
    click vào khách thứ nhất hoặc thứ hai đều trả về đủ 2 appointment.
    """

    def setUp(self):
        self.staff = make_staff(username='staff_bk_detail')
        self.cat   = make_category()
        self.svc   = make_service(self.cat, self.staff)
        _, self.profile1 = make_customer_user(username='guest_bk1', phone='0911000011')
        _, self.profile2 = make_customer_user(username='guest_bk2', phone='0911000022')
        self.room1 = Room.objects.create(code='BKR1', name='Phong BKR1', capacity=1)
        self.room2 = Room.objects.create(code='BKR2', name='Phong BKR2', capacity=1)

        # 1 booking, 2 appointment khác phòng/khác giờ
        self.booking = make_booking(
            booker_name='Thanh Thien',
            booker_phone='0325410204',
            status='CONFIRMED',
            created_by=self.staff,
        )
        self.appt1 = make_appointment(
            self.profile1, self.svc, self.room1, self.booking,
            appt_date=date(2026, 6, 10), appt_time=time(18, 0),
        )
        self.appt2 = make_appointment(
            self.profile2, self.svc, self.room2, self.booking,
            appt_date=date(2026, 6, 10), appt_time=time(18, 30),
        )

        self.client = Client()
        self.client.force_login(self.staff)

    def test_booking_detail_returns_all_appointments(self):
        """GET /api/bookings/<code>/ trả về đủ 2 appointment."""
        resp = self.client.get(f'/api/bookings/{self.booking.booking_code}/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(len(data['appointments']), 2)
        codes = {a['id'] for a in data['appointments']}
        self.assertIn(self.appt1.appointment_code, codes)
        self.assertIn(self.appt2.appointment_code, codes)

    def test_booking_detail_from_appt1_same_as_appt2(self):
        """
        Click appt1 hoặc appt2 đều dẫn đến cùng booking_code
        → cùng trả về 2 appointment.
        """
        # Lấy bookingCode từ appt1
        r1 = self.client.get(f'/api/appointments/{self.appt1.appointment_code}/')
        self.assertEqual(r1.status_code, 200)
        bk_code_from_appt1 = r1.json()['appointment']['bookingCode']

        # Lấy bookingCode từ appt2
        r2 = self.client.get(f'/api/appointments/{self.appt2.appointment_code}/')
        self.assertEqual(r2.status_code, 200)
        bk_code_from_appt2 = r2.json()['appointment']['bookingCode']

        # Cả 2 phải cùng bookingCode
        self.assertEqual(bk_code_from_appt1, bk_code_from_appt2)
        self.assertEqual(bk_code_from_appt1, self.booking.booking_code)

        # Fetch booking detail → phải có đủ 2 appointment
        bk_resp = self.client.get(f'/api/bookings/{bk_code_from_appt1}/')
        self.assertEqual(bk_resp.status_code, 200)
        bk_data = bk_resp.json()
        self.assertEqual(len(bk_data['appointments']), 2)

    def test_booking_detail_includes_booker_info(self):
        """Booking detail trả về đúng booker info."""
        resp = self.client.get(f'/api/bookings/{self.booking.booking_code}/')
        data = resp.json()
        self.assertEqual(data['booking']['bookerName'], 'Thanh Thien')
        self.assertEqual(data['booking']['bookerPhone'], '0325410204')

    def test_booking_detail_anonymous_denied(self):
        """Không có quyền staff → 403."""
        c = Client()
        resp = c.get(f'/api/bookings/{self.booking.booking_code}/')
        self.assertEqual(resp.status_code, 403)

    def test_booking_detail_not_found(self):
        """Booking không tồn tại → 404."""
        resp = self.client.get('/api/bookings/BK9999/')
        self.assertEqual(resp.status_code, 404)


# ─────────────────────────────────────────────
# INVOICE DISCOUNT TESTS
# ─────────────────────────────────────────────

class InvoiceDiscountTests(TestCase):
    """
    Test bắt buộc theo yêu cầu:
    - Invoice cũ không lỗi (discount_type=NONE mặc định)
    - Booking không chiết khấu → tổng tiền không đổi
    - Booking chiết khấu VNĐ (AMOUNT) → tính đúng
    - Booking chiết khấu % (PERCENT) → tính đúng
    - Thanh toán một phần → status PARTIAL
    - Thanh toán đủ → status PAID
    - Xem lại booking đã PAID → nút "Xem hóa đơn"
    """

    def setUp(self):
        self.staff = make_staff("staff_inv")
        self.client = Client(enforce_csrf_checks=False)
        self.client.force_login(self.staff)

        self.cat  = make_category()
        self.room = make_room("P99", capacity=2)

        # Dịch vụ giá 500,000đ
        self.svc = Service.objects.create(
            category=self.cat, name="Facial Test", status="ACTIVE",
            image="", created_by=self.staff,
        )
        self.variant = ServiceVariant.objects.create(
            service=self.svc, label="60 phut", duration_minutes=60, price=500000
        )

        # Booking 1 khách
        self.booking = make_booking(created_by=self.staff)
        _, cust_profile = make_customer_user("cust_inv", "0922222222")
        self.appt = Appointment.objects.create(
            booking=self.booking,
            customer=cust_profile,
            service_variant=self.variant,
            room=self.room,
            customer_name_snapshot="Khach Test",
            customer_phone_snapshot="0922222222",
            appointment_date=date.today(),
            appointment_time=time(10, 0),
            status="NOT_ARRIVED",
        )

    def _pay_url(self):
        return f'/api/bookings/{self.booking.booking_code}/invoice/pay/'

    def _inv_url(self):
        return f'/api/bookings/{self.booking.booking_code}/invoice/'

    def _post(self, data):
        if 'csrftoken' not in self.client.cookies:
            self.client.cookies['csrftoken'] = get_random_string(32)
        csrf_token = self.client.cookies['csrftoken'].value
        return self.client.post(
            self._pay_url(),
            data=json.dumps(data),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=csrf_token,
        )

    # ── 1. Invoice cũ không lỗi ──────────────────────────────────────────────
    def test_invoice_get_no_existing_invoice(self):
        """GET invoice khi chưa có invoice → trả về subtotal đúng, discount=0."""
        resp = self.client.get(self._inv_url())
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        inv = data['invoice']
        self.assertEqual(inv['discountType'],   'NONE')
        self.assertEqual(float(inv['discountValue']),  0)
        self.assertEqual(float(inv['discountAmount']), 0)
        self.assertEqual(float(inv['subtotal']),    500000)
        self.assertEqual(float(inv['finalAmount']), 500000)
        self.assertEqual(float(inv['paidAmount']),  0)
        self.assertEqual(float(inv['remaining']),   500000)

    # ── 2. Không chiết khấu → tổng tiền không đổi ────────────────────────────
    def test_no_discount_total_unchanged(self):
        """discountType=NONE → finalAmount = subtotal."""
        resp = self._post({
            'discountType': 'NONE',
            'discountValue': 0,
            'payAmount': 0,
            'paymentMethod': '',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(float(data['finalAmount']), 500000)
        self.assertEqual(float(data['discountAmount']), 0)
        self.assertEqual(data['paymentStatus'], 'UNPAID')

    # ── 3. Chiết khấu VNĐ (AMOUNT) ───────────────────────────────────────────
    def test_discount_amount_vnd(self):
        """discountType=AMOUNT, discountValue=50000 → finalAmount=450000."""
        resp = self._post({
            'discountType': 'AMOUNT',
            'discountValue': 50000,
            'payAmount': 450000,
            'paymentMethod': 'CASH',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(float(data['finalAmount']),    450000)
        self.assertEqual(float(data['discountAmount']), 50000)
        self.assertEqual(float(data['paidAmount']),     450000)
        self.assertEqual(data['paymentStatus'], 'PAID')

    # ── 4. Chiết khấu % (PERCENT) ────────────────────────────────────────────
    def test_discount_percent(self):
        """discountType=PERCENT, discountValue=10 → discount=50000, final=450000."""
        resp = self._post({
            'discountType': 'PERCENT',
            'discountValue': 10,
            'payAmount': 450000,
            'paymentMethod': 'CASH',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(float(data['discountAmount']), 50000)
        self.assertEqual(float(data['finalAmount']),    450000)
        self.assertEqual(data['paymentStatus'], 'PAID')

    # ── 5. Thanh toán một phần → PARTIAL ─────────────────────────────────────
    def test_partial_payment_status(self):
        """Trả 200,000 / 500,000 → paymentStatus = PARTIAL."""
        resp = self._post({
            'discountType': 'NONE',
            'discountValue': 0,
            'payAmount': 200000,
            'paymentMethod': 'CASH',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['paymentStatus'], 'PARTIAL')
        self.assertEqual(float(data['paidAmount']),  200000)
        self.assertEqual(float(data['remaining']),   300000)

    # ── 6. Thanh toán đủ → PAID ──────────────────────────────────────────────
    def test_full_payment_status(self):
        """Trả đủ 500,000 → paymentStatus = PAID."""
        resp = self._post({
            'discountType': 'NONE',
            'discountValue': 0,
            'payAmount': 500000,
            'paymentMethod': 'BANK_TRANSFER',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['paymentStatus'], 'PAID')
        self.assertEqual(float(data['remaining']), 0)

    # ── 7. Thanh toán nhiều lần cộng dồn ─────────────────────────────────────
    def test_cumulative_payments(self):
        """Trả 200k lần 1, 300k lần 2 → tổng 500k → PAID."""
        self._post({'discountType': 'NONE', 'discountValue': 0,
                    'payAmount': 200000, 'paymentMethod': 'CASH'})
        resp = self._post({'discountType': 'NONE', 'discountValue': 0,
                           'payAmount': 300000, 'paymentMethod': 'CASH'})
        data = resp.json()
        self.assertEqual(data['paymentStatus'], 'PAID')
        self.assertEqual(float(data['paidAmount']), 500000)

    # ── 8. Booking 2 khách → hóa đơn 2 dòng, tổng đúng ──────────────────────
    def test_two_guests_invoice_lines(self):
        """Booking 2 khách → invoice có 2 lines, subtotal = 1,000,000."""
        _, cust2 = make_customer_user("cust_inv2", "0933333333")
        Appointment.objects.create(
            booking=self.booking,
            customer=cust2,
            service_variant=self.variant,
            room=self.room,
            customer_name_snapshot="Khach 2",
            customer_phone_snapshot="0933333333",
            appointment_date=date.today(),
            appointment_time=time(11, 0),
            status="NOT_ARRIVED",
        )
        resp = self.client.get(self._inv_url())
        data = resp.json()
        inv = data['invoice']
        self.assertEqual(len(inv['lines']), 2)
        self.assertEqual(float(inv['subtotal']), 1000000)

    # ── 9. Chiết khấu % vượt 100 → lỗi ──────────────────────────────────────
    def test_discount_percent_over_100_rejected(self):
        resp = self._post({
            'discountType': 'PERCENT',
            'discountValue': 110,
            'payAmount': 0,
            'paymentMethod': '',
        })
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['success'])

    # ── 10. Chiết khấu VNĐ vượt subtotal → clamp về subtotal ─────────────────
    def test_discount_amount_clamped_to_subtotal(self):
        """Chiết khấu 999,999 > subtotal 500,000 → clamp → final=0, PAID."""
        resp = self._post({
            'discountType': 'AMOUNT',
            'discountValue': 999999,
            'payAmount': 0,
            'paymentMethod': '',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(float(data['finalAmount']), 0)
        # final=0, paid=0 → PAID (0 >= 0)
        self.assertEqual(data['paymentStatus'], 'PAID')

    # ── 11. Alias 'VND' → 'AMOUNT' được chấp nhận ────────────────────────────
    def test_discount_type_vnd_alias_accepted(self):
        """discountType='VND' (alias cũ) → được map sang AMOUNT, tính đúng."""
        resp = self._post({
            'discountType': 'VND',
            'discountValue': 100000,
            'payAmount': 400000,
            'paymentMethod': 'CASH',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(float(data['discountAmount']), 100000)
        self.assertEqual(float(data['finalAmount']),    400000)
        self.assertEqual(data['paymentStatus'], 'PAID')

    # ── 12. Invoice GET trả về discountType/Value đã lưu ─────────────────────
    def test_invoice_get_returns_saved_discount(self):
        """Sau khi lưu discount PERCENT 20%, GET lại trả về đúng."""
        self._post({
            'discountType': 'PERCENT',
            'discountValue': 20,
            'payAmount': 0,
            'paymentMethod': '',
        })
        resp = self.client.get(self._inv_url())
        inv = resp.json()['invoice']
        self.assertEqual(inv['discountType'],  'PERCENT')
        self.assertEqual(float(inv['discountValue']), 20)
        self.assertEqual(float(inv['discountAmount']), 100000)  # 20% * 500000
        self.assertEqual(float(inv['finalAmount']),    400000)


# ─────────────────────────────────────────────
# EDIT APPOINTMENT PAST-TIME VALIDATION TESTS
# ─────────────────────────────────────────────

class EditAppointmentPastTimeTests(TestCase):
    """
    Test bắt buộc:
    - Lịch quá khứ, chỉ đổi trạng thái → lưu được.
    - Lịch quá khứ, chỉ sửa ghi chú → lưu được.
    - Lịch quá khứ, đổi giờ sang giờ quá khứ khác → báo lỗi.
    - Tạo lịch mới ở giờ quá khứ → báo lỗi.
    """

    def setUp(self):
        self.staff = make_staff("staff_edit_past")
        self.client = Client(enforce_csrf_checks=False)
        self.client.force_login(self.staff)

        self.cat  = make_category()
        self.room = make_room("P88", capacity=2)
        self.svc  = Service.objects.create(
            category=self.cat, name="Test Svc Past", status="ACTIVE",
            image="", created_by=self.staff,
        )
        self.variant = ServiceVariant.objects.create(
            service=self.svc, label="60 phut", duration_minutes=60, price=300000
        )

        # Booking với lịch hẹn ngày hôm qua (quá khứ)
        self.booking = make_booking(created_by=self.staff, status="CONFIRMED")
        _, cust = make_customer_user("cust_past", "0944444444")
        yesterday = date.today().replace(day=date.today().day - 1) if date.today().day > 1 \
            else date.today().replace(month=date.today().month - 1 or 12, day=28)
        self.appt = Appointment.objects.create(
            booking=self.booking,
            customer=cust,
            service_variant=self.variant,
            room=self.room,
            customer_name_snapshot="Khach Past",
            customer_phone_snapshot="0944444444",
            appointment_date=yesterday,
            appointment_time=time(18, 0),
            status="NOT_ARRIVED",
        )

    def _update_url(self):
        return f'/api/appointments/{self.appt.appointment_code}/update/'

    def _post(self, data):
        if 'csrftoken' not in self.client.cookies:
            self.client.cookies['csrftoken'] = get_random_string(32)
        token = self.client.cookies['csrftoken'].value
        return self.client.post(
            self._update_url(),
            data=json.dumps(data),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=token,
        )

    def _base_payload(self, **overrides):
        """Payload cơ bản — không đổi ngày/giờ."""
        payload = {
            'bookerName':  self.booking.booker_name,
            'bookerPhone': self.booking.booker_phone,
            'customerName': 'Khach Past',
            'phone': '0944444444',
            'variantId': self.variant.id,
            'roomId': self.room.code,
            'date': str(self.appt.appointment_date),
            'time': self.appt.appointment_time.strftime('%H:%M'),
            'apptStatus': 'NOT_ARRIVED',
        }
        payload.update(overrides)
        return payload

    # ── 1. Chỉ đổi trạng thái sang "Đã đến" → lưu được ──────────────────────
    def test_edit_past_change_status_arrived(self):
        """Lịch quá khứ, đổi trạng thái ARRIVED → không báo lỗi giờ."""
        resp = self._post(self._base_payload(apptStatus='ARRIVED'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'], msg=data.get('error', ''))

    # ── 2. Chỉ đổi trạng thái sang "Hoàn thành" → lưu được ──────────────────
    def test_edit_past_change_status_completed(self):
        """Lịch quá khứ, đổi trạng thái COMPLETED (có dịch vụ + payStatus PAID) → không báo lỗi giờ."""
        resp = self._post(self._base_payload(apptStatus='COMPLETED', payStatus='PAID'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'], msg=data.get('error', ''))

    # ── 3. Chỉ sửa ghi chú → lưu được ───────────────────────────────────────
    def test_edit_past_change_note_only(self):
        """Lịch quá khứ, chỉ sửa staffNote → không báo lỗi giờ."""
        resp = self._post(self._base_payload(staffNote='Ghi chu moi'))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])

    # ── 4. Đổi giờ sang giờ quá khứ khác → báo lỗi ──────────────────────────
    def test_edit_past_change_time_to_another_past_time(self):
        """Lịch quá khứ, đổi giờ sang 17:00 cùng ngày hôm qua → báo lỗi."""
        payload = self._base_payload(time='17:00')
        resp = self._post(payload)
        # Ngày hôm qua → validate_appointment_date sẽ chặn (ngày < hôm nay)
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['success'])

    # ── 5. Tạo lịch mới ở giờ quá khứ → báo lỗi ─────────────────────────────
    def test_create_new_appointment_past_time_rejected(self):
        """POST create-batch với ngày hôm qua → báo lỗi."""
        if 'csrftoken' not in self.client.cookies:
            self.client.cookies['csrftoken'] = get_random_string(32)
        token = self.client.cookies['csrftoken'].value

        yesterday = str(self.appt.appointment_date)
        resp = self.client.post(
            '/api/appointments/create-batch/',
            data=json.dumps({
                'booker': {
                    'name': 'Test Booker', 'phone': '0955555555',
                    'source': 'DIRECT', 'payStatus': 'UNPAID',
                },
                'guests': [{
                    'name': 'Khach Moi', 'phone': '0955555556',
                    'variantId': self.variant.id,
                    'roomId': self.room.code,
                    'date': yesterday,
                    'time': '10:00',
                    'apptStatus': 'NOT_ARRIVED',
                }],
            }),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['success'])


# ─────────────────────────────────────────────
# STATUS TIMING VALIDATION TESTS
# ─────────────────────────────────────────────

class StatusTimingValidationTests(TestCase):
    """
    Test bắt buộc:
    - Lịch 15:00–16:00, hiện tại 14:30 → ARRIVED bị chặn, COMPLETED bị chặn
    - Lịch 15:00–16:00, hiện tại 15:10 → ARRIVED pass, COMPLETED bị chặn
    - Lịch 15:00–16:00, hiện tại 16:01, PAID → COMPLETED pass
    - Lịch 15:00–16:00, hiện tại 16:01, UNPAID → COMPLETED bị chặn vì chưa thanh toán
    - Backend direct API cũng chặn giống FE
    """

    def setUp(self):
        from unittest.mock import patch
        self.patch = patch  # lưu để dùng trong test

        self.staff = make_staff("staff_timing")
        self.client = Client(enforce_csrf_checks=False)
        self.client.force_login(self.staff)

        self.cat     = make_category()
        self.room    = make_room("PT1", capacity=2)
        self.svc     = Service.objects.create(
            category=self.cat, name="Timing Test Svc", status="ACTIVE",
            image="", created_by=self.staff,
        )
        self.variant = ServiceVariant.objects.create(
            service=self.svc, label="60 phut", duration_minutes=60, price=300000,
        )
        _, self.cust = make_customer_user("cust_timing", "0955000001")

    def _make_appt(self, appt_date, appt_time, pay_status="UNPAID"):
        bk = Booking.objects.create(
            booker_name="Test Booker",
            booker_phone="0955000001",
            status="CONFIRMED",
            payment_status=pay_status,
            source="DIRECT",
            created_by=self.staff,
        )
        appt = Appointment.objects.create(
            booking=bk,
            customer=self.cust,
            service_variant=self.variant,
            room=self.room,
            customer_name_snapshot="Khach Timing",
            customer_phone_snapshot="0955000001",
            appointment_date=appt_date,
            appointment_time=appt_time,
            status="NOT_ARRIVED",
        )
        return appt, bk

    def _post_status(self, appt_code, new_status):
        if 'csrftoken' not in self.client.cookies:
            from django.utils.crypto import get_random_string
            self.client.cookies['csrftoken'] = get_random_string(32)
        token = self.client.cookies['csrftoken'].value
        return self.client.post(
            f'/api/appointments/{appt_code}/status/',
            data=json.dumps({'status': new_status}),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=token,
        )

    def _mock_now(self, mock_dt):
        """Trả về context manager mock django.utils.timezone.now() về mock_dt."""
        from unittest.mock import patch
        import datetime as _dt
        from django.utils import timezone as _tz
        # mock_dt là naive datetime local → convert sang aware
        aware = _tz.make_aware(mock_dt)
        return patch('django.utils.timezone.now', return_value=aware)

    # ── 1. 14:30 → ARRIVED bị chặn ───────────────────────────────────────────
    def test_arrived_before_start_blocked(self):
        """Lịch 15:00, hiện tại 14:30 → ARRIVED bị chặn."""
        import datetime as _dt
        appt, _ = self._make_appt(date.today(), time(15, 0))
        fake_now = _dt.datetime.combine(date.today(), _dt.time(14, 30))
        with self._mock_now(fake_now):
            resp = self._post_status(appt.appointment_code, 'ARRIVED')
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['success'])
        self.assertIn('Chưa đến giờ hẹn', resp.json()['error'])

    # ── 2. 14:30 → COMPLETED bị chặn ─────────────────────────────────────────
    def test_completed_before_start_blocked(self):
        """Lịch 15:00–16:00, hiện tại 14:30 → COMPLETED bị chặn."""
        import datetime as _dt
        appt, bk = self._make_appt(date.today(), time(15, 0), pay_status="PAID")
        bk.payment_status = "PAID"; bk.save()
        fake_now = _dt.datetime.combine(date.today(), _dt.time(14, 30))
        with self._mock_now(fake_now):
            resp = self._post_status(appt.appointment_code, 'COMPLETED')
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['success'])
        self.assertIn('Chưa kết thúc giờ hẹn', resp.json()['error'])

    # ── 3. 15:10 → ARRIVED pass ──────────────────────────────────────────────
    def test_arrived_after_start_pass(self):
        """Lịch 15:00, hiện tại 15:10 → ARRIVED pass."""
        import datetime as _dt
        appt, _ = self._make_appt(date.today(), time(15, 0))
        fake_now = _dt.datetime.combine(date.today(), _dt.time(15, 10))
        with self._mock_now(fake_now):
            resp = self._post_status(appt.appointment_code, 'ARRIVED')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])

    # ── 4. 15:10 → COMPLETED bị chặn (chưa kết thúc) ────────────────────────
    def test_completed_before_end_blocked(self):
        """Lịch 15:00–16:00, hiện tại 15:10 → COMPLETED bị chặn."""
        import datetime as _dt
        appt, bk = self._make_appt(date.today(), time(15, 0), pay_status="PAID")
        bk.payment_status = "PAID"; bk.save()
        fake_now = _dt.datetime.combine(date.today(), _dt.time(15, 10))
        with self._mock_now(fake_now):
            resp = self._post_status(appt.appointment_code, 'COMPLETED')
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['success'])
        self.assertIn('Chưa kết thúc giờ hẹn', resp.json()['error'])

    # ── 5. 16:01, PAID → COMPLETED pass ──────────────────────────────────────
    def test_completed_after_end_paid_pass(self):
        """Lịch 15:00–16:00, hiện tại 16:01, PAID → COMPLETED pass."""
        import datetime as _dt
        appt, bk = self._make_appt(date.today(), time(15, 0), pay_status="PAID")
        bk.payment_status = "PAID"; bk.save()
        fake_now = _dt.datetime.combine(date.today(), _dt.time(16, 1))
        with self._mock_now(fake_now):
            resp = self._post_status(appt.appointment_code, 'COMPLETED')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])

    # ── 6. 16:01, UNPAID → COMPLETED bị chặn vì chưa thanh toán ─────────────
    def test_completed_after_end_unpaid_blocked(self):
        """Lịch 15:00–16:00, hiện tại 16:01, UNPAID → bị chặn vì chưa thanh toán."""
        import datetime as _dt
        appt, _ = self._make_appt(date.today(), time(15, 0), pay_status="UNPAID")
        fake_now = _dt.datetime.combine(date.today(), _dt.time(16, 1))
        with self._mock_now(fake_now):
            resp = self._post_status(appt.appointment_code, 'COMPLETED')
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['success'])
        self.assertIn('thanh toán', resp.json()['error'])

    # ── 7. 16:01, PARTIAL → COMPLETED bị chặn vì chưa thanh toán đủ ─────────
    def test_completed_after_end_partial_blocked(self):
        """Lịch 15:00–16:00, hiện tại 16:01, PARTIAL → bị chặn vì chưa thanh toán đủ."""
        import datetime as _dt
        appt, bk = self._make_appt(date.today(), time(15, 0), pay_status="PARTIAL")
        bk.payment_status = "PARTIAL"; bk.save()
        fake_now = _dt.datetime.combine(date.today(), _dt.time(16, 1))
        with self._mock_now(fake_now):
            resp = self._post_status(appt.appointment_code, 'COMPLETED')
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['success'])
        self.assertIn('thanh toán', resp.json()['error'])

    # ── 8. NOT_ARRIVED luôn pass bất kể giờ ──────────────────────────────────
    def test_not_arrived_always_pass(self):
        """NOT_ARRIVED không bị chặn bởi timing."""
        import datetime as _dt
        appt, _ = self._make_appt(date.today(), time(15, 0))
        # Giả sử hiện tại là 8:00 sáng — trước giờ hẹn
        fake_now = _dt.datetime.combine(date.today(), _dt.time(8, 0))
        with self._mock_now(fake_now):
            resp = self._post_status(appt.appointment_code, 'NOT_ARRIVED')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])
