from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

from app.models import Role


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "create_admin.py"
SCRIPT_SPEC = importlib.util.spec_from_file_location("create_admin_script", SCRIPT_PATH)
assert SCRIPT_SPEC is not None and SCRIPT_SPEC.loader is not None
create_admin_script = importlib.util.module_from_spec(SCRIPT_SPEC)
SCRIPT_SPEC.loader.exec_module(create_admin_script)


class AsyncSessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class CreateAdminScriptTests(IsolatedAsyncioTestCase):
    def test_normalize_optional_name(self):
        self.assertIsNone(create_admin_script.normalize_optional_name(None))
        self.assertIsNone(create_admin_script.normalize_optional_name("   "))
        self.assertEqual(
            create_admin_script.normalize_optional_name("  Local Demo Admin  "),
            "Local Demo Admin",
        )

    async def test_create_or_update_admin_creates_new_admin(self):
        session = SimpleNamespace(
            add=Mock(),
            commit=AsyncMock(),
            refresh=AsyncMock(),
        )
        role = Role(
            code="administrator",
            name="Administrator",
            description="Operational administrator",
            is_system=True,
        )

        with (
            patch.object(
                create_admin_script,
                "AsyncSessionLocal",
                return_value=AsyncSessionContext(session),
            ),
            patch.object(
                create_admin_script.admin_crud,
                "get_role_by_code",
                AsyncMock(return_value=role),
            ),
            patch.object(
                create_admin_script.admin_crud,
                "get_admin_by_email",
                AsyncMock(return_value=None),
            ),
            patch.object(
                create_admin_script,
                "get_password_hash",
                return_value="hashed-password",
            ),
        ):
            admin = await create_admin_script.create_or_update_admin(
                " Demo.Admin@Exxonim.Local ",
                "Admin123!",
                full_name="  Local Demo Admin  ",
                role="administrator",
                upsert=True,
            )

        self.assertEqual(admin.email, "demo.admin@exxonim.local")
        self.assertEqual(admin.full_name, "Local Demo Admin")
        self.assertTrue(admin.is_active)
        self.assertEqual(admin.hashed_password, "hashed-password")
        self.assertEqual(admin.assigned_roles, [role])
        session.add.assert_called_once_with(admin)
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(admin)

    async def test_create_or_update_admin_updates_existing_admin_when_upsert_enabled(self):
        session = SimpleNamespace(
            add=Mock(),
            commit=AsyncMock(),
            refresh=AsyncMock(),
        )
        role = Role(
            code="administrator",
            name="Administrator",
            description="Operational administrator",
            is_system=True,
        )
        existing_admin = SimpleNamespace(
            email="demo.admin@exxonim.local",
            full_name=None,
            hashed_password="old-hash",
            is_active=False,
            assigned_roles=[],
        )

        with (
            patch.object(
                create_admin_script,
                "AsyncSessionLocal",
                return_value=AsyncSessionContext(session),
            ),
            patch.object(
                create_admin_script.admin_crud,
                "get_role_by_code",
                AsyncMock(return_value=role),
            ),
            patch.object(
                create_admin_script.admin_crud,
                "get_admin_by_email",
                AsyncMock(return_value=existing_admin),
            ),
            patch.object(
                create_admin_script,
                "get_password_hash",
                return_value="updated-hash",
            ),
        ):
            admin = await create_admin_script.create_or_update_admin(
                "demo.admin@exxonim.local",
                "Admin123!",
                full_name="Local Demo Admin",
                role="administrator",
                upsert=True,
            )

        self.assertIs(admin, existing_admin)
        self.assertEqual(admin.full_name, "Local Demo Admin")
        self.assertEqual(admin.hashed_password, "updated-hash")
        self.assertTrue(admin.is_active)
        self.assertEqual(admin.assigned_roles, [role])
        session.add.assert_called_once_with(existing_admin)
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(existing_admin)

    async def test_create_or_update_admin_rejects_existing_admin_without_upsert(self):
        session = SimpleNamespace(
            add=Mock(),
            commit=AsyncMock(),
            refresh=AsyncMock(),
        )
        existing_admin = SimpleNamespace(email="demo.admin@exxonim.local")

        with (
            patch.object(
                create_admin_script,
                "AsyncSessionLocal",
                return_value=AsyncSessionContext(session),
            ),
            patch.object(
                create_admin_script.admin_crud,
                "get_role_by_code",
                AsyncMock(
                    return_value=Role(
                        code="administrator",
                        name="Administrator",
                        description="Operational administrator",
                        is_system=True,
                    )
                ),
            ),
            patch.object(
                create_admin_script.admin_crud,
                "get_admin_by_email",
                AsyncMock(return_value=existing_admin),
            ),
        ):
            with self.assertRaises(SystemExit):
                await create_admin_script.create_or_update_admin(
                    "demo.admin@exxonim.local",
                    "Admin123!",
                    role="administrator",
                )
