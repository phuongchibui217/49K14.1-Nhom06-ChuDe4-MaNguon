from django.db import migrations, models


def copy_snapshot_to_booker(apps, schema_editor):
    """Backfill booker_* from customer_*_snapshot for existing records."""
    Appointment = apps.get_model('appointments', 'Appointment')
    Appointment.objects.filter(booker_name='').update(
        booker_name=models.F('customer_name_snapshot'),
        booker_phone=models.F('customer_phone_snapshot'),
    )
    # email may be null — use COALESCE via Python loop for safety
    for appt in Appointment.objects.filter(booker_email='').exclude(customer_email_snapshot=None):
        appt.booker_email = appt.customer_email_snapshot or ''
        appt.save(update_fields=['booker_email'])


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0003_add_service_variant'),
    ]

    operations = [
        migrations.AddField(
            model_name='appointment',
            name='booker_name',
            field=models.CharField(blank=True, default='', max_length=100, verbose_name='Tên người đặt'),
        ),
        migrations.AddField(
            model_name='appointment',
            name='booker_phone',
            field=models.CharField(blank=True, default='', max_length=15, verbose_name='SĐT người đặt'),
        ),
        migrations.AddField(
            model_name='appointment',
            name='booker_email',
            field=models.CharField(blank=True, default='', max_length=255, verbose_name='Email người đặt'),
        ),
        migrations.RunPython(copy_snapshot_to_booker, migrations.RunPython.noop),
    ]
