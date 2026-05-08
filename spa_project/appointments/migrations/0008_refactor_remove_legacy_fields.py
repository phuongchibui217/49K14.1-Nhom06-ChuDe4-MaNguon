"""
Migration 0008: Refactor Appointment theo đặc tả chốt

Thay đổi:
- appointment_code: max_length 10 → 30
- Xóa field: service, end_time, duration_minutes, guests
- room: nullable → NOT NULL (PROTECT)
- booker_email: default='' → null=True, blank=True
- Data migration:
  * booker_email rỗng → NULL
  * room NULL → gán phòng đầu tiên (nếu có)
  * Xóa constraints cũ liên quan đến guests/duration/end_time
"""

from django.db import migrations, models
import django.db.models.deletion


def backfill_before_schema(apps, schema_editor):
    """
    Chuẩn bị dữ liệu trước khi đổi schema:
    1. room NULL → gán phòng đầu tiên còn hoạt động
    (booker_email rỗng → NULL sẽ xử lý sau khi đổi schema)
    """
    Appointment = apps.get_model('appointments', 'Appointment')
    Room = apps.get_model('appointments', 'Room')

    # room NULL → gán phòng đầu tiên
    first_room = Room.objects.filter(is_active=True).order_by('code').first()
    if first_room:
        Appointment.objects.filter(room__isnull=True).update(room=first_room)
    else:
        from django.utils import timezone
        Appointment.objects.filter(room__isnull=True).update(deleted_at=timezone.now())


def backfill_booker_email(apps, schema_editor):
    """Sau khi đổi booker_email → nullable, chuyển chuỗi rỗng thành NULL."""
    Appointment = apps.get_model('appointments', 'Appointment')
    Appointment.objects.filter(booker_email='').update(booker_email=None)


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0007_service_room_nullable'),
        ('spa_services', '0010_sync_service_variant_and_image_not_null'),
    ]

    operations = [
        # ── Bước 1: Data migration trước khi đổi schema ──────────────────────
        migrations.RunPython(backfill_before_schema, migrations.RunPython.noop),

        # ── Bước 2: Xóa constraints cũ liên quan đến fields sẽ bị xóa ────────
        migrations.RemoveConstraint(
            model_name='appointment',
            name='appointment_guests_positive',
        ),
        migrations.RemoveConstraint(
            model_name='appointment',
            name='appointment_duration_positive',
        ),
        migrations.RemoveConstraint(
            model_name='appointment',
            name='appointment_end_time_after_start',
        ),

        # ── Bước 3: Sửa appointment_code max_length ───────────────────────────
        migrations.AlterField(
            model_name='appointment',
            name='appointment_code',
            field=models.CharField(blank=True, max_length=30, unique=True, verbose_name='Mã lịch hẹn'),
        ),

        # ── Bước 4: Sửa booker_email → nullable ──────────────────────────────
        migrations.AlterField(
            model_name='appointment',
            name='booker_email',
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name='Email người đặt'),
        ),

        # ── Bước 4b: Backfill booker_email rỗng → NULL ───────────────────────
        migrations.RunPython(backfill_booker_email, migrations.RunPython.noop),

        # ── Bước 5: Sửa room → NOT NULL + PROTECT ────────────────────────────
        migrations.AlterField(
            model_name='appointment',
            name='room',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                to='appointments.room',
                verbose_name='Phòng',
            ),
        ),

        # ── Bước 6: Xóa field service (chỉ giữ service_variant) ──────────────
        migrations.RemoveField(
            model_name='appointment',
            name='service',
        ),

        # ── Bước 7: Xóa field end_time ────────────────────────────────────────
        migrations.RemoveField(
            model_name='appointment',
            name='end_time',
        ),

        # ── Bước 8: Xóa field duration_minutes ───────────────────────────────
        migrations.RemoveField(
            model_name='appointment',
            name='duration_minutes',
        ),

        # ── Bước 9: Xóa field guests ─────────────────────────────────────────
        migrations.RemoveField(
            model_name='appointment',
            name='guests',
        ),
    ]
