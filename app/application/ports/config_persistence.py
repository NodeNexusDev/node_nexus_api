"""Focused persistence contracts for configuration import and export."""

from collections.abc import Sequence
from typing import Protocol, TypeVar

from app.application.types import PersistenceObject

RecordT_co = TypeVar("RecordT_co", covariant=True)


class ConfigRecordReader(Protocol[RecordT_co]):
    """Read configuration records in bounded pages."""

    async def get_all(
        self, skip: int = 0, limit: int = 100
    ) -> Sequence[RecordT_co]: ...


class ConfigRecordWriter(Protocol):
    """Create one configuration record in the current transaction."""

    async def create(self, data: PersistenceObject) -> object: ...


class NodeConfigRecord(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def host(self) -> str: ...
    @property
    def port(self) -> int: ...
    @property
    def connection_type(self) -> str: ...
    @property
    def username(self) -> str | None: ...
    @property
    def tags(self) -> list[str] | None: ...


class CommandConfigRecord(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def description(self) -> str | None: ...
    @property
    def command(self) -> str: ...
    @property
    def parameters(self) -> list[dict] | None: ...
    @property
    def tags(self) -> list[str] | None: ...


class ScriptConfigRecord(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def description(self) -> str | None: ...
    @property
    def steps(self) -> list[dict] | None: ...
    @property
    def tags(self) -> list[str] | None: ...


class NodeConfigStore(
    ConfigRecordReader[NodeConfigRecord],
    ConfigRecordWriter,
    Protocol,
):
    """Node configuration persistence."""


class CommandConfigStore(
    ConfigRecordReader[CommandConfigRecord],
    ConfigRecordWriter,
    Protocol,
):
    """Command configuration persistence."""


class ScriptConfigStore(
    ConfigRecordReader[ScriptConfigRecord],
    ConfigRecordWriter,
    Protocol,
):
    """Script configuration persistence."""
