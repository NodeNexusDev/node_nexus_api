"""Shared test helpers."""

import socket
from unittest.mock import MagicMock


class _AsyncBoundary:
    def __init__(self, spy: "TransactionSpy", *, transaction: bool) -> None:
        self._spy = spy
        self._transaction = transaction

    async def __aenter__(self) -> object:
        if self._transaction:
            self._spy.transaction_entries += 1
            self._spy.transaction_active = True
        else:
            self._spy.session_entries += 1
            self._spy.session_active = True
        return self._spy.session

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> bool:
        if self._transaction:
            self._spy.transaction_exits += 1
            self._spy.transaction_active = False
        else:
            self._spy.session_exits += 1
            self._spy.session_active = False
        return False


class TransactionSpy:
    """Sessionmaker test double that records short transaction boundaries."""

    def __init__(self, session: object | None = None) -> None:
        self.session = session if session is not None else object()
        self.session_entries = 0
        self.session_exits = 0
        self.transaction_entries = 0
        self.transaction_exits = 0
        self.session_active = False
        self.transaction_active = False

    def __call__(self) -> _AsyncBoundary:
        return _AsyncBoundary(self, transaction=False)

    def begin(self) -> _AsyncBoundary:
        return _AsyncBoundary(self, transaction=True)


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
