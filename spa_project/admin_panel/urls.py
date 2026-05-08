"""
URL configuration for admin_panel app.

Admin authentication và profile pages.

NOTE: Admin login đã được gộp vào accounts:login
Route admin_login đã bị xóa để chuyển sang login chung.
"""

from django.urls import path
from django.shortcuts import redirect
from . import views

app_name = 'admin_panel'

urlpatterns = [
    # Admin Authentication
    path('login/', lambda request: redirect('accounts:login'), name='admin_login_redirect'),  # Redirect về login chung
    path('logout/', views.admin_logout, name='admin_logout'),

    # Admin Profile
    path('profile/', views.admin_profile, name='admin_profile'),
]
