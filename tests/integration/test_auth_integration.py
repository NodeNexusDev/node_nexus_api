"""Integration tests for API key authentication with in-memory SQLite."""

from collections.abc import AsyncGenerator
from unittest.mock import MagicMock, patch

import pytest_asyncio
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.adapters.persistence.api_key import SqlAlchemyAPIKeyGateway
from app.adapters.persistence.dao.node import NodeRepository
from app.adapters.persistence.node_management import SqlAlchemyNodeManagementGateway
from app.adapters.security import AesGcmCredentialCipher
from app.api.error_mapping import domain_error_handler
from app.api.v1.api_keys import router as api_keys_router
from app.api.v1.health import router as health_router
from app.api.v1.nodes import router as nodes_router
from app.application.services.api_key_authentication import APIKeyAuthenticationService
from app.application.services.api_key_management import APIKeyManagementService
from app.application.services.node_management_service import NodeManagementService
from app.models.base import Base

MASTER_KEY = "test-master-key-123"


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def sessionmaker(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class IntegrationAuthProvider(Provider):
    def __init__(self, sm: async_sessionmaker[AsyncSession]) -> None:
        super().__init__()
        self._sm = sm

    @provide(scope=Scope.REQUEST)
    async def get_session(self) -> AsyncGenerator[AsyncSession]:
        async with self._sm() as session:
            async with session.begin():
                yield session

    @provide(scope=Scope.APP)
    def get_api_key_gateway(self) -> SqlAlchemyAPIKeyGateway:
        return SqlAlchemyAPIKeyGateway(self._sm)

    @provide(scope=Scope.REQUEST)
    def get_node_repo(self, session: AsyncSession) -> NodeRepository:
        return NodeRepository(session)

    @provide(scope=Scope.REQUEST)
    def get_api_key_service(
        self, gateway: SqlAlchemyAPIKeyGateway
    ) -> APIKeyAuthenticationService:
        return APIKeyAuthenticationService(gateway, gateway)

    @provide(scope=Scope.REQUEST)
    def get_api_key_management_service(
        self, gateway: SqlAlchemyAPIKeyGateway
    ) -> APIKeyManagementService:
        return APIKeyManagementService(gateway, gateway)

    @provide(scope=Scope.REQUEST)
    def get_node_service(self) -> NodeManagementService:
        gateway = SqlAlchemyNodeManagementGateway(self._sm)
        return NodeManagementService(
            reader=gateway, writer=gateway, credential_cipher=AesGcmCredentialCipher()
        )


def _mock_settings(master_key: str = "") -> MagicMock:
    settings = MagicMock()
    settings.MASTER_API_KEY = master_key
    return settings


def _create_app(sessionmaker: async_sessionmaker[AsyncSession]) -> FastAPI:
    from app.core.exceptions import DomainError

    provider = IntegrationAuthProvider(sessionmaker)
    container = make_async_container(provider)

    app = FastAPI()
    app.include_router(health_router)
    app.include_router(nodes_router, prefix="/api/v1")
    app.include_router(api_keys_router, prefix="/api/v1")
    setup_dishka(container, app)

    app.add_exception_handler(DomainError, domain_error_handler)

    app.state._container = container
    return app


# --- Unauthenticated access ---


async def test_unauthenticated_returns_401(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    app = _create_app(sessionmaker)
    with patch("app.api.deps.get_settings", return_value=_mock_settings(MASTER_KEY)):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/nodes/")
    assert resp.status_code == 401
    assert "Missing X-API-Key header" in resp.json()["detail"]
    await app.state._container.close()


async def test_invalid_key_returns_401(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    app = _create_app(sessionmaker)
    with patch("app.api.deps.get_settings", return_value=_mock_settings(MASTER_KEY)):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/nodes/", headers={"X-API-Key": "nnk_invalidkey123"}
            )
    assert resp.status_code == 401
    assert "Invalid API key" in resp.json()["detail"]
    await app.state._container.close()


# --- Master key auth ---


async def test_master_key_auth(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    app = _create_app(sessionmaker)
    with patch("app.api.deps.get_settings", return_value=_mock_settings(MASTER_KEY)):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/nodes/", headers={"X-API-Key": MASTER_KEY})
    assert resp.status_code == 200
    assert resp.json()["items"] == []
    await app.state._container.close()


async def test_health_no_auth_required(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """Health endpoint no longer requires authentication (for K8s probes)."""
    app = _create_app(sessionmaker)
    with patch("app.api.deps.get_settings", return_value=_mock_settings(MASTER_KEY)):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "version" in data
    await app.state._container.close()


async def test_health_with_master_key(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    app = _create_app(sessionmaker)
    with patch("app.api.deps.get_settings", return_value=_mock_settings(MASTER_KEY)):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/health", headers={"X-API-Key": MASTER_KEY})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "version" in data
    await app.state._container.close()


# --- Create and use API key ---


async def test_create_and_use_api_key(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    app = _create_app(sessionmaker)
    with patch("app.api.deps.get_settings", return_value=_mock_settings(MASTER_KEY)):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Create key via master key
            create_resp = await client.post(
                "/api/v1/api-keys/",
                json={"name": "service-key"},
                headers={"X-API-Key": MASTER_KEY},
            )
            assert create_resp.status_code == 201
            plain_key = create_resp.json()["key"]
            assert plain_key.startswith("nnk_")

            # Use created key
            resp = await client.get("/api/v1/nodes/", headers={"X-API-Key": plain_key})
    assert resp.status_code == 200
    await app.state._container.close()


async def test_revoke_and_fail(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    app = _create_app(sessionmaker)
    with patch("app.api.deps.get_settings", return_value=_mock_settings(MASTER_KEY)):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Create key
            create_resp = await client.post(
                "/api/v1/api-keys/",
                json={"name": "temp-key"},
                headers={"X-API-Key": MASTER_KEY},
            )
            key_id = create_resp.json()["id"]
            plain_key = create_resp.json()["key"]

            # Verify it works
            resp = await client.get("/api/v1/nodes/", headers={"X-API-Key": plain_key})
            assert resp.status_code == 200

            # Revoke
            revoke_resp = await client.delete(
                f"/api/v1/api-keys/{key_id}", headers={"X-API-Key": MASTER_KEY}
            )
            assert revoke_resp.status_code == 204

            # Use revoked key -> 401
            resp = await client.get("/api/v1/nodes/", headers={"X-API-Key": plain_key})
    assert resp.status_code == 401
    assert "revoked" in resp.json()["detail"].lower()
    await app.state._container.close()


async def test_last_used_at_updated(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    app = _create_app(sessionmaker)
    with patch("app.api.deps.get_settings", return_value=_mock_settings(MASTER_KEY)):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Create key
            create_resp = await client.post(
                "/api/v1/api-keys/",
                json={"name": "tracked-key"},
                headers={"X-API-Key": MASTER_KEY},
            )
            key_id = create_resp.json()["id"]
            plain_key = create_resp.json()["key"]

            # Initially last_used_at should be null
            list_resp = await client.get(
                "/api/v1/api-keys/", headers={"X-API-Key": MASTER_KEY}
            )
            key_data = next(k for k in list_resp.json()["items"] if k["id"] == key_id)
            assert key_data["last_used_at"] is None

            # Use the key
            await client.get("/api/v1/nodes/", headers={"X-API-Key": plain_key})

            # Check last_used_at is now set
            list_resp = await client.get(
                "/api/v1/api-keys/", headers={"X-API-Key": MASTER_KEY}
            )
            key_data = next(k for k in list_resp.json()["items"] if k["id"] == key_id)
    assert key_data["last_used_at"] is not None
    await app.state._container.close()


async def test_list_keys_with_master_key(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    app = _create_app(sessionmaker)
    with patch("app.api.deps.get_settings", return_value=_mock_settings(MASTER_KEY)):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Create a few keys
            for i in range(3):
                await client.post(
                    "/api/v1/api-keys/",
                    json={"name": f"key-{i}"},
                    headers={"X-API-Key": MASTER_KEY},
                )

            resp = await client.get(
                "/api/v1/api-keys/", headers={"X-API-Key": MASTER_KEY}
            )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3
    await app.state._container.close()


async def test_master_wrong_key_returns_401(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    app = _create_app(sessionmaker)
    with patch("app.api.deps.get_settings", return_value=_mock_settings(MASTER_KEY)):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/nodes/", headers={"X-API-Key": "wrong-master-key"}
            )
    assert resp.status_code == 401
    await app.state._container.close()
