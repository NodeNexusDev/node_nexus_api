"""Fixtures for E2E tests with full Docker stack."""

import socket
from collections.abc import Generator
from dataclasses import dataclass

import httpx
import pytest


@dataclass
class ServicePorts:
    api_host: str
    api_port: int
    ssh_host: str
    ssh_port: int


def _is_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def docker_compose_file() -> str:
    return "docker-compose.e2e.yml"


@pytest.fixture(scope="session")
def service_ports(
    docker_ip: str, docker_services: object
) -> ServicePorts:
    api_port = docker_services.port_for("api", 8000)  # type: ignore[attr-defined]
    ssh_port = docker_services.port_for("ssh-server", 2222)  # type: ignore[attr-defined]
    docker_services.wait_until_responsive(  # type: ignore[attr-defined]
        check=lambda: _is_port_open(docker_ip, api_port),
        timeout=120.0,
        pause=1.0,
    )
    return ServicePorts(
        api_host=docker_ip,
        api_port=api_port,
        ssh_host=docker_ip,
        ssh_port=ssh_port,
    )


@pytest.fixture(scope="session")
def e2e_client(service_ports: ServicePorts) -> Generator[httpx.Client, None, None]:
    base_url = f"http://{service_ports.api_host}:{service_ports.api_port}"
    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        yield client
