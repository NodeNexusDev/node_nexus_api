"""Coverage – security / infra (cipher, sse, runner, config)."""

from __future__ import annotations

import asyncio
import base64
import uuid
from typing import override
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.security.credential_cipher import decrypt_value
from app.application.services.config_service import ConfigService, _application_version
from app.application.services.docker.command_runner import DockerCommandRunner
from app.application.services.sse_broadcaster import SseBroadcaster
from app.core.exceptions import CredentialDecryptionError, DockerError


class TestCredentialCipherCoverage:
    def test_decrypt_value_plaintext_raises(self) -> None:
        # legacy plaintext no longer accepted — only enc:v1: allowed
        with pytest.raises(CredentialDecryptionError):
            decrypt_value("plain_text")
        assert decrypt_value("") == ""
        assert decrypt_value(None) is None

    def test_decrypt_without_prefix_raises(self) -> None:
        raw = base64.b64encode(b"a" * 32).decode()
        with pytest.raises(CredentialDecryptionError):
            decrypt_value(raw)

    def test_decrypt_value_generic_exception(self) -> None:
        # line 76-77
        with patch(
            "app.adapters.security.credential_cipher.decrypt",
            side_effect=RuntimeError("boom"),
        ):
            # need a value that looks encrypted -> prefix enc:v1:
            with pytest.raises(CredentialDecryptionError):
                decrypt_value("enc:v1:abc")

    def test_decrypt_value_value_error(self) -> None:
        with patch(
            "app.adapters.security.credential_cipher.decrypt",
            side_effect=ValueError("bad"),
        ):
            with pytest.raises(CredentialDecryptionError):
                decrypt_value("enc:v1:abc")


class TestSseBroadcasterQueueFull:
    def test_subscribe_queue_full_branch(self) -> None:
        bc = SseBroadcaster()
        # fill history with 60 events
        for i in range(60):
            bc.publish(f"ev{i}", {"i": i})
        # make Queue.put_nowait raise QueueFull on first call via patch
        call_count = {"n": 0}

        class FakeQueue(asyncio.Queue[object]):  # type: ignore[type-arg]
            @override
            def put_nowait(self, item: object) -> None:
                call_count["n"] += 1
                if call_count["n"] == 1:
                    raise asyncio.QueueFull
                super().put_nowait(item)

        with patch("asyncio.Queue", FakeQueue):
            # internal subscribe will try to put _history[-50:] (50 items)
            # first put raises -> break
            sub_id, q = bc.subscribe()
            # queue should be empty because break after first failure
            assert q.empty()

    def test_publish_queue_full_removes_dead(self) -> None:
        bc = SseBroadcaster()
        sub_id, q = bc.subscribe()
        # mock put_nowait to raise
        with patch.object(q, "put_nowait", side_effect=asyncio.QueueFull):
            bc.publish("test", {"a": 1})
            assert sub_id not in bc._queues


class TestCommandRunnerCoverage:
    @pytest.mark.asyncio
    async def test_get_targets_by_tags(self) -> None:
        reader = MagicMock()
        reader.get_connections_by_tags = AsyncMock(return_value=[])
        runner = DockerCommandRunner(node_reader=reader, runtime=MagicMock())
        res = await runner.get_targets_by_tags(["prod"])
        assert res == []
        reader.get_connections_by_tags.assert_awaited_once_with(["prod"])

    @pytest.mark.asyncio
    async def test_get_target_docker_error(self) -> None:
        from app.application.dto.node_connection import NodeConnectionDTO
        from app.application.dto.value_objects import NodeCredentials, NodeEndpoint

        node = NodeConnectionDTO(
            id=uuid.uuid4(),
            name="n",
            endpoint=NodeEndpoint(
                host="h", port=22, connection_type="ssh", has_docker=False
            ),
            credentials=NodeCredentials(username="root"),
        )
        # need is_docker_available false -> has_docker false already
        reader = MagicMock()
        reader.get_connection = AsyncMock(return_value=node)
        runner = DockerCommandRunner(node_reader=reader, runtime=MagicMock())
        with pytest.raises(DockerError):
            await runner.get_target(uuid.uuid4())


class TestConfigServiceCoverage:
    def test_application_version_fallback(self) -> None:
        with patch(
            "app.application.services.config_service.version",
            side_effect=__import__(
                "importlib.metadata", fromlist=["PackageNotFoundError"]
            ).PackageNotFoundError,
        ):
            assert _application_version() == "unknown"

    def test_application_version_ok(self) -> None:
        with patch(
            "app.application.services.config_service.version", return_value="9.9.9"
        ):
            assert _application_version() == "9.9.9"

    @pytest.mark.asyncio
    async def test_export_all(self) -> None:
        exporter = AsyncMock()
        from app.application.dto.config import ConfigTransferDTO

        exporter.export_config = AsyncMock(
            return_value=ConfigTransferDTO(nodes=(), commands=(), scripts=())
        )
        svc = ConfigService(exporter=exporter, importer=AsyncMock())
        res = await svc.export_all()
        assert res.format_version == "1.0"

    @pytest.mark.asyncio
    async def test_import_config_unsupported(self) -> None:
        svc = ConfigService(exporter=MagicMock(), importer=AsyncMock())
        from app.application.dto.config import ConfigTransferDTO
        from app.core.exceptions import UnsupportedConfigFormatError

        with pytest.raises(UnsupportedConfigFormatError):
            await svc.import_config(
                ConfigTransferDTO(
                    format_version="9.0", nodes=(), commands=(), scripts=()
                )
            )

    @pytest.mark.asyncio
    async def test_import_config_dry_run(self) -> None:
        importer = AsyncMock()
        importer.preview_import = AsyncMock(return_value=MagicMock())
        svc = ConfigService(exporter=MagicMock(), importer=importer)
        from app.application.dto.config import ConfigTransferDTO

        await svc.import_config(
            ConfigTransferDTO(format_version="1.0", nodes=(), commands=(), scripts=()),
            dry_run=True,
        )
        importer.preview_import.assert_awaited_once()
