from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.core.rbac import PERMISSION_DEFINITIONS, ROLE_CODES, ROLE_PERMISSION_MAP  # noqa: E402
from app.models import AdminUser, Permission, Role, RolePermission  # noqa: E402

ROLE_METADATA = {
    "superuser": {
        "name": "Superuser",
        "description": "Full platform access, including role and permission administration.",
    },
    "administrator": {
        "name": "Administrator",
        "description": "Operational administration, publishing, and settings management.",
    },
    "editor": {
        "name": "Editor",
        "description": "Creates and updates draft content, then submits it for review.",
    },
    "reviewer": {
        "name": "Reviewer",
        "description": "Reviews submitted content and can request changes.",
    },
    "viewer": {
        "name": "Viewer",
        "description": "Read-only back-office access.",
    },
}


async def seed_roles_permissions() -> None:
    async with AsyncSessionLocal() as db:
        desired_permission_codes = {
            definition["code"]
            for definition in PERMISSION_DEFINITIONS
        }
        existing_roles = {
            role.code: role
            for role in (
                await db.execute(
                    select(Role).options(selectinload(Role.granted_permissions)).order_by(Role.id.asc())
                )
            )
            .scalars()
            .all()
        }
        existing_permissions = {
            permission.code: permission
            for permission in (await db.execute(select(Permission))).scalars().all()
        }

        for role_code in ROLE_CODES:
            metadata = ROLE_METADATA[role_code]
            role = existing_roles.get(role_code)
            if role is None:
                role = Role(
                    code=role_code,
                    name=metadata["name"],
                    description=metadata["description"],
                    is_system=True,
                )
                db.add(role)
                existing_roles[role_code] = role
            else:
                role.name = metadata["name"]
                role.description = metadata["description"]
                role.is_system = True
                db.add(role)

        for definition in PERMISSION_DEFINITIONS:
            permission = existing_permissions.get(definition["code"])
            if permission is None:
                permission = Permission(**definition)
                db.add(permission)
                existing_permissions[definition["code"]] = permission
            else:
                permission.module = definition["module"]
                permission.action = definition["action"]
                permission.description = definition["description"]
                db.add(permission)

        stale_permissions = [
            permission
            for code, permission in existing_permissions.items()
            if code not in desired_permission_codes
        ]
        if stale_permissions:
            stale_permission_ids = [permission.id for permission in stale_permissions if permission.id is not None]
            if stale_permission_ids:
                await db.execute(delete(RolePermission).where(RolePermission.permission_id.in_(stale_permission_ids)))
            await db.flush()
            for permission in stale_permissions:
                await db.delete(permission)
                existing_permissions.pop(permission.code, None)

        await db.flush()

        desired_pairs = {
            (existing_roles[role_code].id, existing_permissions[permission_code].id)
            for role_code, permission_codes in ROLE_PERMISSION_MAP.items()
            for permission_code in permission_codes
        }
        existing_pairs = {
            (row.role_id, row.permission_id)
            for row in (await db.execute(select(RolePermission))).scalars().all()
        }

        for role_id, permission_id in desired_pairs - existing_pairs:
            db.add(RolePermission(role_id=role_id, permission_id=permission_id))

        for role_id, permission_id in existing_pairs - desired_pairs:
            await db.execute(
                delete(RolePermission).where(
                    RolePermission.role_id == role_id,
                    RolePermission.permission_id == permission_id,
                )
            )

        admins = (
            await db.execute(
                select(AdminUser)
                .options(selectinload(AdminUser.assigned_roles))
                .order_by(AdminUser.created_at.asc(), AdminUser.id.asc())
            )
        ).scalars().all()

        if admins:
            superuser_role = existing_roles["superuser"]
            administrator_role = existing_roles["administrator"]
            has_superuser = any("superuser" in admin.roles for admin in admins)

            for index, admin in enumerate(admins):
                if admin.assigned_roles:
                    continue

                if not has_superuser and index == 0:
                    admin.assigned_roles = [superuser_role]
                    has_superuser = True
                else:
                    admin.assigned_roles = [administrator_role]
                db.add(admin)

        await db.commit()

        print(
            f"Seeded {len(existing_roles)} roles, {len(existing_permissions)} permissions, "
            f"and bootstrapped {len(admins)} admin accounts."
        )


if __name__ == "__main__":
    asyncio.run(seed_roles_permissions())
