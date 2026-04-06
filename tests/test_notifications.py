from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from app.crud import notification as notification_crud
from app.routers.notifications import _notification_out


def make_admin(**overrides):
    data = {
        "id": 1,
        "email": "admin@example.com",
        "full_name": None,
        "permissions": [],
        "notification_preferences": [],
        "is_active": True,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def make_service_request(**overrides):
    data = {
        "id": uuid4(),
        "tracking_id": "REQ-123",
        "legacy_consultation_id": None,
        "created_at": datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc),
        "assignments": [],
        "customer": SimpleNamespace(display_name="Client Example"),
        "due_at": datetime(2026, 4, 5, 12, 0, tzinfo=timezone.utc),
        "status": "in_progress",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def make_scalar_result(items):
    return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: items))


def make_unique_scalar_result(items):
    return SimpleNamespace(
        scalars=lambda: SimpleNamespace(
            unique=lambda: SimpleNamespace(all=lambda: items)
        )
    )


class NotificationCrudTests(IsolatedAsyncioTestCase):
    async def test_create_or_bump_notification_bumps_existing_unread_item(self):
        existing = SimpleNamespace(
            id=uuid4(),
            category="request_ops",
            event_type="request.submitted",
            severity="info",
            title="Old title",
            body="Old body",
            href="/admin/consultations/?search=REQ-123",
            resource_type="service_request",
            resource_id="request-id",
            actor_admin_id=None,
            occurrence_count=2,
            last_occurred_at=datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc),
        )
        db = SimpleNamespace(
            scalar=AsyncMock(return_value=existing),
            add=Mock(),
            flush=AsyncMock(),
        )

        result = await notification_crud.create_or_bump_notification(
            db,
            recipient_admin_id=1,
            category="request_ops",
            event_type="request.submitted",
            severity="info",
            title="New title",
            body="New body",
            dedupe_key="request-submitted:1",
            occurred_at=datetime(2026, 4, 6, 13, 0, tzinfo=timezone.utc),
        )

        self.assertIs(result, existing)
        self.assertEqual(existing.occurrence_count, 3)
        self.assertEqual(existing.title, "New title")
        self.assertEqual(existing.body, "New body")
        db.add.assert_called_once_with(existing)
        db.flush.assert_awaited_once()

    async def test_mark_notification_read_sets_timestamp(self):
        notification = SimpleNamespace(is_read=False, read_at=None)
        db = SimpleNamespace(add=Mock(), flush=AsyncMock())

        result = await notification_crud.mark_notification_read(db, notification=notification)

        self.assertIs(result, notification)
        self.assertTrue(notification.is_read)
        self.assertIsNotNone(notification.read_at)
        db.add.assert_called_once_with(notification)
        db.flush.assert_awaited_once()

    async def test_emit_request_submitted_uses_tracking_search_link(self):
        recipient = make_admin(id=7, permissions=["service_request.read"])
        service_request = make_service_request()

        with (
            patch.object(
                notification_crud,
                "list_active_admins_with_permissions",
                AsyncMock(return_value=[recipient]),
            ),
            patch.object(
                notification_crud,
                "create_or_bump_notification",
                AsyncMock(),
            ) as create_notification,
        ):
            emitted = await notification_crud.emit_request_submitted_notifications(
                SimpleNamespace(),
                service_request=service_request,
                customer_name="Client Example",
            )

        self.assertEqual(emitted, 1)
        create_notification.assert_awaited_once()
        kwargs = create_notification.await_args.kwargs
        self.assertEqual(kwargs["severity"], "info")
        self.assertEqual(kwargs["event_type"], "request.submitted")
        self.assertEqual(
            kwargs["href"],
            "/admin/consultations/?search=REQ-123",
        )

    async def test_emit_request_inbound_message_prefers_assignees(self):
        assignee = make_admin(
            id=9,
            permissions=["service_request.read"],
            notification_preferences=[
                SimpleNamespace(category="request_ops", in_app_enabled=True)
            ],
        )
        service_request = make_service_request(
            assignments=[SimpleNamespace(admin_user_id=9, unassigned_at=None)]
        )
        db = SimpleNamespace(execute=AsyncMock(return_value=make_scalar_result([assignee])))

        with (
            patch.object(
                notification_crud,
                "list_active_admins_with_permissions",
                AsyncMock(),
            ) as fallback_recipients,
            patch.object(
                notification_crud,
                "create_or_bump_notification",
                AsyncMock(),
            ) as create_notification,
        ):
            emitted = await notification_crud.emit_request_inbound_message_notifications(
                db,
                service_request=service_request,
                customer_name="Client Example",
                occurred_at=datetime(2026, 4, 6, 12, 30, tzinfo=timezone.utc),
            )

        self.assertEqual(emitted, 1)
        fallback_recipients.assert_not_awaited()
        self.assertEqual(create_notification.await_args.kwargs["recipient_admin_id"], 9)
        self.assertEqual(create_notification.await_args.kwargs["severity"], "info")

    async def test_emit_request_assigned_respects_disabled_request_ops_preferences(self):
        recipient = make_admin(id=3)

        with patch.object(
            notification_crud,
            "get_notification_preferences_map",
            AsyncMock(return_value={"request_ops": False}),
        ):
            emitted = await notification_crud.emit_request_assigned_notification(
                SimpleNamespace(),
                service_request=make_service_request(),
                recipient_admin=recipient,
                assigned_by_admin=make_admin(id=5, email="manager@example.com"),
                occurred_at=datetime(2026, 4, 6, 12, 45, tzinfo=timezone.utc),
            )

        self.assertIsNone(emitted)

    async def test_emit_suspicious_login_normalizes_dedupe_key(self):
        recipient = make_admin(id=11, permissions=["audit_log.read"])

        with (
            patch.object(
                notification_crud,
                "list_active_admins_with_permissions",
                AsyncMock(return_value=[recipient]),
            ),
            patch.object(
                notification_crud,
                "create_or_bump_notification",
                AsyncMock(),
            ) as create_notification,
        ):
            await notification_crud.emit_suspicious_login_notifications(
                SimpleNamespace(),
                email="  Admin@Example.com  ",
                attempt_count=5,
                observed_at=datetime(2026, 4, 6, 12, 14, tzinfo=timezone.utc),
            )

        kwargs = create_notification.await_args.kwargs
        self.assertEqual(
            kwargs["dedupe_key"],
            "security-login-failed:admin@example.com:2026-04-06T12:00:00+00:00",
        )
        self.assertEqual(kwargs["resource_id"], "admin@example.com")

    async def test_emit_admin_role_changed_routes_to_filtered_access_roles(self):
        recipient = make_admin(id=21, permissions=["audit_log.read"])
        target_admin = make_admin(id=8, email="target@example.com", full_name="Target User")

        with (
            patch.object(
                notification_crud,
                "list_active_admins_with_permissions",
                AsyncMock(return_value=[recipient]),
            ),
            patch.object(
                notification_crud,
                "create_or_bump_notification",
                AsyncMock(),
            ) as create_notification,
        ):
            emitted = await notification_crud.emit_admin_role_changed_notifications(
                SimpleNamespace(),
                target_admin=target_admin,
                actor_admin=make_admin(id=4, email="actor@example.com", full_name="Amina"),
                old_role="editor",
                new_role="administrator",
                occurred_at=datetime(2026, 4, 6, 13, 0, tzinfo=timezone.utc),
            )

        self.assertEqual(emitted, 1)
        kwargs = create_notification.await_args.kwargs
        self.assertEqual(kwargs["event_type"], "security.admin_role_changed")
        self.assertEqual(kwargs["severity"], "warning")
        self.assertEqual(kwargs["href"], "/admin/access/roles/?search=target%40example.com")
        self.assertIn("changed Target User's role from editor to administrator", kwargs["body"])

    async def test_emit_admin_status_changed_uses_activation_severity_mapping(self):
        recipient = make_admin(id=22, permissions=["audit_log.read"])
        target_admin = make_admin(id=8, email="target@example.com", full_name="Target User")

        with (
            patch.object(
                notification_crud,
                "list_active_admins_with_permissions",
                AsyncMock(return_value=[recipient]),
            ),
            patch.object(
                notification_crud,
                "create_or_bump_notification",
                AsyncMock(),
            ) as create_notification,
        ):
            await notification_crud.emit_admin_status_changed_notifications(
                SimpleNamespace(),
                target_admin=target_admin,
                actor_admin=make_admin(id=4, email="actor@example.com", full_name="Amina"),
                is_active=False,
                occurred_at=datetime(2026, 4, 6, 13, 5, tzinfo=timezone.utc),
            )

        kwargs = create_notification.await_args.kwargs
        self.assertEqual(kwargs["event_type"], "security.admin_status_changed")
        self.assertEqual(kwargs["severity"], "error")
        self.assertEqual(kwargs["href"], "/admin/access/roles/?search=target%40example.com")
        self.assertIn("deactivated by Amina", kwargs["body"])

    async def test_emit_overdue_notifications_uses_daily_dedupe_key(self):
        timestamp = datetime(2026, 4, 6, 15, 0, tzinfo=timezone.utc)
        recipient = make_admin(id=30, permissions=["service_request.read"])
        service_request = make_service_request()
        db = SimpleNamespace(execute=AsyncMock(return_value=make_unique_scalar_result([service_request])))

        with (
            patch.object(
                notification_crud,
                "list_active_admins_with_permissions",
                AsyncMock(return_value=[recipient]),
            ),
            patch.object(
                notification_crud,
                "create_or_bump_notification",
                AsyncMock(),
            ) as create_notification,
        ):
            emitted = await notification_crud.emit_overdue_notifications(
                db,
                now=timestamp,
            )

        self.assertEqual(emitted, 1)
        kwargs = create_notification.await_args.kwargs
        self.assertEqual(kwargs["event_type"], "request.overdue")
        self.assertEqual(kwargs["severity"], "warning")
        self.assertEqual(
            kwargs["dedupe_key"],
            f"request-overdue:{service_request.id}:30:2026-04-06",
        )


class NotificationRouterTests(IsolatedAsyncioTestCase):
    async def test_notification_out_hides_admin_user_link_without_permission(self):
        notification = SimpleNamespace(
            id=uuid4(),
            category="security",
            event_type="security.admin_status_changed",
            severity="error",
            title="Admin account deactivated",
            body="Target User was deactivated by Amina.",
            href="/admin/access/roles/?search=target%40example.com",
            resource_type="admin_user",
            resource_id="8",
            actor_admin=None,
            occurrence_count=1,
            is_read=False,
            read_at=None,
            last_occurred_at=datetime(2026, 4, 6, 13, 5, tzinfo=timezone.utc),
            created_at=datetime(2026, 4, 6, 13, 5, tzinfo=timezone.utc),
            updated_at=datetime(2026, 4, 6, 13, 5, tzinfo=timezone.utc),
        )
        current_admin = make_admin(permissions=["audit_log.read"])

        payload = _notification_out(notification, current_admin)

        self.assertIsNone(payload.href)

    async def test_notification_out_keeps_admin_user_link_with_permission(self):
        notification = SimpleNamespace(
            id=uuid4(),
            category="security",
            event_type="security.admin_role_changed",
            severity="warning",
            title="Admin role changed",
            body="Amina changed Target User's role from editor to administrator.",
            href="/admin/access/roles/?search=target%40example.com",
            resource_type="admin_user",
            resource_id="8",
            actor_admin=None,
            occurrence_count=1,
            is_read=False,
            read_at=None,
            last_occurred_at=datetime(2026, 4, 6, 13, 0, tzinfo=timezone.utc),
            created_at=datetime(2026, 4, 6, 13, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 4, 6, 13, 0, tzinfo=timezone.utc),
        )
        current_admin = make_admin(permissions=["audit_log.read", "user.manage"])

        payload = _notification_out(notification, current_admin)

        self.assertEqual(payload.href, "/admin/access/roles/?search=target%40example.com")
