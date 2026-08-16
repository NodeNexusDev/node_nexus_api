"""Tests for clone methods in command and script management services."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.application.dto.command_management import CommandViewDTO
from app.application.dto.script_management import ScriptViewDTO
from app.application.services.command_management_service import (
    CommandManagementService,
)
from app.application.services.script_management_service import (
    ScriptManagementService,
)
from app.core.exceptions import CommandNotFoundError, ScriptNotFoundError


class TestCommandManagementServiceClone:
    @pytest.mark.asyncio
    async def test_clone_command(self) -> None:
        reader = AsyncMock()
        writer = AsyncMock()
        svc = CommandManagementService(reader=reader, writer=writer)

        original = CommandViewDTO(
            id=uuid.uuid4(),
            name="deploy",
            description="Deploy app",
            command="echo ok",
            parameters=(),
            tags=("prod",),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        reader.get_command.return_value = original

        cloned = CommandViewDTO(
            id=uuid.uuid4(),
            name="deploy-copy",
            description="Deploy app",
            command="echo ok",
            parameters=(),
            tags=("prod",),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        writer.create_command.return_value = cloned

        result = await svc.clone_command(original.id, new_name="deploy-copy")
        assert result.name == "deploy-copy"
        writer.create_command.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_clone_command_default_name(self) -> None:
        reader = AsyncMock()
        writer = AsyncMock()
        svc = CommandManagementService(reader=reader, writer=writer)

        original = CommandViewDTO(
            id=uuid.uuid4(),
            name="deploy",
            description=None,
            command="echo ok",
            parameters=(),
            tags=(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        reader.get_command.return_value = original

        cloned = CommandViewDTO(
            id=uuid.uuid4(),
            name="deploy-copy",
            description=None,
            command="echo ok",
            parameters=(),
            tags=(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        writer.create_command.return_value = cloned

        result = await svc.clone_command(original.id)
        assert result.name == "deploy-copy"

    @pytest.mark.asyncio
    async def test_clone_command_not_found(self) -> None:
        reader = AsyncMock()
        reader.get_command.return_value = None
        writer = AsyncMock()
        svc = CommandManagementService(reader=reader, writer=writer)

        with pytest.raises(CommandNotFoundError):
            await svc.clone_command(uuid.uuid4())


class TestScriptManagementServiceClone:
    @pytest.mark.asyncio
    async def test_clone_script(self) -> None:
        reader = AsyncMock()
        writer = AsyncMock()
        svc = ScriptManagementService(reader=reader, writer=writer)

        original = ScriptViewDTO(
            id=uuid.uuid4(),
            name="backup",
            description="Backup DB",
            steps=(),
            tags=("db",),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        reader.get_script.return_value = original

        cloned = ScriptViewDTO(
            id=uuid.uuid4(),
            name="backup-copy",
            description="Backup DB",
            steps=(),
            tags=("db",),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        writer.create_script.return_value = cloned

        result = await svc.clone_script(original.id, new_name="backup-copy")
        assert result.name == "backup-copy"
        writer.create_script.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_clone_script_default_name(self) -> None:
        reader = AsyncMock()
        writer = AsyncMock()
        svc = ScriptManagementService(reader=reader, writer=writer)

        original = ScriptViewDTO(
            id=uuid.uuid4(),
            name="backup",
            description=None,
            steps=(),
            tags=(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        reader.get_script.return_value = original

        cloned = ScriptViewDTO(
            id=uuid.uuid4(),
            name="backup-copy",
            description=None,
            steps=(),
            tags=(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        writer.create_script.return_value = cloned

        result = await svc.clone_script(original.id)
        assert result.name == "backup-copy"

    @pytest.mark.asyncio
    async def test_clone_script_not_found(self) -> None:
        reader = AsyncMock()
        reader.get_script.return_value = None
        writer = AsyncMock()
        svc = ScriptManagementService(reader=reader, writer=writer)

        with pytest.raises(ScriptNotFoundError):
            await svc.clone_script(uuid.uuid4())
