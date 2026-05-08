from django.urls import path
from . import views

app_name = 'customers'

urlpatterns = [
    path('manage/customers/', views.admin_customers, name='admin_customers'),
    path('tai-khoan/', views.customer_profile, name='customer_profile'),
]
