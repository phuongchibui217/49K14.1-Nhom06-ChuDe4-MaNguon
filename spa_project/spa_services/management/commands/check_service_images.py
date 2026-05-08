"""
Management command: check_service_images

# TODO: Xác nhận đã chạy xong trên production rồi xóa file này (risk MEDIUM).

Rà soát toàn bộ Service records và kiểm tra file ảnh có tồn tại thực sự
trong MEDIA_ROOT hay không.

Cách dùng:
    python manage.py check_service_images
    python manage.py check_service_images --fix   # xóa image path của bản ghi bị hỏng

Lưu ý về "máy này thấy, máy khác không thấy":
    - Thư mục /media/ bị .gitignore → KHÔNG được commit vào git.
    - Ảnh upload là dữ liệu runtime local, không tự theo source code sang máy khác.
    - Giải pháp dev: copy thư mục media/ sang máy khác thủ công.
    - Giải pháp production: dùng shared storage (S3, GCS, NFS...) thay vì local disk.
"""

import os
from django.core.management.base import BaseCommand
from django.conf import settings
from spa_services.models import Service


class Command(BaseCommand):
    help = (
        'Kiểm tra file ảnh dịch vụ có tồn tại trong MEDIA_ROOT không. '
        'Dùng --fix để xóa image path của bản ghi bị hỏng.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Xóa image field của các bản ghi có path nhưng file không tồn tại',
        )

    def handle(self, *args, **options):
        fix = options['fix']
        services = Service.objects.all().order_by('id')

        total = services.count()
        ok = 0
        missing = []
        empty = 0

        self.stdout.write(f'\nKiểm tra {total} dịch vụ...\n')
        self.stdout.write(f'MEDIA_ROOT: {settings.MEDIA_ROOT}\n')
        self.stdout.write('-' * 60)

        for service in services:
            if not service.image:
                empty += 1
                self.stdout.write(
                    self.style.WARNING(f'  [EMPTY]   ID={service.id} | {service.name}')
                )
                continue

            # ImageField.name là relative path, vd: services/abc.jpg
            abs_path = os.path.join(settings.MEDIA_ROOT, service.image.name)
            if os.path.isfile(abs_path):
                ok += 1
                self.stdout.write(
                    self.style.SUCCESS(f'  [OK]      ID={service.id} | {service.name} → {service.image.name}')
                )
            else:
                missing.append(service)
                self.stdout.write(
                    self.style.ERROR(
                        f'  [MISSING] ID={service.id} | {service.name} → {service.image.name}\n'
                        f'            File không tồn tại: {abs_path}'
                    )
                )

        self.stdout.write('-' * 60)
        self.stdout.write(f'\nTổng kết:')
        self.stdout.write(f'  ✓ Có ảnh hợp lệ : {ok}')
        self.stdout.write(f'  ✗ Ảnh bị mất    : {len(missing)}')
        self.stdout.write(f'  - Không có ảnh  : {empty}')

        if missing:
            self.stdout.write(
                self.style.WARNING(
                    '\n⚠ Nguyên nhân ảnh bị mất:\n'
                    '  - Thư mục /media/ bị .gitignore → không được commit vào git.\n'
                    '  - Ảnh upload chỉ tồn tại trên máy đã upload, không tự sang máy khác.\n'
                    '  - Giải pháp dev: copy thư mục media/ sang máy khác thủ công.\n'
                    '  - Giải pháp production: dùng shared storage (S3, GCS, NFS...).'
                )
            )

            if fix:
                self.stdout.write('\nĐang xóa image path của các bản ghi bị hỏng...')
                for service in missing:
                    old_path = service.image.name
                    service.image = None
                    service.save(update_fields=['image'])
                    self.stdout.write(
                        self.style.SUCCESS(f'  Đã xóa image path: ID={service.id} | {old_path}')
                    )
                self.stdout.write(self.style.SUCCESS(f'\nĐã xử lý {len(missing)} bản ghi.'))
            else:
                self.stdout.write(
                    '\nDùng --fix để tự động xóa image path của các bản ghi bị hỏng:\n'
                    '  python manage.py check_service_images --fix\n'
                )
        else:
            self.stdout.write(self.style.SUCCESS('\n✓ Tất cả ảnh đều hợp lệ!'))
