"""Tests for credential-safe API-key application contracts."""

from datetime import UTC, datetime
from uuid import uuid4

from app.application.dto.api_key import (
    APIKeyCreateResultDTO,
    APIKeyPersistenceDTO,
)


def test_plain_key_is_hidden_from_create_result_repr() -> None:
    result = APIKeyCreateResultDTO(
        id=uuid4(),
        name="automation",
        plain_key="nnk_secret",
        key_prefix="nnk_secr",
        created_at=datetime.now(UTC),
    )

    assert "nnk_secret" not in repr(result)


def test_hash_is_hidden_from_persistence_payload_repr() -> None:
    payload = APIKeyPersistenceDTO(
        name="automation",
        key_hash="sensitive-hash",
        key_prefix="nnk_abcd",
        scope="read-only",
    )

    assert "sensitive-hash" not in repr(payload)
