"""Tests for domain error handler status code mapping."""

import pytest
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from app.api.error_mapping import domain_error_handler
from app.core.exceptions import (
    APIKeyExpiredError,
    APIKeyNotFoundError,
    APIKeyRevokedError,
    AuditWriteError,
    AuthenticationError,
    CommandNotFoundError,
    ConnectionFailedError,
    ContainerNotFoundError,
    CredentialDecryptionError,
    DockerDaemonError,
    DockerError,
    DockerValidationError,
    DomainError,
    ExecutionNotFoundError,
    FavoriteNotFoundError,
    ImageNotFoundError,
    NodeNameConflictError,
    NodeNotFoundError,
    NoteNotFoundError,
    RequestTimeoutError,
    ScheduledScriptExecutionError,
    ScheduleNotFoundError,
    SchedulePersistenceError,
    SchedulerOwnershipError,
    ScheduleValidationError,
    ScriptNotFoundError,
    TagNotFoundError,
    TemplateRenderError,
    UnsupportedConfigFormatError,
)

app = FastAPI()
app.add_exception_handler(DomainError, domain_error_handler)

_ROUTES: dict[str, type[DomainError]] = {
    "/test-node-not-found": NodeNotFoundError,
    "/test-node-name-conflict": NodeNameConflictError,
    "/test-command-not-found": CommandNotFoundError,
    "/test-script-not-found": ScriptNotFoundError,
    "/test-apikey-not-found": APIKeyNotFoundError,
    "/test-apikey-revoked": APIKeyRevokedError,
    "/test-apikey-expired": APIKeyExpiredError,
    "/test-authentication": AuthenticationError,
    "/test-tag-not-found": TagNotFoundError,
    "/test-connection-failed": ConnectionFailedError,
    "/test-credential-decryption": CredentialDecryptionError,
    "/test-template-render": TemplateRenderError,
    "/test-container-not-found": ContainerNotFoundError,
    "/test-image-not-found": ImageNotFoundError,
    "/test-docker-daemon": DockerDaemonError,
    "/test-docker-validation": DockerValidationError,
    "/test-docker-error": DockerError,
    "/test-request-timeout": RequestTimeoutError,
    "/test-unsupported-config-format": UnsupportedConfigFormatError,
    "/test-schedule-validation": ScheduleValidationError,
    "/test-schedule-not-found": ScheduleNotFoundError,
    "/test-scheduler-ownership": SchedulerOwnershipError,
    "/test-schedule-persistence": SchedulePersistenceError,
    "/test-audit-write": AuditWriteError,
    "/test-execution-not-found": ExecutionNotFoundError,
    "/test-scheduled-script-execution": ScheduledScriptExecutionError,
    "/test-favorite-not-found": FavoriteNotFoundError,
    "/test-note-not-found": NoteNotFoundError,
}

for _path, _exc_cls in _ROUTES.items():

    @app.get(_path)
    async def _raise(exc_cls: type[DomainError] = _exc_cls) -> None:  # type: ignore[misc]
        raise exc_cls("test error")


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
            resp = await client.get("/test-node-not-found")
        assert resp.status_code == 404
        body = resp.json()
        assert body["code"] == "NodeNotFoundError"
        assert body["detail"] == "test error"
        assert body["message"] == "test error"
        assert "request_id" in body

    async def test_unknown_domain_error_returns_422(self) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/test-unknown")
        assert resp.status_code == 422

    @pytest.mark.parametrize(
        ("path", "expected_message"),
        [
            ("/test-connection-failed", "Remote connection failed"),
            ("/test-credential-decryption", "Credential processing failed"),
            ("/test-container-not-found", "Docker container not found"),
            ("/test-image-not-found", "Docker image not found"),
            ("/test-docker-daemon", "Docker daemon unavailable"),
            ("/test-docker-error", "Docker operation failed"),
        ],
    )
    async def test_infrastructure_error_details_are_not_exposed(
        self, path: str, expected_message: str
    ) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(path)

        body = resp.json()
        assert body["message"] == expected_message
        assert body["detail"] == expected_message
        assert "test error" not in str(body)

    @pytest.mark.parametrize(
        ("path", "expected_status"),
        [
            pytest.param("/test-node-not-found", 404, id="NodeNotFoundError"),
            pytest.param("/test-node-name-conflict", 409, id="NodeNameConflictError"),
            pytest.param("/test-command-not-found", 404, id="CommandNotFoundError"),
            pytest.param("/test-script-not-found", 404, id="ScriptNotFoundError"),
            pytest.param("/test-apikey-not-found", 404, id="APIKeyNotFoundError"),
            pytest.param("/test-apikey-revoked", 401, id="APIKeyRevokedError"),
            pytest.param("/test-apikey-expired", 401, id="APIKeyExpiredError"),
            pytest.param("/test-authentication", 401, id="AuthenticationError"),
            pytest.param("/test-tag-not-found", 404, id="TagNotFoundError"),
            pytest.param("/test-connection-failed", 503, id="ConnectionFailedError"),
            pytest.param(
                "/test-credential-decryption", 503, id="CredentialDecryptionError"
            ),
            pytest.param("/test-template-render", 422, id="TemplateRenderError"),
            pytest.param("/test-container-not-found", 404, id="ContainerNotFoundError"),
            pytest.param("/test-image-not-found", 404, id="ImageNotFoundError"),
            pytest.param("/test-docker-daemon", 503, id="DockerDaemonError"),
            pytest.param("/test-docker-validation", 422, id="DockerValidationError"),
            pytest.param("/test-docker-error", 502, id="DockerError"),
            pytest.param("/test-request-timeout", 504, id="RequestTimeoutError"),
            pytest.param(
                "/test-unsupported-config-format",
                422,
                id="UnsupportedConfigFormatError",
            ),
            pytest.param(
                "/test-schedule-validation", 422, id="ScheduleValidationError"
            ),
            pytest.param("/test-schedule-not-found", 404, id="ScheduleNotFoundError"),
            pytest.param(
                "/test-scheduler-ownership", 503, id="SchedulerOwnershipError"
            ),
            pytest.param(
                "/test-schedule-persistence", 503, id="SchedulePersistenceError"
            ),
            pytest.param("/test-audit-write", 503, id="AuditWriteError"),
            pytest.param("/test-execution-not-found", 404, id="ExecutionNotFoundError"),
            pytest.param(
                "/test-scheduled-script-execution",
                422,
                id="ScheduledScriptExecutionError",
            ),
            pytest.param("/test-favorite-not-found", 404, id="FavoriteNotFoundError"),
            pytest.param("/test-note-not-found", 404, id="NoteNotFoundError"),
        ],
    )
    async def test_exception_maps_to_correct_status(
        self, path: str, expected_status: int
    ) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(path)
        assert resp.status_code == expected_status

    @pytest.mark.parametrize(
        "path",
        [
            "/test-node-not-found",
            "/test-apikey-expired",
            "/test-docker-error",
            "/test-favorite-not-found",
            "/test-note-not-found",
        ],
    )
    async def test_error_response_body_contract(self, path: str) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(path)
        body = resp.json()
        assert "code" in body
        assert "message" in body
        assert "detail" in body
        assert "request_id" in body
        assert body["message"] == body["detail"]
