"""
Management command: backfill_invoice_items

Tạo InvoiceItem cho các Invoice cũ chưa có item.
Chạy 1 lần sau migration 0015_booking_refactor.

# TODO: Xác nhận đã chạy xong trên production rồi xóa file này (risk MEDIUM).
# Verify: python manage.py backfill_invoice_items --dry-run
Usage:
    python manage.py backfill_invoice_items
    python manage.py backfill_invoice_items --dry-run
"""

from decimal import Decimal

from django.core.management.base import BaseCommand

from appointments.models import Invoice, InvoiceItem


class Command(BaseCommand):
    help = 'Backfill InvoiceItem cho các Invoice cũ chưa có item'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Chỉ in ra sẽ làm gì, không ghi vào DB',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('=== DRY RUN — không ghi DB ==='))

        invoices_no_items = Invoice.objects.filter(
            items__isnull=True
        ).select_related('booking').prefetch_related(
            'booking__appointments__service_variant__service'
        ).distinct()

        total_invoices = invoices_no_items.count()
        self.stdout.write(f'Tìm thấy {total_invoices} invoice chưa có item')

        created_count = 0
        skipped_count = 0

        for invoice in invoices_no_items:
            booking = invoice.booking
            appointments = list(
                booking.appointments.filter(deleted_at__isnull=True)
                .select_related('service_variant__service')
            )

            if not appointments:
                self.stdout.write(
                    self.style.WARNING(f'  {invoice.code}: booking {booking.booking_code} không có appointment — bỏ qua')
                )
                skipped_count += 1
                continue

            for appt in appointments:
                # Kiểm tra đã có InvoiceItem cho appointment này chưa
                if InvoiceItem.objects.filter(invoice=invoice, appointment=appt).exists():
                    self.stdout.write(f'  {invoice.code} / {appt.appointment_code}: đã có item — bỏ qua')
                    skipped_count += 1
                    continue

                sv = appt.service_variant
                if sv:
                    unit_price = Decimal(str(sv.price))
                    desc_parts = []
                    if sv.service_id:
                        try:
                            desc_parts.append(sv.service.name)
                        except Exception:
                            pass
                    if sv.label:
                        desc_parts.append(sv.label)
                    description = ' — '.join(desc_parts) if desc_parts else sv.label or ''
                else:
                    unit_price = Decimal('0')
                    description = appt.customer_name_snapshot or ''

                line_total = unit_price * 1  # quantity = 1

                self.stdout.write(
                    f'  {invoice.code} / {appt.appointment_code}: '
                    f'{description} — {unit_price:,.0f}đ'
                )

                if not dry_run:
                    InvoiceItem.objects.create(
                        invoice=invoice,
                        appointment=appt,
                        service_variant=sv,
                        description=description,
                        quantity=1,
                        unit_price=unit_price,
                        line_total=line_total,
                    )
                    created_count += 1
                else:
                    created_count += 1  # đếm để báo cáo

            # Cập nhật lại subtotal/final của Invoice nếu cần
            if not dry_run:
                items = list(invoice.items.all())
                if items:
                    subtotal = sum(i.line_total for i in items)
                    if invoice.subtotal_amount != subtotal or invoice.final_amount != subtotal - invoice.discount_amount:
                        invoice.subtotal_amount = subtotal
                        invoice.final_amount = subtotal - invoice.discount_amount
                        invoice.save(update_fields=['subtotal_amount', 'final_amount'])
                        self.stdout.write(
                            f'  → Cập nhật {invoice.code}: subtotal={subtotal:,.0f}đ'
                        )

        action = 'Sẽ tạo' if dry_run else 'Đã tạo'
        self.stdout.write(
            self.style.SUCCESS(
                f'\n{action} {created_count} InvoiceItem, bỏ qua {skipped_count}'
            )
        )
