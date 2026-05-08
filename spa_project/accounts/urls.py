from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from . import api

app_name = 'accounts'

urlpatterns = [
    # ── HTML views ────────────────────────────────────────────────────
    path('login/', views.login_view, name='login'),
    path('register/', views.register, name='register'),
    path('logout/', views.logout_view, name='logout'),

    # Password reset — dùng Django built-in views
    # email_template_name: plain-text fallback cho email client cũ
    # html_email_template_name: HTML email gửi qua SendGrid (hiển thị đẹp)
    path('quen-mat-khau/', auth_views.PasswordResetView.as_view(
        template_name='accounts/password_reset.html',
        email_template_name='accounts/password_reset_email.txt',
        html_email_template_name='accounts/password_reset_email.html',
        success_url='/quen-mat-khau/da-gui/',
    ), name='password_reset'),

    path('quen-mat-khau/da-gui/', auth_views.PasswordResetDoneView.as_view(
        template_name='accounts/password_reset_sent.html',
    ), name='password_reset_done'),

    path('reset-mat-khau/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='accounts/password_reset_confirm.html',
        success_url='/reset-mat-khau/hoan-tat/',
    ), name='password_reset_confirm'),

    path('reset-mat-khau/hoan-tat/', auth_views.PasswordResetCompleteView.as_view(
        template_name='accounts/password_reset_complete.html',
    ), name='password_reset_complete'),

    # ── JSON API ──────────────────────────────────────────────────────
    path('api/auth/login/', api.api_login, name='api_login'),
    path('api/auth/register/', api.api_register, name='api_register'),
    path('api/auth/logout/', api.api_logout, name='api_logout'),
    path('api/auth/me/', api.api_me, name='api_me'),
]
