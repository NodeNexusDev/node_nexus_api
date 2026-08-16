"""Tests for uncovered DTOs, services, and remaining low-coverage files."""

from __future__ import annotations

import uuid

from app.application.dto.clone import CloneCommandDTO, CloneScriptDTO


class TestCloneDTO:
    def test_clone_command_dto(self) -> None:
        cmd_id = uuid.uuid4()
        dto = CloneCommandDTO(command_id=cmd_id, new_name="my-copy")
        assert dto.command_id == cmd_id
        assert dto.new_name == "my-copy"

    def test_clone_command_dto_default_name(self) -> None:
        dto = CloneCommandDTO(command_id=uuid.uuid4())
        assert dto.new_name is None

    def test_clone_script_dto(self) -> None:
        script_id = uuid.uuid4()
        dto = CloneScriptDTO(script_id=script_id, new_name="backup-copy")
        assert dto.script_id == script_id
        assert dto.new_name == "backup-copy"

    def test_clone_script_dto_default_name(self) -> None:
        dto = CloneScriptDTO(script_id=uuid.uuid4())
        assert dto.new_name is None
