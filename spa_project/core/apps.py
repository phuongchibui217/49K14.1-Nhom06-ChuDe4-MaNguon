from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        from django.db.backends.signals import connection_created
        from django.db.utils import OperationalError

        def configure_sqlite_connection(sender, connection, **kwargs):
            if connection.vendor != 'sqlite':
                return

            with connection.cursor() as cursor:
                cursor.execute('PRAGMA busy_timeout = 20000;')
                try:
                    cursor.execute('PRAGMA journal_mode=WAL;')
                    cursor.execute('PRAGMA synchronous=NORMAL;')
                except OperationalError:
                    # Nếu một process khác đang giữ lock lúc startup, vẫn cho app tiếp tục chạy
                    # và dùng timeout/session-cookie để giảm xung đột ở các request sau.
                    pass

        connection_created.connect(
            configure_sqlite_connection,
            dispatch_uid='core.configure_sqlite_connection',
        )
