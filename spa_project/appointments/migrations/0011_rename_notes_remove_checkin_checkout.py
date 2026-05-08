"""
Migration 0011:
- Rename Appointment.notes → Appointment.booker_notes (không mất dữ liệu)
- Remove Appointment.check_in_at (không có UI/API sử dụng)
- Remove Appointment.check_out_at (không có UI/API sử dụng)
- Remove constraint appointment_checkout_after_checkin
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0010_add_cancelled_by'),
    ]

    operations = [
        # 1. Rename notes → booker_notes (dữ liệu cũ được giữ nguyên)
        migrations.RenameField(
            model_name='appointment',
            old_name='notes',
            new_name='booker_notes',
        ),

        # 2. Cập nhật verbose_name cho field mới
        migrations.AlterField(
            model_name='appointment',
            name='booker_notes',
            field=models.CharField(
                max_length=1000,
                blank=True,
                null=True,
                verbose_name='Ghi chú lần đặt lịch',
            ),
        ),

        # 3. Xóa constraint check_in/check_out trước khi xóa field
        migrations.RemoveConstraint(
            model_name='appointment',
            name='appointment_checkout_after_checkin',
        ),

        # 4. Xóa check_in_at
        migrations.RemoveField(
            model_name='appointment',
            name='check_in_at',
        ),

        # 5. Xóa check_out_at
        migrations.RemoveField(
            model_name='appointment',
            name='check_out_at',
        ),
    ]
