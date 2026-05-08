"""
Migration 0003:
- Thêm unique constraint cho CustomerProfile.email
- NULL được phép (nhiều profile chưa có email) — unique chỉ áp dụng cho non-null values
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0002_add_email'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customerprofile',
            name='email',
            field=models.CharField(
                max_length=255,
                blank=True,
                null=True,
                unique=True,
                verbose_name='Email',
            ),
        ),
    ]
