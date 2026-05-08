from django import forms
from django.contrib.auth.models import User
from .models import CustomerProfile
import re


class CustomerProfileForm(forms.ModelForm):
    """Form cập nhật thông tin profile khách hàng (UC 9.2)"""

    # username nằm trên User — xử lý thủ công
    username = forms.CharField(
        label='Tên đăng nhập',
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Tên đăng nhập (không dấu, không khoảng trắng)',
            'autocomplete': 'username',
        })
    )

    class Meta:
        model = CustomerProfile
        fields = ['full_name', 'phone', 'email', 'gender', 'dob', 'address']
        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Họ và tên đầy đủ'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Số điện thoại',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Địa chỉ email (không bắt buộc)',
                'autocomplete': 'email',
            }),
            'gender': forms.Select(attrs={
                'class': 'form-select'
            }),
            'dob': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'address': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Địa chỉ của bạn'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Điền sẵn username từ User nếu có
        if self.instance and self.instance.user:
            self.fields['username'].initial = self.instance.user.username

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        if not username:
            raise forms.ValidationError('Vui lòng nhập tên đăng nhập.')
        if ' ' in username:
            raise forms.ValidationError('Tên đăng nhập không được chứa khoảng trắng.')
        if not username.isascii():
            raise forms.ValidationError('Tên đăng nhập chỉ được dùng ký tự không dấu.')
        # Loại trừ chính user hiện tại khi kiểm tra trùng
        qs = User.objects.filter(username=username)
        if self.instance and self.instance.user:
            qs = qs.exclude(pk=self.instance.user.pk)
        if qs.exists():
            raise forms.ValidationError('Tên đăng nhập này đã được sử dụng.')
        return username

    def clean_full_name(self):
        full_name = self.cleaned_data.get('full_name', '').strip()
        if not full_name:
            raise forms.ValidationError('Vui lòng nhập họ và tên.')
        if len(full_name) < 2:
            raise forms.ValidationError('Họ và tên phải có ít nhất 2 ký tự.')
        return full_name

    def clean_phone(self):
        phone = self.cleaned_data.get('phone', '').strip()
        if not phone:
            raise forms.ValidationError('Vui lòng nhập số điện thoại.')
        if not re.fullmatch(r'0\d{9}', phone):
            raise forms.ValidationError('Số điện thoại phải gồm 10 chữ số bắt đầu bằng 0.')
        if CustomerProfile.objects.filter(phone=phone).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Số điện thoại này đã được sử dụng.')
        return phone

    def clean_email(self):
        # Fix: Check None trước khi strip() để tránh AttributeError
        email_raw = self.cleaned_data.get('email')
        if email_raw:
            email = email_raw.strip().lower()
        else:
            email = None

        if email:
            qs = CustomerProfile.objects.filter(email=email)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError('Địa chỉ email này đã được sử dụng.')
        return email

    def clean_dob(self):
        dob = self.cleaned_data.get('dob')
        if dob:
            from django.utils import timezone
            if dob > timezone.now().date():
                raise forms.ValidationError('Ngày sinh không được lớn hơn ngày hiện tại.')
        return dob

    def save(self, commit=True):
        profile = super().save(commit=commit)
        # Đồng bộ thông tin từ CustomerProfile về User
        if commit and profile.user:
            user = profile.user
            user_fields_changed = []

            # Đồng bộ username
            username = self.cleaned_data.get('username', '').strip()
            if username and user.username != username:
                user.username = username
                user_fields_changed.append('username')

            # Đồng bộ họ tên → first_name / last_name
            full_name = self.cleaned_data.get('full_name', '').strip()
            if full_name:
                parts = full_name.split(None, 1)
                new_first = parts[0]
                new_last  = parts[1] if len(parts) > 1 else ''
                if user.first_name != new_first:
                    user.first_name = new_first
                    user_fields_changed.append('first_name')
                if user.last_name != new_last:
                    user.last_name = new_last
                    user_fields_changed.append('last_name')

            # Đồng bộ email
            email = self.cleaned_data.get('email') or ''
            if email and user.email != email:
                user.email = email
                user_fields_changed.append('email')

            if user_fields_changed:
                user.save(update_fields=user_fields_changed)

        return profile

class ChangePasswordForm(forms.Form):
    """Form đổi mật khẩu khách hàng"""

    current_password = forms.CharField(
        label='Mật khẩu hiện tại',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nhập mật khẩu hiện tại',
            'autocomplete': 'current-password'
        })
    )
    new_password = forms.CharField(
        label='Mật khẩu mới',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nhập mật khẩu mới',
            'autocomplete': 'new-password'
        })
    )
    confirm_password = forms.CharField(
        label='Xác nhận mật khẩu mới',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nhập lại mật khẩu mới',
            'autocomplete': 'new-password'
        })
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_current_password(self):
        current_password = self.cleaned_data.get('current_password')
        if not self.user.check_password(current_password):
            raise forms.ValidationError('Mật khẩu hiện tại không đúng.')
        return current_password

    def clean_new_password(self):
        new_password = self.cleaned_data.get('new_password')
        if not new_password:
            raise forms.ValidationError('Vui lòng nhập mật khẩu mới.')
        if len(new_password) < 6:
            raise forms.ValidationError('Mật khẩu mới phải có ít nhất 6 ký tự.')
        # Không cho đặt mật khẩu mới trùng mật khẩu cũ
        if self.user.check_password(new_password):
            raise forms.ValidationError('Mật khẩu mới không được trùng mật khẩu hiện tại.')
        return new_password

    def clean_confirm_password(self):
        new_password = self.cleaned_data.get('new_password')
        confirm_password = self.cleaned_data.get('confirm_password')
        if new_password and confirm_password and new_password != confirm_password:
            raise forms.ValidationError('Mật khẩu xác nhận không khớp.')
        return confirm_password

    def save(self):
        self.user.set_password(self.cleaned_data['new_password'])
        self.user.save()
        return self.user


class CustomerRegistrationForm(forms.ModelForm):
    """Form đăng ký khách hàng mới"""

    username = forms.CharField(
        label='Tên đăng nhập',
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Tên đăng nhập (không dấu, không khoảng trắng)',
            'autocomplete': 'username',
        })
    )
    email = forms.EmailField(
        label='Email',
        required=True,
        error_messages={'required': 'Vui lòng nhập địa chỉ Gmail.'},
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Địa chỉ Gmail (ví dụ: ten@gmail.com)',
            'autocomplete': 'email',
        })
    )
    password1 = forms.CharField(
        label='Mật khẩu',
        error_messages={'required': 'Vui lòng nhập mật khẩu.'},
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nhập mật khẩu (ít nhất 6 ký tự)',
        })
    )
    password2 = forms.CharField(
        label='Xác nhận mật khẩu',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nhập lại mật khẩu',
        })
    )
    agree_terms = forms.BooleanField(
        label='Đồng ý điều khoản',
        required=True,
        error_messages={'required': 'Bạn phải đồng ý với điều khoản dịch vụ để tiếp tục.'},
    )

    class Meta:
        model = CustomerProfile
        fields = ['full_name', 'phone', 'gender', 'dob', 'address']
        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Họ và tên đầy đủ',
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Số điện thoại (10-11 chữ số)',
            }),
            'gender': forms.Select(attrs={
                'class': 'form-select',
            }),
            'dob': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Địa chỉ của bạn',
            }),
        }
        error_messages = {
            'full_name': {'required': 'Vui lòng nhập họ và tên.'},
            'phone': {'required': 'Vui lòng nhập số điện thoại.'},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # gender bắt buộc theo use case dù DB cho null
        self.fields['gender'].required = True
        self.fields['gender'].error_messages = {'required': 'Vui lòng chọn giới tính.'}
        # dob optional nhưng validate nếu có nhập
        self.fields['dob'].required = False
        # address optional
        self.fields['address'].required = False

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if not email:
            raise forms.ValidationError('Vui lòng nhập địa chỉ Gmail.')
        if not email.endswith('@gmail.com'):
            raise forms.ValidationError('Vui lòng nhập địa chỉ Gmail hợp lệ (phải kết thúc bằng @gmail.com).')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('Địa chỉ Gmail này đã được sử dụng.')
        return email

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        if not username:
            raise forms.ValidationError('Vui lòng nhập tên đăng nhập.')
        if ' ' in username:
            raise forms.ValidationError('Tên đăng nhập không được chứa khoảng trắng.')
        if not username.isascii():
            raise forms.ValidationError('Tên đăng nhập chỉ được dùng ký tự không dấu.')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('Tên đăng nhập này đã được sử dụng.')
        return username

    def clean_full_name(self):
        full_name = self.cleaned_data.get('full_name', '').strip()
        if not full_name:
            raise forms.ValidationError('Vui lòng nhập họ và tên.')
        if len(full_name) < 2:
            raise forms.ValidationError('Họ và tên phải có ít nhất 2 ký tự.')
        return full_name

    def clean_phone(self):
        phone = self.cleaned_data.get('phone', '').strip()
        if not phone:
            raise forms.ValidationError('Vui lòng nhập số điện thoại.')
        digits = ''.join(filter(str.isdigit, phone))
        if not re.match(r'^0\d{9}$', digits):
            raise forms.ValidationError('Số điện thoại không hợp lệ (phải có 10 số và bắt đầu bằng 0).')
        if CustomerProfile.objects.filter(phone=digits).exists():
            raise forms.ValidationError('Số điện thoại này đã được đăng ký.')
        return digits

    def clean_gender(self):
        gender = self.cleaned_data.get('gender', '').strip()
        if not gender:
            raise forms.ValidationError('Vui lòng chọn giới tính.')
        return gender

    def clean_dob(self):
        dob = self.cleaned_data.get('dob')
        if dob:
            from django.utils import timezone
            if dob > timezone.now().date():
                raise forms.ValidationError('Ngày sinh không được lớn hơn ngày hiện tại.')
        return dob

    def clean_password1(self):
        password = self.cleaned_data.get('password1', '')
        if not password:
            raise forms.ValidationError('Vui lòng nhập mật khẩu.')
        if len(password) < 6:
            raise forms.ValidationError('Mật khẩu phải có ít nhất 6 ký tự.')
        return password

    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if not password2:
            raise forms.ValidationError('Vui lòng xác nhận mật khẩu.')
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError('Mật khẩu xác nhận không khớp.')
        return password2

    def save(self, commit=True):
        from core.user_service import create_customer_user
        profile = create_customer_user(
            username=self.cleaned_data['username'],
            password=self.cleaned_data['password1'],
            full_name=self.cleaned_data['full_name'],
            phone=self.cleaned_data['phone'],
            email=self.cleaned_data.get('email', '') or '',
            gender=self.cleaned_data.get('gender') or None,
            dob=self.cleaned_data.get('dob') or None,
            address=self.cleaned_data.get('address') or '',
        )
        return profile
