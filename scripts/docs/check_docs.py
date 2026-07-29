"""Validate bilingual documentation structure, metadata, and local links."""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
LOCALES = ("en", "ru")
ALLOWED_STATUSES = {"accepted", "draft", "stable", "deprecated", "superseded"}
FRONT_MATTER = re.compile(r"\A---\n(?P<body>.*?)\n---\n", re.DOTALL)
LINK = re.compile(r"!?\[[^\]]*]\(([^)]+)\)")
REQUIRED_KEYS = ("title:", "status:", "translation_key:", "source_revision:")


def markdown_files(locale: str) -> set[Path]:
    """Return relative Markdown paths for one locale."""
    root = DOCS / locale
    return {path.relative_to(root) for path in root.rglob("*.md")}


def content_files(locale: str) -> set[Path]:
    """Return navigable Markdown and HTML paths for one locale."""
    root = DOCS / locale
    return {
        path.relative_to(root)
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix in {".md", ".html"}
        and "assets" not in path.relative_to(root).parts
    }


def metadata(path: Path) -> dict[str, str]:
    """Return simple scalar front-matter values."""
    match = FRONT_MATTER.match(path.read_text(encoding="utf-8"))
    if not match:
        return {}
    return {
        key.strip(): value.strip().strip("\"'")
        for line in match.group("body").splitlines()
        if ":" in line
        for key, value in [line.split(":", maxsplit=1)]
    }


def nav_targets(items: Iterable[object]) -> set[Path]:
    """Flatten MkDocs navigation values into relative paths."""
    targets: set[Path] = set()
    for item in items:
        if isinstance(item, str):
            targets.add(Path(item))
        elif isinstance(item, dict):
            for value in item.values():
                nested = value if isinstance(value, list) else [value]
                targets.update(nav_targets(nested))
    return targets


def check_parity(errors: list[str]) -> None:
    """Require identical English and Russian content paths."""
    english = content_files("en")
    russian = content_files("ru")
    for path in sorted(english - russian):
        errors.append(f"missing Russian page: {path}")
    for path in sorted(russian - english):
        errors.append(f"missing English page: {path}")
    for path in sorted(markdown_files("en") & markdown_files("ru")):
        en_metadata = metadata(DOCS / "en" / path)
        ru_metadata = metadata(DOCS / "ru" / path)
        for key in ("translation_key", "source_revision"):
            if en_metadata.get(key) != ru_metadata.get(key):
                errors.append(f"{path}: locale metadata differs for {key}")


def check_metadata(locale: str, errors: list[str]) -> None:
    """Validate status values and unique translation identifiers."""
    seen_keys: dict[str, Path] = {}
    for path in sorted((DOCS / locale).rglob("*.md")):
        values = metadata(path)
        status = values.get("status")
        if status not in ALLOWED_STATUSES:
            errors.append(f"{path.relative_to(ROOT)}: unsupported status {status!r}")
        key = values.get("translation_key")
        if key in seen_keys:
            errors.append(
                f"{path.relative_to(ROOT)}: duplicate translation_key {key!r}; "
                f"first used by {seen_keys[key].relative_to(ROOT)}"
            )
        elif key:
            seen_keys[key] = path


def check_navigation(locale: str, errors: list[str]) -> None:
    """Require every content page to appear exactly once in locale navigation."""
    config_path = ROOT / f"mkdocs.{locale}.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    targets = nav_targets(config.get("nav", []))
    pages = content_files(locale)
    for path in sorted(pages - targets):
        errors.append(f"{path}: missing from mkdocs.{locale}.yml navigation")
    for path in sorted(targets - pages):
        errors.append(f"mkdocs.{locale}.yml: missing navigation target {path}")


def check_page(path: Path, errors: list[str]) -> None:
    """Validate front matter and local Markdown links."""
    text = path.read_text(encoding="utf-8")
    if text.count("\n# ") != 1:
        errors.append(f"{path.relative_to(ROOT)}: expected exactly one H1")
    if any(line.endswith((" ", "\t")) for line in text.splitlines()):
        errors.append(f"{path.relative_to(ROOT)}: trailing whitespace")
    if text.count("```") % 2:
        errors.append(f"{path.relative_to(ROOT)}: unbalanced code fence")
    match = FRONT_MATTER.match(text)
    if not match:
        errors.append(f"{path.relative_to(ROOT)}: missing YAML front matter")
        return
    metadata = match.group("body")
    for key in REQUIRED_KEYS:
        if key not in metadata:
            errors.append(f"{path.relative_to(ROOT)}: missing {key[:-1]}")

    for target in LINK.findall(text):
        target = target.split("#", maxsplit=1)[0]
        if not target or "://" in target or target.startswith(("mailto:", "/")):
            continue
        resolved = (path.parent / target).resolve()
        if target.endswith("/"):
            resolved /= "index.md"
        if not resolved.exists():
            errors.append(f"{path.relative_to(ROOT)}: broken link {target!r}")


def main() -> int:
    """Run all documentation checks."""
    errors: list[str] = []
    check_parity(errors)
    for locale in LOCALES:
        check_metadata(locale, errors)
        check_navigation(locale, errors)
        for path in sorted((DOCS / locale).rglob("*.md")):
            check_page(path, errors)
    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors), file=sys.stderr)
        return 1
    pages = len(markdown_files("en"))
    print(f"Documentation checks passed: {pages} paired pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
