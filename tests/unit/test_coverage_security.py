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


class TestJWTHandlerCoverage:
    def test_encode_and_decode_access(self) -> None:
        from app.adapters.security.jwt_handler import JWTHandlerAdapter

        handler = JWTHandlerAdapter()
        # Use test settings: SECRET_KEY len 32+
        token = handler.encode_access_token(
            user_id=str(uuid.uuid4()), email="test@example.com", is_superuser=True
        )
        payload = handler.decode_token(token, expected_type="access")
        assert payload["email"] == "test@example.com"
        assert payload["is_superuser"] is True
        assert payload["type"] == "access"

    def test_encode_and_decode_refresh(self) -> None:
        from app.adapters.security.jwt_handler import JWTHandlerAdapter

        handler = JWTHandlerAdapter()
        token = handler.encode_refresh_token(user_id=str(uuid.uuid4()))
        payload = handler.decode_token(token, expected_type="refresh")
        assert payload["type"] == "refresh"

    def test_decode_wrong_type_raises(self) -> None:
        import jwt

        from app.adapters.security.jwt_handler import JWTHandlerAdapter

        handler = JWTHandlerAdapter()
        token = handler.encode_access_token(
            user_id=str(uuid.uuid4()), email="a@a.com", is_superuser=False
        )
        with pytest.raises(jwt.InvalidTokenError):
            handler.decode_token(token, expected_type="refresh")

    def test_hash_token(self) -> None:
        from app.adapters.security.jwt_handler import JWTHandlerAdapter

        handler = JWTHandlerAdapter()
        h = handler.hash_token("mytoken")
        assert len(h) == 64

    def test_decode_unsupported_claim(self) -> None:
        import jwt

        from app.adapters.security.jwt_handler import JWTHandlerAdapter

        handler = JWTHandlerAdapter()
        # create token with unsupported claim type (list)
        import datetime

        settings = MagicMock()
        settings.SECRET_KEY = "0123456789abcdef0123456789ABCDEF"
        payload = {
            "sub": str(uuid.uuid4()),
            "type": "access",
            "exp": datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=5),
            "iat": datetime.datetime.now(datetime.UTC),
            "iss": "node-nexus-api",
            "bad": ["unsupported"],
        }
        token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
        with patch(
            "app.adapters.security.jwt_handler.get_settings", return_value=settings
        ):
            with pytest.raises(jwt.InvalidTokenError):
                handler.decode_token(token, expected_type="access")


class TestKnownHostsCoverage:
    @pytest.mark.asyncio
    async def test_ensure_directory_creates(self, tmp_path) -> None:
        from app.adapters.runtime.known_hosts import FileKnownHostsManager

        settings = MagicMock()
        settings.SSH_KNOWN_HOSTS_PATH = str(tmp_path / ".ssh" / "known_hosts")
        settings.SSH_KNOWN_HOSTS_FETCH_TIMEOUT = 10
        settings.SSH_KNOWN_HOSTS_AUTO_ADD = False
        mgr = FileKnownHostsManager(settings)
        await mgr.ensure_directory()
        assert (tmp_path / ".ssh" / "known_hosts").exists()

    @pytest.mark.asyncio
    async def test_is_present_no_file(self, tmp_path) -> None:
        from app.adapters.runtime.known_hosts import FileKnownHostsManager

        settings = MagicMock()
        settings.SSH_KNOWN_HOSTS_PATH = str(tmp_path / "missing" / "known_hosts")
        settings.SSH_KNOWN_HOSTS_FETCH_TIMEOUT = 10
        settings.SSH_KNOWN_HOSTS_AUTO_ADD = True
        mgr = FileKnownHostsManager(settings)
        # no file
        result = await mgr._is_present("10.0.0.1", 22)
        assert result is False

    @pytest.mark.asyncio
    async def test_is_present_with_content(self, tmp_path) -> None:
        from app.adapters.runtime.known_hosts import FileKnownHostsManager

        p = tmp_path / "known_hosts"
        p.write_text("example.com ssh-rsa AAAAB3", encoding="utf-8")
        settings = MagicMock()
        settings.SSH_KNOWN_HOSTS_PATH = str(p)
        settings.SSH_KNOWN_HOSTS_FETCH_TIMEOUT = 5
        settings.SSH_KNOWN_HOSTS_AUTO_ADD = True
        mgr = FileKnownHostsManager(settings)
        # mock shutil.which to avoid ssh-keygen
        with patch("app.adapters.runtime.known_hosts.shutil.which", return_value=None):
            result = await mgr._is_present("example.com", 22)
            assert result is True
            result2 = await mgr._is_present("other.com", 22)
            assert result2 is False

    @pytest.mark.asyncio
    async def test_ensure_host_auto_add_disabled(self, tmp_path) -> None:
        from app.adapters.runtime.known_hosts import FileKnownHostsManager

        settings = MagicMock()
        settings.SSH_KNOWN_HOSTS_PATH = str(tmp_path / "known_hosts")
        settings.SSH_KNOWN_HOSTS_FETCH_TIMEOUT = 5
        settings.SSH_KNOWN_HOSTS_AUTO_ADD = False
        mgr = FileKnownHostsManager(settings)
        result = await mgr.ensure_host("1.2.3.4", 22)
        assert result is False

    @pytest.mark.asyncio
    async def test_refresh_host_no_ssh_keygen(self, tmp_path) -> None:
        from app.adapters.runtime.known_hosts import FileKnownHostsManager

        p = tmp_path / "known_hosts"
        p.write_text("", encoding="utf-8")
        settings = MagicMock()
        settings.SSH_KNOWN_HOSTS_PATH = str(p)
        settings.SSH_KNOWN_HOSTS_FETCH_TIMEOUT = 5
        settings.SSH_KNOWN_HOSTS_AUTO_ADD = True
        mgr = FileKnownHostsManager(settings)
        # mock fetch to avoid actual ssh-keyscan
        with patch.object(
            mgr, "_fetch_and_append", new=AsyncMock(return_value=True)
        ) as mock_fetch:
            with patch(
                "app.adapters.runtime.known_hosts.shutil.which", return_value=None
            ):
                result = await mgr.refresh_host("1.2.3.4", 22)
                assert result is True
                mock_fetch.assert_awaited_once()
