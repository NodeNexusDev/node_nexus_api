"""Remote command execution application DTO."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CommandExecutionDTO:
    """Transport-independent result of a command executed on one node."""

    node_id: UUID
    node_name: str
    stdout: str
    stderr: str
    exit_code: int
