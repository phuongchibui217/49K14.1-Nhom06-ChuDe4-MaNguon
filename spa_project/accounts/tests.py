from django.contrib.auth import SESSION_KEY
from django.contrib.auth.models import User, Group
from django.test import Client, TestCase
from django.urls import reverse

from customers.models import CustomerProfile
from core.user_service import GROUP_CUSTOMER


def _make_register_data(**overrides):
    """Dữ liệu hợp lệ mặc định cho form đăng ký."""
    data = {
        'username': 'testkhach',
        'full_name': 'Nguyen Van A',
        'phone': '0912345678',
        'email': '',
        'gender': 'Nam',
        'dob': '',
        'password1': 'pass1234',
        'password2': 'pass1234',
        'address': '',
        'agree_terms': 'on',
    }
    data.update(overrides)
    return data


class RegisterFlowTests(TestCase):
    """Kiểm tra toàn bộ luồng đăng ký khách hàng."""

    def setUp(self):
        Group.objects.get_or_create(name=GROUP_CUSTOMER)
        self.url = reverse('accounts:register')
        self.client = Client()

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_register_success(self):
        """Đăng ký thành công: tạo User, CustomerProfile, gán group."""
        resp = self.client.post(self.url, _make_register_data())
        self.assertEqual(resp.status_code, 302)

        user = User.objects.get(username='testkhach')
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

        # Có CustomerProfile
        self.assertTrue(CustomerProfile.objects.filter(user=user).exists())

        # Không có StaffProfile
        self.assertFalse(hasattr(user, 'staff_profile'))

        # Đúng group
        self.assertIn(GROUP_CUSTOMER, user.groups.values_list('name', flat=True))

    def test_register_success_auto_login(self):
        """Sau đăng ký thành công, user được tự động đăng nhập."""
        resp = self.client.post(self.url, _make_register_data())
        self.assertEqual(resp.status_code, 302)
        self.assertIn(SESSION_KEY, self.client.session)

    # ------------------------------------------------------------------
    # Required fields
    # ------------------------------------------------------------------

    def test_missing_full_name(self):
        resp = self.client.post(self.url, _make_register_data(full_name=''))
        self.assertEqual(resp.status_code, 200)
        self.assertFormError(resp, 'form', 'full_name', 'Vui lòng nhập họ và tên.')
        self.assertEqual(User.objects.filter(username='testkhach').count(), 0)

    def test_missing_phone(self):
        resp = self.client.post(self.url, _make_register_data(phone=''))
        self.assertEqual(resp.status_code, 200)
        self.assertFormError(resp, 'form', 'phone', 'Vui lòng nhập số điện thoại.')

    def test_missing_password(self):
        resp = self.client.post(self.url, _make_register_data(password1='', password2=''))
        self.assertEqual(resp.status_code, 200)
        self.assertFormError(resp, 'form', 'password1', 'Vui lòng nhập mật khẩu.')

    def test_missing_gender(self):
        resp = self.client.post(self.url, _make_register_data(gender=''))
        self.assertEqual(resp.status_code, 200)
        self.assertFormError(resp, 'form', 'gender', 'Vui lòng chọn giới tính.')

    def test_agree_terms_not_checked(self):
        data = _make_register_data()
        data.pop('agree_terms')
        resp = self.client.post(self.url, data)
        self.assertEqual(resp.status_code, 200)
        self.assertFormError(
            resp, 'form', 'agree_terms',
            'Bạn phải đồng ý với điều khoản dịch vụ để tiếp tục.'
        )

    # ------------------------------------------------------------------
    # Phone validation
    # ------------------------------------------------------------------

    def test_phone_invalid_format(self):
        resp = self.client.post(self.url, _make_register_data(phone='abc123'))
        self.assertEqual(resp.status_code, 200)
        self.assertFormError(resp, 'form', 'phone', 'Số điện thoại chỉ được chứa chữ số.')

    def test_phone_too_short(self):
        resp = self.client.post(self.url, _make_register_data(phone='091234'))
        self.assertEqual(resp.status_code, 200)
        self.assertFormError(resp, 'form', 'phone', 'Số điện thoại phải có 10-11 chữ số.')

    def test_phone_duplicate(self):
        # Tạo trước 1 profile với phone này
        CustomerProfile.objects.create(full_name='Cu', phone='0912345678')
        resp = self.client.post(self.url, _make_register_data())
        self.assertEqual(resp.status_code, 200)
        self.assertFormError(resp, 'form', 'phone', 'Số điện thoại này đã được đăng ký.')

    # ------------------------------------------------------------------
    # Username validation
    # ------------------------------------------------------------------

    def test_username_duplicate(self):
        User.objects.create_user(username='testkhach', password='x')
        resp = self.client.post(self.url, _make_register_data())
        self.assertEqual(resp.status_code, 200)
        self.assertFormError(resp, 'form', 'username', 'Tên đăng nhập này đã được sử dụng.')

    def test_username_with_space(self):
        resp = self.client.post(self.url, _make_register_data(username='ten co dau'))
        self.assertEqual(resp.status_code, 200)
        self.assertFormError(resp, 'form', 'username', 'Tên đăng nhập không được chứa khoảng trắng.')

    # ------------------------------------------------------------------
    # Password validation
    # ------------------------------------------------------------------

    def test_password_too_short(self):
        resp = self.client.post(self.url, _make_register_data(password1='abc', password2='abc'))
        self.assertEqual(resp.status_code, 200)
        self.assertFormError(resp, 'form', 'password1', 'Mật khẩu phải có ít nhất 6 ký tự.')

    def test_password_mismatch(self):
        resp = self.client.post(self.url, _make_register_data(password2='wrongpass'))
        self.assertEqual(resp.status_code, 200)
        self.assertFormError(resp, 'form', 'password2', 'Mật khẩu xác nhận không khớp.')

    # ------------------------------------------------------------------
    # Optional fields
    # ------------------------------------------------------------------

    def test_email_invalid_format(self):
        resp = self.client.post(self.url, _make_register_data(email='notanemail'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('email', resp.context['form'].errors)

    def test_dob_in_future(self):
        resp = self.client.post(self.url, _make_register_data(dob='2099-01-01'))
        self.assertEqual(resp.status_code, 200)
        self.assertFormError(
            resp, 'form', 'dob',
            'Ngày sinh không được lớn hơn ngày hiện tại.'
        )

    def test_register_without_optional_fields(self):
        """Đăng ký thành công khi bỏ trống email, dob, address."""
        resp = self.client.post(self.url, _make_register_data(email='', dob='', address=''))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(User.objects.filter(username='testkhach').exists())


class LogoutViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='logout_staff',
            password='LogoutPass@123',
            is_staff=True,
        )

    def test_logout_redirects_home_and_clears_auth_session(self):
        client = Client()
        self.assertTrue(client.login(username='logout_staff', password='LogoutPass@123'))

        response = client.get(reverse('accounts:logout'))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('pages:home'))
        self.assertNotIn(SESSION_KEY, client.session)
