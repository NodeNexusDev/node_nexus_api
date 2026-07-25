"""Tests for domain error handler status code mapping."""

import os

import pytest
import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from app.core.exceptions import (
    APIKeyNotFoundError,
    CommandNotFoundError,
    ConnectionFailedError,
    ContainerNotFoundError,
    DockerDaemonError,
    DockerError,
    DockerValidationError,
    DomainError,
    ImageNotFoundError,
    NodeNotFoundError,
    TagNotFoundError,
    TemplateRenderError,
)

audit = structlog.get_logger("audit")

# Standalone test app with copy of the error handler
app = FastAPI()


@app.exception_handler(DomainError)
async def _domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    _error_status_map: dict[type[DomainError], int] = {
        NodeNotFoundError: 404,
        CommandNotFoundError: 404,
        APIKeyNotFoundError: 401,
        TagNotFoundError: 404,
        ConnectionFailedError: 503,
        TemplateRenderError: 422,
        DockerError: 502,
        ContainerNotFoundError: 404,
        ImageNotFoundError: 404,
        DockerDaemonError: 503,
        DockerValidationError: 422,
    }
    status_code = _error_status_map.get(type(exc), 422)
    return JSONResponse(
        status_code=status_code,
        content={"detail": str(exc)},
    )


@app.get("/test-node")
async def raise_node_not_found() -> None:
    raise NodeNotFoundError("node not found")


@app.get("/test-command")
async def raise_command_not_found() -> None:
    raise CommandNotFoundError("command not found")


@app.get("/test-apikey")
async def raise_apikey_not_found() -> None:
    raise APIKeyNotFoundError("key not found")


@app.get("/test-tag")
async def raise_tag_not_found() -> None:
    raise TagNotFoundError("tag not found")


@app.get("/test-connection")
async def raise_connection_failed() -> None:
    raise ConnectionFailedError("connection failed")


@app.get("/test-template")
async def raise_template_error() -> None:
    raise TemplateRenderError("bad template")


@app.get("/test-docker")
async def raise_docker_error() -> None:
    raise DockerError("docker error")


@app.get("/test-container")
async def raise_container_not_found() -> None:
    raise ContainerNotFoundError("container not found")


@app.get("/test-image")
async def raise_image_not_found() -> None:
    raise ImageNotFoundError("image not found")


@app.get("/test-daemon")
async def raise_docker_daemon_error() -> None:
    raise DockerDaemonError("daemon error")


@app.get("/test-validation")
async def raise_docker_validation_error() -> None:
    raise DockerValidationError("validation error")


@app.get("/test-unknown")
async def raise_unknown_domain_error() -> None:
    class CustomDomainError(DomainError):
        pass

    raise CustomDomainError("unknown error")


class TestDomainErrorHandler:
    async def test_node_not_found_returns_404(self) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/test-node")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "node not found"

    async def test_command_not_found_returns_404(self) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/test-command")
        assert resp.status_code == 404

    async def test_apikey_not_found_returns_401(self) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/test-apikey")
        assert resp.status_code == 401

    async def test_tag_not_found_returns_404(self) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/test-tag")
        assert resp.status_code == 404

    async def test_connection_failed_returns_503(self) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/test-connection")
        assert resp.status_code == 503

    async def test_template_error_returns_422(self) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/test-template")
        assert resp.status_code == 422

    async def test_docker_error_returns_502(self) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/test-docker")
        assert resp.status_code == 502

    async def test_container_not_found_returns_404(self) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/test-container")
        assert resp.status_code == 404

    async def test_image_not_found_returns_404(self) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/test-image")
        assert resp.status_code == 404

    async def test_docker_daemon_error_returns_503(self) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/test-daemon")
        assert resp.status_code == 503

    async def test_docker_validation_error_returns_422(self) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/test-validation")
        assert resp.status_code == 422

    async def test_unknown_domain_error_returns_422(self) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/test-unknown")
        assert resp.status_code == 422
