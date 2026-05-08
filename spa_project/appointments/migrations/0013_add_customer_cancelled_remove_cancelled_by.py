"""
Migration 0013:
- Migrate data: status='CANCELLED' + cancelled_by='customer' → status='CUSTOMER_CANCELLED'
- Cập nhật CheckConstraint để cho phép status='CUSTOMER_CANCELLED'
- Xóa field cancelled_by (không cần nữa)

Logic nghiệp vụ sau migration:
  PENDING            → Chờ xác nhận (Tab 2)
  CUSTOMER_CANCELLED → Khách đã hủy  (Tab 2 — khách tự hủy trước khi xác nhận)
  REJECTED           → Đã từ chối    (Tab 2 — nhân viên từ chối)
  NOT_ARRIVED/ARRIVED/COMPLETED/CANCELLED → Tab 1 (lịch đã xác nhận)
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0012_add_booking_code'),
    ]

    operations = [
        # 1. Xóa constraint cũ (chỉ cho phép CANCELLED, chưa có CUSTOMER_CANCELLED)
        migrations.RemoveConstraint(
            model_name='appointment',
            name='appointment_status_valid',
        ),

        # 2. Thêm constraint mới cho phép cả CUSTOMER_CANCELLED
        migrations.AddConstraint(
            model_name='appointment',
            constraint=models.CheckConstraint(
                check=models.Q(status__in=[
                    'PENDING', 'NOT_ARRIVED', 'ARRIVED', 'COMPLETED',
                    'CANCELLED', 'CUSTOMER_CANCELLED', 'REJECTED',
                ]),
                name='appointment_status_valid',
            ),
        ),

        # 3. Migrate data: CANCELLED + cancelled_by='customer' → CUSTOMER_CANCELLED
        migrations.RunSQL(
            sql="""
                UPDATE appointments
                SET status = 'CUSTOMER_CANCELLED'
                WHERE status = 'CANCELLED'
                  AND cancelled_by = 'customer';
            """,
            reverse_sql="""
                UPDATE appointments
                SET status = 'CANCELLED',
                    cancelled_by = 'customer'
                WHERE status = 'CUSTOMER_CANCELLED';
            """,
        ),

        # 4. Xóa field cancelled_by
        migrations.RemoveField(
            model_name='appointment',
            name='cancelled_by',
        ),
    ]
