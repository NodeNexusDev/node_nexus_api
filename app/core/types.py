"""Shared serializable value types used at external boundaries."""

from typing import Literal

type ConnectionType = Literal["ssh", "docker", "proxmox"]
type NodeStatus = Literal["active", "unreachable", "error"]

type Tag = str
type TagList = tuple[Tag, ...]
type NodeName = str
type Host = str
type DockerHost = str

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]
