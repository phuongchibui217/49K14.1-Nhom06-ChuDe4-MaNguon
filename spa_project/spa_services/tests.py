"""
Tests cho spa_services app — models, public views, admin views, APIs.
"""
import json

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from .models import Service, ServiceCategory, ServiceVariant


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def make_staff(username="svc_staff"):
    return User.objects.create_user(username=username, password="pass1234", is_staff=True)


def make_category(code="MS", name="Massage"):
    cat, _ = ServiceCategory.objects.get_or_create(code=code, defaults={"name": name, "status": "ACTIVE"})
    return cat


def make_service(category, created_by, name="Massage Body"):
    return Service.objects.create(
        category=category, name=name, status="ACTIVE",
        image="", created_by=created_by,
    )


def make_variant(service, label="60 phut", duration=60, price=200000):
    return ServiceVariant.objects.create(
        service=service, label=label, duration_minutes=duration, price=price
    )


# ─────────────────────────────────────────────
# MODEL TESTS
# ─────────────────────────────────────────────

class ServiceModelTests(TestCase):
    def setUp(self):
        self.staff = make_staff()
        self.cat = make_category()

    def test_service_code_auto_generated(self):
        svc = make_service(self.cat, self.staff)
        self.assertTrue(svc.code.startswith("DV"))

    def test_service_slug_auto_generated(self):
        svc = make_service(self.cat, self.staff)
        self.assertIsNotNone(svc.slug)

    def test_get_image_url_default(self):
        svc = make_service(self.cat, self.staff)
        svc.image = ""
        self.assertIn("unsplash", svc.get_image_url())

    def test_get_image_url_with_image(self):
        svc = make_service(self.cat, self.staff)
        svc.image = "services/test.jpg"
        self.assertIn("/media/", svc.get_image_url())

    def test_variant_str(self):
        svc = make_service(self.cat, self.staff)
        v = make_variant(svc)
        self.assertIn("Massage Body", str(v))

    def test_category_status_invalid_raises(self):
        from django.db import IntegrityError
        with self.assertRaises(Exception):
            ServiceCategory.objects.create(code="BAD", name="Bad Cat", status="WRONG")


# ─────────────────────────────────────────────
# PUBLIC VIEW TESTS
# ─────────────────────────────────────────────

class ServicePublicViewTests(TestCase):
    def setUp(self):
        self.staff = make_staff()
        self.cat = make_category()
        self.svc = make_service(self.cat, self.staff)
        make_variant(self.svc)
        self.client = Client()

    def test_service_list_ok(self):
        resp = self.client.get(reverse("spa_services:service_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Massage Body")

    def test_service_list_only_active(self):
        inactive = make_service(self.cat, self.staff, name="Inactive Svc")
        inactive.status = "INACTIVE"
        inactive.save()
        resp = self.client.get(reverse("spa_services:service_list"))
        self.assertNotContains(resp, "Inactive Svc")

    def test_service_list_has_categories(self):
        resp = self.client.get(reverse("spa_services:service_list"))
        self.assertIn("categories", resp.context)

    def test_service_detail_ok(self):
        resp = self.client.get(reverse("spa_services:service_detail", args=[self.svc.id]))
        self.assertEqual(resp.status_code, 200)

    def test_service_detail_inactive_404(self):
        self.svc.status = "INACTIVE"
        self.svc.save()
        resp = self.client.get(reverse("spa_services:service_detail", args=[self.svc.id]))
        self.assertEqual(resp.status_code, 404)


# ─────────────────────────────────────────────
# ADMIN VIEW TESTS
# ─────────────────────────────────────────────

class ServiceAdminViewTests(TestCase):
    def setUp(self):
        self.staff = make_staff()
        self.cat = make_category()
        self.svc = make_service(self.cat, self.staff)
        self.client = Client()
        self.client.force_login(self.staff)

    def test_admin_services_list_ok(self):
        resp = self.client.get(reverse("spa_services:admin_services"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Massage Body")

    def test_admin_services_requires_staff(self):
        c = Client()
        non_staff = User.objects.create_user(username="ns", password="pass1234")
        c.force_login(non_staff)
        resp = c.get(reverse("spa_services:admin_services"))
        self.assertEqual(resp.status_code, 302)

    def test_admin_services_search(self):
        resp = self.client.get(reverse("spa_services:admin_services") + "?search=Massage")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Massage Body")

    def test_admin_services_search_no_result(self):
        resp = self.client.get(reverse("spa_services:admin_services") + "?search=NOTEXIST")
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Massage Body")


# ─────────────────────────────────────────────
# API TESTS
# ─────────────────────────────────────────────

class ServiceAPITests(TestCase):
    def setUp(self):
        self.staff = make_staff()
        self.cat = make_category()
        self.svc = make_service(self.cat, self.staff)
        self.variant = make_variant(self.svc)
        self.client = Client()
        self.client.force_login(self.staff)

    def post_json(self, url, data):
        return self.client.post(url, json.dumps(data), content_type="application/json")

    # --- List ---
    def test_api_services_list(self):
        resp = self.client.get("/api/services/")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()["services"]), 1)

    def test_api_services_list_anonymous_denied(self):
        c = Client()
        resp = c.get("/api/services/")
        self.assertEqual(resp.status_code, 403)

    def test_api_services_list_by_id(self):
        resp = self.client.get(f"/api/services/?id={self.svc.id}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["services"]), 1)

    # --- Variants ---
    def test_api_variant_list(self):
        resp = self.client.get(f"/api/services/{self.svc.id}/variants/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
        self.assertEqual(len(resp.json()["variants"]), 1)

    def test_api_variant_create(self):
        resp = self.post_json(
            f"/api/services/{self.svc.id}/variants/create/",
            {"label": "90 phut", "duration_minutes": 90, "price": 280000}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
        self.assertEqual(ServiceVariant.objects.filter(service=self.svc).count(), 2)

    def test_api_variant_create_invalid_duration(self):
        resp = self.post_json(
            f"/api/services/{self.svc.id}/variants/create/",
            {"label": "Bad", "duration_minutes": -1, "price": 100000}
        )
        self.assertEqual(resp.status_code, 400)

    def test_api_variant_update(self):
        resp = self.post_json(
            f"/api/services/{self.svc.id}/variants/{self.variant.id}/update/",
            {"price": 250000}
        )
        self.assertEqual(resp.status_code, 200)
        self.variant.refresh_from_db()
        self.assertEqual(float(self.variant.price), 250000.0)

    def test_api_variant_delete(self):
        resp = self.post_json(
            f"/api/services/{self.svc.id}/variants/{self.variant.id}/delete/", {}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(ServiceVariant.objects.filter(id=self.variant.id).exists())
