from django.contrib import admin
from .models import CustomerProfile


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'phone', 'user', 'gender', 'created_at']
    list_filter = ['gender', 'created_at']
    search_fields = ['full_name', 'phone', 'user__username', 'user__email']
    readonly_fields = ['created_at', 'updated_at']
