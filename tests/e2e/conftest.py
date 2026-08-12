"""Fixtures for E2E tests with full Docker stack."""

import subprocess
from collections.abc import AsyncGenerator, Generator
from dataclasses import dataclass
from pathlib import Path

import asyncpg
import httpx2 as httpx
import pytest
from pytest_docker.plugin import Services

from tests.e2e.helpers.resources import UniqueResourceFactory, resource_factory
from tests.e2e.helpers.service_controller import DockerServiceController
from tests.e2e.helpers.websocket import WebSocketClientFactory
from tests.helpers import is_port_open

_MASTER_API_KEY = "e2e-master-key-12345"


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
    connection = await asyncpg.connect(
        host=service_ports.db_host,
        port=service_ports.db_port,
        user="postgres",
        password="postgres",
        database="node_nexus_e2e",
    )
    try:
        yield connection
    finally:
        await connection.close()


_E2E_MARKERS = frozenset(
    {"docker", "e2e_smoke", "e2e_full", "e2e_resilience", "e2e_slow"}
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
                         nodes, api_keys
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
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
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
