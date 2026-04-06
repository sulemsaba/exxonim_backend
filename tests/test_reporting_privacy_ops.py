from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock
from uuid import uuid4

from app.core.rbac import get_role_permission_codes
from app.crud import admin as admin_crud
from app.crud import privacy as privacy_crud
from app.crud import reporting as reporting_crud
from app.schemas.privacy import PrivacyPolicyVersions
from app.schemas.reporting import ReportFiltersOut


def make_admin_user(admin_id: int, email: str, full_name: str | None = None):
    return SimpleNamespace(id=admin_id, email=email, full_name=full_name)


def make_assignment(
    *,
    admin_id: int,
    email: str,
    assigned_at: datetime,
    unassigned_at: datetime | None = None,
):
    return SimpleNamespace(
        admin_user_id=admin_id,
        assigned_at=assigned_at,
        unassigned_at=unassigned_at,
        admin_user=make_admin_user(admin_id, email),
    )


def make_request(
    *,
    customer_id=None,
    service_type_id=None,
    service_type_code="compliance",
    service_type_label="Compliance",
    status="new",
    opened_at: datetime,
    due_at: datetime | None = None,
    source_channel="public_consultation_form",
    assignments=None,
    inbox_states=None,
    status_history=None,
    notes=None,
    threads=None,
    last_customer_message_at: datetime | None = None,
):
    return SimpleNamespace(
        id=uuid4(),
        customer_id=customer_id or uuid4(),
        service_type_id=service_type_id or uuid4(),
        service_type=SimpleNamespace(code=service_type_code, label=service_type_label),
        status=status,
        opened_at=opened_at,
        due_at=due_at,
        source_channel=source_channel,
        assignments=assignments or [],
        inbox_states=inbox_states or [],
        status_history=status_history or [],
        notes=notes or [],
        threads=threads or [],
        last_customer_message_at=last_customer_message_at,
    )


def make_thread(messages):
    return SimpleNamespace(messages=messages)


def make_message(*, direction: str, created_at: datetime, author_admin_id: int | None = None):
    return SimpleNamespace(
        direction=direction,
        created_at=created_at,
        author_admin_id=author_admin_id,
    )


def make_status_history(
    *,
    old_status: str | None,
    new_status: str,
    created_at: datetime,
    changed_by_admin_id: int | None = 1,
):
    return SimpleNamespace(
        old_status=old_status,
        new_status=new_status,
        created_at=created_at,
        changed_by_admin_id=changed_by_admin_id,
    )


class ReportingCrudTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.filters = ReportFiltersOut(
            **{
                "from": date(2026, 4, 1),
                "to": date(2026, 4, 30),
                "grain": "day",
            }
        )

    def test_build_operations_report_tracks_repeat_customers_and_response_times(self):
        prior_customer_id = uuid4()
        service_type_id = uuid4()
        prior_request = make_request(
            customer_id=prior_customer_id,
            service_type_id=service_type_id,
            status="completed",
            opened_at=datetime(2026, 3, 20, 9, 0, tzinfo=timezone.utc),
        )
        repeat_request = make_request(
            customer_id=prior_customer_id,
            service_type_id=service_type_id,
            status="completed",
            opened_at=datetime(2026, 4, 5, 9, 0, tzinfo=timezone.utc),
            assignments=[
                make_assignment(
                    admin_id=3,
                    email="ops@example.com",
                    assigned_at=datetime(2026, 4, 5, 11, 0, tzinfo=timezone.utc),
                )
            ],
            threads=[
                make_thread(
                    [
                        make_message(
                            direction="outbound",
                            created_at=datetime(2026, 4, 5, 12, 0, tzinfo=timezone.utc),
                            author_admin_id=3,
                        )
                    ]
                )
            ],
            status_history=[
                make_status_history(
                    old_status="new",
                    new_status="completed",
                    created_at=datetime(2026, 4, 6, 9, 0, tzinfo=timezone.utc),
                )
            ],
        )
        new_request = make_request(
            customer_id=uuid4(),
            service_type_id=uuid4(),
            service_type_label="Registration",
            status="in_progress",
            opened_at=datetime(2026, 4, 10, 9, 0, tzinfo=timezone.utc),
            assignments=[
                make_assignment(
                    admin_id=3,
                    email="ops@example.com",
                    assigned_at=datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc),
                )
            ],
            threads=[
                make_thread(
                    [
                        make_message(
                            direction="outbound",
                            created_at=datetime(2026, 4, 10, 14, 0, tzinfo=timezone.utc),
                            author_admin_id=3,
                        )
                    ]
                )
            ],
        )

        report = reporting_crud.build_operations_report(
            [prior_request, repeat_request, new_request],
            filters=self.filters,
        )

        repeat_row = next(row for row in report.repeat_customer_breakdown if row.key == "repeat")
        new_row = next(row for row in report.repeat_customer_breakdown if row.key == "new")
        self.assertEqual(repeat_row.value, 1)
        self.assertEqual(new_row.value, 1)
        self.assertEqual(report.response_times.first_handled_samples, 2)
        self.assertEqual(report.response_times.first_customer_response_samples, 2)
        self.assertAlmostEqual(report.response_times.first_handled_average_hours or 0, 1.5)
        self.assertAlmostEqual(report.response_times.first_customer_response_average_hours or 0, 4.0)

    def test_build_operations_report_tracks_workload_overdue_and_unread(self):
        admin_id = 7
        now = datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc)
        open_request = make_request(
            status="in_progress",
            opened_at=datetime(2026, 4, 6, 8, 0, tzinfo=timezone.utc),
            due_at=now - timedelta(days=1),
            assignments=[
                make_assignment(
                    admin_id=admin_id,
                    email="owner@example.com",
                    assigned_at=datetime(2026, 4, 6, 9, 0, tzinfo=timezone.utc),
                )
            ],
            inbox_states=[
                SimpleNamespace(
                    admin_user_id=admin_id,
                    last_read_at=datetime(2026, 4, 7, 8, 0, tzinfo=timezone.utc),
                )
            ],
            threads=[
                make_thread(
                    [
                        make_message(
                            direction="inbound",
                            created_at=datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc),
                        )
                    ]
                )
            ],
            last_customer_message_at=datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc),
        )
        completed_request = make_request(
            status="completed",
            opened_at=datetime(2026, 4, 2, 8, 0, tzinfo=timezone.utc),
            assignments=[
                make_assignment(
                    admin_id=admin_id,
                    email="owner@example.com",
                    assigned_at=datetime(2026, 4, 2, 9, 0, tzinfo=timezone.utc),
                )
            ],
            status_history=[
                make_status_history(
                    old_status="in_progress",
                    new_status="completed",
                    created_at=datetime(2026, 4, 7, 14, 0, tzinfo=timezone.utc),
                )
            ],
        )

        report = reporting_crud.build_operations_report(
            [open_request, completed_request],
            filters=ReportFiltersOut(
                **{
                    "from": date(2026, 4, 1),
                    "to": date(2026, 4, 8),
                    "grain": "day",
                }
            ),
        )

        workload_row = report.staff_workload[0]
        self.assertEqual(workload_row.admin_id, admin_id)
        self.assertEqual(workload_row.active_open_assignments, 1)
        self.assertEqual(workload_row.unread_count, 1)
        self.assertEqual(workload_row.overdue_count, 1)
        self.assertEqual(workload_row.completions_in_range, 1)

    def test_build_content_activity_report_only_keeps_supported_actions(self):
        logs = [
            SimpleNamespace(
                actor_email="admin@example.com",
                action="page.publish",
                target_type="page",
                created_at=datetime(2026, 4, 6, 10, 0, tzinfo=timezone.utc),
            ),
            SimpleNamespace(
                actor_email="editor@example.com",
                action="blog_post.submit_review",
                target_type="blog_post",
                created_at=datetime(2026, 4, 6, 11, 0, tzinfo=timezone.utc),
            ),
            SimpleNamespace(
                actor_email="admin@example.com",
                action="testimonial.delete",
                target_type="testimonial",
                created_at=datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc),
            ),
        ]

        report = reporting_crud.build_content_activity_report(logs, filters=self.filters)

        self.assertEqual(len(report.rows), 2)
        self.assertEqual({row.action for row in report.rows}, {"publish", "submit"})


class PrivacyCrudTests(IsolatedAsyncioTestCase):
    def test_build_consent_state_defaults_to_necessary_only(self):
        result = privacy_crud.build_consent_state(
            consent_log=None,
            policy_versions=PrivacyPolicyVersions(
                privacy_policy="2026-04-v1",
                cookie_notice="2026-04-v1",
                data_rights_notice="2026-04-v1",
            ),
        )

        self.assertFalse(result.consent_recorded)
        self.assertTrue(result.categories.necessary)
        self.assertFalse(result.categories.preferences)

    def test_build_privacy_request_list_response_tracks_total_pages(self):
        response = privacy_crud.build_privacy_request_list_response(
            [],
            page=2,
            limit=10,
            total=23,
        )

        self.assertEqual(response.page, 2)
        self.assertEqual(response.total_pages, 3)

    async def test_purge_expired_refresh_sessions_returns_deleted_count(self):
        db = SimpleNamespace(
            execute=AsyncMock(return_value=SimpleNamespace(rowcount=3)),
            commit=AsyncMock(),
        )

        deleted = await admin_crud.purge_expired_refresh_sessions(
            db,
            now=datetime(2026, 4, 6, 12, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(deleted, 3)
        db.commit.assert_awaited_once()

    def test_role_permission_codes_include_reports_and_exclude_privacy_manage_for_viewer(self):
        viewer_permissions = get_role_permission_codes("viewer")

        self.assertIn("report.read", viewer_permissions)
        self.assertNotIn("privacy_request.manage", viewer_permissions)
