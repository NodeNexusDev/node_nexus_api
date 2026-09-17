"""Tests for SafeName (no control characters in user-supplied names)."""

import pytest
from pydantic import BaseModel, ValidationError

from app.schemas.api_key import APIKeyCreate
from app.schemas.command import CommandCreate
from app.schemas.common import SafeName
from app.schemas.compose import ComposeCreate
from app.schemas.docker_schemas.container import ContainerRenameRequest
from app.schemas.docker_schemas.network import NetworkCreateRequest
from app.schemas.docker_schemas.volume import VolumeCreateRequest
from app.schemas.favorite import FavoriteCreate
from app.schemas.node_schemas.node import NodeCreate
from app.schemas.script import ScriptCreate
from app.schemas.template_pack import PackCreate
from app.schemas.template_registry import RegistryCreate


class _M(BaseModel):
    name: SafeName


@pytest.mark.parametrize("bad", ["bad\x00name", "a\nb", "a\tb", "a\x1fb", "a\x7fb"])
def test_control_characters_rejected(bad: str) -> None:
    with pytest.raises(ValidationError):
        _M(name=bad)


@pytest.mark.parametrize("good", ["n", "bulk-tag-1", "docker-install", "имя_ноды 1.0"])
def test_normal_names_accepted(good: str) -> None:
    assert _M(name=good).name == good


def test_node_create_rejects_null_byte() -> None:
    with pytest.raises(ValidationError):
        NodeCreate(name="bad\x00name", host="h")


def test_create_models_reject_null_byte() -> None:
    with pytest.raises(ValidationError):
        CommandCreate(name="x\x00", command="echo hi")
    with pytest.raises(ValidationError):
        ScriptCreate(name="x\x00", steps=[{"label": "s", "type": "inline"}])
    with pytest.raises(ValidationError):
        APIKeyCreate(name="x\x00")
    with pytest.raises(ValidationError):
        FavoriteCreate(target_type="node", target_id="1", name="x\x00")
    with pytest.raises(ValidationError):
        ContainerRenameRequest(new_name="x\x00")
    with pytest.raises(ValidationError):
        NetworkCreateRequest(name="x\x00")
    with pytest.raises(ValidationError):
        VolumeCreateRequest(name="x\x00")
    with pytest.raises(ValidationError):
        ComposeCreate(project_name="x\x00", compose="services: {}")
    with pytest.raises(ValidationError):
        RegistryCreate(owner="o", name="x\x00")
    with pytest.raises(ValidationError):
        PackCreate(pack_id="p", name="x\x00", version="1.0.0")
