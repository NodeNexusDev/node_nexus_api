"""HTTP client helpers for E2E tests."""

import httpx2 as httpx


def make_client(
    base_url: str,
    api_key: str = "e2e-master-key-12345",
    timeout: float = 30.0,
) -> httpx.Client:
    """Create a synchronous HTTP client with default auth headers."""
    return httpx.Client(
        base_url=base_url,
        timeout=timeout,
        headers={"X-API-Key": api_key},
    )


def make_client_no_auth(
    base_url: str,
    timeout: float = 30.0,
) -> httpx.Client:
    """Create a synchronous HTTP client without authentication headers."""
    return httpx.Client(
        base_url=base_url,
        timeout=timeout,
    )


def e2e_base_url(host: str, port: int) -> str:
    """Build the base URL for the E2E API."""
    return f"http://{host}:{port}"
