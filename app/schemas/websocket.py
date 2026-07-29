"""Versioned WebSocket command protocol schemas."""

from typing import Literal

from pydantic import BaseModel, Field


class WebSocketCommandMessage(BaseModel):
    """Start one remote command."""

    version: Literal["1"] = "1"
    type: Literal["command"] = "command"
    command: str = Field(min_length=1, max_length=4096)


class WebSocketSignalMessage(BaseModel):
    """Signal the currently active remote command."""

    version: Literal["1"] = "1"
    type: Literal["signal"]
    signal: Literal["SIGINT", "SIGTERM", "SIGHUP"]
