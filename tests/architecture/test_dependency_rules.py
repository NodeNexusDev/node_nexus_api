"""Executable dependency rules for the modular monolith."""

import ast
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).parents[2] / "app"

FORBIDDEN_IMPORTS: dict[str, tuple[str, ...]] = {
    "models": ("app.api", "app.services", "app.repositories"),
    "core": ("app.api",),
    "repositories": ("app.api", "app.services"),
    "services": ("app.api",),
    "api": ("app.repositories", "app.models", "app.di.container"),
    "application": ("fastapi", "sqlalchemy"),
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


@pytest.mark.parametrize(
    ("layer", "forbidden"),
    FORBIDDEN_IMPORTS.items(),
    ids=FORBIDDEN_IMPORTS,
)
def test_layer_does_not_import_forbidden_dependencies(
    layer: str, forbidden: tuple[str, ...]
) -> None:
    violations: list[str] = []
    for path in (APP_ROOT / layer).rglob("*.py"):
        for imported in _imports(path):
            if any(
                imported == prefix or imported.startswith(f"{prefix}.")
                for prefix in forbidden
            ):
                violations.append(f"{path.relative_to(APP_ROOT)} -> {imported}")

    assert not violations, "Forbidden dependencies:\n" + "\n".join(violations)


def test_api_does_not_construct_services_or_repositories() -> None:
    violations: list[str] = []
    for path in (APP_ROOT / "api").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", "")
            if name.endswith(("Service", "Repository")):
                violations.append(f"{path.relative_to(APP_ROOT)}:{node.lineno} {name}")

    assert not violations, "Manual dependency construction:\n" + "\n".join(violations)


def test_docker_router_delegates_domain_errors_to_global_handler() -> None:
    """Docker endpoints must not maintain a second error-to-HTTP registry."""
    path = APP_ROOT / "api" / "v1" / "docker.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    caught_names = {
        getattr(handler.type, "id", "")
        for node in ast.walk(tree)
        if isinstance(node, ast.Try)
        for handler in node.handlers
        if handler.type is not None
    }
    assert not caught_names & {
        "DomainError",
        "DockerError",
        "DockerValidationError",
        "NodeNotFoundError",
    }
