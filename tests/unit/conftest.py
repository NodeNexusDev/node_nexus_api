"""Shared test fixtures for unit tests."""

import uuid
from typing import cast
from unittest.mock import AsyncMock, MagicMock

from dishka import Provider, Scope, provide

from app.application.dto.node_view import NodeViewDTO
from app.application.dto.value_objects import NodeEndpoint
from app.application.ports.jwt_handler import JWTHandler
from app.application.services.api_key_authentication import (
    APIKeyAuthenticationService,
    AuthenticatedPrincipal,
)
from app.core.types import ConnectionType, NodeStatus
from app.models.api_key import APIKeyModel  # noqa: F401
from app.models.audit_log import AuditLogModel  # noqa: F401
from app.models.audit_outbox import AuditOutboxModel  # noqa: F401
from app.models.command import CommandModel
from app.models.command_execution import CommandExecutionModel  # noqa: F401
from app.models.compose_project import ComposeProjectModel  # noqa: F401
from app.models.favorite import FavoriteModel  # noqa: F401
from app.models.node import NodeModel
from app.models.node_status_history import NodeStatusHistoryModel  # noqa: F401
from app.models.refresh_token import RefreshTokenModel  # noqa: F401
from app.models.script import ScriptModel  # noqa: F401
from app.models.script_execution import ScriptExecutionModel  # noqa: F401
from app.models.script_schedule import ScriptScheduleModel  # noqa: F401
from app.models.template_asset import TemplateAssetModel  # noqa: F401
from app.models.template_installation import TemplateInstallationModel  # noqa: F401
from app.models.template_pack import TemplatePackModel  # noqa: F401
from app.models.template_registry import TemplateRegistryModel  # noqa: F401
from app.models.user import UserModel  # noqa: F401
from app.schemas.node import NodeResponse
from tests.typing import as_typed_mock


def _mock_settings(master_key: str = "") -> MagicMock:
    settings = MagicMock()
    settings.MASTER_API_KEY = master_key
    return settings


class MockAuthServiceProvider(Provider):
    """Provider that returns a mock API-key authentication use case."""

    @provide(scope=Scope.REQUEST)
    def get_api_key_service(self) -> APIKeyAuthenticationService:
        mock = AsyncMock(spec=APIKeyAuthenticationService)
        mock.authenticate.return_value = AuthenticatedPrincipal(
            key_id=uuid.uuid4(),
            key_prefix="nnk_test",
            scope="read-write",
        )
        return as_typed_mock(APIKeyAuthenticationService, mock)

    @provide(scope=Scope.APP)
    def get_jwt_handler(self) -> JWTHandler:
        return as_typed_mock(JWTHandler, MagicMock(spec=JWTHandler))


def make_orm_node(**overrides: object) -> NodeModel:
    """Create a NodeModel with defaults for testing."""
    import uuid
    from datetime import UTC, datetime

    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "name": "server-1",
        "host": "10.0.0.1",
        "port": 22,
        "connection_type": "ssh",
        "status": "active",
        "username": "root",
        "password": None,
        "ssh_key": None,
        "passphrase": None,
        "docker_host": None,
        "has_docker": False,
        "tags": [],
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return NodeModel(**defaults)


def make_node_view(**overrides: object) -> NodeViewDTO:
    """Create a public-safe node DTO with defaults for testing."""
    node = make_orm_node(**overrides)
    has_docker = bool(getattr(node, "has_docker", False))
    return NodeViewDTO(
        id=node.id,
        name=node.name,
        status=cast(NodeStatus, node.status),
        username=node.username,
        tags=tuple(node.tags or ()),
        created_at=node.created_at,
        updated_at=node.updated_at,
        endpoint=NodeEndpoint(
            host=node.host,
            port=node.port,
            connection_type=cast(ConnectionType, node.connection_type),
            docker_host=node.docker_host,
            has_docker=has_docker,
        ),
    )


def make_orm_command(**overrides: object) -> CommandModel:
    """Create a CommandModel with defaults for testing."""
    import uuid
    from datetime import UTC, datetime

    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "name": "check_disk",
        "description": "Check disk usage",
        "command": "df -h",
        "parameters": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return CommandModel(**defaults)


def make_response(**overrides: object) -> NodeResponse:
    """Create a NodeResponse with defaults for testing."""
    import uuid
    from datetime import UTC, datetime

    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "name": "server-1",
        "host": "10.0.0.1",
        "port": 22,
        "connection_type": "ssh",
        "status": "active",
        "username": "root",
        "docker_host": None,
        "has_docker": False,
        "tags": [],
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return NodeResponse.model_validate(defaults)
