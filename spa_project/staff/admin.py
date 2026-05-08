from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from .models import StaffProfile


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ('id', 'full_name', 'phone', 'gender', 'dob', 'created_at')
    search_fields = ('full_name', 'phone')
    list_filter = ('gender', 'created_at')


# Override UserAdmin để đảm bảo staff user luôn có StaffProfile
admin.site.unregister(User)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Nếu user vừa được set is_staff hoặc is_superuser → đảm bảo có StaffProfile
        if obj.is_staff or obj.is_superuser:
            from core.user_service import ensure_staff_profile
            ensure_staff_profile(obj)

