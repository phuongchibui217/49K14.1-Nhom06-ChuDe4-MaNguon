from django.db import migrations


def seed_categories(apps, schema_editor):
    ServiceCategory = apps.get_model('spa_services', 'ServiceCategory')
    categories = [
        {'code': 'CAT01', 'name': 'Chăm sóc da', 'sort_order': 1},
        {'code': 'CAT02', 'name': 'Massage',      'sort_order': 2},
        {'code': 'CAT03', 'name': 'Phun thêu',    'sort_order': 3},
        {'code': 'CAT04', 'name': 'Triệt lông',   'sort_order': 4},
    ]
    for cat in categories:
        ServiceCategory.objects.get_or_create(
            code=cat['code'],
            defaults={
                'name': cat['name'],
                'sort_order': cat['sort_order'],
                'status': 'ACTIVE',
            }
        )


def reverse_seed(apps, schema_editor):
    ServiceCategory = apps.get_model('spa_services', 'ServiceCategory')
    ServiceCategory.objects.filter(
        code__in=['CAT01', 'CAT02', 'CAT03', 'CAT04']
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('spa_services', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_categories, reverse_seed),
    ]
