"""
Migration 0012:
- Thêm Appointment.booking_code (VARCHAR 30, nullable, indexed)
- Dùng để gom nhóm các appointment tạo cùng 1 lần đặt (1 booker, nhiều khách)
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0011_rename_notes_remove_checkin_checkout'),
    ]

    operations = [
        migrations.AddField(
            model_name='appointment',
            name='booking_code',
            field=models.CharField(
                max_length=30,
                blank=True,
                null=True,
                db_index=True,
                verbose_name='Mã nhóm đặt lịch',
            ),
        ),
        migrations.AddIndex(
            model_name='appointment',
            index=models.Index(fields=['booking_code'], name='appt_booking_code_idx'),
        ),
    ]
