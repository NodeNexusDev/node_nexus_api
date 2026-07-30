"""Executable dependency rules for the modular monolith."""

import ast
import re
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).parents[2] / "app"

FORBIDDEN_IMPORTS: dict[str, tuple[str, ...]] = {
    "models": ("app.api", "app.services", "app.repositories"),
    "core": ("app.api",),
    "repositories": ("app.api", "app.services"),
    "api": ("app.repositories", "app.models", "app.di.container"),
    "application": (
        "app.api",
        "app.schemas",
        "app.models",
        "app.repositories",
        "app.adapters",
        "app.di",
        "app.services",
        "fastapi",
        "sqlalchemy",
        "dishka",
    ),
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


def test_application_boundaries_do_not_use_any() -> None:
    """Application contracts must describe values without unbounded Any."""
    violations = [
        str(path.relative_to(APP_ROOT))
        for path in (APP_ROOT / "application").rglob("*.py")
        if re.search(r"\bAny\b", path.read_text(encoding="utf-8"))
    ]
    assert not violations, "Unbounded application values:\n" + "\n".join(violations)


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


def test_docker_facade_is_removed_from_production() -> None:
    """Prevent the compatibility facade from returning to application code."""
    path = APP_ROOT / "services" / "docker_service.py"
    assert not path.exists()


def test_legacy_service_namespace_is_removed() -> None:
    """All application use cases belong to the application layer."""
    assert not list((APP_ROOT / "services").rglob("*.py"))


def test_legacy_generic_repository_contract_is_removed() -> None:
    """Persistence adapters must implement focused application ports."""
    assert not (APP_ROOT / "repositories" / "base.py").exists()


def test_legacy_repository_namespace_is_removed() -> None:
    """All SQLAlchemy DAOs belong to the outbound persistence adapter."""
    assert not list((APP_ROOT / "repositories").glob("*.py"))


@pytest.mark.parametrize(
    "relative_path",
    ["api/v1/websocket.py", "core/scheduler.py"],
)
def test_runtime_orchestration_does_not_import_global_container(
    relative_path: str,
) -> None:
    path = APP_ROOT / relative_path
    assert "app.di.container" not in _imports(path)


def test_app_resources_define_lifecycle_finalizers() -> None:
    source = (APP_ROOT / "di" / "providers.py").read_text(encoding="utf-8")
    assert "await engine.dispose()" in source
    assert "await scheduler.stop()" in source


def test_application_ports_have_explicit_dishka_bindings() -> None:
    """Composition root must identify port registrations explicitly."""
    path = APP_ROOT / "di" / "providers.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    port_factories = {
        "get_api_key_reader",
        "get_api_key_writer",
        "get_api_key_hasher",
        "get_script_execution_writer",
        "get_script_reader",
        "get_script_writer",
        "get_script_execution_reader",
        "get_script_definition_reader",
        "get_command_management_reader",
        "get_command_management_writer",
        "get_command_template_reader",
        "get_node_connection_reader",
        "get_node_management_reader",
        "get_node_management_writer",
        "get_node_status_writer",
        "get_schedule_reader",
        "get_schedule_writer",
        "get_audit_log_reader",
        "get_audit_log_writer",
        "get_configuration_exporter",
        "get_configuration_importer",
        "get_database_health_probe",
        "get_remote_connector_factory",
        "get_remote_streaming_connector_factory",
        "get_credential_cipher",
        "get_docker_runtime",
        "get_audit_event_sink",
        "get_job_scheduler_port",
    }
    factories = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in port_factories
    }

    missing = []
    for name in sorted(port_factories):
        factory = factories.get(name)
        if factory is None:
            missing.append(f"{name}: factory missing")
            continue
        has_explicit_binding = any(
            isinstance(decorator, ast.Call)
            and getattr(decorator.func, "id", "") == "provide"
            and any(keyword.arg == "provides" for keyword in decorator.keywords)
            for decorator in factory.decorator_list
        )
        if not has_explicit_binding:
            missing.append(f"{name}: provides=Port missing")

    assert not missing, "Implicit port bindings:\n" + "\n".join(missing)


@pytest.mark.parametrize(
    "relative_path",
    (
        "application/services/script_execution_service.py",
        "application/services/node_bulk_command_service.py",
        "application/services/docker/bulk_service.py",
    ),
)
def test_concurrent_remote_workers_cannot_import_persistence_state(
    relative_path: str,
) -> None:
    """Concurrent worker modules receive DTOs, never sessions, DAOs, or ORM."""
    path = APP_ROOT / relative_path
    source = path.read_text(encoding="utf-8")
    imports = _imports(path)
    forbidden = (
        "sqlalchemy",
        "app.models",
        "app.repositories",
        "app.adapters.persistence",
    )

    assert "asyncio.gather" in source
    assert not [
        imported
        for imported in imports
        if any(
            imported == prefix or imported.startswith(f"{prefix}.")
            for prefix in forbidden
        )
    ]
