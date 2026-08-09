"""WebSocket client factory for E2E authentication modes."""

from dataclasses import dataclass
from urllib.parse import quote

import websockets
from websockets.asyncio.client import connect


@dataclass(frozen=True)
class WebSocketClientFactory:
    """Build WebSocket connections using header or legacy query-token auth."""

    base_url: str

    def connect_with_header(
        self,
        path: str,
        token: str,
        *,
        open_timeout: float | None = 10,
    ) -> connect:
        """Return a connection context manager authenticated by header."""
        return websockets.connect(
            f"{self.base_url}{path}",
            additional_headers={"X-API-Key": token},
            open_timeout=open_timeout,
        )

    def connect_with_query(
        self,
        path: str,
        token: str,
        *,
        open_timeout: float | None = 10,
    ) -> connect:
        """Return a connection context manager using the compatibility token."""
        separator = "&" if "?" in path else "?"
        url = f"{self.base_url}{path}{separator}token={quote(token, safe='')}"
        return websockets.connect(url, open_timeout=open_timeout)
