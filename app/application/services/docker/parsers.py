"""Docker CLI output parsers."""

import json


def parse_json_lines(stdout: str) -> list[dict[str, object]]:
    """Parse valid JSON objects from newline-delimited Docker output."""
    results: list[dict[str, object]] = []
    for raw_line in stdout.strip().splitlines():
        line = raw_line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            results.append({str(key): item for key, item in value.items()})
    return results


def parse_json_array(stdout: str) -> list[dict[str, object]]:
    """Parse Docker inspect output into a list of JSON objects."""
    try:
        value = json.loads(stdout.strip())
    except json.JSONDecodeError:
        return []
    items = value if isinstance(value, list) else [value]
    return [item for item in items if isinstance(item, dict)]


def json_string(item: dict[str, object], key: str) -> str:
    """Read a required string field from Docker JSON output."""
    value = item.get(key)
    return value if isinstance(value, str) else ""


def json_optional_string(item: dict[str, object], key: str) -> str | None:
    """Read an optional string field from Docker JSON output."""
    value = item.get(key)
    return value if isinstance(value, str) else None
