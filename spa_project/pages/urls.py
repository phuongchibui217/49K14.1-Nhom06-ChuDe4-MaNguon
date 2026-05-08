"""
URL configuration cho pages app

Chứa URL patterns cho:
- Trang chủ (home)
- Giới thiệu (about)

Author: Spa ANA Team
"""

from django.urls import path
from . import views

app_name = 'pages'

urlpatterns = [
    # Trang chủ
    path('', views.home, name='index'),
    path('home/', views.home, name='home'),

    # Trang giới thiệu
    path('about/', views.about, name='about'),
]
