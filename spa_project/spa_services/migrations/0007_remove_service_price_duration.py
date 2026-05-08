from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('spa_services', '0006_add_service_variant'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='service',
            name='service_price_non_negative',
        ),
        migrations.RemoveConstraint(
            model_name='service',
            name='service_duration_positive',
        ),
        migrations.RemoveField(
            model_name='service',
            name='price',
        ),
        migrations.RemoveField(
            model_name='service',
            name='duration_minutes',
        ),
    ]
