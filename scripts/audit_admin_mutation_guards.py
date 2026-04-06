from __future__ import annotations

import ast
from pathlib import Path


ADMIN_ROUTER_PATH = Path(__file__).resolve().parents[1] / "app" / "routers" / "admin.py"
EXEMPT_ROUTES = {
    "/auth/login",
    "/auth/refresh",
}
MUTATION_METHODS = {"post", "put", "patch", "delete"}
AUTH_GUARDS = {
    "get_active_refresh_session",
    "get_current_admin",
    "require_permission",
    "require_any_permission",
}
WRITE_GUARDS = {"require_csrf", "require_admin_api_key"}


def _decorated_route(definition: ast.AsyncFunctionDef) -> tuple[str, str] | None:
    for decorator in definition.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        if not isinstance(decorator.func, ast.Attribute):
            continue
        if not isinstance(decorator.func.value, ast.Name) or decorator.func.value.id != "router":
            continue

        method = decorator.func.attr
        if method not in MUTATION_METHODS:
            continue

        if not decorator.args or not isinstance(decorator.args[0], ast.Constant):
            continue

        route_path = decorator.args[0].value
        if not isinstance(route_path, str):
            continue

        return method, route_path

    return None


def _depends_target(argument: ast.arg, default: ast.expr) -> str | None:
    if not isinstance(default, ast.Call):
        return None
    if not isinstance(default.func, ast.Name) or default.func.id != "Depends":
        return None
    if not default.args:
        return None

    dependency = default.args[0]
    if isinstance(dependency, ast.Name):
        return dependency.id
    if isinstance(dependency, ast.Call) and isinstance(dependency.func, ast.Name):
        return dependency.func.id
    return None


def main() -> int:
    module = ast.parse(ADMIN_ROUTER_PATH.read_text())
    failures: list[str] = []

    for node in module.body:
        if not isinstance(node, ast.AsyncFunctionDef):
            continue

        route = _decorated_route(node)
        if route is None:
            continue

        _, route_path = route
        defaults = list(node.args.defaults)
        args = list(node.args.args)
        defaults_offset = len(args) - len(defaults)

        dependencies = {
            _depends_target(argument, default)
            for argument, default in zip(args[defaults_offset:], defaults)
        }
        dependencies.discard(None)

        if route_path not in EXEMPT_ROUTES and not dependencies.intersection(WRITE_GUARDS):
            failures.append(f"{route_path}: missing CSRF/write guard dependency")

        if route_path not in EXEMPT_ROUTES and not dependencies.intersection(AUTH_GUARDS):
            failures.append(f"{route_path}: missing auth/permission dependency")

    if failures:
        print("Admin mutation route audit failed:")
        for failure in failures:
            print(f" - {failure}")
        return 1

    print("Admin mutation route audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
