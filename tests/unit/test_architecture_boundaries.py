"""Executable dependency rules for the application architecture."""

import ast
from pathlib import Path

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
    _assert_no_imports(
        "api",
        (
            "app.adapters",
            "app.core.connectors.ssh",
            "app.di",
            "app.models",
            "app.repositories",
        ),
    )


def test_repositories_do_not_depend_on_transport_or_services() -> None:
    """Persistence implementations must not call outward layers."""
    _assert_no_imports("repositories", ("app.api", "app.services"))


def test_node_metrics_use_case_depends_on_persistence_port() -> None:
    """Remote metrics collection must not depend on repository implementations."""
    violations = [
        module
        for path, module in _imports_in("services")
        if path.name == "node_metrics_service.py"
        and (module == "app.repositories" or module.startswith("app.repositories."))
    ]
    assert not violations


def test_node_management_use_case_depends_on_application_ports() -> None:
    """Node management must not know transport or persistence implementations."""
    forbidden = (
        "app.adapters",
        "app.models",
        "app.repositories",
        "app.schemas",
        "app.core.security",
        "app.core.ssh_utils",
        "sqlalchemy",
    )
    violations = [
        module
        for module in _imports_in_file(
            APP_ROOT / "services" / "node_management_service.py"
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
        "sqlalchemy",
    )
    violations = [
        module
        for module in _imports_in_file(
            APP_ROOT / "services" / "node_command_service.py"
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
        "sqlalchemy",
    )
    violations = [
        module
        for module in _imports_in_file(
            APP_ROOT / "services" / "node_bulk_command_service.py"
        )
        if any(
            module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden
        )
    ]
    assert not violations


def test_models_are_persistence_only() -> None:
    """ORM models may only depend on other ORM model modules."""
    violations = [
        f"{path.relative_to(APP_ROOT.parent)} -> {module}"
        for path, module in _imports_in("models")
        if not (module == "app.models" or module.startswith("app.models."))
    ]
    assert not violations, "Forbidden model dependencies:\n" + "\n".join(violations)
