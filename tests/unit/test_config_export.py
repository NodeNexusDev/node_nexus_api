"""Tests for configuration export/import."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.config import (
    CONFIG_FORMAT_VERSION,
    CommandExport,
    ConfigExport,
    ConfigImport,
    ImportResult,
    NodeExport,
    ScriptExport,
)
from app.services.config_service import ConfigService


def _make_node_model(**overrides):
    m = MagicMock()
    m.name = overrides.get("name", "server-1")
    m.host = overrides.get("host", "10.0.0.1")
    m.port = overrides.get("port", 22)
    m.connection_type = overrides.get("connection_type", "ssh")
    m.username = overrides.get("username", "root")
    m.tags = overrides.get("tags", ["prod"])
    return m


def _make_command_model(**overrides):
    m = MagicMock()
    m.name = overrides.get("name", "check_disk")
    m.description = overrides.get("description", "Check disk")
    m.command = overrides.get("command", "df -h")
    m.parameters = overrides.get("parameters", None)
    m.tags = overrides.get("tags", [])
    return m


def _make_script_model(**overrides):
    m = MagicMock()
    m.name = overrides.get("name", "deploy")
    m.description = overrides.get("description", "Deploy script")
    m.steps = overrides.get("steps", [{"command": "echo ok"}])
    m.tags = overrides.get("tags", [])
    return m


class TestConfigExport:
    """Tests for config export."""

    @pytest.mark.asyncio
    async def test_export_all(self):
        """Export returns all nodes, commands, scripts."""
        node_repo = AsyncMock()
        cmd_repo = AsyncMock()
        script_repo = AsyncMock()

        node_repo.get_all.return_value = [
            _make_node_model(),
            _make_node_model(name="server-2"),
        ]
        cmd_repo.get_all.return_value = [_make_command_model()]
        script_repo.get_all.return_value = [_make_script_model()]

        svc = ConfigService(node_repo, cmd_repo, script_repo)
        result = await svc.export_all()

        assert len(result.nodes) == 2
        assert len(result.commands) == 1
        assert len(result.scripts) == 1
        assert result.format_version == CONFIG_FORMAT_VERSION
        assert result.application_version
        assert result.version == "0.5.0"
        assert result.exported_at is not None

    @pytest.mark.asyncio
    async def test_export_excludes_secrets(self):
        """Exported nodes don't have password/ssh_key fields."""
        node_repo = AsyncMock()
        node_repo.get_all.return_value = [_make_node_model()]
        cmd_repo = AsyncMock()
        cmd_repo.get_all.return_value = []
        script_repo = AsyncMock()
        script_repo.get_all.return_value = []

        svc = ConfigService(node_repo, cmd_repo, script_repo)
        result = await svc.export_all()

        # NodeExport schema doesn't have password/ssh_key fields
        node = result.nodes[0]
        assert not hasattr(node, "password")
        assert not hasattr(node, "ssh_key")

    @pytest.mark.asyncio
    async def test_export_empty(self):
        """Export with no data returns empty lists."""
        node_repo = AsyncMock()
        node_repo.get_all.return_value = []
        cmd_repo = AsyncMock()
        cmd_repo.get_all.return_value = []
        script_repo = AsyncMock()
        script_repo.get_all.return_value = []

        svc = ConfigService(node_repo, cmd_repo, script_repo)
        result = await svc.export_all()

        assert result.nodes == []
        assert result.commands == []
        assert result.scripts == []


class TestConfigImport:
    """Tests for config import."""

    @pytest.mark.asyncio
    async def test_import_new_items(self):
        """Import creates new items."""
        node_repo = AsyncMock()
        cmd_repo = AsyncMock()
        script_repo = AsyncMock()

        node_repo.get_all.return_value = []
        cmd_repo.get_all.return_value = []
        script_repo.get_all.return_value = []

        svc = ConfigService(node_repo, cmd_repo, script_repo)

        data = ConfigImport(
            nodes=[
                NodeExport(name="n1", host="1.1.1.1", port=22, connection_type="ssh")
            ],
            commands=[CommandExport(name="c1", command="ls")],
            scripts=[ScriptExport(name="s1", steps=[{"command": "echo hi"}])],
        )

        result = await svc.import_config(data)

        assert result.nodes_created == 1
        assert result.commands_created == 1
        assert result.scripts_created == 1
        assert result.errors == []
        node_repo.create.assert_called_once()
        cmd_repo.create.assert_called_once()
        script_repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_import_skips_duplicates(self):
        """Import skips items that already exist by name."""
        node_repo = AsyncMock()
        cmd_repo = AsyncMock()
        script_repo = AsyncMock()

        existing_node = _make_node_model(name="existing")
        node_repo.get_all.return_value = [existing_node]
        cmd_repo.get_all.return_value = []
        script_repo.get_all.return_value = []

        svc = ConfigService(node_repo, cmd_repo, script_repo)

        data = ConfigImport(
            nodes=[
                NodeExport(
                    name="existing",
                    host="1.1.1.1",
                    port=22,
                    connection_type="ssh",
                )
            ],
        )

        result = await svc.import_config(data)

        assert result.nodes_created == 0
        assert len(result.errors) == 1
        assert "already exists" in result.errors[0]
        node_repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_import_empty(self):
        """Import with no data returns zeros."""
        node_repo = AsyncMock()
        cmd_repo = AsyncMock()
        script_repo = AsyncMock()

        svc = ConfigService(node_repo, cmd_repo, script_repo)

        result = await svc.import_config(ConfigImport())

        assert result.nodes_created == 0
        assert result.commands_created == 0
        assert result.scripts_created == 0
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_unknown_major_is_rejected_before_repository_access(self):
        from app.core.exceptions import UnsupportedConfigFormatError

        node_repo = AsyncMock()
        cmd_repo = AsyncMock()
        script_repo = AsyncMock()
        svc = ConfigService(node_repo, cmd_repo, script_repo)

        with pytest.raises(UnsupportedConfigFormatError):
            await svc.import_config(ConfigImport(format_version="2.0"))

        node_repo.get_all.assert_not_called()
        cmd_repo.get_all.assert_not_called()
        script_repo.get_all.assert_not_called()

    @pytest.mark.asyncio
    async def test_import_preloads_once_and_skips_payload_duplicates(self):
        """Duplicate detection is linear and includes earlier payload items."""
        node_repo = AsyncMock()
        cmd_repo = AsyncMock()
        script_repo = AsyncMock()
        node_repo.get_all.return_value = []
        svc = ConfigService(node_repo, cmd_repo, script_repo)
        duplicate = NodeExport(
            name="same",
            host="1.1.1.1",
            port=22,
            connection_type="ssh",
        )

        result = await svc.import_config(ConfigImport(nodes=[duplicate, duplicate]))

        assert result.nodes_created == 1
        assert len(result.errors) == 1
        node_repo.get_all.assert_awaited_once_with(skip=0, limit=1000)
        node_repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_load_all_has_no_fixed_total_limit(self):
        repo = AsyncMock()
        repo.get_all.side_effect = [[MagicMock()] * 1000, [MagicMock()] * 2]

        items = await ConfigService._load_all(repo)

        assert len(items) == 1002
        assert repo.get_all.await_args_list[1].kwargs == {"skip": 1000, "limit": 1000}


class TestConfigSchemas:
    """Tests for config export/import schemas."""

    def test_config_export_schema(self):
        """ConfigExport can be serialized."""
        data = ConfigExport(
            exported_at="2026-01-01T00:00:00Z",
            nodes=[
                NodeExport(name="n", host="1.1.1.1", port=22, connection_type="ssh")
            ],
        )
        d = data.model_dump()
        assert d["format_version"] == CONFIG_FORMAT_VERSION
        assert d["application_version"]
        assert d["version"] == "0.5.0"
        assert len(d["nodes"]) == 1

    def test_import_result_schema(self):
        """ImportResult has correct defaults."""
        r = ImportResult()
        assert r.nodes_created == 0
        assert r.errors == []
