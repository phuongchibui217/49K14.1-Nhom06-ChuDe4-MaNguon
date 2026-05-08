from django.db import migrations


# Map mã cũ → mã mới
CATEGORY_CODE_MAP = {
    'CAT01': 'CSD',
    'CAT02': 'MS',
    'CAT05': 'GD',
    'CAT06': 'TDC',
}

# Dịch vụ mẫu theo nghiệp vụ spa
# (category_code_new, service_code, service_name)
SERVICES_SEED = [
    ('CSD', 'CSDCB', 'Chăm sóc da cơ bản'),
    ('CSD', 'CSDCS', 'Chăm sóc da chuyên sâu'),
    ('CSD', 'DTDM',  'Dưỡng trắng da mặt'),
    ('MS',  'MSBODY','Massage body'),
    ('MS',  'MSDN',  'Massage đá nóng'),
    ('MS',  'MSVG',  'Massage vai gáy'),
    ('GD',  'GDDS',  'Gội đầu dưỡng sinh'),
    ('GD',  'GDTM',  'Gội đầu thảo mộc'),
    ('TDC', 'TDCTT', 'Tẩy tế bào chết toàn thân'),
    ('TDC', 'TDCDM', 'Tẩy tế bào chết da mặt'),
]


def update_codes(apps, schema_editor):
    ServiceCategory = apps.get_model('spa_services', 'ServiceCategory')
    Service = apps.get_model('spa_services', 'Service')
    User = apps.get_model('auth', 'User')

    # 1. Đổi mã danh mục — dùng temp code trước để tránh unique conflict
    for old_code, new_code in CATEGORY_CODE_MAP.items():
        ServiceCategory.objects.filter(code=old_code).update(code=f'_tmp_{new_code}')
    for old_code, new_code in CATEGORY_CODE_MAP.items():
        ServiceCategory.objects.filter(code=f'_tmp_{new_code}').update(code=new_code)

    # 2. Đổi mã dịch vụ hiện có (DV0001 → DTDM vì tên là "Dưỡng trắng")
    svc = Service.objects.filter(code='DV0001').first()
    if svc:
        svc.code = 'DTDM'
        svc.name = 'Dưỡng trắng da mặt'
        svc.save()

    # 3. Tạo dịch vụ mẫu còn thiếu
    # Lấy superuser đầu tiên làm created_by (bắt buộc NOT NULL)
    admin_user = User.objects.filter(is_superuser=True).first() \
              or User.objects.filter(is_staff=True).first() \
              or User.objects.first()

    if not admin_user:
        return  # không có user nào thì bỏ qua seed

    for cat_code, svc_code, svc_name in SERVICES_SEED:
        if Service.objects.filter(code=svc_code).exists():
            continue
        cat = ServiceCategory.objects.filter(code=cat_code).first()
        if not cat:
            continue
        Service.objects.create(
            code=svc_code,
            name=svc_name,
            category=cat,
            price=200000,
            duration_minutes=60,
            status='ACTIVE',
            is_active=True,
            image='',
            created_by=admin_user,
        )


def reverse_codes(apps, schema_editor):
    ServiceCategory = apps.get_model('spa_services', 'ServiceCategory')
    Service = apps.get_model('spa_services', 'Service')

    # Đổi lại mã danh mục
    reverse_map = {v: k for k, v in CATEGORY_CODE_MAP.items()}
    for new_code, old_code in reverse_map.items():
        ServiceCategory.objects.filter(code=new_code).update(code=f'_tmp_{old_code}')
    for new_code, old_code in reverse_map.items():
        ServiceCategory.objects.filter(code=f'_tmp_{old_code}').update(code=old_code)

    # Xóa dịch vụ seed (trừ DTDM đã tồn tại trước)
    seed_codes = [s[1] for s in SERVICES_SEED if s[1] != 'DTDM']
    Service.objects.filter(code__in=seed_codes).delete()

    # Đổi lại DTDM → DV0001
    Service.objects.filter(code='DTDM').update(code='DV0001', name='Dưỡng trắng')


class Migration(migrations.Migration):

    dependencies = [
        ('spa_services', '0004_shrink_code_fields'),
    ]

    operations = [
        migrations.RunPython(update_codes, reverse_codes),
    ]
