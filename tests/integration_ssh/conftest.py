"""Fixtures for SSH integration tests with Docker."""

from collections.abc import Generator
from dataclasses import dataclass

import pytest
from pytest_docker.plugin import Services

from tests.helpers import is_port_open


@dataclass
class SSHServer:
    host: str
    port: int
    username: str
    password: str


@pytest.fixture(scope="session")
def docker_compose_file() -> str:
    return "tests/docker-compose.yml"


@pytest.fixture(scope="session")
def docker_compose_project_name() -> str:
    return "node-nexus-test"


@pytest.fixture(scope="session")
def docker_cleanup() -> list[str]:
    return ["down -v --remove-orphans"]


@pytest.fixture(scope="session")
def ssh_server(docker_ip: str, docker_services: Services) -> Generator[SSHServer]:
    port = docker_services.port_for("ssh-server", 2222)
    docker_services.wait_until_responsive(
        check=lambda: is_port_open(docker_ip, port),
        timeout=60.0,
        pause=0.5,
    )
    yield SSHServer(
        host=docker_ip,
        port=port,
        username="testuser",
        password="testpass",
    )
