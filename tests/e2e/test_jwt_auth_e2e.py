"""E2E tests for JWT authentication flow."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import httpx2 as httpx
import pytest

pytestmark = pytest.mark.docker

_SUPERUSER_EMAIL = "admin@example.com"
_SUPERUSER_PASSWORD = "e2e-super-secret"


def _login(
    client: httpx.Client,
    email: str = _SUPERUSER_EMAIL,
    password: str = _SUPERUSER_PASSWORD,
) -> httpx.Response:
    return client.post(
        "/api/v2/auth/login", json={"email": email, "password": password}
    )


def _bearer_client(base_url: str, token: str) -> httpx.Client:
    return httpx.Client(
        base_url=base_url,
        timeout=30.0,
        headers={"Authorization": f"Bearer {token}"},
    )


class TestLogin:
    def test_login_success(self, e2e_client: httpx.Client) -> None:
        result = _login(e2e_client)
        assert result.status_code == 200
        body = result.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    def test_login_sets_refresh_cookie(self, e2e_client: httpx.Client) -> None:
        result = _login(e2e_client)
        assert result.status_code == 200
        cookies = result.cookies
        assert "refresh_token" in cookies
        assert len(cookies["refresh_token"]) > 0

    def test_login_invalid_password(self, e2e_client: httpx.Client) -> None:
        result = _login(e2e_client, password="wrong-password")
        assert result.status_code == 401
        assert "Invalid" in result.json()["detail"]

    def test_login_invalid_email(self, e2e_client: httpx.Client) -> None:
        result = _login(e2e_client, email=f"nonexistent-{uuid4()}@test.com")
        assert result.status_code == 401

    def test_login_validation_error(self, e2e_client: httpx.Client) -> None:
        result = e2e_client.post(
            "/api/v2/auth/login", json={"email": "not-an-email", "password": "x"}
        )
        assert result.status_code == 422


class TestGetMe:
    def test_me_with_valid_token(
        self, e2e_client: httpx.Client, api_base_url: str
    ) -> None:
        login_resp = _login(e2e_client)
        token = login_resp.json()["access_token"]

        with _bearer_client(api_base_url, token) as bc:
            result = bc.get("/api/v2/auth/me")
        assert result.status_code == 200
        body = result.json()
        assert body["email"] == _SUPERUSER_EMAIL
        assert body["is_superuser"] is True
        assert body["is_active"] is True
        assert "id" in body
        assert "created_at" in body

    def test_me_without_token(self, e2e_client_no_auth: httpx.Client) -> None:
        result = e2e_client_no_auth.get("/api/v2/auth/me")
        assert result.status_code == 401

    def test_me_invalid_token(self, e2e_client_no_auth: httpx.Client) -> None:
        result = e2e_client_no_auth.get(
            "/api/v2/auth/me",
            headers={"Authorization": "Bearer invalid-token-value"},
        )
        assert result.status_code == 401

    def test_me_with_api_key_rejected(self, e2e_client: httpx.Client) -> None:
        result = e2e_client.get("/api/v2/auth/me")
        assert result.status_code == 401


class TestRefresh:
    def test_refresh_success(self, e2e_client: httpx.Client, api_base_url: str) -> None:
        login_resp = _login(e2e_client)
        refresh_cookie = login_resp.cookies["refresh_token"]

        with httpx.Client(base_url=api_base_url, timeout=30.0) as client:
            client.cookies.set("refresh_token", refresh_cookie)
            result = client.post("/api/v2/auth/refresh")
        assert result.status_code == 200
        body = result.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        # New refresh token cookie should be set
        assert "refresh_token" in result.cookies

    def test_refresh_rotates_token(
        self, e2e_client: httpx.Client, api_base_url: str
    ) -> None:
        login_resp = _login(e2e_client)
        old_refresh = login_resp.cookies["refresh_token"]

        with httpx.Client(base_url=api_base_url, timeout=30.0) as client:
            client.cookies.set("refresh_token", old_refresh)
            resp1 = client.post("/api/v2/auth/refresh")
        new_refresh = resp1.cookies["refresh_token"]
        assert new_refresh != old_refresh

        # Old refresh token should no longer work (rotation)
        with httpx.Client(base_url=api_base_url, timeout=30.0) as client:
            client.cookies.set("refresh_token", old_refresh)
            resp2 = client.post("/api/v2/auth/refresh")
        assert resp2.status_code == 401

    def test_concurrent_refresh_consumes_token_once(
        self, e2e_client: httpx.Client, api_base_url: str
    ) -> None:
        login_resp = _login(e2e_client)
        old_refresh = login_resp.cookies["refresh_token"]
        barrier = Barrier(2)

        def refresh_once() -> int:
            barrier.wait(timeout=10)
            with httpx.Client(base_url=api_base_url, timeout=30.0) as client:
                client.cookies.set("refresh_token", old_refresh)
                response = client.post("/api/v2/auth/refresh")
            return response.status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(lambda _index: refresh_once(), range(2)))

        assert sorted(statuses) == [200, 401]

    def test_refresh_missing_cookie(self, api_base_url: str) -> None:
        with httpx.Client(base_url=api_base_url, timeout=30.0) as client:
            result = client.post("/api/v2/auth/refresh")
        assert result.status_code == 401
        assert "Missing refresh token" in result.json()["detail"]

    def test_refresh_invalid_token(self, api_base_url: str) -> None:
        with httpx.Client(base_url=api_base_url, timeout=30.0) as client:
            client.cookies.set("refresh_token", "invalid-refresh-token")
            result = client.post("/api/v2/auth/refresh")
        assert result.status_code == 401


class TestLogout:
    def test_logout_clears_cookie(
        self, e2e_client: httpx.Client, api_base_url: str
    ) -> None:
        login_resp = _login(e2e_client)
        refresh_cookie = login_resp.cookies["refresh_token"]

        with httpx.Client(base_url=api_base_url, timeout=30.0) as client:
            client.cookies.set("refresh_token", refresh_cookie)
            result = client.post("/api/v2/auth/logout")
        assert result.status_code == 204

    def test_logout_without_cookie(self, api_base_url: str) -> None:
        with httpx.Client(base_url=api_base_url, timeout=30.0) as client:
            result = client.post("/api/v2/auth/logout")
        assert result.status_code == 204

    def test_logout_invalidates_refresh_token(
        self, e2e_client: httpx.Client, api_base_url: str
    ) -> None:
        login_resp = _login(e2e_client)
        refresh_cookie = login_resp.cookies["refresh_token"]

        with httpx.Client(base_url=api_base_url, timeout=30.0) as client:
            client.cookies.set("refresh_token", refresh_cookie)
            client.post("/api/v2/auth/logout")
            # Try to use the same refresh token after logout
            client.cookies.set("refresh_token", refresh_cookie)
            result = client.post("/api/v2/auth/refresh")
        assert result.status_code == 401
