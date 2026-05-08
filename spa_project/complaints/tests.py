"""
Tests cho Complaints app — models, customer views, admin views, APIs.
"""
import json

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from customers.models import CustomerProfile
from .models import Complaint, ComplaintHistory, ComplaintReply


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def make_staff(username="cmp_staff"):
    return User.objects.create_user(username=username, password="pass1234", is_staff=True)


def make_customer(username="cmp_cust", phone="0933333333"):
    user = User.objects.create_user(username=username, password="pass1234")
    profile = CustomerProfile.objects.create(user=user, phone=phone, full_name="Khach Test")
    return user, profile


def make_complaint(customer_profile, title="Dich vu kem", status="NEW"):
    return Complaint.objects.create(
        customer=customer_profile,
        full_name=customer_profile.full_name,
        phone=customer_profile.phone,
        customer_name_snapshot=customer_profile.full_name,
        customer_phone_snapshot=customer_profile.phone,
        title=title,
        content="Noi dung khieu nai",
        status=status,
    )


# ─────────────────────────────────────────────
# MODEL TESTS
# ─────────────────────────────────────────────

class ComplaintModelTests(TestCase):
    def setUp(self):
        _, self.profile = make_customer()

    def test_code_auto_generated(self):
        c = make_complaint(self.profile)
        self.assertTrue(c.code.startswith("KN"))

    def test_status_default_new(self):
        c = make_complaint(self.profile)
        self.assertEqual(c.status, "NEW")

    def test_invalid_status_raises(self):
        with self.assertRaises(Exception):
            Complaint.objects.create(
                customer=self.profile,
                full_name="Test", phone="0900000000",
                title="T", content="C", status="INVALID"
            )

    def test_history_log(self):
        staff = make_staff()
        c = make_complaint(self.profile)
        ComplaintHistory.log(c, "CREATE", note="test", performed_by=staff)
        self.assertEqual(c.history.count(), 1)


# ─────────────────────────────────────────────
# CUSTOMER VIEW TESTS
# ─────────────────────────────────────────────

class ComplaintCustomerViewTests(TestCase):
    def setUp(self):
        self.user, self.profile = make_customer()
        self.client = Client()
        self.client.force_login(self.user)

    def test_complaint_list_ok(self):
        resp = self.client.get(reverse("complaints:customer_complaint_list"))
        self.assertEqual(resp.status_code, 200)

    def test_complaint_create_get(self):
        resp = self.client.get(reverse("complaints:customer_complaint_create"))
        self.assertEqual(resp.status_code, 200)

    def test_complaint_create_post(self):
        resp = self.client.post(reverse("complaints:customer_complaint_create"), {
            "title": "Dich vu kem chat luong",
            "content": "Nhan vien khong nhiet tinh",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Complaint.objects.filter(customer=self.profile).count(), 1)

    def test_complaint_detail_ok(self):
        c = make_complaint(self.profile)
        resp = self.client.get(reverse("complaints:customer_complaint_detail", args=[c.id]))
        self.assertEqual(resp.status_code, 200)

    def test_complaint_detail_wrong_owner(self):
        other_user, other_profile = make_customer(username="other2", phone="0944444444")
        c = make_complaint(other_profile)
        resp = self.client.get(reverse("complaints:customer_complaint_detail", args=[c.id]))
        self.assertEqual(resp.status_code, 302)

    def test_complaint_requires_login(self):
        c = Client()
        resp = c.get(reverse("complaints:customer_complaint_list"))
        self.assertEqual(resp.status_code, 302)


# ─────────────────────────────────────────────
# ADMIN VIEW TESTS
# ─────────────────────────────────────────────

class ComplaintAdminViewTests(TestCase):
    def setUp(self):
        self.staff = make_staff()
        _, self.profile = make_customer()
        self.complaint = make_complaint(self.profile)
        self.client = Client()
        self.client.force_login(self.staff)

    def test_admin_list_ok(self):
        resp = self.client.get(reverse("complaints:admin_complaints"))
        self.assertEqual(resp.status_code, 200)

    def test_admin_list_requires_staff(self):
        user, _ = make_customer(username="ns2", phone="0955555555")
        c = Client()
        c.force_login(user)
        resp = c.get(reverse("complaints:admin_complaints"))
        self.assertEqual(resp.status_code, 302)

    def test_admin_detail_ok(self):
        resp = self.client.get(reverse("complaints:admin_complaint_detail", args=[self.complaint.id]))
        self.assertEqual(resp.status_code, 200)

    def test_admin_take_complaint(self):
        resp = self.client.post(reverse("complaints:admin_complaint_take", args=[self.complaint.id]))
        self.assertEqual(resp.status_code, 302)
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.assigned_to, self.staff)
        self.assertEqual(self.complaint.status, "IN_PROGRESS")

    def test_admin_status_update(self):
        resp = self.client.post(
            reverse("complaints:admin_complaint_status", args=[self.complaint.id]),
            {"status": "IN_PROGRESS"}
        )
        self.assertEqual(resp.status_code, 302)
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, "IN_PROGRESS")

    def test_admin_complete_requires_resolution(self):
        self.complaint.assigned_to = self.staff
        self.complaint.save()
        resp = self.client.post(
            reverse("complaints:admin_complaint_complete", args=[self.complaint.id]),
            {"resolution": ""}
        )
        self.complaint.refresh_from_db()
        self.assertNotEqual(self.complaint.status, "RESOLVED")

    def test_admin_complete_success(self):
        self.complaint.assigned_to = self.staff
        self.complaint.save()
        resp = self.client.post(
            reverse("complaints:admin_complaint_complete", args=[self.complaint.id]),
            {"resolution": "Da xu ly xong"}
        )
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, "RESOLVED")

    def test_admin_layout_no_longer_exposes_complaints_stream_url(self):
        resp = self.client.get(reverse("complaints:admin_complaints"))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        self.assertIn("/api/complaints/new-count/", content)
        self.assertNotIn("/api/complaints/new-count/stream/", content)
        self.assertNotIn("countStreamUrl", content)


# ─────────────────────────────────────────────
# API TESTS
# ─────────────────────────────────────────────

class ComplaintAPITests(TestCase):
    def setUp(self):
        self.staff = make_staff()
        self.user, self.profile = make_customer()
        self.complaint = make_complaint(self.profile)
        self.client = Client()

    def post_json(self, url, data, user=None):
        c = Client()
        if user:
            c.force_login(user)
        return c.post(url, json.dumps(data), content_type="application/json")

    def test_api_list_staff_only(self):
        self.client.force_login(self.staff)
        resp = self.client.get("/api/complaints/")
        self.assertEqual(resp.status_code, 200)

    def test_api_list_anonymous_denied(self):
        resp = self.client.get("/api/complaints/")
        self.assertEqual(resp.status_code, 403)

    def test_api_detail_owner_ok(self):
        self.client.force_login(self.user)
        resp = self.client.get(f"/api/complaints/{self.complaint.id}/")
        self.assertEqual(resp.status_code, 200)

    def test_api_detail_wrong_owner_denied(self):
        other, _ = make_customer(username="oth3", phone="0966666666")
        self.client.force_login(other)
        resp = self.client.get(f"/api/complaints/{self.complaint.id}/")
        self.assertEqual(resp.status_code, 403)

    def test_api_create_authenticated(self):
        resp = self.post_json("/api/complaints/create/", {
            "title": "Khieu nai moi",
            "content": "Noi dung chi tiet",
        }, user=self.user)
        self.assertIn(resp.status_code, [200, 201])
        self.assertTrue(resp.json()["success"])

    def test_api_stats_staff_only(self):
        self.client.force_login(self.staff)
        resp = self.client.get("/api/complaints/stats/")
        self.assertEqual(resp.status_code, 200)
