"""
URL configuration for complaints app.

File này chứa các URL routes cho:
- Khách hàng tạo, xem danh sách, chi tiết, phản hồi khiếu nại
- Admin quản lý, phân công, phản hồi, đổi trạng thái, hoàn thành khiếu nại

Author: Spa ANA Team
"""

from django.urls import path
from . import views
from . import api

app_name = 'complaints'

urlpatterns = [
    # =====================================================
    # CUSTOMER COMPLAINT PAGES
    # =====================================================
    path('gui-khieu-nai/', views.customer_complaint_create, name='customer_complaint_create'),
    path('khieu-nai-cua-toi/', views.customer_complaint_list, name='customer_complaint_list'),
    path('khieu-nai-cua-toi/<int:complaint_id>/', views.customer_complaint_detail, name='customer_complaint_detail'),
    path('khieu-nai-cua-toi/<int:complaint_id>/reply/', views.customer_complaint_reply, name='customer_complaint_reply'),

    # =====================================================
    # ADMIN COMPLAINT MANAGEMENT
    # =====================================================
    path('manage/complaints/', views.admin_complaints, name='admin_complaints'),
    path('manage/complaints/<int:complaint_id>/', views.admin_complaint_detail, name='admin_complaint_detail'),
    path('manage/complaints/<int:complaint_id>/take/', views.admin_complaint_take, name='admin_complaint_take'),
    path('manage/complaints/<int:complaint_id>/assign/', views.admin_complaint_assign, name='admin_complaint_assign'),
    path('manage/complaints/<int:complaint_id>/reply/', views.admin_complaint_reply, name='admin_complaint_reply'),
    path('manage/complaints/<int:complaint_id>/status/', views.admin_complaint_status, name='admin_complaint_status'),
    path('manage/complaints/<int:complaint_id>/complete/', views.admin_complaint_complete, name='admin_complaint_complete'),

    # =====================================================
    # REST API ENDPOINTS (api.py) - Trả về JSON
    # =====================================================
    path('api/complaints/', api.api_complaints_list, name='api_complaints_list'),
    path('api/complaints/stats/', api.api_complaints_stats, name='api_complaints_stats'),
    path('api/complaints/new-count/', api.api_complaints_new_count, name='api_complaints_new_count'),
    path('api/complaints/create/', api.api_complaint_create, name='api_complaint_create'),
    path('api/complaints/<int:complaint_id>/', api.api_complaint_detail, name='api_complaint_detail'),
    path('api/complaints/<int:complaint_id>/reply/', api.api_complaint_reply, name='api_complaint_reply'),
    path('api/complaints/<int:complaint_id>/status/', api.api_complaint_status, name='api_complaint_status'),
    path('api/complaints/<int:complaint_id>/assign/', api.api_complaint_assign, name='api_complaint_assign'),
    path('api/complaints/<int:complaint_id>/take/', api.api_complaint_take, name='api_complaint_take'),
    path('api/complaints/<int:complaint_id>/complete/', api.api_complaint_complete, name='api_complaint_complete'),
]
