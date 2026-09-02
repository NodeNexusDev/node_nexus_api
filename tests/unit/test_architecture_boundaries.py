"""Executable dependency rules for the application architecture."""

import ast
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).parents[2] / "app"


def _imports_in_file(path: Path) -> list[str]:
    """Collect all absolute imports from one Python file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
        elif isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
    return imports


def _imports_in(package: str) -> list[tuple[Path, str]]:
    """Collect absolute app imports from one package."""
    imports: list[tuple[Path, str]] = []
    for path in sorted((APP_ROOT / package).rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module == "app" or node.module.startswith("app."):
                    imports.append((path, node.module))
            elif isinstance(node, ast.Import):
                imports.extend(
                    (path, alias.name)
                    for alias in node.names
                    if alias.name == "app" or alias.name.startswith("app.")
                )
    return imports


def _assert_no_imports(package: str, forbidden: tuple[str, ...]) -> None:
    """Assert that a package does not depend on forbidden app namespaces."""

    def is_forbidden(module: str) -> bool:
        for prefix in forbidden:
            if module == prefix or module.startswith(f"{prefix}."):
                return True
        return False

    violations = [
        f"{path.relative_to(APP_ROOT.parent)} -> {module}"
        for path, module in _imports_in(package)
        if is_forbidden(module)
    ]
    assert not violations, "Forbidden architecture dependencies:\n" + "\n".join(
        violations
    )


def test_application_depends_only_on_inward_contracts() -> None:
    """Application code must not know transport or persistence implementations."""
    _assert_no_imports(
        "application",
        (
            "app.api",
            "app.adapters",
            "app.di",
            "app.models",
            "app.repositories",
            "app.schemas",
            "app.services",
        ),
    )


def test_api_does_not_access_persistence_or_concrete_connectors() -> None:
    """Transport adapters must delegate persistence and remote operations."""
    violations = [
        f"{path.relative_to(APP_ROOT.parent)} -> {module}"
        for path, module in _imports_in("api")
        if any(
            module == prefix or module.startswith(f"{prefix}.")
            for prefix in (
                "app.adapters",
                "app.adapters.runtime.ssh",
                "app.di",
                "app.models",
                "app.repositories",
            )
        )
    ]
    assert not violations, "Forbidden architecture dependencies:\n" + "\n".join(
        violations
    )


def test_repositories_do_not_depend_on_transport_or_services() -> None:
    """Persistence implementations must not call outward layers."""
    _assert_no_imports("repositories", ("app.api", "app.services"))


def test_node_metrics_use_case_depends_on_persistence_port() -> None:
    """Remote metrics collection must not depend on repository implementations."""
    forbidden = (
        "app.core.connectors",
        "app.core.security",
        "app.core.ssh_utils",
        "app.repositories",
    )
    violations = [
        module
        for module in _imports_in_file(
            APP_ROOT / "application" / "services" / "node_metrics_service.py"
        )
        if any(
            module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden
        )
    ]
    assert not violations


def test_node_management_use_case_depends_on_application_ports() -> None:
    """Node management must not know transport or persistence implementations."""
    forbidden = (
        "app.adapters",
        "app.models",
        "app.repositories",
        "app.schemas",
        "app.services",
        "app.core.security",
        "app.core.ssh_utils",
        "sqlalchemy",
    )
    violations = [
        module
        for module in _imports_in_file(
            APP_ROOT / "application" / "services" / "node_management_service.py"
        )
        if any(
            module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden
        )
    ]
    assert not violations


def test_node_command_use_case_does_not_depend_on_persistence() -> None:
    """Single-node remote commands must use application persistence ports."""
    forbidden = (
        "app.adapters",
        "app.models",
        "app.repositories",
        "app.schemas",
        "app.services",
        "app.core.connectors",
        "app.core.security",
        "app.core.ssh_utils",
        "sqlalchemy",
    )
    violations = [
        module
        for module in _imports_in_file(
            APP_ROOT / "application" / "services" / "node_command_service.py"
        )
        if any(
            module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden
        )
    ]
    assert not violations


def test_node_bulk_command_workers_do_not_depend_on_persistence() -> None:
    """Bulk remote workers must receive DTOs resolved through application ports."""
    forbidden = (
        "app.adapters",
        "app.models",
        "app.repositories",
        "app.schemas",
        "app.services",
        "app.core.connectors",
        "app.core.security",
        "app.core.ssh_utils",
        "sqlalchemy",
    )
    violations = [
        module
        for module in _imports_in_file(
            APP_ROOT / "application" / "services" / "node_bulk_command_service.py"
        )
        if any(
            module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden
        )
    ]
    assert not violations


@pytest.mark.parametrize(
    "filename",
    ("command_management_service.py", "command_execution_service.py"),
)
def test_command_services_depend_only_on_inward_facing_modules(
    filename: str,
) -> None:
    """Focused command services must depend only on inward-facing modules."""
    imports = _imports_in_file(APP_ROOT / "application" / "services" / filename)
    forbidden = (
        "app.adapters",
        "app.core.connectors",
        "app.core.security",
        "app.core.ssh_utils",
        "app.models",
        "app.repositories",
        "app.schemas",
        "sqlalchemy",
    )
    violations = [
        module
        for module in imports
        if any(
            module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden
        )
    ]
    assert not violations


@pytest.mark.parametrize(
    "filename",
    (
        "script_management_service.py",
        "script_history_service.py",
    ),
)
def test_focused_script_services_depend_only_on_inward_facing_modules(
    filename: str,
) -> None:
    """Focused script services must not know transport or persistence details."""
    imports = _imports_in_file(APP_ROOT / "application" / "services" / filename)
    forbidden = (
        "app.adapters",
        "app.models",
        "app.repositories",
        "app.schemas",
        "sqlalchemy",
    )
    violations = [
        module
        for module in imports
        if any(
            module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden
        )
    ]
    assert not violations


def test_legacy_script_service_is_removed() -> None:
    """Scripts must resolve focused use cases instead of a repository façade."""
    assert not (APP_ROOT / "services" / "script_service.py").exists()


def test_docker_command_runner_uses_only_application_ports() -> None:
    """Docker runner must not know repositories, crypto, or SSH implementations."""
    imports = _imports_in_file(
        APP_ROOT / "application" / "services" / "docker" / "command_runner.py"
    )
    forbidden = (
        "app.adapters",
        "app.core.connectors",
        "app.core.security",
        "app.core.ssh_utils",
        "app.repositories",
    )
    assert not [
        module
        for module in imports
        if any(
            module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden
        )
    ]


def test_production_composition_does_not_import_docker_facade() -> None:
    """Composition root must expose focused Docker use cases only."""
    imports = _imports_in_file(APP_ROOT / "di" / "providers.py")
    assert "app.application.services.docker_service" not in imports
    assert not (APP_ROOT / "services" / "docker_service.py").exists()


def test_docker_use_cases_do_not_depend_on_transport_or_infrastructure() -> None:
    """Focused Docker services must depend inward through application ports."""
    forbidden = (
        "app.adapters",
        "app.core.connectors",
        "app.repositories",
        "app.schemas",
    )
    violations = [
        f"{path.name} -> {module}"
        for path, module in _imports_in("application/services/docker")
        if any(
            module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden
        )
    ]
    assert not violations


def test_config_service_depends_on_persistence_ports() -> None:
    """Configuration orchestration must not know SQLAlchemy DAO implementations."""
    imports = _imports_in_file(
        APP_ROOT / "application" / "services" / "config_service.py"
    )
    forbidden = ("app.adapters", "app.models", "app.repositories", "sqlalchemy")
    assert not [
        module
        for module in imports
        if any(
            module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden
        )
    ]


def test_models_are_persistence_only() -> None:
    """ORM models may only depend on other ORM model modules."""
    violations = [
        f"{path.relative_to(APP_ROOT.parent)} -> {module}"
        for path, module in _imports_in("models")
        if not (module == "app.models" or module.startswith("app.models."))
    ]
    assert not violations, "Forbidden model dependencies:\n" + "\n".join(violations)


def test_api_does_not_access_private_service_attributes() -> None:
    """API layer must not reach into service private attributes."""
    import re

    pattern = re.compile(r"service\._\w+")
    violations: list[str] = []
    for path in sorted((APP_ROOT / "api").rglob("*.py")):
        content = path.read_text(encoding="utf-8")
        for match in pattern.finditer(content):
            violations.append(f"{path.relative_to(APP_ROOT.parent)}:{match.group()}")
    assert not violations, "Private attribute access in API:\n" + "\n".join(violations)


def test_core_does_not_import_infrastructure() -> None:
    """Core layer must not depend on FastAPI, SQLAlchemy, or OpenTelemetry."""
    forbidden = ("fastapi", "sqlalchemy", "opentelemetry", "dishka")
    violations = [
        f"{path.relative_to(APP_ROOT.parent)} -> {module}"
        for path, module in _imports_in("core")
        if any(module == p or module.startswith(f"{p}.") for p in forbidden)
    ]
    assert not violations, "Core imports infrastructure:\n" + "\n".join(violations)
