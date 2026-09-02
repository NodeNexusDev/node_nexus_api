"""Full coverage tests for NodeManagementService."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.security import AesGcmCredentialCipher
from app.adapters.security.credential_cipher import decrypt, encrypt
from app.application.dto.command_execution import (
    BulkCommandRequestDTO,
    BulkCommandResultDTO,
    CommandRequestDTO,
    CommandResultDTO,
)
from app.application.dto.node_management import (
    NodeCreateDTO,
    NodePageDTO,
    NodeUpdateDTO,
)
from app.application.dto.node_view import NodeViewDTO
from app.application.dto.value_objects import NodeCredentials, NodeEndpoint
from app.application.services.node_bulk_command_service import NodeBulkCommandService
from app.application.services.node_command_service import NodeCommandService
from app.application.services.node_management_service import (
    NodeManagementService as _NodeManagementService,
)
from app.core.exceptions import NodeNameConflictError, NodeNotFoundError
from tests.unit.conftest import make_node_view, make_orm_node


@pytest.fixture
def repo() -> AsyncMock:
    return AsyncMock()


class NodeManagementService(_NodeManagementService):
    """Test-only facade matching the legacy combined node API surface."""

    def attach_command_services(
        self,
        command_service: NodeCommandService,
        bulk_service: NodeBulkCommandService,
    ) -> None:
        self._command_service = command_service
        self._bulk_command_service = bulk_service

    async def check_connectivity(self, node_id: uuid.UUID) -> NodeViewDTO:
        return await self._command_service.check_connectivity(node_id)

    async def execute_command(
        self, node_id: uuid.UUID, data: CommandRequestDTO
    ) -> CommandResultDTO:
        return await self._command_service.execute_command(node_id, data)

    async def bulk_execute_command(
        self, data: BulkCommandRequestDTO
    ) -> BulkCommandResultDTO:
        return await self._bulk_command_service.bulk_execute_command(data)


@pytest.fixture
def service(repo: AsyncMock) -> NodeManagementService:
    service = NodeManagementService(
        reader=repo, writer=repo, credential_cipher=AesGcmCredentialCipher()
    )
    command_service = NodeCommandService(
        node_reader=repo,
        status_writer=repo,
        credential_cipher=AesGcmCredentialCipher(),
        connector_factory=MagicMock(),
    )
    bulk_service = NodeBulkCommandService(
        node_reader=repo,
        credential_cipher=AesGcmCredentialCipher(),
        connector_factory=MagicMock(),
    )
    service.attach_command_services(command_service, bulk_service)
    return service


class TestGetNode:
    async def test_found(self, service: NodeManagementService, repo: AsyncMock) -> None:
        node = make_node_view()
        repo.get_node.return_value = node
        result = await service.get_node(node.id)
        assert result.name == "server-1"

    async def test_not_found(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        repo.get_node.return_value = None
        with pytest.raises(NodeNotFoundError):
            await service.get_node(uuid.uuid4())


class TestGetAllNodes:
    async def test_empty(self, service: NodeManagementService, repo: AsyncMock) -> None:
        repo.list_nodes.return_value = NodePageDTO(items=(), total=0)
        nodes, total = await service.get_all_nodes()
        assert nodes == []
        assert total == 0

    async def test_with_data(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        nodes = (make_node_view(name="n1"), make_node_view(name="n2"))
        repo.list_nodes.return_value = NodePageDTO(items=nodes, total=2)
        result_nodes, total = await service.get_all_nodes()
        assert len(result_nodes) == 2
        assert total == 2


class TestCreateNode:
    async def test_creates_node(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        node = make_node_view()
        repo.create_node.return_value = node
        data = NodeCreateDTO(
            name="test",
            endpoint=NodeEndpoint(host="1.2.3.4", port=22, connection_type="ssh"),
        )
        result = await service.create_node(data)
        assert result.name == "server-1"
        repo.create_node.assert_called_once()

    async def test_duplicate_name_is_domain_conflict(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        repo.create_node.side_effect = NodeNameConflictError("duplicate")
        data = NodeCreateDTO(
            name="duplicate",
            endpoint=NodeEndpoint(host="1.2.3.4", port=22, connection_type="ssh"),
        )

        with pytest.raises(NodeNameConflictError, match="duplicate"):
            await service.create_node(data)

    async def test_encrypts_password(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        repo.create_node.return_value = make_node_view()
        data = NodeCreateDTO(
            name="test",
            endpoint=NodeEndpoint(host="1.2.3.4", port=22, connection_type="ssh"),
            credentials=NodeCredentials(password="secret123"),
        )
        await service.create_node(data)
        call_data = repo.create_node.call_args.args[0]
        assert call_data.password != "secret123"
        assert decrypt(call_data.password) == "secret123"

    async def test_encrypts_ssh_key(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        repo.create_node.return_value = make_node_view()
        key = "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----"
        data = NodeCreateDTO(
            name="test",
            endpoint=NodeEndpoint(host="1.2.3.4", port=22, connection_type="ssh"),
            credentials=NodeCredentials(ssh_key=key),
        )
        await service.create_node(data)
        call_data = repo.create_node.call_args.args[0]
        assert call_data.ssh_key is not None
        assert "BEGIN" not in call_data.ssh_key

    async def test_encrypts_passphrase(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        repo.create_node.return_value = make_node_view()
        data = NodeCreateDTO(
            name="test",
            endpoint=NodeEndpoint(host="1.2.3.4", port=22, connection_type="ssh"),
            credentials=NodeCredentials(ssh_key="fake-key", passphrase="my-passphrase"),
        )
        await service.create_node(data)
        call_data = repo.create_node.call_args.args[0]
        assert call_data.passphrase is not None
        assert decrypt(call_data.passphrase) == "my-passphrase"


class TestUpdateNode:
    async def test_found(self, service: NodeManagementService, repo: AsyncMock) -> None:
        node = make_node_view()
        repo.update_node.return_value = node
        data = NodeUpdateDTO(changes=(("name", "updated"),))
        result = await service.update_node(node.id, data)
        assert result.name == "server-1"

    async def test_not_found(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        repo.update_node.return_value = None
        with pytest.raises(NodeNotFoundError):
            await service.update_node(
                uuid.uuid4(), NodeUpdateDTO(changes=(("name", "x"),))
            )

    async def test_encrypts_fields(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        node = make_node_view()
        repo.update_node.return_value = node
        data = NodeUpdateDTO(changes=(("password", "newpass"),))
        await service.update_node(node.id, data)
        call_data = repo.update_node.call_args.args[1]
        assert dict(call_data.changes)["password"] != "newpass"


class TestDeleteNode:
    async def test_found(self, service: NodeManagementService, repo: AsyncMock) -> None:
        repo.get_node.return_value = make_node_view()
        result = await service.delete_node(uuid.uuid4())
        assert result is True
        repo.delete_node.assert_awaited_once()

    async def test_not_found(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        repo.get_node.return_value = None
        with pytest.raises(NodeNotFoundError):
            await service.delete_node(uuid.uuid4())


class TestDecryptValue:
    def test_none_returns_none(self) -> None:
        from app.adapters.security.credential_cipher import decrypt_value

        assert decrypt_value(None) is None

    def test_empty_string_returns_empty(self) -> None:
        from app.adapters.security.credential_cipher import decrypt_value

        assert decrypt_value("") == ""

    def test_encrypted_value_decrypts(self) -> None:
        from app.adapters.security.credential_cipher import decrypt_value

        token = encrypt("secret")
        assert decrypt_value(token) == "secret"

    def test_non_encrypted_value_raises(self) -> None:
        from app.adapters.security.credential_cipher import decrypt_value
        from app.core.exceptions import CredentialDecryptionError

        with pytest.raises(CredentialDecryptionError):
            decrypt_value("plain-text")

    def test_tampered_ciphertext_fails_closed(self) -> None:
        from app.adapters.security.credential_cipher import decrypt_value
        from app.core.exceptions import CredentialDecryptionError

        token = encrypt("secret")
        tampered = f"{token[:-1]}{'A' if token[-1] != 'A' else 'B'}"
        with pytest.raises(CredentialDecryptionError):
            decrypt_value(tampered)


class TestCheckConnectivityEdgeCases:
    async def test_node_not_found(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        repo.get_connection.return_value = None
        with pytest.raises(NodeNotFoundError):
            await service.check_connectivity(uuid.uuid4())


class TestExecuteCommandEdgeCases:
    async def test_node_not_found(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        repo.get_connection.return_value = None
        with pytest.raises(NodeNotFoundError):
            await service.execute_command(uuid.uuid4(), CommandRequestDTO(command="ls"))


class TestGetAllNodesFiltering:
    async def test_delegates_to_filtered_with_tags(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        nodes = (make_node_view(name="n1"),)
        repo.list_nodes.return_value = NodePageDTO(items=nodes, total=1)
        result_nodes, total = await service.get_all_nodes(tags=["prod"])
        assert len(result_nodes) == 1
        assert total == 1
        query = repo.list_nodes.call_args.args[0]
        assert query.tags == ("prod",)

    async def test_delegates_to_filtered_with_search(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        repo.list_nodes.return_value = NodePageDTO(items=(), total=0)
        result_nodes, total = await service.get_all_nodes(search="web")
        assert result_nodes == []
        assert total == 0
        query = repo.list_nodes.call_args.args[0]
        assert query.search == "web"

    async def test_falls_back_to_get_all_without_filters(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        nodes = (make_node_view(),)
        repo.list_nodes.return_value = NodePageDTO(items=nodes, total=1)
        result_nodes, total = await service.get_all_nodes()
        assert len(result_nodes) == 1
        query = repo.list_nodes.call_args.args[0]
        assert query.tags == ()
        assert query.search is None


class TestBulkExecuteCommand:
    async def test_all_nodes_succeed(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        from unittest.mock import AsyncMock, MagicMock

        n1 = make_orm_node(name="n1")
        n2 = make_orm_node(name="n2")
        repo.get_connections_by_ids.return_value = [n1, n2]

        connector = AsyncMock()
        connector.execute_command.return_value = ("ok", "", 0)
        connector.__aenter__ = AsyncMock(return_value=connector)
        connector.__aexit__ = AsyncMock(return_value=False)

        factory = MagicMock()
        factory.create_ssh.return_value = connector
        service._bulk_command_service._connector_factory = factory

        result = await service.bulk_execute_command(
            BulkCommandRequestDTO(command="uptime", node_ids=(n1.id, n2.id))
        )
        assert result.total == 2
        assert result.succeeded == 2
        assert result.failed == 0
        assert all(r.exit_code == 0 for r in result.results)

    async def test_partial_failure(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        from unittest.mock import AsyncMock, MagicMock

        n1 = make_orm_node(name="n1")
        n2 = make_orm_node(name="n2")
        repo.get_connections_by_ids.return_value = [n1, n2]

        call_count = 0

        async def fake_execute(command: str) -> tuple[str, str, int]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ("ok", "", 0)
            return ("", "connection refused", 1)

        connector = AsyncMock()
        connector.execute_command = fake_execute
        connector.__aenter__ = AsyncMock(return_value=connector)
        connector.__aexit__ = AsyncMock(return_value=False)

        factory = MagicMock()
        factory.create_ssh.return_value = connector
        service._bulk_command_service._connector_factory = factory

        result = await service.bulk_execute_command(
            BulkCommandRequestDTO(command="uptime", node_ids=(n1.id, n2.id))
        )
        assert result.total == 2
        assert result.succeeded == 1
        assert result.failed == 1

    async def test_no_nodes_raises(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        repo.get_connections_by_ids.return_value = []
        with pytest.raises(NodeNotFoundError):
            await service.bulk_execute_command(
                BulkCommandRequestDTO(command="ls", node_ids=(uuid.uuid4(),))
            )

    async def test_connection_error_returns_error_result(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        from unittest.mock import AsyncMock, MagicMock

        n1 = make_orm_node(name="n1")
        repo.get_connections_by_ids.return_value = [n1]

        connector = AsyncMock()
        connector.execute_command.side_effect = OSError("Connection refused")
        connector.__aenter__ = AsyncMock(return_value=connector)
        connector.__aexit__ = AsyncMock(return_value=False)

        factory = MagicMock()
        factory.create_ssh.return_value = connector
        service._bulk_command_service._connector_factory = factory

        result = await service.bulk_execute_command(
            BulkCommandRequestDTO(command="uptime", node_ids=(n1.id,))
        )
        assert result.total == 1
        assert result.failed == 1
        assert "Connection refused" in result.results[0].stderr

    async def test_resolve_by_tags(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        from unittest.mock import AsyncMock, MagicMock

        n1 = make_orm_node(name="n1")
        repo.get_connections_by_tags.return_value = [n1]

        connector = AsyncMock()
        connector.execute_command.return_value = ("ok", "", 0)
        connector.__aenter__ = AsyncMock(return_value=connector)
        connector.__aexit__ = AsyncMock(return_value=False)

        factory = MagicMock()
        factory.create_ssh.return_value = connector
        service._bulk_command_service._connector_factory = factory

        result = await service.bulk_execute_command(
            BulkCommandRequestDTO(command="uptime", tags=("prod",))
        )
        assert result.total == 1
        repo.get_connections_by_tags.assert_called_once_with(["prod"])

    async def test_resolve_by_both_ids_and_tags(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        from unittest.mock import AsyncMock, MagicMock

        n1 = make_orm_node(name="n1")
        n2 = make_orm_node(name="n2")
        n3 = make_orm_node(name="n3")
        # node_ids returns n1, n2; tags returns n1, n3 → intersection = n1
        repo.get_connections_by_ids.return_value = [n1, n2]
        repo.get_connections_by_tags.return_value = [n1, n3]

        connector = AsyncMock()
        connector.execute_command.return_value = ("ok", "", 0)
        connector.__aenter__ = AsyncMock(return_value=connector)
        connector.__aexit__ = AsyncMock(return_value=False)

        factory = MagicMock()
        factory.create_ssh.return_value = connector
        service._bulk_command_service._connector_factory = factory

        result = await service.bulk_execute_command(
            BulkCommandRequestDTO(
                command="uptime",
                node_ids=(n1.id, n2.id),
                tags=("prod",),
            )
        )
        assert result.total == 1
        assert result.results[0].node_id == n1.id

    async def test_resolve_by_tags_empty(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        repo.get_connections_by_tags.return_value = []
        with pytest.raises(NodeNotFoundError):
            await service.bulk_execute_command(
                BulkCommandRequestDTO(command="ls", tags=("nonexistent",))
            )

    async def test_resolve_by_both_empty_intersection(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        n1 = make_orm_node(name="n1")
        n2 = make_orm_node(name="n2")
        # No overlap between ids and tags
        repo.get_connections_by_ids.return_value = [n1]
        repo.get_connections_by_tags.return_value = [n2]
        with pytest.raises(NodeNotFoundError):
            await service.bulk_execute_command(
                BulkCommandRequestDTO(command="ls", node_ids=(n1.id,), tags=("prod",))
            )


class TestLogWithAudit:
    async def test_calls_audit(self, repo: AsyncMock) -> None:
        from unittest.mock import AsyncMock

        from app.application.services.node_management_service import (
            NodeManagementService,
        )

        audit_mock = AsyncMock()
        svc = NodeManagementService(
            reader=repo,
            writer=repo,
            credential_cipher=AesGcmCredentialCipher(),
            audit_service=audit_mock,
        )
        await svc._log("test_action", node_id=uuid.uuid4(), details={"k": "v"})
        audit_mock.log.assert_awaited_once()
