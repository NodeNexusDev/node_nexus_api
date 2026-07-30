"""Transport-independent remote process stream values."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class RemoteStreamEventDTO:
    """One stdout, stderr, or process-exit event."""

    type: Literal["stdout", "stderr", "exit"]
    data: str | None = None
    exit_code: int | None = None
