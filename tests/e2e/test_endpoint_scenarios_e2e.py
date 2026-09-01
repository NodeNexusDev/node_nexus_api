"""Missing endpoint scenarios from the executable E2E inventory."""

from uuid import uuid4

import httpx2 as httpx
import pytest

from tests.e2e.helpers.assertions import assert_http_error
from tests.e2e.helpers.resources import UniqueResourceFactory

pytestmark = [pytest.mark.docker, pytest.mark.e2e_smoke]


@pytest.mark.parametrize(
    "payload",
    [
        {"name": ""},
        {"scope": "administrator"},
    ],
)
def test_api_key_patch_validation(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
    payload: dict[str, str],
) -> None:
    """PATCH rejects invalid API-key changes."""
    api_key = e2e_resources.create_api_key()
    response = e2e_client.patch(
        f"/api/v2/api-keys/{api_key['id']}",
        json=payload,
    )
    assert_http_error(response, 422)


def test_api_key_patch_not_found(e2e_client: httpx.Client) -> None:
    """PATCH returns 404 for an unknown API key."""
    response = e2e_client.patch(
        f"/api/v2/api-keys/{uuid4()}",
        json={"name": "missing-key"},
    )
    assert_http_error(response, 404)


def test_schedule_replace_updates_existing_job(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Scheduling the same script again replaces its persistent projection."""
    script = e2e_resources.create_script()
    node = e2e_resources.create_ssh_node()

    first = e2e_resources.create_schedule(
        script["id"],
        [node["id"]],
        cron="0 9 * * *",
    )
    assert first["cron"] == "0 9 * * *"

    second = e2e_resources.create_schedule(
        script["id"],
        [node["id"]],
        cron="30 10 * * *",
    )
    assert second["cron"] == "30 10 * * *"

    current = e2e_client.get(f"/api/v2/scripts/{script['id']}/schedule")
    assert current.status_code == 200, current.text
    assert current.json()["cron"] == "30 10 * * *"


def test_audit_filters_without_matches(e2e_client: httpx.Client) -> None:
    """Unknown node and action filters return an empty page."""
    response = e2e_client.get(
        "/api/v2/audit/",
        params={"node_id": str(uuid4()), "action": f"missing.{uuid4().hex}"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["items"] == []
    assert response.json()["total"] == 0
