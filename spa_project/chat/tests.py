import base64
import re
import shutil
import tempfile

from asgiref.sync import async_to_sync, sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from customers.models import CustomerProfile
from spa_project.asgi import application

from .models import ChatMessage, ChatSession, SessionStaff
from .services import create_chat_message, serialize_chat_message


class ChatPageTests(TestCase):
    def setUp(self):
        self.customer_user = User.objects.create_user(
            username="0912345678",
            password="testpass123",
            first_name="Lan",
            last_name="Nguyen",
        )
        CustomerProfile.objects.create(
            user=self.customer_user,
            phone="0912345678",
            full_name="Lan Nguyen",
        )
        self.admin_user = User.objects.create_user(
            username="receptionist",
            password="testpass123",
            first_name="Le",
            last_name="Reception",
            is_staff=True,
        )

    def test_admin_live_chat_template_only_exposes_websocket_paths(self):
        client = Client()
        client.force_login(self.admin_user)

        response = client.get(reverse("chat:admin_live_chat"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn("/ws/admin/chat/sessions/", content)
        self.assertIn("/ws/admin/chat/sessions/__CHAT_CODE__/", content)
        self.assertNotIn("/api/chat/", content)
        self.assertNotIn("/api/admin/chat/", content)

    def test_admin_live_chat_template_uses_versioned_chat_stylesheet(self):
        client = Client(HTTP_HOST="localhost")
        client.force_login(self.admin_user)

        response = client.get(reverse("chat:admin_live_chat"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn('class="admin-chat-page admin-chat-page--balanced"', content)
        self.assertRegex(
            content,
            re.compile(r'/static/css/admin-chat\.css\?v=\d{14}'),
        )

    def test_admin_sidebar_chat_badge_uses_websocket_only(self):
        client = Client()
        client.force_login(self.admin_user)

        response = client.get(reverse("appointments:admin_appointments"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn('id="adminSidebarChatBadge"', content)
        self.assertIn("/ws/admin/chat/sessions/", content)
        self.assertNotIn("/api/admin/chat/", content)

    def test_non_staff_user_cannot_open_admin_live_chat(self):
        client = Client()
        client.force_login(self.customer_user)

        response = client.get(reverse("chat:admin_live_chat"))

        self.assertEqual(response.status_code, 302)


class BaseChatWebSocketTestCase(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._temp_media = tempfile.mkdtemp(prefix="spa-chat-test-")
        cls._media_override = override_settings(MEDIA_ROOT=cls._temp_media)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._temp_media, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.customer_user = User.objects.create_user(
            username="0912345678",
            password="testpass123",
            first_name="Lan",
            last_name="Nguyen",
            email="lan@example.com",
        )
        self.customer_profile = CustomerProfile.objects.create(
            user=self.customer_user,
            phone="0912345678",
            full_name="Lan Nguyen",
        )
        self.admin_user = User.objects.create_user(
            username="receptionist",
            password="testpass123",
            first_name="Le",
            last_name="Reception",
            email="admin@example.com",
            is_staff=True,
        )

    def build_cookie_header(self, client):
        cookies = [f"{key}={morsel.value}" for key, morsel in client.cookies.items()]
        return "; ".join(cookies)

    def get_websocket_headers(self, client=None):
        headers = [(b"origin", b"http://localhost")]
        if client:
            cookie_header = self.build_cookie_header(client)
            if cookie_header:
                headers.append((b"cookie", cookie_header.encode("utf-8")))
        return headers

    async def connect_websocket(self, path, client=None):
        communicator = WebsocketCommunicator(
            application,
            path,
            headers=self.get_websocket_headers(client),
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        return communicator

    async def receive_until_event(self, communicator, event_name, timeout=5, max_messages=10):
        for _ in range(max_messages):
            payload = await communicator.receive_json_from(timeout=timeout)
            if payload.get("event") == event_name:
                return payload
        self.fail(f"Did not receive websocket event {event_name!r}")

    async def send_ws_json(self, communicator, payload):
        await communicator.send_json_to(payload)

    async def disconnect_ws(self, communicator):
        await communicator.disconnect()

    async def make_logged_in_client(self, user):
        client = Client(HTTP_HOST="localhost")
        await sync_to_async(client.force_login, thread_sensitive=True)(user)
        return client


class ChatWebSocketTests(BaseChatWebSocketTestCase):
    def setUp(self):
        super().setUp()
        self.guest_session = ChatSession.objects.create(
            customer_type="guest",
            guest_session_key="guest-session-001",
            source_page="/",
        )
        create_chat_message(
            session=self.guest_session,
            sender_type="customer",
            sender_name="Khach vang lai",
            content="Toi can gap le tan",
            client_message_id="guest-seed-msg",
        )

    def test_customer_socket_bootstraps_empty_state_before_first_message(self):
        async def scenario():
            communicator = await self.connect_websocket("/ws/chat/customer/")
            try:
                bootstrap_event = await self.receive_until_event(communicator, "bootstrap")
                self.assertIsNone(bootstrap_event["session"])
                self.assertEqual(bootstrap_event["messages"], [])
                self.assertTrue(bootstrap_event["isNewSession"])
            finally:
                await self.disconnect_ws(communicator)

        async_to_sync(scenario)()

    def test_customer_can_create_session_and_send_first_message_via_websocket(self):
        async def scenario():
            communicator = await self.connect_websocket("/ws/chat/customer/")
            try:
                await self.receive_until_event(communicator, "bootstrap")

                await self.send_ws_json(
                    communicator,
                    {
                        "action": "send_message",
                        "content": "Xin chao Spa ANA",
                        "clientMessageId": "guest-ws-first-msg-001",
                        "sourcePage": "/",
                    },
                )

                session_event = await self.receive_until_event(communicator, "session")
                self.assertTrue(session_event["guestKey"])
                self.assertTrue(session_event["session"]["chatCode"])

                message_event = await self.receive_until_event(communicator, "message")
                self.assertEqual(message_event["message"]["content"], "Xin chao Spa ANA")
                self.assertEqual(message_event["message"]["clientMessageId"], "guest-ws-first-msg-001")

                created_session = await sync_to_async(
                    ChatSession.objects.get,
                    thread_sensitive=True,
                )(chat_code=session_event["session"]["chatCode"])
                self.assertEqual(created_session.customer_type, "guest")
            finally:
                await self.disconnect_ws(communicator)

        async_to_sync(scenario)()

    def test_customer_socket_masks_admin_sender_name(self):
        async def scenario():
            communicator = await self.connect_websocket(
                f"/ws/chat/customer/?guestKey={self.guest_session.guest_session_key}"
            )
            admin_communicator = None
            try:
                bootstrap_event = await self.receive_until_event(communicator, "bootstrap")
                self.assertEqual(bootstrap_event["session"]["chatCode"], self.guest_session.chat_code)
                self.assertEqual(len(bootstrap_event["messages"]), 1)

                admin_client = await self.make_logged_in_client(self.admin_user)
                admin_communicator = await self.connect_websocket(
                    f"/ws/admin/chat/sessions/{self.guest_session.chat_code}/",
                    admin_client,
                )
                await self.receive_until_event(admin_communicator, "bootstrap")
                await self.receive_until_event(admin_communicator, "session")

                await self.send_ws_json(
                    admin_communicator,
                    {
                        "action": "send_message",
                        "content": "Nhan vien se ho tro ban ngay.",
                        "clientMessageId": "admin-ws-mask-customer-001",
                    },
                )

                message_event = await self.receive_until_event(communicator, "message")
                self.assertEqual(message_event["message"]["senderType"], "admin")
                self.assertNotEqual(
                    message_event["message"]["senderName"],
                    self.admin_user.get_full_name() or self.admin_user.username,
                )
            finally:
                if admin_communicator:
                    await self.disconnect_ws(admin_communicator)
                await self.disconnect_ws(communicator)

        async_to_sync(scenario)()

    def test_admin_sessions_socket_sends_snapshot(self):
        async def scenario():
            admin_client = await self.make_logged_in_client(self.admin_user)

            communicator = await self.connect_websocket("/ws/admin/chat/sessions/", admin_client)
            try:
                sessions_event = await self.receive_until_event(communicator, "sessions")

                self.assertEqual(sessions_event["unreadTotal"], 1)
                self.assertTrue(
                    any(item["chatCode"] == self.guest_session.chat_code for item in sessions_event["sessions"])
                )
            finally:
                await self.disconnect_ws(communicator)

        async_to_sync(scenario)()

    def test_admin_session_socket_bootstraps_history_and_marks_read(self):
        async def scenario():
            admin_client = await self.make_logged_in_client(self.admin_user)
            communicator = await self.connect_websocket(
                f"/ws/admin/chat/sessions/{self.guest_session.chat_code}/",
                admin_client,
            )
            try:
                bootstrap_event = await self.receive_until_event(communicator, "bootstrap")
                self.assertEqual(bootstrap_event["session"]["chatCode"], self.guest_session.chat_code)
                self.assertEqual(len(bootstrap_event["messages"]), 1)

                session_event = await self.receive_until_event(communicator, "session")
                self.assertEqual(session_event["session"]["chatCode"], self.guest_session.chat_code)

                refreshed_session = await sync_to_async(
                    ChatSession.objects.get,
                    thread_sensitive=True,
                )(pk=self.guest_session.pk)
                self.assertEqual(refreshed_session.admin_unread_count, 0)

                session_staff_count = await sync_to_async(
                    lambda: SessionStaff.objects.filter(session=self.guest_session, staff=self.admin_user).count(),
                    thread_sensitive=True,
                )()
                self.assertEqual(session_staff_count, 1)
            finally:
                await self.disconnect_ws(communicator)

        async_to_sync(scenario)()

    def test_admin_can_send_attachment_via_websocket(self):
        async def scenario():
            admin_client = await self.make_logged_in_client(self.admin_user)
            communicator = await self.connect_websocket(
                f"/ws/admin/chat/sessions/{self.guest_session.chat_code}/",
                admin_client,
            )
            try:
                await self.receive_until_event(communicator, "bootstrap")
                await self.receive_until_event(communicator, "session")

                attachment_payload = {
                    "name": "quy-trinh.pdf",
                    "contentType": "application/pdf",
                    "data": (
                        "data:application/pdf;base64,"
                        + base64.b64encode(b"%PDF-1.4\nchat attachment\n").decode("ascii")
                    ),
                }

                await self.send_ws_json(
                    communicator,
                    {
                        "action": "send_message",
                        "content": "Spa gui ban tai lieu tham khao.",
                        "clientMessageId": "admin-ws-attachment-001",
                        "attachment": attachment_payload,
                    },
                )

                message_event = await self.receive_until_event(communicator, "message")
                self.assertEqual(message_event["message"]["senderType"], "admin")
                self.assertEqual(message_event["message"]["clientMessageId"], "admin-ws-attachment-001")
                self.assertEqual(message_event["message"]["messageType"], "file")
                self.assertEqual(message_event["message"]["attachmentName"], "quy-trinh.pdf")

                refreshed_session = await sync_to_async(
                    ChatSession.objects.get,
                    thread_sensitive=True,
                )(pk=self.guest_session.pk)
                self.assertEqual(refreshed_session.customer_unread_count, 1)

                message_count = await sync_to_async(
                    lambda: ChatMessage.objects.filter(session=self.guest_session).count(),
                    thread_sensitive=True,
                )()
                self.assertEqual(message_count, 2)
            finally:
                await self.disconnect_ws(communicator)

        async_to_sync(scenario)()

    def test_serialize_message_hides_missing_attachment_url(self):
        attachment_content = b"%PDF-1.4\nchat attachment\n"
        attachment = SimpleUploadedFile(
            "quy-trinh.pdf",
            attachment_content,
            content_type="application/pdf",
        )
        message = ChatMessage.objects.create(
            session=self.guest_session,
            sender_type="admin",
            sender_name="Le Reception",
            message_type="file",
            attachment=attachment,
            attachment_name="quy-trinh.pdf",
            attachment_size=len(attachment_content),
            attachment_content_type="application/pdf",
        )

        message.attachment.delete(save=False)

        payload = serialize_chat_message(message)

        self.assertEqual(payload["attachmentUrl"], "")
        self.assertEqual(payload["attachmentName"], "quy-trinh.pdf")
