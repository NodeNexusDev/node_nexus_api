#!/usr/bin/env python3
"""Generate openapi.snapshot.json for fast E2E coverage guard."""

from __future__ import annotations

import json
import os
from pathlib import Path

_CANONICAL_ENV = {
    "PROMETHEUS_ENABLED": "true",
    "E2E_ENABLED": "true",
    "OTEL_ENABLED": "false",
    "ENVIRONMENT": "test",
    "DATABASE_URL": "postgresql+asyncpg://postgres:postgres@localhost:5432/test",
    "SECRET_KEY": "0123456789abcdef0123456789ABCDEF",
    "ENCRYPTION_SALT": "0123456789abcdef",
}


def main() -> None:
    saved = {k: os.environ.get(k) for k in _CANONICAL_ENV}
    os.environ.update(_CANONICAL_ENV)
    try:
        from app.core.config import get_settings
        from app.main import create_app

        get_settings.cache_clear()
        schema = create_app().openapi()
        out = Path("scripts/openapi.snapshot.json")
        out.write_text(
            json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"Wrote {out} ({len(schema.get('paths', {}))} paths)")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        try:
            from app.core.config import get_settings as gs2

            gs2.cache_clear()
        except Exception:
            pass


if __name__ == "__main__":
    main()
