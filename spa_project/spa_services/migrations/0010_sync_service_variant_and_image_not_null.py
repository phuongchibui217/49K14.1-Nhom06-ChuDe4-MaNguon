from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('spa_services', '0009_remove_service_is_active'),
    ]

    operations = [
        # Xóa is_active khỏi ServiceVariant
        migrations.RemoveField(
            model_name='servicevariant',
            name='is_active',
        ),
        # Xóa created_at khỏi ServiceVariant
        migrations.RemoveField(
            model_name='servicevariant',
            name='created_at',
        ),
        # Đổi image thành NOT NULL (blank=False, null=False)
        migrations.AlterField(
            model_name='service',
            name='image',
            field=models.ImageField(default='', upload_to='services/', verbose_name='Hình ảnh dịch vụ'),
        ),
    ]
