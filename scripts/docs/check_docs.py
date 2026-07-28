"""Validate bilingual documentation structure, metadata, and local links."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
LOCALES = ("en", "ru")
FRONT_MATTER = re.compile(r"\A---\n(?P<body>.*?)\n---\n", re.DOTALL)
LINK = re.compile(r"!?\[[^\]]*]\(([^)]+)\)")
REQUIRED_KEYS = ("title:", "status:", "translation_key:", "source_revision:")


def markdown_files(locale: str) -> set[Path]:
    """Return relative Markdown paths for one locale."""
    root = DOCS / locale
    return {path.relative_to(root) for path in root.rglob("*.md")}


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


def check_parity(errors: list[str]) -> None:
    """Require identical English and Russian page paths."""
    english = markdown_files("en")
    russian = markdown_files("ru")
    for path in sorted(english - russian):
        errors.append(f"missing Russian page: {path}")
    for path in sorted(russian - english):
        errors.append(f"missing English page: {path}")
    for path in sorted(english & russian):
        en_metadata = metadata(DOCS / "en" / path)
        ru_metadata = metadata(DOCS / "ru" / path)
        for key in ("translation_key", "source_revision"):
            if en_metadata.get(key) != ru_metadata.get(key):
                errors.append(f"{path}: locale metadata differs for {key}")


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
