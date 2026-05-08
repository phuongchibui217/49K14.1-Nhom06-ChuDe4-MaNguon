from django.db import migrations


def update_categories(apps, schema_editor):
    ServiceCategory = apps.get_model('spa_services', 'ServiceCategory')

    # Xóa CAT03 và CAT04 (đã kiểm tra không có service nào dùng)
    ServiceCategory.objects.filter(code__in=['CAT03', 'CAT04']).delete()

    # Thêm 2 danh mục mới
    new_categories = [
        {
            'code': 'CAT05',
            'name': 'Gội đầu',
            'slug': 'goi-dau',
            'sort_order': 3,
            'status': 'ACTIVE',
        },
        {
            'code': 'CAT06',
            'name': 'Tẩy tế bào chết',
            'slug': 'tay-te-bao-chet',
            'sort_order': 4,
            'status': 'ACTIVE',
        },
    ]
    for cat in new_categories:
        ServiceCategory.objects.get_or_create(
            code=cat['code'],
            defaults=cat,
        )


def reverse_update(apps, schema_editor):
    ServiceCategory = apps.get_model('spa_services', 'ServiceCategory')

    # Xóa 2 danh mục mới
    ServiceCategory.objects.filter(code__in=['CAT05', 'CAT06']).delete()

    # Khôi phục CAT03 và CAT04
    ServiceCategory.objects.get_or_create(
        code='CAT03',
        defaults={'name': 'Phun thêu', 'sort_order': 3, 'status': 'ACTIVE'},
    )
    ServiceCategory.objects.get_or_create(
        code='CAT04',
        defaults={'name': 'Triệt lông', 'sort_order': 4, 'status': 'ACTIVE'},
    )


class Migration(migrations.Migration):

    dependencies = [
        ('spa_services', '0002_seed_service_categories'),
    ]

    operations = [
        migrations.RunPython(update_categories, reverse_update),
    ]
