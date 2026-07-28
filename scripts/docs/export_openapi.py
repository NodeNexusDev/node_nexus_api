"""Export the FastAPI OpenAPI contract without starting the server."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "openapi-export-only")
os.environ.setdefault("MASTER_API_KEY", "openapi-export-only")
os.environ.setdefault("PROMETHEUS_ENABLED", "false")
os.environ.setdefault("OTEL_ENABLED", "false")

from app.main import create_app  # noqa: E402


def main() -> None:
    """Write a deterministic, sorted OpenAPI JSON document."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("build/openapi.json"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    schema = create_app().openapi()
    args.output.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
