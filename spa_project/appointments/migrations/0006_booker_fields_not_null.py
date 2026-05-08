from django.db import migrations, models


def backfill_booker_fields(apps, schema_editor):
    """
    Đảm bảo booker_name và booker_phone không rỗng trước khi set NOT NULL.
    Copy từ customer_*_snapshot nếu đang rỗng hoặc null.
    """
    Appointment = apps.get_model('appointments', 'Appointment')
    for appt in Appointment.objects.filter(
        models.Q(booker_name='') | models.Q(booker_name__isnull=True) |
        models.Q(booker_phone='') | models.Q(booker_phone__isnull=True)
    ):
        if not appt.booker_name:
            appt.booker_name = appt.customer_name_snapshot or 'Không rõ'
        if not appt.booker_phone:
            appt.booker_phone = appt.customer_phone_snapshot or ''
        appt.save(update_fields=['booker_name', 'booker_phone'])


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0005_nullable_customer_phone_snapshot'),
    ]

    operations = [
        # Bước 1: backfill dữ liệu cũ
        migrations.RunPython(backfill_booker_fields, migrations.RunPython.noop),

        # Bước 2: bỏ blank + default, set NOT NULL
        migrations.AlterField(
            model_name='appointment',
            name='booker_name',
            field=models.CharField(max_length=100, verbose_name='Tên người đặt'),
        ),
        migrations.AlterField(
            model_name='appointment',
            name='booker_phone',
            field=models.CharField(max_length=15, verbose_name='SĐT người đặt'),
        ),
    ]
