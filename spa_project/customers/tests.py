"""
Tests cho Customers app — model, admin view, profile view.
"""
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from .models import CustomerProfile


def make_staff(username="cust_staff"):
    return User.objects.create_user(username=username, password="pass1234", is_staff=True)


def make_customer(username="cust_user", phone="0977777777"):
    user = User.objects.create_user(username=username, password="pass1234")
    profile = CustomerProfile.objects.create(user=user, phone=phone, full_name="Nguyen Van B")
    return user, profile


class CustomerProfileModelTests(TestCase):
    def test_str(self):
        _, p = make_customer()
        self.assertIn("Nguyen Van B", str(p))

    def test_phone_unique(self):
        make_customer()
        with self.assertRaises(Exception):
            make_customer(username="dup", phone="0977777777")

    def test_invalid_gender_raises(self):
        from django.db import IntegrityError
        with self.assertRaises(Exception):
            CustomerProfile.objects.create(
                phone="0900000001", full_name="Test", gender="INVALID"
            )

    def test_valid_genders(self):
        for i, gender in enumerate(["Nam", "Nu", "Khac"]):
            p = CustomerProfile.objects.create(
                phone=f"090000000{i+2}", full_name="Test", gender=gender
            )
            self.assertEqual(p.gender, gender)


class CustomerAdminViewTests(TestCase):
    def setUp(self):
        self.staff = make_staff()
        self.user, self.profile = make_customer()
        self.client = Client()

    def test_admin_customers_requires_staff(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse("customers:admin_customers"))
        self.assertEqual(resp.status_code, 302)

    def test_admin_customers_staff_ok(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("customers:admin_customers"))
        self.assertEqual(resp.status_code, 200)

    def test_customer_profile_page_requires_login(self):
        resp = self.client.get(reverse("customers:customer_profile"))
        self.assertEqual(resp.status_code, 302)

    def test_customer_profile_page_ok(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse("customers:customer_profile"))
        self.assertEqual(resp.status_code, 200)
