"""Additional E2E quality tests: negative paths, observability, request id."""

import uuid

import httpx2 as httpx
import pytest

from tests.e2e.helpers.resources import UniqueResourceFactory

pytestmark = [pytest.mark.docker, pytest.mark.e2e_smoke]


class TestRequestIdAndErrors:
    def test_request_id_propagated(self, e2e_client: httpx.Client) -> None:
        """Client-provided X-Request-ID is echoed on the response."""
        resp = e2e_client.get("/api/v1/nodes/", headers={"X-Request-ID": "client-123"})
        assert resp.status_code == 200
        assert resp.headers["x-request-id"] == "client-123"

    def test_request_id_in_404_body(self, e2e_client: httpx.Client) -> None:
        """404 responses include the request id in the body and headers."""
        resp = e2e_client.get(f"/api/v1/nodes/{uuid.uuid4()}")
        assert resp.status_code == 404
        assert "x-request-id" in resp.headers
        body = resp.json()
        assert "request_id" in body
        assert body["request_id"] == resp.headers["x-request-id"]

    def test_request_id_in_422_body(self, e2e_client: httpx.Client) -> None:
        """Validation errors include the request id in the body."""
        resp = e2e_client.post("/api/v1/nodes/", json={"name": "x"})
        assert resp.status_code == 422
        assert "x-request-id" in resp.headers
        body = resp.json()
        assert "request_id" in body
        assert body["request_id"] == resp.headers["x-request-id"]
        assert isinstance(body["detail"], list)

    def test_request_id_in_401_body(self, e2e_client_no_auth: httpx.Client) -> None:
        """Missing API key errors include the request id."""
        resp = e2e_client_no_auth.get("/api/v1/nodes/")
        assert resp.status_code == 401
        assert "x-request-id" in resp.headers
        body = resp.json()
        assert "request_id" in body
        assert body["request_id"] == resp.headers["x-request-id"]


class TestObservability:
    def test_metrics_has_request_labels(self, e2e_client: httpx.Client) -> None:
        """Prometheus metrics include method/handler labels for API calls."""
        e2e_client.get("/api/v1/nodes/")
        resp = e2e_client.get("/metrics")
        assert resp.status_code == 200
        text = resp.text
        assert 'method="GET"' in text
        assert 'handler="/api/v1/nodes/"' in text

    def test_ready_checks_have_details(self, e2e_client: httpx.Client) -> None:
        """Readiness probe returns nested status and detail for each check."""
        resp = e2e_client.get("/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["checks"]["database"]["status"] == "ok"
        assert "reachable" in data["checks"]["database"]["detail"].lower()
        assert data["checks"]["scheduler"]["status"] == "ok"
        assert data["checks"]["scheduler"]["detail"]


class TestConfigErrors:
    def test_config_import_invalid_json(self, e2e_client: httpx.Client) -> None:
        """Malformed JSON body during import is rejected with 422."""
        resp = e2e_client.post(
            "/api/v1/config/import",
            content=b"not-json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422


@pytest.mark.e2e_slow
class TestDockerNegativePaths:
    """Negative Docker scenarios against a real DinD daemon."""

    def test_docker_image_pull_not_found(
        self,
        e2e_client: httpx.Client,
        e2e_resources: UniqueResourceFactory,
    ) -> None:
        """Pulling a non-existent image returns a DockerError, not 200."""
        node = e2e_resources.create_docker_node()
        resp = e2e_client.post(
            f"/api/v1/nodes/{node['id']}/docker/images/pull",
            json={
                "image": "alpine:definitely-not-exists-abc123",
                "timeout": 60,
            },
        )
        assert resp.status_code == 502
        assert resp.json()["code"] == "DockerError"

    def test_docker_image_inspect_not_found(
        self,
        e2e_client: httpx.Client,
        e2e_resources: UniqueResourceFactory,
    ) -> None:
        """Inspecting a non-existent image returns 404."""
        node = e2e_resources.create_docker_node()
        resp = e2e_client.get(
            f"/api/v1/nodes/{node['id']}/docker/images/"
            "alpine:definitely-not-exists-abc123"
        )
        assert resp.status_code == 404

    def test_docker_image_remove_not_found(
        self,
        e2e_client: httpx.Client,
        e2e_resources: UniqueResourceFactory,
    ) -> None:
        """Removing a non-existent image returns 404."""
        node = e2e_resources.create_docker_node()
        resp = e2e_client.delete(
            f"/api/v1/nodes/{node['id']}/docker/images/"
            "alpine:definitely-not-exists-abc123"
        )
        assert resp.status_code == 404

    def test_docker_image_build_invalid_dockerfile(
        self,
        e2e_client: httpx.Client,
        e2e_resources: UniqueResourceFactory,
    ) -> None:
        """Building from an invalid Dockerfile returns a DockerError."""
        node = e2e_resources.create_docker_node()
        resp = e2e_client.post(
            f"/api/v1/nodes/{node['id']}/docker/images/build",
            json={"dockerfile": "INVALID DOCKERFILE", "tag": "local/fail:1"},
        )
        assert resp.status_code == 502
        assert resp.json()["code"] == "DockerError"

    def test_docker_create_container_invalid_image(
        self,
        e2e_client: httpx.Client,
        e2e_resources: UniqueResourceFactory,
    ) -> None:
        """Container creation with a shell-injection image name is rejected."""
        node = e2e_resources.create_docker_node()
        resp = e2e_client.post(
            f"/api/v1/nodes/{node['id']}/docker/containers",
            json={"image": "nginx; rm -rf /", "name": "bad-ctr"},
        )
        assert resp.status_code == 422

    def test_docker_create_container_invalid_name(
        self,
        e2e_client: httpx.Client,
        e2e_resources: UniqueResourceFactory,
    ) -> None:
        """Container creation with an invalid name is rejected."""
        node = e2e_resources.create_docker_node()
        resp = e2e_client.post(
            f"/api/v1/nodes/{node['id']}/docker/containers",
            json={"image": "alpine:latest", "name": "bad name"},
        )
        assert resp.status_code == 422


@pytest.mark.e2e_slow
class TestDockerBulk:
    """Edge cases for bulk Docker operations."""

    def test_docker_bulk_start_empty_request(self, e2e_client: httpx.Client) -> None:
        """Bulk start with no nodes/tags is rejected with 422."""
        resp = e2e_client.post(
            "/api/v1/docker/bulk/start",
            json={"node_ids": [], "container_id": "ctr"},
        )
        assert resp.status_code == 422
        assert "node_ids or node_tags" in resp.text

    def test_docker_bulk_exec_requires_command(self, e2e_client: httpx.Client) -> None:
        """Bulk exec without a command is rejected."""
        resp = e2e_client.post(
            "/api/v1/docker/bulk/exec",
            json={"node_ids": [], "container_id": "ctr"},
        )
        assert resp.status_code == 422

    def test_docker_bulk_start_by_tags(
        self,
        e2e_client: httpx.Client,
        e2e_resources: UniqueResourceFactory,
    ) -> None:
        """Bulk start resolves only nodes with matching tags."""
        n1 = e2e_resources.create_docker_node(name="bulk-tag-1", tags=["bulk-zone"])
        n2 = e2e_resources.create_docker_node(name="bulk-tag-2", tags=["other-zone"])
        try:
            for node in (n1, n2):
                pull = e2e_client.post(
                    f"/api/v1/nodes/{node['id']}/docker/images/pull",
                    json={"image": "alpine:latest", "timeout": 120},
                )
                assert pull.status_code == 200, pull.text

            container_name = f"bulk-ctr-{n1['id'][:8]}"
            create = e2e_client.post(
                f"/api/v1/nodes/{n1['id']}/docker/containers",
                json={
                    "image": "alpine:latest",
                    "name": container_name,
                    "command": "sleep 60",
                },
            )
            assert create.status_code == 201, create.text

            e2e_client.post(
                f"/api/v1/nodes/{n1['id']}/docker/containers/{container_name}/stop"
            )

            resp = e2e_client.post(
                "/api/v1/docker/bulk/start",
                json={
                    "node_ids": [],
                    "container_id": container_name,
                    "node_tags": ["bulk-zone"],
                },
            )
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert data["total"] == 1
            assert data["succeeded"] == 1
            assert data["results"][0]["node_id"] == n1["id"]

            e2e_client.delete(
                f"/api/v1/nodes/{n1['id']}/docker/containers/{container_name}?force=true"
            )
        finally:
            pass
