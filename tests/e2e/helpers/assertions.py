"""HTTP assertion helpers for E2E tests."""

from typing import Any


def assert_http_error(
    response: Any,
    expected_status: int,
    detail_substring: str | None = None,
) -> None:
    """Assert that an HTTP response is an error with the expected status.

    Optionally checks that the error detail contains a specific substring.
    """
    assert response.status_code == expected_status, (
        f"Expected {expected_status}, got {response.status_code}: {response.text}"
    )
    if detail_substring is not None:
        try:
            body = response.json()
        except ValueError:
            body_text = response.text
            assert detail_substring in body_text, (
                f"Detail '{detail_substring}' not found in response body: {body_text}"
            )
            return

        # FastAPI validation errors use "detail" list; domain errors use "detail" str
        detail = body.get("detail", "")
        if isinstance(detail, list):
            detail_text = " ".join(
                d.get("msg", "") if isinstance(d, dict) else str(d) for d in detail
            )
        else:
            detail_text = str(detail)
        assert detail_substring in detail_text, (
            f"Detail '{detail_substring}' not found in error detail: {detail_text}"
        )


def assert_json_schema(
    response: Any,
    required_fields: list[str],
    forbidden_fields: list[str] | None = None,
    is_list: bool = False,
) -> None:
    """Assert that a JSON response contains required fields and no forbidden ones.

    Args:
        response: httpx Response object.
        required_fields: Fields that MUST be present in the JSON body.
        forbidden_fields: Fields that MUST NOT be present (e.g. secrets).
        is_list: If True, validate each item in a JSON array.
    """
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text}"
    )
    body = response.json()

    items: list[dict] = body if is_list else [body]
    forbidden = forbidden_fields or []

    for idx, item in enumerate(items):
        prefix = f"item[{idx}]" if is_list else "response"
        for field in required_fields:
            assert field in item, f"{prefix}: missing required field '{field}'"
        for field in forbidden:
            assert field not in item, f"{prefix}: forbidden field '{field}' present"
