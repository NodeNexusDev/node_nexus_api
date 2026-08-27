"""E2E tests for user management endpoints (superuser-only)."""

from uuid import uuid4

import httpx2 as httpx
import pytest

pytestmark = pytest.mark.docker

_SUPERUSER_EMAIL = "admin@example.com"
_SUPERUSER_PASSWORD = "e2e-super-secret"


def _superuser_client(base_url: str) -> httpx.Client:
    """Login as superuser and return a Bearer-authenticated client."""
    with httpx.Client(base_url=base_url, timeout=30.0) as tmp:
        resp = tmp.post(
            "/api/v1/auth/login",
            json={"email": _SUPERUSER_EMAIL, "password": _SUPERUSER_PASSWORD},
        )
        assert resp.status_code == 200, f"Login failed: {resp.text}"
        token = resp.json()["access_token"]
    return httpx.Client(
        base_url=base_url,
        timeout=30.0,
        headers={"Authorization": f"Bearer {token}"},
    )


def _non_superuser_client(base_url: str) -> httpx.Client:
    """Create a non-superuser by logging in with a freshly created user."""
    email = f"regular-{uuid4().hex[:8]}@test.com"
    password = "test-password-123"
    # Create user via superuser client
    with _superuser_client(base_url) as sc:
        create_resp = sc.post(
            "/api/v1/users/",
            json={"email": email, "password": password, "is_superuser": False},
        )
        assert create_resp.status_code == 201
    # Login as the new user
    with httpx.Client(base_url=base_url, timeout=30.0) as tmp:
        resp = tmp.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        assert resp.status_code == 200, f"Login failed: {resp.text}"
        token = resp.json()["access_token"]
    return httpx.Client(
        base_url=base_url,
        timeout=30.0,
        headers={"Authorization": f"Bearer {token}"},
    )


class TestListUsers:
    def test_list_users_as_superuser(
        self, e2e_client: httpx.Client, api_base_url: str
    ) -> None:
        with _superuser_client(api_base_url) as sc:
            result = sc.get("/api/v1/users/")
        assert result.status_code == 200
        body = result.json()
        assert "items" in body
        assert "total" in body
        assert isinstance(body["items"], list)
        assert body["total"] >= 1
        # Superuser should be in the list
        emails = [u["email"] for u in body["items"]]
        assert _SUPERUSER_EMAIL in emails

    def test_list_users_non_superuser_forbidden(
        self, e2e_client: httpx.Client, api_base_url: str
    ) -> None:
        with _non_superuser_client(api_base_url) as nc:
            result = nc.get("/api/v1/users/")
        assert result.status_code == 403

    def test_list_users_no_auth(self, api_base_url: str) -> None:
        with httpx.Client(base_url=api_base_url, timeout=30.0) as client:
            result = client.get("/api/v1/users/")
        assert result.status_code == 401


class TestCreateUser:
    def test_create_user(self, api_base_url: str) -> None:
        email = f"new-{uuid4().hex[:8]}@test.com"
        with _superuser_client(api_base_url) as sc:
            result = sc.post(
                "/api/v1/users/",
                json={"email": email, "password": "secure-pass-123"},
            )
        assert result.status_code == 201
        body = result.json()
        assert body["email"] == email
        assert body["is_active"] is True
        assert body["is_superuser"] is False
        assert "id" in body

    def test_create_superuser(self, api_base_url: str) -> None:
        email = f"super-{uuid4().hex[:8]}@test.com"
        with _superuser_client(api_base_url) as sc:
            result = sc.post(
                "/api/v1/users/",
                json={
                    "email": email,
                    "password": "secure-pass-123",
                    "is_superuser": True,
                },
            )
        assert result.status_code == 201
        assert result.json()["is_superuser"] is True

    def test_create_user_duplicate_email(self, api_base_url: str) -> None:
        email = f"dup-{uuid4().hex[:8]}@test.com"
        with _superuser_client(api_base_url) as sc:
            sc.post(
                "/api/v1/users/",
                json={"email": email, "password": "duplicate-pass-1"},
            )
            result = sc.post(
                "/api/v1/users/",
                json={"email": email, "password": "duplicate-pass-2"},
            )
        assert result.status_code == 409

    def test_create_user_non_superuser_forbidden(self, api_base_url: str) -> None:
        email = f"blocked-{uuid4().hex[:8]}@test.com"
        with _non_superuser_client(api_base_url) as nc:
            result = nc.post(
                "/api/v1/users/",
                json={"email": email, "password": "forbidden-pass-123"},
            )
        assert result.status_code == 403


class TestDeleteUser:
    def test_delete_user(self, api_base_url: str) -> None:
        email = f"del-{uuid4().hex[:8]}@test.com"
        with _superuser_client(api_base_url) as sc:
            create_resp = sc.post(
                "/api/v1/users/",
                json={"email": email, "password": "delete-pass-123"},
            )
            user_id = create_resp.json()["id"]
            result = sc.delete(f"/api/v1/users/{user_id}")
        assert result.status_code == 204

        # Verify user is gone
        with _superuser_client(api_base_url) as sc:
            list_resp = sc.get("/api/v1/users/")
        emails = [u["email"] for u in list_resp.json()["items"]]
        assert email not in emails

    def test_delete_nonexistent_user(self, api_base_url: str) -> None:
        fake_id = str(uuid4())
        with _superuser_client(api_base_url) as sc:
            result = sc.delete(f"/api/v1/users/{fake_id}")
        assert result.status_code == 404

    def test_delete_user_non_superuser_forbidden(self, api_base_url: str) -> None:
        email = f"protected-{uuid4().hex[:8]}@test.com"
        with _superuser_client(api_base_url) as sc:
            create_resp = sc.post(
                "/api/v1/users/",
                json={"email": email, "password": "protected-pass-123"},
            )
            user_id = create_resp.json()["id"]
        with _non_superuser_client(api_base_url) as nc:
            result = nc.delete(f"/api/v1/users/{user_id}")
        assert result.status_code == 403
