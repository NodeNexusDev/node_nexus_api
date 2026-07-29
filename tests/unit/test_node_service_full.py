"""Full coverage tests for NodeService."""

import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import NodeNameConflictError, NodeNotFoundError
from app.core.security import decrypt, encrypt
from app.repositories.node_repo import NodeRepository
from app.schemas.node import BulkCommandRequest, NodeCreate, NodeUpdate
from app.services.node_service import NodeService
from tests.unit.conftest import make_orm_node


@pytest.fixture
def repo() -> AsyncMock:
    return AsyncMock(spec=NodeRepository)


@pytest.fixture
def service(repo: AsyncMock) -> NodeService:
    return NodeService(repository=repo)


class TestGetNode:
    async def test_found(self, service: NodeService, repo: AsyncMock) -> None:
        orm_node = make_orm_node()
        repo.get_by_id.return_value = orm_node
        result = await service.get_node(orm_node.id)
        assert result.name == "server-1"

    async def test_not_found(self, service: NodeService, repo: AsyncMock) -> None:
        repo.get_by_id.return_value = None
        with pytest.raises(NodeNotFoundError):
            await service.get_node(uuid.uuid4())


class TestGetAllNodes:
    async def test_empty(self, service: NodeService, repo: AsyncMock) -> None:
        repo.get_all.return_value = []
        repo.count.return_value = 0
        nodes, total = await service.get_all_nodes()
        assert nodes == []
        assert total == 0

    async def test_with_data(self, service: NodeService, repo: AsyncMock) -> None:
        nodes = [make_orm_node(name="n1"), make_orm_node(name="n2")]
        repo.get_all.return_value = nodes
        repo.count.return_value = 2
        result_nodes, total = await service.get_all_nodes()
        assert len(result_nodes) == 2
        assert total == 2


class TestCreateNode:
    async def test_creates_node(self, service: NodeService, repo: AsyncMock) -> None:
        orm_node = make_orm_node()
        repo.create.return_value = orm_node
        data = NodeCreate(name="test", host="1.2.3.4", connection_type="ssh")
        result = await service.create_node(data)
        assert result.name == "server-1"
        repo.create.assert_called_once()

    async def test_duplicate_name_is_domain_conflict(
        self, service: NodeService, repo: AsyncMock
    ) -> None:
        repo.create.side_effect = IntegrityError("insert", {}, Exception("unique"))
        data = NodeCreate(name="duplicate", host="1.2.3.4", connection_type="ssh")

        with pytest.raises(NodeNameConflictError, match="duplicate"):
            await service.create_node(data)

    async def test_encrypts_password(
        self, service: NodeService, repo: AsyncMock
    ) -> None:
        orm_node = make_orm_node()
        repo.create.return_value = orm_node
        data = NodeCreate(
            name="test",
            host="1.2.3.4",
            connection_type="ssh",
            password="secret123",
        )
        await service.create_node(data)
        call_data = repo.create.call_args[0][0]
        assert call_data["password"] != "secret123"
        assert decrypt(call_data["password"]) == "secret123"

    async def test_encrypts_ssh_key(
        self, service: NodeService, repo: AsyncMock
    ) -> None:
        orm_node = make_orm_node()
        repo.create.return_value = orm_node
        key = "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----"
        data = NodeCreate(
            name="test",
            host="1.2.3.4",
            connection_type="ssh",
            ssh_key=key,
        )
        await service.create_node(data)
        call_data = repo.create.call_args[0][0]
        assert "BEGIN" not in call_data["ssh_key"]


class TestUpdateNode:
    async def test_found(self, service: NodeService, repo: AsyncMock) -> None:
        orm_node = make_orm_node()
        repo.update.return_value = orm_node
        data = NodeUpdate(name="updated")
        result = await service.update_node(orm_node.id, data)
        assert result.name == "server-1"

    async def test_not_found(self, service: NodeService, repo: AsyncMock) -> None:
        repo.update.return_value = None
        with pytest.raises(NodeNotFoundError):
            await service.update_node(uuid.uuid4(), NodeUpdate(name="x"))

    async def test_encrypts_fields(self, service: NodeService, repo: AsyncMock) -> None:
        orm_node = make_orm_node()
        repo.update.return_value = orm_node
        data = NodeUpdate(password="newpass")
        await service.update_node(orm_node.id, data)
        call_data = repo.update.call_args[0][1]
        assert call_data["password"] != "newpass"


class TestDeleteNode:
    async def test_found(self, service: NodeService, repo: AsyncMock) -> None:
        repo.get_by_id.return_value = make_orm_node()
        result = await service.delete_node(uuid.uuid4())
        assert result is True
        repo.delete.assert_awaited_once()

    async def test_not_found(self, service: NodeService, repo: AsyncMock) -> None:
        repo.get_by_id.return_value = None
        with pytest.raises(NodeNotFoundError):
            await service.delete_node(uuid.uuid4())


class TestDecryptValue:
    def test_none_returns_none(self) -> None:
        from app.core.ssh_utils import decrypt_value

        assert decrypt_value(None) is None

    def test_empty_string_returns_empty(self) -> None:
        from app.core.ssh_utils import decrypt_value

        assert decrypt_value("") == ""

    def test_encrypted_value_decrypts(self) -> None:
        from app.core.ssh_utils import decrypt_value

        token = encrypt("secret")
        assert decrypt_value(token) == "secret"

    def test_non_encrypted_value_returns_as_is(self) -> None:
        from app.core.ssh_utils import decrypt_value

        assert decrypt_value("plain-text") == "plain-text"

    def test_tampered_ciphertext_fails_closed(self) -> None:
        from app.core.exceptions import CredentialDecryptionError
        from app.core.ssh_utils import decrypt_value

        token = encrypt("secret")
        tampered = f"{token[:-1]}{'A' if token[-1] != 'A' else 'B'}"
        with pytest.raises(CredentialDecryptionError):
            decrypt_value(tampered)


class TestCheckConnectivityEdgeCases:
    async def test_node_not_found(self, service: NodeService, repo: AsyncMock) -> None:
        repo.get_by_id.return_value = None
        with pytest.raises(NodeNotFoundError):
            await service.check_connectivity(uuid.uuid4())


class TestExecuteCommandEdgeCases:
    async def test_node_not_found(self, service: NodeService, repo: AsyncMock) -> None:
        repo.get_by_id.return_value = None
        with pytest.raises(NodeNotFoundError):
            from app.schemas.node import CommandRequest

            await service.execute_command(uuid.uuid4(), CommandRequest(command="ls"))


class TestGetAllNodesFiltering:
    async def test_delegates_to_filtered_with_tags(
        self, service: NodeService, repo: AsyncMock
    ) -> None:
        nodes = [make_orm_node(name="n1")]
        repo.get_filtered.return_value = nodes
        repo.count_filtered.return_value = 1
        result_nodes, total = await service.get_all_nodes(tags=["prod"])
        assert len(result_nodes) == 1
        assert total == 1
        repo.get_filtered.assert_called_once_with(
            tags=["prod"], search=None, skip=0, limit=20
        )

    async def test_delegates_to_filtered_with_search(
        self, service: NodeService, repo: AsyncMock
    ) -> None:
        repo.get_filtered.return_value = []
        repo.count_filtered.return_value = 0
        result_nodes, total = await service.get_all_nodes(search="web")
        assert result_nodes == []
        assert total == 0
        repo.get_filtered.assert_called_once_with(
            tags=None, search="web", skip=0, limit=20
        )

    async def test_falls_back_to_get_all_without_filters(
        self, service: NodeService, repo: AsyncMock
    ) -> None:
        nodes = [make_orm_node()]
        repo.get_all.return_value = nodes
        repo.count.return_value = 1
        result_nodes, total = await service.get_all_nodes()
        assert len(result_nodes) == 1
        repo.get_all.assert_called_once()
        repo.get_filtered.assert_not_called()


class TestBulkExecuteCommand:
    async def test_all_nodes_succeed(
        self, service: NodeService, repo: AsyncMock
    ) -> None:
        from unittest.mock import AsyncMock, MagicMock

        n1 = make_orm_node(name="n1")
        n2 = make_orm_node(name="n2")
        repo.get_by_ids.return_value = [n1, n2]

        connector = AsyncMock()
        connector.execute_command.return_value = ("ok", "", 0)
        connector.__aenter__ = AsyncMock(return_value=connector)
        connector.__aexit__ = AsyncMock(return_value=False)

        factory = MagicMock()
        factory.create_ssh.return_value = connector
        service._connector_factory = factory

        result = await service.bulk_execute_command(
            BulkCommandRequest(command="uptime", node_ids=[n1.id, n2.id])
        )
        assert result.total == 2
        assert result.succeeded == 2
        assert result.failed == 0
        assert all(r.exit_code == 0 for r in result.results)

    async def test_partial_failure(self, service: NodeService, repo: AsyncMock) -> None:
        from unittest.mock import AsyncMock, MagicMock

        n1 = make_orm_node(name="n1")
        n2 = make_orm_node(name="n2")
        repo.get_by_ids.return_value = [n1, n2]

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
        service._connector_factory = factory

        result = await service.bulk_execute_command(
            BulkCommandRequest(command="uptime", node_ids=[n1.id, n2.id])
        )
        assert result.total == 2
        assert result.succeeded == 1
        assert result.failed == 1

    async def test_no_nodes_raises(self, service: NodeService, repo: AsyncMock) -> None:
        repo.get_by_ids.return_value = []
        with pytest.raises(NodeNotFoundError):
            await service.bulk_execute_command(
                BulkCommandRequest(command="ls", node_ids=[uuid.uuid4()])
            )

    async def test_connection_error_returns_error_result(
        self, service: NodeService, repo: AsyncMock
    ) -> None:
        from unittest.mock import AsyncMock, MagicMock

        n1 = make_orm_node(name="n1")
        repo.get_by_ids.return_value = [n1]

        connector = AsyncMock()
        connector.execute_command.side_effect = OSError("Connection refused")
        connector.__aenter__ = AsyncMock(return_value=connector)
        connector.__aexit__ = AsyncMock(return_value=False)

        factory = MagicMock()
        factory.create_ssh.return_value = connector
        service._connector_factory = factory

        result = await service.bulk_execute_command(
            BulkCommandRequest(command="uptime", node_ids=[n1.id])
        )
        assert result.total == 1
        assert result.failed == 1
        assert "Connection refused" in result.results[0].stderr

    async def test_resolve_by_tags(self, service: NodeService, repo: AsyncMock) -> None:
        from unittest.mock import AsyncMock, MagicMock

        n1 = make_orm_node(name="n1")
        repo.get_by_tags.return_value = [n1]

        connector = AsyncMock()
        connector.execute_command.return_value = ("ok", "", 0)
        connector.__aenter__ = AsyncMock(return_value=connector)
        connector.__aexit__ = AsyncMock(return_value=False)

        factory = MagicMock()
        factory.create_ssh.return_value = connector
        service._connector_factory = factory

        result = await service.bulk_execute_command(
            BulkCommandRequest(command="uptime", tags=["prod"])
        )
        assert result.total == 1
        repo.get_by_tags.assert_called_once_with(["prod"])

    async def test_resolve_by_both_ids_and_tags(
        self, service: NodeService, repo: AsyncMock
    ) -> None:
        from unittest.mock import AsyncMock, MagicMock

        n1 = make_orm_node(name="n1")
        n2 = make_orm_node(name="n2")
        n3 = make_orm_node(name="n3")
        # node_ids returns n1, n2; tags returns n1, n3 → intersection = n1
        repo.get_by_ids.return_value = [n1, n2]
        repo.get_by_tags.return_value = [n1, n3]

        connector = AsyncMock()
        connector.execute_command.return_value = ("ok", "", 0)
        connector.__aenter__ = AsyncMock(return_value=connector)
        connector.__aexit__ = AsyncMock(return_value=False)

        factory = MagicMock()
        factory.create_ssh.return_value = connector
        service._connector_factory = factory

        result = await service.bulk_execute_command(
            BulkCommandRequest(command="uptime", node_ids=[n1.id, n2.id], tags=["prod"])
        )
        assert result.total == 1
        assert result.results[0].node_id == n1.id

    async def test_resolve_by_tags_empty(
        self, service: NodeService, repo: AsyncMock
    ) -> None:
        repo.get_by_tags.return_value = []
        with pytest.raises(NodeNotFoundError):
            await service.bulk_execute_command(
                BulkCommandRequest(command="ls", tags=["nonexistent"])
            )

    async def test_resolve_by_both_empty_intersection(
        self, service: NodeService, repo: AsyncMock
    ) -> None:
        n1 = make_orm_node(name="n1")
        n2 = make_orm_node(name="n2")
        # No overlap between ids and tags
        repo.get_by_ids.return_value = [n1]
        repo.get_by_tags.return_value = [n2]
        with pytest.raises(NodeNotFoundError):
            await service.bulk_execute_command(
                BulkCommandRequest(command="ls", node_ids=[n1.id], tags=["prod"])
            )


class TestLogWithAudit:
    async def test_calls_audit(self, repo: AsyncMock) -> None:
        from unittest.mock import AsyncMock

        from app.services.node_service import NodeService

        audit_mock = AsyncMock()
        svc = NodeService(
            repository=repo,
            audit_service=audit_mock,
            connector_factory=AsyncMock(),
        )
        await svc._log("test_action", node_id=uuid.uuid4(), details={"k": "v"})
        audit_mock.log.assert_awaited_once()
