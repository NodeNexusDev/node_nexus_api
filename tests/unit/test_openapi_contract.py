"""OpenAPI contract quality checks."""

import hashlib
import json
import os
from pathlib import Path

from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import app
from tests.types import UnvalidatedJsonObject

OPENAPI_CONTRACT_SHA256 = (
    "a931ae31ac21a2c94be73fefc43b8df584ce80e49955a5ab74cd6d76a611a4f4"
)

_CANONICAL_ENV = {
    "PROMETHEUS_ENABLED": "true",
    "E2E_ENABLED": "false",
    "OTEL_ENABLED": "false",
}


def _build_canonical_app() -> FastAPI:
    """Build the app with pinned settings so the schema never depends on local .env."""
    from app.main import create_app

    get_settings.cache_clear()
    saved = {key: os.environ.get(key) for key in _CANONICAL_ENV}
    os.environ.update(_CANONICAL_ENV)
    try:
        return create_app()
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()


def _canonical_schema() -> UnvalidatedJsonObject:
    schema = _build_canonical_app().openapi()
    schema["info"].pop("version", None)
    return schema


def _compute_canonical_hash() -> str:
    canonical_schema = json.dumps(
        _canonical_schema(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(canonical_schema).hexdigest()


def _persist_new_hash(new_hash: str) -> None:
    """Rewrite OPENAPI_CONTRACT_SHA256 in this source file."""
    source = Path(__file__).read_text(encoding="utf-8")
    updated = source.replace(OPENAPI_CONTRACT_SHA256, new_hash)
    Path(__file__).write_text(updated, encoding="utf-8")


def test_openapi_schema_matches_reviewed_snapshot() -> None:
    """Require an explicit review for every public HTTP contract change."""
    new_hash = _compute_canonical_hash()

    if os.environ.get("UPDATE_OPENAPI_HASH"):
        _persist_new_hash(new_hash)
        return

    assert new_hash == OPENAPI_CONTRACT_SHA256


def test_openapi_metadata_and_operation_ids_are_stable() -> None:
    schema = app.openapi()

    assert schema["info"]["title"] == "Node Nexus API"
    assert schema["info"]["license"]["identifier"] == "MIT"
    assert schema["info"]["contact"]["name"] == "Node Nexus maintainers"

    operation_ids = [
        operation["operationId"]
        for path_item in schema["paths"].values()
        for method, operation in path_item.items()
        if method in {"get", "post", "put", "patch", "delete"}
    ]
    assert operation_ids
    assert len(operation_ids) == len(set(operation_ids))
    assert all(" " not in operation_id for operation_id in operation_ids)


def test_openapi_exposes_api_key_security_scheme() -> None:
    schema = app.openapi()

    scheme = schema["components"]["securitySchemes"]["APIKeyHeader"]
    assert scheme == {"type": "apiKey", "in": "header", "name": "X-API-Key"}


def test_openapi_auth_and_sse_contracts_are_explicit() -> None:
    """Keep auth alternatives and the streaming media type visible in OpenAPI."""
    schema = app.openapi()

    events_get = schema["paths"]["/api/v1/events/stream"]["get"]
    assert events_get["security"] == [{"HTTPBearer": []}, {"APIKeyHeader": []}]
    assert set(events_get["responses"]["200"]["content"]) == {"text/event-stream"}

    auth_me_get = schema["paths"]["/api/v1/auth/me"]["get"]
    assert auth_me_get["security"] == [{"HTTPBearer": []}]


def test_protected_operations_document_standard_auth_errors() -> None:
    """Require the shared error contract on every secured HTTP operation."""
    schema = app.openapi()
    methods = {"get", "post", "put", "patch", "delete"}

    for path_item in schema["paths"].values():
        for method, operation in path_item.items():
            if method not in methods or not operation.get("security"):
                continue
            responses = operation["responses"]
            expected_statuses = {"401", "403", "404", "409", "422", "429", "503"}
            assert expected_statuses <= responses.keys()
            for status_code in expected_statuses:
                response_schema = responses[status_code]["content"]["application/json"][
                    "schema"
                ]
                assert response_schema == {"$ref": "#/components/schemas/ErrorResponse"}


def test_public_response_schemas_never_expose_credentials() -> None:
    """Guard public entity responses against accidental credential leakage."""
    schema = app.openapi()
    public_responses = {
        "APIKeyResponse",
        "CommandResponse",
        "NodeResponse",
        "ScriptResponse",
        "UserResponse",
    }
    forbidden_fields = {
        "password",
        "passphrase",
        "secret",
        "secret_key",
        "ssh_key",
        "token",
    }

    for schema_name in public_responses:
        properties = schema["components"]["schemas"][schema_name]["properties"]
        assert forbidden_fields.isdisjoint(properties), schema_name


async def test_runtime_api_documentation_endpoints() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        openapi = await client.get("/openapi.json")
        swagger = await client.get("/docs")
        redoc = await client.get("/redoc")

    assert openapi.status_code == 200
    assert openapi.json()["info"]["title"] == "Node Nexus API"
    assert swagger.status_code == 200
    assert "swagger-ui" in swagger.text
    assert redoc.status_code == 200
    assert "redoc" in redoc.text.lower()
