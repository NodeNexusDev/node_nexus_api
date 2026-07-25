"""Fixtures for E2E tests with full Docker stack."""

from collections.abc import Generator
from dataclasses import dataclass

import httpx
import pytest
from pytest_docker.plugin import Services

from tests.helpers import is_port_open


@dataclass
class ServicePorts:
    api_host: str
    api_port: int
    ssh_host: str
    ssh_port: int


@pytest.fixture(scope="session")
def docker_compose_file() -> str:
    return "tests/docker-compose.e2e.yml"


@pytest.fixture(scope="session")
def service_ports(docker_ip: str, docker_services: Services) -> ServicePorts:
    api_port = docker_services.port_for("api", 8000)
    ssh_port = docker_services.port_for("ssh-server", 2222)
    docker_services.wait_until_responsive(
        check=lambda: is_port_open(docker_ip, api_port),
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
def e2e_client(service_ports: ServicePorts) -> Generator[httpx.Client]:
    base_url = f"http://{service_ports.api_host}:{service_ports.api_port}"
    default_headers = {"X-API-Key": "e2e-master-key-12345"}
    with httpx.Client(
        base_url=base_url, timeout=30.0, headers=default_headers
    ) as client:
        yield client


@pytest.fixture(scope="session")
def e2e_client_no_auth(service_ports: ServicePorts) -> Generator[httpx.Client]:
    base_url = f"http://{service_ports.api_host}:{service_ports.api_port}"
    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        yield client
