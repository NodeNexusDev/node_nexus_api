"""Docker CLI output parsers."""

import json
from typing import Any


def parse_json_lines(stdout: str) -> list[dict[str, Any]]:
    """Parse valid JSON objects from newline-delimited Docker output."""
    results: list[dict[str, Any]] = []
    for raw_line in stdout.strip().splitlines():
        line = raw_line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            results.append(value)
    return results


def parse_json_array(stdout: str) -> list[dict[str, Any]]:
    """Parse Docker inspect output into a list of JSON objects."""
    try:
        value = json.loads(stdout.strip())
    except json.JSONDecodeError:
        return []
    items = value if isinstance(value, list) else [value]
    return [item for item in items if isinstance(item, dict)]
