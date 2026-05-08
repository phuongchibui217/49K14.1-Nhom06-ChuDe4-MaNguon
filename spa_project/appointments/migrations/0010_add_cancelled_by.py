from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0009_add_rejected_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='appointment',
            name='cancelled_by',
            field=models.CharField(
                max_length=10,
                blank=True,
                null=True,
                choices=[('customer', 'Khách hủy'), ('admin', 'Admin hủy')],
                verbose_name='Người hủy',
            ),
        ),
    ]
