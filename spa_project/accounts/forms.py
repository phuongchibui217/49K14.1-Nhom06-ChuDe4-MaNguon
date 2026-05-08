from django import forms
from django.contrib.auth.forms import AuthenticationForm


class AdminLoginForm(AuthenticationForm):
    """Form đăng nhập Admin/Staff"""

    username = forms.CharField(
        label='Tên đăng nhập',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nhập tên đăng nhập',
            'autocapitalize': 'none',
            'autocomplete': 'username'
        })
    )
    password = forms.CharField(
        label='Mật khẩu',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nhập mật khẩu',
            'autocomplete': 'current-password'
        })
    )
    remember_me = forms.BooleanField(
        label='Ghi nhớ đăng nhập',
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    error_messages = {
        'invalid_login': 'Tên đăng nhập hoặc mật khẩu không chính xác.',
        'inactive': 'Tài khoản này đã bị vô hiệu hóa.',
    }
