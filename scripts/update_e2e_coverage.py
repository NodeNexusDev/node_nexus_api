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


def build_inventory(use_cache: bool = True) -> set[str]:
    import json
    from pathlib import Path

    snapshot = Path("scripts/openapi.snapshot.json")
    schema: dict[str, object] | None = None
    if use_cache and snapshot.exists():
        try:
            schema = json.loads(snapshot.read_text(encoding="utf-8"))
        except Exception:
            schema = None
    if schema is None:
        # Ensure env before app import (app/main.py creates app at import)
        saved = {k: os.environ.get(k) for k in _CANONICAL_ENV}
        os.environ.update(_CANONICAL_ENV)
        try:
            from app.core.config import get_settings
            from app.main import create_app

            get_settings.cache_clear()
            schema = create_app().openapi()
            if use_cache:
                try:
                    snapshot.write_text(
                        json.dumps(schema, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                except Exception:
                    pass
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
        assert schema is not None

    inv: set[str] = set()
    for path, methods in schema.get("paths", {}).items():  # type: ignore[assignment]
        assert isinstance(methods, dict)
        for method in methods:  # type: ignore[assignment]
            if method in ("parameters", "servers", "description", "summary"):
                continue
            inv.add(f"{method.upper()} {path}")
    return inv


def _parse_existing_manifest(text: str) -> tuple[set[str], set[str], int, int]:
    """Parse COVERED and EXCLUDED via AST (robust to formatting)."""
    import ast

    tree = ast.parse(text)
    covered: set[str] = set()
    excluded: set[str] = set()
    covered_start = covered_end = -1
    for node in tree.body:
        if not isinstance(node, ast.AnnAssign):
            continue
        target = node.target
        if not isinstance(target, ast.Name):
            continue
        if target.id == "COVERED_ENDPOINTS" and isinstance(
            node.value, ast.Set
        ):
            covered = {
                elt.value  # type: ignore[attr-defined]
                for elt in node.value.elts  # type: ignore[attr-defined]
                if isinstance(elt, ast.Constant)
                and isinstance(elt.value, str)
            }
            # lineno is 1-indexed
            covered_start = node.lineno - 1  # type: ignore[attr-defined]
            end = getattr(node, "end_lineno", None)
            covered_end = int(end) if end is not None else -1
        if target.id == "EXCLUDED_ENDPOINTS" and isinstance(
            node.value, ast.Dict
        ):
                excluded = {
                    k.value  # type: ignore[attr-defined]
                    for k in node.value.keys  # type: ignore[attr-defined]
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)
                }
    # Fallback to regex if AST didn't find (e.g., old formatting)
    if not covered or covered_start == -1:
        # regex fallback
        covered_match = re.search(
            r"COVERED_ENDPOINTS:\s*set\[str\]\s*=\s*\{([^}]*)\}", text, re.DOTALL
        )
        if covered_match:
            covered = set(re.findall(r'"([^"]+)"', covered_match.group(0)))
            covered = {c for c in covered if " " in c and c.split()[0].isupper()}
        # approximate lines
        start_marker = "COVERED_ENDPOINTS: set[str] = {"
        start_idx = text.find(start_marker)
        if start_idx != -1:
            lines_before = text[:start_idx].count("\n")
            covered_start = lines_before
            # find closing
            end_idx = text.find("\n}\n", start_idx)
            if end_idx == -1:
                end_idx = text.find("}\n", start_idx)
            if end_idx != -1:
                covered_end = text[: end_idx + 2].count("\n")
    if not excluded:
        excluded_match = re.search(
            r"EXCLUDED_ENDPOINTS:\s*dict\[str, str\]\s*=\s*\{([^}]*)\}", text, re.DOTALL
        )
        if excluded_match:
            excluded = set(re.findall(r'"([^"]+)"\s*:', excluded_match.group(0)))
            excluded = {k for k in excluded if " " in k and k.split()[0].isupper()}
    return covered, excluded, covered_start, covered_end


def main() -> None:
    target = Path("tests/e2e/test_endpoint_coverage_e2e.py")
    text = target.read_text(encoding="utf-8")

    old_eps, excluded_keys, start_line, end_line = _parse_existing_manifest(text)

    inventory = build_inventory()
    # COVERED should be inventory - EXCLUDED
    desired = sorted(inventory - excluded_keys)

    # Build new set literal
    new_set = "COVERED_ENDPOINTS: set[str] = {\n"
    for ep in desired:
        new_set += f'    "{ep}",\n'
    new_set += "}"

    if set(desired) == old_eps:
        print(f"No change — {len(desired)} endpoints already in sync.")
        return

    # Rebuild via lines (AST gives 0-indexed start, 1-indexed end)
    lines = text.splitlines()
    # start_line is 0-indexed, end_line is 1-indexed exclusive
    if start_line != -1 and end_line != -1:
        new_lines = lines[:start_line] + new_set.splitlines() + lines[end_line:]
        new_text = "\n".join(new_lines) + "\n"
    else:
        # fallback to old string method
        start_marker = "COVERED_ENDPOINTS: set[str] = {"
        start_idx = text.find(start_marker)
        if start_idx == -1:
            raise RuntimeError("Could not find COVERED_ENDPOINTS in target file")
        end_idx = text.find("\n}\n", start_idx)
        if end_idx == -1:
            end_idx = text.find("}\n", start_idx)
            if end_idx == -1:
                raise RuntimeError("Could not find closing } for COVERED_ENDPOINTS")
            end_idx += 1
        else:
            end_idx += 2
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
