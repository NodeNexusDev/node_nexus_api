"""Enforce an explicit and reviewable static-analysis suppression policy."""

from __future__ import annotations

import re
import sys
from pathlib import Path

_SUPPRESSION_RE = re.compile(
    r"#\s*(?P<kind>ty:|type:)\s*ignore(?:\[(?P<code>[^]]+)\])?"
)
_ALLOWED_PRODUCTION = {
    ("app/core/config.py", "type:", "call-arg"),
}


def _scan(root: Path) -> list[str]:
    violations: list[str] = []
    for path in sorted(
        (*root.joinpath("app").rglob("*.py"), *root.joinpath("tests").rglob("*.py"))
    ):
        relative = path.relative_to(root).as_posix()
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            match = _SUPPRESSION_RE.search(line)
            if match is None:
                continue
            code = match.group("code")
            if not code:
                violations.append(
                    f"{relative}:{line_number}: suppression requires a rule code"
                )
                continue
            if (
                relative.startswith("app/")
                and (relative, match.group("kind"), code) not in _ALLOWED_PRODUCTION
            ):
                violations.append(
                    f"{relative}:{line_number}: unapproved production "
                    f"suppression {code}"
                )
    return violations


def main() -> int:
    """Return non-zero when a suppression violates the project policy."""
    violations = _scan(Path(__file__).resolve().parents[1])
    if violations:
        print("Static-analysis suppression policy violations:")
        print("\n".join(f"- {violation}" for violation in violations))
        return 1
    print("Static-analysis suppression policy passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
