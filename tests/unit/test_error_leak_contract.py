"""Contract: 5xx DomainError details must not leak exception text."""

import json
from typing import Any
from unittest.mock import MagicMock

from fastapi import Request

from app.api.error_mapping import domain_error_handler, problem_content
from app.core.exceptions import (
    AuditReadError,
    AuditStatsUnavailableError,
    AuditWriteError,
    NodeNotFoundError,
)


def _mock_request(path: str = "/test") -> MagicMock:
    req = MagicMock(spec=Request)
    req.url.path = path
    req.state.request_id = "req-contract-1"
    return req


async def _body_for(exc: Exception, path: str = "/test") -> tuple[int, dict[str, Any]]:
    req = _mock_request(path)
    resp = await domain_error_handler(req, exc)  # type: ignore[arg-type]
    raw = bytes(resp.body).decode()
    return resp.status_code, json.loads(raw)


async def test_500_returns_generic_detail_without_leak() -> None:
    secret = "super-secret-500-pg-password-xyz"
    status, body = await _body_for(AuditReadError(secret))
    assert status == 500
    assert body["detail"] == "Internal server error"
    assert body["message"] == "Internal server error"
    assert secret not in json.dumps(body)


async def test_501_returns_generic_detail_without_leak() -> None:
    secret = "super-secret-501-stats-token-xyz"
    status, body = await _body_for(AuditStatsUnavailableError(secret))
    assert status == 501
    assert body["detail"] == "Internal server error"
    assert body["message"] == "Internal server error"
    assert secret not in json.dumps(body)


async def test_503_returns_generic_detail_without_leak() -> None:
    secret = "super-secret-503-audit-path-xyz"
    status, body = await _body_for(AuditWriteError(secret))
    assert status == 503
    assert body["detail"] == "Internal server error"
    assert body["message"] == "Internal server error"
    assert secret not in json.dumps(body)


async def test_4xx_still_returns_specific_detail() -> None:
    status, body = await _body_for(NodeNotFoundError("node-abc-missing"))
    assert status == 404
    assert body["detail"] == "node-abc-missing"


def test_problem_content_survives_unknown_status() -> None:
    body = problem_content(
        status_code=599,
        code="CustomError",
        detail="Internal server error",
        request_id="r1",
        path="/x",
    )
    assert body["status"] == 599
    assert body["title"] == "HTTP 599"
    assert body["detail"] == "Internal server error"
