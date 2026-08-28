"""Fixtures for E2E tests with full Docker stack."""

import subprocess
from collections.abc import AsyncGenerator, Generator
from dataclasses import dataclass
from pathlib import Path

import asyncpg
import httpx2 as httpx
import pytest
from pytest_docker.plugin import Services, get_cleanup_command

from tests.e2e.helpers.resources import UniqueResourceFactory, resource_factory
from tests.e2e.helpers.service_controller import DockerServiceController
from tests.e2e.helpers.websocket import WebSocketClientFactory
from tests.e2e.settings import MASTER_API_KEY
from tests.helpers import is_port_open
from tests.typing import as_typed_mock

_MASTER_API_KEY = MASTER_API_KEY

_SSH_KEYS_DIR = Path("tests/ssh-keys")


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add E2E-specific CLI options."""
    group = parser.getgroup("e2e", "E2E test options")
    group.addoption(
        "--keep-stack",
        action="store_true",
        default=False,
        help="Keep the Docker Compose stack running after tests for inspection.",
    )


@pytest.fixture(scope="session")
def docker_cleanup(request: pytest.FixtureRequest) -> list[str] | str | None:
    """Return cleanup command or skip teardown when --keep-stack is passed."""
    if request.config.getoption("--keep-stack"):
        return []
    return get_cleanup_command()


_E2E_COMPOSE_FILES = (
    "docker-compose.e2e.yml",
    "docker-compose.e2e-ratelimit.yml",
    "docker-compose.e2e-timeout.yml",
)


@pytest.fixture(scope="session", autouse=True)
def _cleanup_orphaned_containers() -> None:
    """Remove orphaned E2E containers and networks from previous failed runs."""
    try:
        result = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        names = result.stdout.strip().split("\n") if result.stdout.strip() else []
        for name in names:
            if "e2e" in name or "pytest" in name:
                subprocess.run(
                    ["docker", "rm", "-f", name],
                    capture_output=True,
                    timeout=10,
                )
        result = subprocess.run(
            ["docker", "network", "ls", "--format", "{{.Name}}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        networks = result.stdout.strip().split("\n") if result.stdout.strip() else []
        for net in networks:
            if "e2e" in net or "pytest" in net:
                subprocess.run(
                    ["docker", "network", "rm", net],
                    capture_output=True,
                    timeout=10,
                )
    except (subprocess.SubprocessError, OSError):
        pass  # best effort cleanup


@dataclass(frozen=True)
class ServicePorts:
    api_host: str
    api_port: int
    ssh_host: str
    ssh_port: int
    db_host: str
    db_port: int
    dind_host: str
    dind_port: int


@pytest.fixture(scope="session", autouse=True)
def _generate_ssh_keys() -> None:
    """Generate test SSH key pairs before Docker stack starts.

    Keys are written to tests/ssh-keys/ and mounted into containers via
    docker-compose. The Makefile targets run this automatically; this
    fixture handles direct ``pytest`` invocations.
    """
    _SSH_KEYS_DIR.mkdir(parents=True, exist_ok=True)
    key = _SSH_KEYS_DIR / "test-key"
    enc = _SSH_KEYS_DIR / "test-key-enc"
    if not key.exists():
        subprocess.run(
            [
                "ssh-keygen",
                "-t",
                "ed25519",
                "-f",
                str(key),
                "-N",
                "",
                "-C",
                "e2e-unencrypted",
            ],
            check=True,
            capture_output=True,
        )
        key.chmod(0o644)
    if not enc.exists():
        subprocess.run(
            [
                "ssh-keygen",
                "-t",
                "ed25519",
                "-f",
                str(enc),
                "-N",
                "keypass123",
                "-C",
                "e2e-encrypted",
            ],
            check=True,
            capture_output=True,
        )
        enc.chmod(0o644)


@pytest.fixture(scope="session")
def docker_compose_file() -> str:
    return "tests/docker-compose.e2e.yml"


@pytest.fixture(scope="session")
def service_ports(docker_ip: str, docker_services: Services) -> ServicePorts:
    api_port = docker_services.port_for("api", 8000)
    ssh_port = docker_services.port_for("ssh-server", 2222)
    db_port = docker_services.port_for("db", 5432)
    dind_port = docker_services.port_for("dind", 2375)

    def stack_is_ready() -> bool:
        if not all(
            is_port_open(docker_ip, port)
            for port in (api_port, ssh_port, db_port, dind_port)
        ):
            return False
        try:
            response = httpx.get(
                f"http://{docker_ip}:{api_port}/ready",
                headers={"X-API-Key": _MASTER_API_KEY},
                timeout=2.0,
            )
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    docker_services.wait_until_responsive(
        check=stack_is_ready,
        timeout=120.0,
        pause=1.0,
    )
    return ServicePorts(
        api_host=docker_ip,
        api_port=api_port,
        ssh_host=docker_ip,
        ssh_port=ssh_port,
        db_host=docker_ip,
        db_port=db_port,
        dind_host=docker_ip,
        dind_port=dind_port,
    )


@pytest.fixture(scope="session")
def api_base_url(service_ports: ServicePorts) -> str:
    """Return the externally reachable E2E API base URL."""
    return f"http://{service_ports.api_host}:{service_ports.api_port}"


@pytest.fixture(scope="session")
def websocket_base_url(service_ports: ServicePorts) -> str:
    """Return the externally reachable E2E WebSocket base URL."""
    return f"ws://{service_ports.api_host}:{service_ports.api_port}"


@pytest.fixture(scope="session")
def websocket_client(websocket_base_url: str) -> WebSocketClientFactory:
    """Return WebSocket connection builders for both authentication modes."""
    return WebSocketClientFactory(websocket_base_url)


@pytest.fixture(scope="session")
def e2e_client(api_base_url: str) -> Generator[httpx.Client]:
    default_headers = {"X-API-Key": _MASTER_API_KEY}
    with httpx.Client(
        base_url=api_base_url, timeout=30.0, headers=default_headers
    ) as client:
        yield client


@pytest.fixture(scope="session")
def e2e_client_no_auth(api_base_url: str) -> Generator[httpx.Client]:
    with httpx.Client(base_url=api_base_url, timeout=30.0) as client:
        yield client


@pytest.fixture
async def async_e2e_client(api_base_url: str) -> AsyncGenerator[httpx.AsyncClient]:
    """Yield an authenticated async client isolated to one E2E test."""
    async with httpx.AsyncClient(
        base_url=api_base_url,
        timeout=30.0,
        headers={"X-API-Key": _MASTER_API_KEY},
    ) as client:
        yield client


@pytest.fixture
async def postgres_connection(
    service_ports: ServicePorts,
) -> AsyncGenerator[asyncpg.Connection]:
    """Yield a direct PostgreSQL connection for durable-state assertions."""
    connection = as_typed_mock(
        asyncpg.Connection,
        await asyncpg.connect(
            host=service_ports.db_host,
            port=service_ports.db_port,
            user="postgres",
            password="postgres",
            database="node_nexus_e2e",
        ),
    )
    try:
        yield connection
    finally:
        await connection.close()


_E2E_MARKERS = frozenset(
    {
        "docker",
        "e2e_smoke",
        "e2e_scheduler",
        "e2e_resilience",
        "e2e_migration",
        "e2e_slow",
    }
)


@pytest.fixture(autouse=True)
async def e2e_db_isolation(
    request: pytest.FixtureRequest,
    postgres_connection: asyncpg.Connection,
    api_base_url: str,
) -> AsyncGenerator[None]:
    """Truncate mutable tables after each E2E test for full DB isolation.

    Background workers (audit outbox delivery and the script scheduler) are
    paused before truncation and resumed afterwards so that their concurrent
    locks cannot deadlock with the TRUNCATE statement.
    """
    yield
    if not any(request.node.get_closest_marker(marker) for marker in _E2E_MARKERS):
        return
    async with httpx.AsyncClient(
        base_url=api_base_url,
        timeout=30.0,
        headers={"X-API-Key": _MASTER_API_KEY},
    ) as client:
        await client.post("/api/v1/internal/e2e/pause-background")
        try:
            await postgres_connection.execute(
                """
                TRUNCATE audit_logs, audit_outbox, script_executions,
                         command_executions, script_schedules, scripts, commands,
                         nodes, node_status_history, api_keys, notes, favorites
                RESTART IDENTITY CASCADE
                """
            )
        finally:
            await client.post("/api/v1/internal/e2e/resume-background")


@pytest.fixture(scope="session", autouse=True)
def docker_service_controller(
    docker_compose_project_name: str,
) -> DockerServiceController:
    """Return a controller scoped to the exact pytest-docker project."""
    return DockerServiceController(
        compose_file=Path("tests/docker-compose.e2e.yml").resolve(),
        project_name=docker_compose_project_name,
    )


@pytest.fixture
def e2e_resources(e2e_client: httpx.Client) -> Generator[UniqueResourceFactory]:
    """Yield unique resource helpers with deterministic LIFO cleanup."""
    with resource_factory(e2e_client) as factory:
        yield factory


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[object]):
    """Attach full-stack service logs to failed E2E test reports."""
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or not report.failed:
        return

    if not isinstance(item, pytest.Function):
        return
    controller = item.funcargs.get("docker_service_controller")
    if not isinstance(controller, DockerServiceController):
        return

    for service in ("api", "db", "ssh-server", "dind"):
        try:
            logs = controller.logs(service)
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            logs = f"Unable to collect {service} logs: {type(exc).__name__}: {exc}"
        report.sections.append((f"docker logs: {service}", logs))
