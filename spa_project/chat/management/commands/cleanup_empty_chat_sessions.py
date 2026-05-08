"""
Management command: dọn các chat session rỗng (không có tin nhắn nào).

Usage:
    python manage.py cleanup_empty_chat_sessions          # dry-run, chỉ đếm
    python manage.py cleanup_empty_chat_sessions --delete # xóa thật
"""

from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef

from chat.models import ChatMessage, ChatSession


class Command(BaseCommand):
    help = "Xóa các chat session không có tin nhắn nào (session rỗng)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--delete",
            action="store_true",
            help="Thực sự xóa session rỗng. Mặc định chỉ hiển thị số lượng (dry-run).",
        )

    def handle(self, *args, **options):
        empty_sessions = ChatSession.objects.filter(
            ~Exists(ChatMessage.objects.filter(session=OuterRef("pk")))
        )
        count = empty_sessions.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS("Không có session rỗng nào."))
            return

        if options["delete"]:
            empty_sessions.delete()
            self.stdout.write(self.style.SUCCESS(f"Đã xóa {count} session rỗng."))
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"Tìm thấy {count} session rỗng. "
                    "Chạy với --delete để xóa thật."
                )
            )
