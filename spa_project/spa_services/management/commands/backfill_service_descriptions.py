"""
Management command: backfill_service_descriptions

# TODO: Xác nhận đã chạy xong trên production rồi xóa file này (risk MEDIUM).
# Verify: python manage.py backfill_service_descriptions --dry-run

Mục đích:
  - Với mỗi Service trong DB:
    1. Nếu short_description rỗng → copy description cũ vào short_description
    2. Nếu description rỗng / quá ngắn / giống short_description → tự sinh description mới
  - Không bao giờ overwrite description tốt đang có.
  - Chạy an toàn nhiều lần (idempotent).

Cách dùng:
  python manage.py backfill_service_descriptions
  python manage.py backfill_service_descriptions --dry-run   # chỉ xem, không lưu
"""

from django.core.management.base import BaseCommand

from spa_services.models import Service
from spa_services.description_helpers import (
    generate_service_description,
    should_generate_description,
)


class Command(BaseCommand):
    help = 'Backfill short_description và auto-generate description cho các service cũ'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Chỉ in ra những gì sẽ thay đổi, không lưu vào DB',
        )
        parser.add_argument(
            '--force-description',
            action='store_true',
            help='Tự sinh lại description cho tất cả service (kể cả đã có)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force_desc = options['force_description']
        if dry_run:
            self.stdout.write(self.style.WARNING('=== DRY RUN — không lưu vào DB ===\n'))

        services = Service.objects.prefetch_related('variants', 'category').all()
        total = services.count()
        updated_short = 0
        updated_desc = 0

        for service in services:
            changed = False
            old_desc = (service.description or '').strip()
            old_short = (service.short_description or '').strip()

            # 1. Backfill short_description từ description cũ
            if not old_short and old_desc:
                new_short = old_desc[:255]
                self.stdout.write(
                    f'[{service.code}] {service.name}: '
                    f'short_description rỗng → copy từ description '
                    f'("{new_short[:60]}{"..." if len(new_short) > 60 else ""}")'
                )
                if not dry_run:
                    service.short_description = new_short
                updated_short += 1
                changed = True

            # 2. Auto-generate description nếu cần
            # Reload short_description sau bước 1 (có thể vừa set)
            effective_short = (service.short_description or '').strip() if not dry_run else (
                old_desc[:255] if (not old_short and old_desc) else old_short
            )
            # Tạm gán để should_generate_description đọc đúng
            _orig_short = service.short_description
            if not dry_run and changed:
                pass  # đã set ở trên
            elif dry_run and not old_short and old_desc:
                service.short_description = old_desc[:255]

            if force_desc or should_generate_description(service):
                new_desc = generate_service_description(service)
                self.stdout.write(
                    f'[{service.code}] {service.name}: '
                    f'description nghèo → tự sinh '
                    f'({len(new_desc)} ký tự)'
                )
                if not dry_run:
                    service.description = new_desc
                updated_desc += 1
                changed = True

            # Restore nếu dry-run đã tạm thay đổi
            if dry_run:
                service.short_description = _orig_short

            if changed and not dry_run:
                service.save(update_fields=['short_description', 'description'])

        # Summary
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Hoàn thành: {total} dịch vụ — '
            f'{updated_short} short_description được backfill, '
            f'{updated_desc} description được tự sinh'
            + (' (DRY RUN)' if dry_run else '')
        ))
