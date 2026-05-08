"""
Migration 0015: Refactor Booking + Appointment

Thực hiện:
1. Tạo bảng bookings (model Booking)
2. Migrate dữ liệu từ Appointment cũ → Booking mới
   - Gom các Appointment cùng booking_code vào 1 Booking
   - Appointment chưa có booking_code → tạo Booking riêng
3. Thêm cột booking_id vào appointments, gán FK
4. Xóa các cột booker_name, booker_phone, booker_email, booker_notes,
   payment_status, source, booking_code (cũ) khỏi appointments
5. Tạo bảng invoice_items
6. Sửa invoices: thêm booking_id, migrate từ appointment.booking_id,
   xóa appointment_id
7. Tạo constraint mới cho appointment.status (chỉ còn 4 giá trị)

KHÔNG xóa dữ liệu cũ — chỉ migrate.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


# ── DATA MIGRATION FUNCTIONS ──────────────────────────────────────────────────
# Phải định nghĩa TRƯỚC class Migration để RunPython có thể tham chiếu.

def _generate_booking_code_for_migration(Booking):
    """Tạo booking_code unique trong quá trình migration."""
    import time
    prefix = 'BK'
    last = Booking.objects.filter(booking_code__startswith=prefix).order_by('-booking_code').first()
    if last and last.booking_code:
        try:
            num = int(last.booking_code[len(prefix):]) + 1
        except (ValueError, IndexError):
            num = 1
    else:
        num = 1

    for _ in range(1000):
        code = f'{prefix}{num:04d}'
        if not Booking.objects.filter(booking_code=code).exists():
            return code
        num += 1

    return f'{prefix}{int(time.time()) % 10000:04d}'


def migrate_appointments_to_bookings(apps, schema_editor):
    """
    Tạo Booking từ dữ liệu Appointment cũ.

    Logic:
    - Gom các Appointment cùng booking_code vào 1 Booking
    - Appointment chưa có booking_code → tạo Booking riêng
    - Copy: booker_name, booker_phone, booker_email, booker_notes,
            payment_status, source, created_by, created_at
    - Map status:
        PENDING                       → Booking.PENDING
        NOT_ARRIVED/ARRIVED/COMPLETED → Booking.CONFIRMED
        CANCELLED/CUSTOMER_CANCELLED  → Booking.CANCELLED
        REJECTED                      → Booking.REJECTED
    """
    Appointment = apps.get_model('appointments', 'Appointment')
    Booking     = apps.get_model('appointments', 'Booking')

    STATUS_MAP = {
        'PENDING':            'PENDING',
        'NOT_ARRIVED':        'CONFIRMED',
        'ARRIVED':            'CONFIRMED',
        'COMPLETED':          'CONFIRMED',
        'CANCELLED':          'CANCELLED',
        'CUSTOMER_CANCELLED': 'CANCELLED',
        'REJECTED':           'REJECTED',
    }

    booking_code_map = {}  # booking_code_str → Booking instance

    for appt in Appointment.objects.all().order_by('created_at'):
        bc = (appt.booking_code or '').strip()

        if bc and bc in booking_code_map:
            appt.booking = booking_code_map[bc]
            appt.save(update_fields=['booking'])
            continue

        booking_status = STATUS_MAP.get(appt.status or '', 'PENDING')
        payment_status = appt.payment_status or 'UNPAID'
        source         = appt.source or 'DIRECT'

        valid_payment = {'UNPAID', 'PARTIAL', 'PAID', 'REFUNDED'}
        valid_source  = {'DIRECT', 'ONLINE', 'PHONE', 'FACEBOOK', 'ZALO'}
        if payment_status not in valid_payment:
            payment_status = 'UNPAID'
        if source not in valid_source:
            source = 'DIRECT'

        new_booking_code = bc if bc else _generate_booking_code_for_migration(Booking)

        booking = Booking(
            booking_code=new_booking_code,
            booker_name=appt.booker_name or appt.customer_name_snapshot or 'Khach',
            booker_phone=appt.booker_phone or appt.customer_phone_snapshot or '0000000000',
            booker_email=appt.booker_email or None,
            booker_notes=appt.booker_notes or None,
            status=booking_status,
            payment_status=payment_status,
            source=source,
            staff_notes=None,
            created_by=appt.created_by,
            deleted_at=appt.deleted_at,
        )
        booking.save()

        # Override created_at sau khi save (auto_now_add không cho phép override)
        Booking.objects.filter(pk=booking.pk).update(created_at=appt.created_at)

        if bc:
            booking_code_map[bc] = booking

        appt.booking = booking
        appt.save(update_fields=['booking'])


def migrate_invoice_booking(apps, schema_editor):
    """
    Migrate invoice.booking từ invoice.appointment.booking.
    Nếu 1 booking đã có invoice (nhiều appointment cùng booking),
    chỉ giữ invoice đầu tiên, xóa các invoice trùng.
    """
    Invoice = apps.get_model('appointments', 'Invoice')

    seen_bookings = set()

    for invoice in Invoice.objects.select_related('appointment__booking').order_by('id'):
        appt = invoice.appointment
        if not appt:
            invoice.delete()
            continue

        booking = appt.booking
        if not booking:
            invoice.delete()
            continue

        if booking.pk in seen_bookings:
            invoice.delete()
            continue

        invoice.booking = booking
        invoice.save(update_fields=['booking'])
        seen_bookings.add(booking.pk)


def migrate_appointment_statuses(apps, schema_editor):
    """
    Chuyển đổi appointment.status cũ sang giá trị mới hợp lệ.
    Phải chạy SAU khi đã xóa constraint cũ, TRƯỚC khi thêm constraint mới.

    PENDING            → NOT_ARRIVED  (Booking đã lưu PENDING)
    CUSTOMER_CANCELLED → CANCELLED
    REJECTED           → CANCELLED    (Booking đã lưu REJECTED)
    """
    Appointment = apps.get_model('appointments', 'Appointment')

    STATUS_MAP = {
        'PENDING':            'NOT_ARRIVED',
        'CUSTOMER_CANCELLED': 'CANCELLED',
        'REJECTED':           'CANCELLED',
    }

    for old_status, new_status in STATUS_MAP.items():
        Appointment.objects.filter(status=old_status).update(status=new_status)


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0014_customer_nullable'),
        ('customers', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── BƯỚC 1: Tạo bảng bookings ────────────────────────────────────────
        migrations.CreateModel(
            name='Booking',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('booking_code', models.CharField(db_index=True, max_length=30, unique=True, verbose_name='Mã đặt lịch')),
                ('booker_name', models.CharField(max_length=100, verbose_name='Tên người đặt')),
                ('booker_phone', models.CharField(max_length=15, verbose_name='SĐT người đặt')),
                ('booker_email', models.CharField(blank=True, max_length=255, null=True, verbose_name='Email người đặt')),
                ('booker_notes', models.CharField(blank=True, max_length=1000, null=True, verbose_name='Ghi chú lần đặt lịch')),
                ('status', models.CharField(
                    choices=[('PENDING', 'Chờ xác nhận'), ('CONFIRMED', 'Đã xác nhận'), ('CANCELLED', 'Đã hủy'), ('REJECTED', 'Đã từ chối')],
                    db_index=True, default='PENDING', max_length=20, verbose_name='Trạng thái'
                )),
                ('payment_status', models.CharField(
                    choices=[('UNPAID', 'Chưa thanh toán'), ('PARTIAL', 'Thanh toán một phần'), ('PAID', 'Đã thanh toán'), ('REFUNDED', 'Đã hoàn tiền')],
                    default='UNPAID', max_length=20, verbose_name='Trạng thái thanh toán'
                )),
                ('source', models.CharField(
                    choices=[('DIRECT', 'Trực tiếp'), ('ONLINE', 'Đặt online'), ('PHONE', 'Điện thoại'), ('FACEBOOK', 'Facebook'), ('ZALO', 'Zalo')],
                    default='DIRECT', max_length=20, verbose_name='Nguồn đặt lịch'
                )),
                ('staff_notes', models.CharField(blank=True, max_length=1000, null=True, verbose_name='Ghi chú nội bộ')),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='bookings_created',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Người tạo'
                )),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Thời điểm tạo')),
                ('updated_at', models.DateTimeField(auto_now=True, blank=True, null=True, verbose_name='Thời điểm cập nhật')),
                ('deleted_at', models.DateTimeField(blank=True, null=True, verbose_name='Thời điểm xóa')),
                ('deleted_by_user', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='bookings_deleted',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Người xóa'
                )),
                ('cancelled_at', models.DateTimeField(blank=True, null=True, verbose_name='Thời điểm hủy')),
            ],
            options={
                'verbose_name': 'Đặt lịch',
                'verbose_name_plural': 'Đặt lịch',
                'db_table': 'bookings',
                'ordering': ['-created_at'],
            },
        ),

        # ── BƯỚC 2: Thêm indexes cho Booking ─────────────────────────────────
        migrations.AddIndex(
            model_name='booking',
            index=models.Index(fields=['booking_code'], name='booking_code_idx'),
        ),
        migrations.AddIndex(
            model_name='booking',
            index=models.Index(fields=['status', 'source'], name='booking_status_source_idx'),
        ),
        migrations.AddIndex(
            model_name='booking',
            index=models.Index(fields=['created_at'], name='booking_created_at_idx'),
        ),

        # ── BƯỚC 3: Thêm constraints cho Booking ─────────────────────────────
        migrations.AddConstraint(
            model_name='booking',
            constraint=models.CheckConstraint(
                check=models.Q(status__in=['PENDING', 'CONFIRMED', 'CANCELLED', 'REJECTED']),
                name='booking_status_valid'
            ),
        ),
        migrations.AddConstraint(
            model_name='booking',
            constraint=models.CheckConstraint(
                check=models.Q(payment_status__in=['UNPAID', 'PARTIAL', 'PAID', 'REFUNDED']),
                name='booking_payment_status_valid'
            ),
        ),
        migrations.AddConstraint(
            model_name='booking',
            constraint=models.CheckConstraint(
                check=models.Q(source__in=['DIRECT', 'ONLINE', 'PHONE', 'FACEBOOK', 'ZALO']),
                name='booking_source_valid'
            ),
        ),

        # ── BƯỚC 4: Thêm cột booking_id (nullable) vào appointments ──────────
        migrations.AddField(
            model_name='appointment',
            name='booking',
            field=models.ForeignKey(
                null=True, blank=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='appointments',
                to='appointments.booking',
                verbose_name='Đặt lịch'
            ),
        ),

        # ── BƯỚC 5: Migrate dữ liệu — tạo Booking từ Appointment cũ ─────────
        migrations.RunPython(
            code=migrate_appointments_to_bookings,
            reverse_code=migrations.RunPython.noop,
        ),

        # ── BƯỚC 6: Đổi booking FK thành NOT NULL ────────────────────────────
        migrations.AlterField(
            model_name='appointment',
            name='booking',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='appointments',
                to='appointments.booking',
                verbose_name='Đặt lịch'
            ),
        ),

        # ── BƯỚC 7: Xóa index cũ booking_code trên appointments ──────────────
        migrations.RemoveIndex(
            model_name='appointment',
            name='appt_booking_code_idx',
        ),

        # ── BƯỚC 8: Xóa index cũ source_status trên appointments ─────────────
        migrations.RemoveIndex(
            model_name='appointment',
            name='appt_source_status_idx',
        ),

        # ── BƯỚC 9: Xóa constraint status cũ (có PENDING, CUSTOMER_CANCELLED, REJECTED) ──
        migrations.RemoveConstraint(
            model_name='appointment',
            name='appointment_status_valid',
        ),
        migrations.RemoveConstraint(
            model_name='appointment',
            name='appointment_payment_status_valid',
        ),
        migrations.RemoveConstraint(
            model_name='appointment',
            name='appointment_source_valid',
        ),

        # ── BƯỚC 9b: Migrate appointment.status cũ → giá trị mới ─────────────
        # PENDING → NOT_ARRIVED (đã được xác nhận khi tạo Booking)
        # CUSTOMER_CANCELLED → CANCELLED
        # REJECTED → CANCELLED (Booking đã lưu REJECTED)
        migrations.RunPython(
            code=migrate_appointment_statuses,
            reverse_code=migrations.RunPython.noop,
        ),

        # ── BƯỚC 10: Xóa các cột booker/payment/source khỏi appointments ─────
        migrations.RemoveField(model_name='appointment', name='booker_name'),
        migrations.RemoveField(model_name='appointment', name='booker_phone'),
        migrations.RemoveField(model_name='appointment', name='booker_email'),
        migrations.RemoveField(model_name='appointment', name='booker_notes'),
        migrations.RemoveField(model_name='appointment', name='payment_status'),
        migrations.RemoveField(model_name='appointment', name='source'),
        migrations.RemoveField(model_name='appointment', name='booking_code'),
        migrations.RemoveField(model_name='appointment', name='created_by'),

        # ── BƯỚC 11: Thêm index mới cho appointments ─────────────────────────
        migrations.AddIndex(
            model_name='appointment',
            index=models.Index(fields=['booking'], name='appt_booking_idx'),
        ),

        # ── BƯỚC 12: Thêm constraint status mới cho appointments ─────────────
        migrations.AddConstraint(
            model_name='appointment',
            constraint=models.CheckConstraint(
                check=models.Q(status__in=['NOT_ARRIVED', 'ARRIVED', 'COMPLETED', 'CANCELLED']),
                name='appointment_status_valid'
            ),
        ),

        # ── BƯỚC 13: Sửa room thành nullable ─────────────────────────────────
        migrations.AlterField(
            model_name='appointment',
            name='room',
            field=models.ForeignKey(
                to='appointments.room',
                null=True, blank=True,
                on_delete=django.db.models.deletion.PROTECT,
                verbose_name='Phòng'
            ),
        ),

        # ── BƯỚC 14: Tạo bảng invoice_items ──────────────────────────────────
        migrations.CreateModel(
            name='InvoiceItem',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('invoice', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='items',
                    to='appointments.invoice',
                    verbose_name='Hóa đơn'
                )),
                ('appointment', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='invoice_items',
                    to='appointments.appointment',
                    verbose_name='Lịch hẹn'
                )),
                ('service_variant', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='invoice_items',
                    to='spa_services.servicevariant',
                    verbose_name='Gói dịch vụ'
                )),
                ('description', models.CharField(blank=True, max_length=500, verbose_name='Mô tả')),
                ('quantity', models.PositiveIntegerField(default=1, verbose_name='Số lượng')),
                ('unit_price', models.DecimalField(decimal_places=2, default=0, max_digits=18, verbose_name='Đơn giá')),
                ('line_total', models.DecimalField(decimal_places=2, default=0, max_digits=18, verbose_name='Thành tiền dòng')),
            ],
            options={
                'verbose_name': 'Chi tiết hóa đơn',
                'verbose_name_plural': 'Chi tiết hóa đơn',
                'db_table': 'invoice_items',
                'ordering': ['id'],
            },
        ),
        migrations.AddConstraint(
            model_name='invoiceitem',
            constraint=models.CheckConstraint(
                check=models.Q(quantity__gt=0),
                name='invoice_item_quantity_positive'
            ),
        ),
        migrations.AddConstraint(
            model_name='invoiceitem',
            constraint=models.CheckConstraint(
                check=models.Q(unit_price__gte=0),
                name='invoice_item_unit_price_non_negative'
            ),
        ),
        migrations.AddConstraint(
            model_name='invoiceitem',
            constraint=models.CheckConstraint(
                check=models.Q(line_total__gte=0),
                name='invoice_item_line_total_non_negative'
            ),
        ),

        # ── BƯỚC 15: Thêm booking_id vào invoices (nullable trước) ───────────
        migrations.AddField(
            model_name='invoice',
            name='booking',
            field=models.OneToOneField(
                null=True, blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='invoice',
                to='appointments.booking',
                verbose_name='Đặt lịch'
            ),
        ),

        # ── BƯỚC 16: Migrate invoice.booking từ invoice.appointment.booking ───
        migrations.RunPython(
            code=migrate_invoice_booking,
            reverse_code=migrations.RunPython.noop,
        ),

        # ── BƯỚC 17: Đổi invoice.booking thành NOT NULL ───────────────────────
        migrations.AlterField(
            model_name='invoice',
            name='booking',
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='invoice',
                to='appointments.booking',
                verbose_name='Đặt lịch'
            ),
        ),

        # ── BƯỚC 18: Xóa invoice.appointment ─────────────────────────────────
        migrations.RemoveField(model_name='invoice', name='appointment'),
    ]


