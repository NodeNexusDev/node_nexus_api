"""Validate an exported OpenAPI contract and project-specific invariants."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from openapi_spec_validator import validate


def main() -> None:
    """Validate the schema and stable operation identifiers."""
    parser = argparse.ArgumentParser()
    parser.add_argument("schema", type=Path)
    args = parser.parse_args()
    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    validate(schema)

    operation_ids: list[str] = []
    for path_item in schema["paths"].values():
        for method, operation in path_item.items():
            if method in {"get", "post", "put", "patch", "delete"}:
                operation_ids.append(operation["operationId"])
    if len(operation_ids) != len(set(operation_ids)):
        raise ValueError("OpenAPI operationId values must be unique")
    if not operation_ids:
        raise ValueError("OpenAPI contains no HTTP operations")
    print(f"OpenAPI validation passed: {len(operation_ids)} operations")


if __name__ == "__main__":
    main()
