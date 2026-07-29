"""Unit tests for the API-key persistence adapter mappings."""

from datetime import UTC, datetime
from uuid import uuid4

from app.adapters.persistence.api_key import SqlAlchemyAPIKeyGateway
from app.models.api_key import APIKeyModel


def test_maps_auth_projection_without_hash() -> None:
    model = APIKeyModel(
        id=uuid4(),
        name="automation",
        key_hash="sensitive",
        key_prefix="nnk_abcd",
        scope="read-only",
        is_active=True,
        created_at=datetime.now(UTC),
    )

    auth = SqlAlchemyAPIKeyGateway._to_auth(model)

    assert auth.id == model.id
    assert auth.key_prefix == "nnk_abcd"
    assert not hasattr(auth, "key_hash")


def test_maps_management_view_without_hash() -> None:
    model = APIKeyModel(
        id=uuid4(),
        name="automation",
        key_hash="sensitive",
        key_prefix="nnk_abcd",
        scope="read-write",
        is_active=True,
        created_at=datetime.now(UTC),
    )

    view = SqlAlchemyAPIKeyGateway._to_view(model)

    assert view.name == "automation"
    assert not hasattr(view, "key_hash")
