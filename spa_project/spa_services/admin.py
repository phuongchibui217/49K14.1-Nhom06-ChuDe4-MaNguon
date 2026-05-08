from django.contrib import admin
from .models import Service, ServiceVariant,ServiceCategory

class ServiceVariantInline(admin.TabularInline):
    model = ServiceVariant
    extra = 1
    fields = ['label', 'duration_minutes', 'price', 'sort_order']
    ordering = ['sort_order', 'duration_minutes']


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'status', 'created_at']
    list_filter = ['category', 'status', 'created_at']
    search_fields = ['name', 'description']
    list_editable = ['status']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [ServiceVariantInline]
    fieldsets = (
        ('Thông tin cơ bản', {
            'fields': ('name', 'category')
        }),
        ('Mô tả', {
            'fields': ('short_description', 'description', 'image')
        }),
        ('Trạng thái', {
            'fields': ('status',)
        }),
        ('Thời gian', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def save_model(self, request, obj, form, change):
        if not change:
            # Tạo mới: set cả created_by và updated_by
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    """Admin interface cho ServiceCategory"""
    list_display = ['code', 'name', 'status', 'sort_order', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['name', 'code', 'description']
    list_editable = ['status', 'sort_order']
    readonly_fields = ['created_at', 'updated_at', 'slug']
    ordering = ['sort_order', 'name']
    fieldsets = (
        ('Thông tin cơ bản', {
            'fields': ('code', 'name', 'slug')
        }),
        ('Mô tả', {
            'fields': ('description',)
        }),
        ('Cấu hình', {
            'fields': ('status', 'sort_order')
        }),
        ('Thời gian', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ServiceVariant)
class ServiceVariantAdmin(admin.ModelAdmin):
    list_display = ['service', 'label', 'duration_minutes', 'price', 'sort_order']
    list_filter = ['service']
    search_fields = ['service__name', 'label']
    list_editable = ['price', 'sort_order']
    ordering = ['service', 'sort_order', 'duration_minutes']
