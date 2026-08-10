"""Alembic migration E2E tests (Phase K).

Verifies that database migrations run correctly on fresh and existing databases,
and that data survives migration and restart cycles.
"""

import time

import asyncpg
import httpx2 as httpx
import pytest

from tests.e2e.helpers.resources import UniqueResourceFactory
from tests.e2e.helpers.service_controller import DockerServiceController

pytestmark = [pytest.mark.docker, pytest.mark.e2e_migration]


class TestMigrationFreshDB:
    """Migration behavior on a fresh database (AUTO_MIGRATE=true)."""

    def test_api_starts_and_becomes_ready(self, e2e_client: httpx.Client) -> None:
        """API with AUTO_MIGRATE=true starts and passes readiness probe."""
        resp = e2e_client.get("/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert data["checks"]["database"]["status"] == "ok"
        assert data["checks"]["database"]["detail"]

    @pytest.mark.asyncio
    async def test_fresh_db_has_all_tables(
        self,
        postgres_connection: asyncpg.Connection,
    ) -> None:
        """Fresh database has all expected tables after migration."""
        rows = await postgres_connection.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' ORDER BY table_name"
        )
        tables = {row["table_name"] for row in rows}
        expected = {
            "nodes",
            "commands",
            "scripts",
            "script_executions",
            "api_keys",
            "audit_logs",
            "audit_outbox",
            "script_schedules",
        }
        assert expected.issubset(tables), f"Missing tables: {expected - tables}"

    @pytest.mark.asyncio
    async def test_alembic_version_row_exists(
        self,
        postgres_connection: asyncpg.Connection,
    ) -> None:
        """alembic_version table has exactly one head revision."""
        rows = await postgres_connection.fetch(
            "SELECT version_num FROM alembic_version"
        )
        assert len(rows) == 1, f"Expected 1 alembic version row, got {len(rows)}"
        assert rows[0]["version_num"], "Version num should not be empty"


class TestMigrationDataPreservation:
    """Data survives migration and restart cycles."""

    def test_data_survives_api_restart(
        self,
        e2e_client: httpx.Client,
        e2e_resources: UniqueResourceFactory,
        docker_service_controller: DockerServiceController,
    ) -> None:
        """Persistent data (nodes, keys) survives API restart with AUTO_MIGRATE."""
        # Create resources
        node = e2e_resources.create_ssh_node()

        # Restart API (triggers migration check + startup)
        docker_service_controller.restart("api")

        # Wait for readiness
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            try:
                resp = e2e_client.get("/ready")
                if resp.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)

        # Data should still be accessible
        resp = e2e_client.get(f"/api/v1/nodes/{node['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == node["id"]
        assert resp.json()["name"] == node["name"]

    def test_repeated_restart_idempotent(
        self,
        e2e_client: httpx.Client,
        e2e_resources: UniqueResourceFactory,
        docker_service_controller: DockerServiceController,
    ) -> None:
        """Multiple restarts don't corrupt data or change schema."""
        node = e2e_resources.create_ssh_node()

        # Restart API twice
        for _ in range(2):
            docker_service_controller.restart("api")
            deadline = time.monotonic() + 30.0
            while time.monotonic() < deadline:
                try:
                    resp = e2e_client.get("/ready")
                    if resp.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(1)

        # Data should still be accessible
        resp = e2e_client.get(f"/api/v1/nodes/{node['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == node["id"]

    def test_audit_log_survives_restart(
        self,
        e2e_client: httpx.Client,
        e2e_resources: UniqueResourceFactory,
        docker_service_controller: DockerServiceController,
    ) -> None:
        """Audit logs survive API restart."""
        # Create a node (generates audit log)
        node = e2e_resources.create_ssh_node()

        # Wait for audit delivery
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            resp = e2e_client.get(f"/api/v1/audit/?node_id={node['id']}")
            if resp.status_code == 200 and resp.json()["total"] > 0:
                break
            time.sleep(0.5)

        # Restart API
        docker_service_controller.restart("api")
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            try:
                resp = e2e_client.get("/ready")
                if resp.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)

        # Audit log should still exist
        resp = e2e_client.get(f"/api/v1/audit/?node_id={node['id']}")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1
