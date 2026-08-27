"""Shared test fixtures."""

import os
import socket
from unittest.mock import MagicMock

os.environ.setdefault("ENVIRONMENT", "test")


def is_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def mock_settings(master_key: str = "") -> MagicMock:
    settings = MagicMock()
    settings.MASTER_API_KEY = master_key
    return settings
