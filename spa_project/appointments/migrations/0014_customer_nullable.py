"""
Migration 0014:
- Appointment.customer: NOT NULL + CASCADE → NULL + SET_NULL
- Cho phép tạo lịch cho khách đặt dùm mà không cần CustomerProfile
- Thông tin khách vẫn được lưu qua snapshot fields (name/phone/email)
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0013_add_customer_cancelled_remove_cancelled_by'),
        ('customers', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='appointment',
            name='customer',
            field=models.ForeignKey(
                to='customers.CustomerProfile',
                on_delete=django.db.models.deletion.SET_NULL,
                null=True,
                blank=True,
                related_name='appointments',
                verbose_name='Khách hàng',
            ),
        ),
    ]
