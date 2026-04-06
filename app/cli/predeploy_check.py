from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.core.config import settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Exxonim predeploy validation checks.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if media/documents roots or required scripts are missing.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    backend_root = Path(__file__).resolve().parents[2]
    required_paths = {
        "alembic.ini": backend_root / "alembic.ini",
        "emit_overdue_notifications.py": backend_root / "scripts" / "emit_overdue_notifications.py",
    }
    if args.strict:
        required_paths["media_root"] = settings.media_root_path
        required_paths["documents_root"] = settings.documents_root_path

    failures: list[str] = []
    for label, path in required_paths.items():
        if not path.exists():
            failures.append(f"Missing required path: {label} -> {path}")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1

    print("Predeploy validation passed.")
    print(f"APP_ENV={settings.APP_ENV}")
    print(f"PUBLIC_SITE_URL={settings.PUBLIC_SITE_URL}")
    print(f"ADMIN_SITE_URL={settings.ADMIN_SITE_URL}")
    print(f"MEDIA_ROOT={settings.media_root_path}")
    print(f"DOCUMENTS_ROOT={settings.documents_root_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
