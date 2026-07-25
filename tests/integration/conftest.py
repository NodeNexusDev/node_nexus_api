"""Fixtures for Docker integration tests."""

from collections.abc import Generator
from dataclasses import dataclass

import pytest
from pytest_docker.plugin import Services

from tests.helpers import is_port_open


@dataclass
class DockerSSHServer:
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
def docker_ssh_server(
    docker_ip: str, docker_services: Services
) -> Generator[DockerSSHServer]:
    port = docker_services.port_for("ssh-with-docker", 2222)
    docker_services.wait_until_responsive(
        check=lambda: is_port_open(docker_ip, port),
        timeout=60.0,
        pause=0.5,
    )
    yield DockerSSHServer(
        host=docker_ip,
        port=port,
        username="testuser",
        password="testpass",
    )
