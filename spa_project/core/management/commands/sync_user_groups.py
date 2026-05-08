"""
Management command: sync_user_groups

Dùng để:
1. --init-groups : tạo 3 group nếu chưa có
2. (mặc định)   : kiểm tra và báo cáo / tự động fix dữ liệu user/group/profile

Cách chạy:
    python manage.py sync_user_groups              # báo cáo + tự fix
    python manage.py sync_user_groups --init-groups  # chỉ tạo group
    python manage.py sync_user_groups --dry-run    # chỉ báo cáo, không sửa
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group
from django.db import transaction

from core.user_service import GROUP_CUSTOMER, GROUP_RECEPTIONIST, GROUP_MANAGER


class Command(BaseCommand):
    help = 'Sync user groups và profiles theo nghiệp vụ'

    def add_arguments(self, parser):
        parser.add_argument('--init-groups', action='store_true',
                            help='Tạo 3 group nếu chưa có')
        parser.add_argument('--dry-run', action='store_true',
                            help='Chỉ báo cáo, không sửa dữ liệu')

    def handle(self, *args, **options):
        if options['init_groups']:
            self._init_groups()
            return

        dry_run = options['dry_run']
        self._report_and_fix(dry_run)

    def _init_groups(self):
        for name in [GROUP_CUSTOMER, GROUP_RECEPTIONIST, GROUP_MANAGER]:
            group, created = Group.objects.get_or_create(name=name)
            if created:
                self.stdout.write(self.style.SUCCESS(f'  Đã tạo group: {name}'))
            else:
                self.stdout.write(f'  Group đã tồn tại: {name}')

    @transaction.atomic
    def _report_and_fix(self, dry_run: bool):
        from customers.models import CustomerProfile
        from staff.models import StaffProfile

        try:
            g_customer = Group.objects.get(name=GROUP_CUSTOMER)
            g_receptionist = Group.objects.get(name=GROUP_RECEPTIONIST)
            g_manager = Group.objects.get(name=GROUP_MANAGER)
        except Group.DoesNotExist as e:
            self.stderr.write(self.style.ERROR(
                f'Group chưa tồn tại: {e}. Chạy --init-groups trước.'
            ))
            return

        issues = []

        for user in User.objects.prefetch_related('groups').all():
            groups = set(user.groups.values_list('name', flat=True))
            has_customer = CustomerProfile.objects.filter(user=user).exists()
            has_staff = StaffProfile.objects.filter(user=user).exists()

            # Vừa có cả 2 profile
            if has_customer and has_staff:
                issues.append(f'[CONFLICT] {user.username}: có cả CustomerProfile lẫn StaffProfile')

            # Khách hàng
            if not user.is_staff and not user.is_superuser:
                if GROUP_CUSTOMER not in groups:
                    issues.append(f'[FIX] {user.username}: thiếu group "{GROUP_CUSTOMER}"')
                    if not dry_run:
                        user.groups.add(g_customer)
                if not has_customer:
                    issues.append(f'[WARN] {user.username}: group Khách hàng nhưng chưa có CustomerProfile')

            # Nhân viên / admin
            if user.is_staff or user.is_superuser:
                expected_group = GROUP_MANAGER if user.is_superuser else GROUP_RECEPTIONIST
                if expected_group not in groups:
                    issues.append(f'[FIX] {user.username}: thiếu group "{expected_group}"')
                    if not dry_run:
                        g = g_manager if user.is_superuser else g_receptionist
                        user.groups.add(g)
                if not has_staff:
                    issues.append(f'[FIX] {user.username}: is_staff=True nhưng chưa có StaffProfile → tạo tự động')
                    if not dry_run:
                        from core.user_service import ensure_staff_profile
                        ensure_staff_profile(user)

        if not issues:
            self.stdout.write(self.style.SUCCESS('Tất cả user đều đúng nghiệp vụ.'))
        else:
            for msg in issues:
                if msg.startswith('[FIX]'):
                    style = self.style.WARNING
                elif msg.startswith('[CONFLICT]'):
                    style = self.style.ERROR
                else:
                    style = self.style.NOTICE
                self.stdout.write(style(msg))

            if dry_run:
                self.stdout.write('\n[dry-run] Không có gì bị thay đổi.')
            else:
                self.stdout.write(self.style.SUCCESS('\nĐã tự động fix các mục [FIX].'))
