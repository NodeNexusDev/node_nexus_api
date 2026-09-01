#!/usr/bin/env python3
"""Auto-sync E2E coverage manifest from canonical OpenAPI inventory.

Usage:
  uv run python scripts/update_e2e_coverage.py
  make update-e2e-coverage

Compares live OpenAPI (via create_app().openapi()) with
tests/e2e/test_endpoint_coverage_e2e.py COVERED_ENDPOINTS and
rewrites the file if they differ (preserving EXCLUDED).
"""

from __future__ import annotations

import os
import re
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


def build_inventory() -> set[str]:
    # Ensure env is set before any app import (app/main.py creates `app` at import time)
    saved = {k: os.environ.get(k) for k in _CANONICAL_ENV}
    os.environ.update(_CANONICAL_ENV)
    try:
        from app.core.config import get_settings
        from app.main import create_app

        get_settings.cache_clear()
        schema = create_app().openapi()
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

    inv: set[str] = set()
    for path, methods in schema.get("paths", {}).items():
        assert isinstance(methods, dict)
        for method in methods:
            if method in ("parameters", "servers", "description", "summary"):
                continue
            inv.add(f"{method.upper()} {path}")
    return inv


def main() -> None:
    target = Path("tests/e2e/test_endpoint_coverage_e2e.py")
    text = target.read_text(encoding="utf-8")

    # Extract current EXCLUDED keys to keep them excluded
    excluded_match = re.search(
        r"EXCLUDED_ENDPOINTS:\s*dict\[str, str\]\s*=\s*\{([^}]*)\}", text, re.DOTALL
    )
    excluded_keys: set[str] = set()
    if excluded_match:
        excluded_keys = set(
            re.findall(r'"([^"]+)"\s*:', excluded_match.group(0))
        )
        excluded_keys = {
            k for k in excluded_keys if " " in k and k.split()[0].isupper()
        }

    inventory = build_inventory()
    # COVERED should be inventory - EXCLUDED
    desired = sorted(inventory - excluded_keys)

    # Build new set literal
    new_set = "COVERED_ENDPOINTS: set[str] = {\n"
    for ep in desired:
        new_set += f'    "{ep}",\n'
    new_set += "}"

    # Find COVERED_ENDPOINTS block via line scanning (robust to } inside strings)
    start_marker = "COVERED_ENDPOINTS: set[str] = {"
    start_idx = text.find(start_marker)
    if start_idx == -1:
        raise RuntimeError("Could not find COVERED_ENDPOINTS in target file")
    # Find closing } on its own line after start
    end_idx = text.find("\n}\n", start_idx)
    if end_idx == -1:
        # fallback: find next }\n
        end_idx = text.find("}\n", start_idx)
        if end_idx == -1:
            raise RuntimeError("Could not find closing } for COVERED_ENDPOINTS")
        end_idx += 1
    else:
        end_idx += 2  # include "\n}"
    old_block = text[start_idx : end_idx + 1]
    old_eps = set(re.findall(r'"([^"]+)"', old_block))
    old_eps = {e for e in old_eps if " " in e and e.split()[0].isupper()}

    if set(desired) == old_eps:
        print(f"No change — {len(desired)} endpoints already in sync.")
        return

    new_text = text[:start_idx] + new_set + text[end_idx + 1 :]
    target.write_text(new_text, encoding="utf-8")
    print(
        f"Updated {target} — {len(desired)} endpoints "
        f"(inventory {len(inventory)}, excluded {len(excluded_keys)})."
    )
    added = sorted(set(desired) - old_eps)
    removed = sorted(old_eps - set(desired))
    if added:
        print(f"  Added ({len(added)}):")
        for a in added:
            print(f"    + {a}")
    if removed:
        print(f"  Removed ({len(removed)}):")
        for r in removed:
            print(f"    - {r}")


if __name__ == "__main__":
    main()
