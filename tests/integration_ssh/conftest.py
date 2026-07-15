"""Fixtures for SSH integration tests with Docker."""

import socket
from collections.abc import Generator
from dataclasses import dataclass

import pytest
from pytest_docker.plugin import Services


@dataclass
class SSHServer:
    host: str
    port: int
    username: str
    password: str


def _is_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def docker_compose_file() -> str:
    return "tests/docker-compose.yml"


@pytest.fixture(scope="session")
def ssh_server(docker_ip: str, docker_services: Services) -> Generator[SSHServer]:
    port = docker_services.port_for("ssh-server", 2222)
    docker_services.wait_until_responsive(
        check=lambda: _is_port_open(docker_ip, port),
        timeout=60.0,
        pause=0.5,
    )
    yield SSHServer(
        host=docker_ip,
        port=port,
        username="testuser",
        password="testpass",
    )
