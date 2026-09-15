"""Slug conformance between documented error pages and runtime mapping.

Every ``code`` in ``DOMAIN_ERROR_STATUS`` (plus the ``InternalError`` and
``RequestValidationError`` extras) must be documented in both
``docs/en/errors.md`` and ``docs/ru/errors.md`` with a ``## <slug>``
heading and a ``Type: <uri>`` line that exactly equal the runtime output
of ``_error_slug`` / ``problem_content``. Guards against regressions like
``APIKeyExpiredError`` documented as ``a-p-i-key-expired-error`` instead
of the runtime ``api-key-expired-error``.
"""

import re
from http import HTTPStatus
from pathlib import Path

from app.api.error_mapping import (
    DOMAIN_ERROR_STATUS,
    ERROR_TYPE_BASE,
    _error_slug,
    problem_content,
)

ROOT = Path(__file__).resolve().parents[2]
DOCS = {
    "en": ROOT / "docs" / "en" / "errors.md",
    "ru": ROOT / "docs" / "ru" / "errors.md",
}

SECTION = re.compile(r"^## (\S+)\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)
TYPE_LINE = re.compile(r"^Type: `([^`]+)`", re.MULTILINE)
CODE_REF = re.compile(r"\(`code: ([^`,)]+)`")
FALLBACK_SUFFIX = re.compile(r"^\| `([a-z0-9-]+)` \| `(\d+)` \|", re.MULTILINE)

EXTRA_CODES: dict[str, int] = {
    "InternalError": 500,
    "RequestValidationError": 422,
}


def _expected_codes() -> dict[str, int]:
    codes = {
        exc_cls.__name__: status for exc_cls, status in DOMAIN_ERROR_STATUS.items()
    }
    codes.update(EXTRA_CODES)
    return codes


def _documented_sections(locale: str) -> dict[str, dict[str, str]]:
    """Map error code -> {slug, type_uri} for one locale's error sections."""
    text = DOCS[locale].read_text(encoding="utf-8")
    sections: dict[str, dict[str, str]] = {}
    for slug, body in SECTION.findall(text):
        if slug.startswith("HTTP"):
            continue
        code_match = CODE_REF.search(body)
        type_match = TYPE_LINE.search(body)
        assert code_match is not None, f"{locale}: section '{slug}' has no code ref"
        assert type_match is not None, f"{locale}: section '{slug}' has no Type line"
        sections[code_match.group(1)] = {"slug": slug, "type_uri": type_match.group(1)}
    return sections


def test_all_mapped_error_codes_are_documented_in_both_locales() -> None:
    expected = _expected_codes()
    for locale in ("en", "ru"):
        documented = _documented_sections(locale)
        assert set(documented) == set(expected), (
            f"{locale}: documented codes differ from runtime mapping: "
            f"missing={sorted(set(expected) - set(documented))} "
            f"extra={sorted(set(documented) - set(expected))}"
        )


def test_documented_slugs_equal_runtime_slugs() -> None:
    for locale in ("en", "ru"):
        for code, section in _documented_sections(locale).items():
            assert section["slug"] == _error_slug(code), (
                f"{locale}: section for {code} documents slug "
                f"'{section['slug']}' but runtime gives '{_error_slug(code)}'"
            )


def test_documented_type_uris_equal_runtime_problem_type() -> None:
    expected = _expected_codes()
    for locale in ("en", "ru"):
        for code, section in _documented_sections(locale).items():
            status = expected[code]
            runtime_type = problem_content(
                status_code=status,
                code=code,
                detail="conformance probe",
                request_id=None,
                path="/probe",
            )["type"]
            assert section["type_uri"] == runtime_type
            assert section["type_uri"] == f"{ERROR_TYPE_BASE}/{_error_slug(code)}"


def test_acronym_codes_use_collapsed_slugs() -> None:
    for locale in ("en", "ru"):
        text = DOCS[locale].read_text(encoding="utf-8")
        assert "a-p-i-key" not in text
        documented = _documented_sections(locale)
        assert documented["APIKeyExpiredError"]["slug"] == "api-key-expired-error"
        assert documented["APIKeyNotFoundError"]["slug"] == "api-key-not-found-error"
        assert documented["APIKeyRevokedError"]["slug"] == "api-key-revoked-error"


def test_http_fallback_suffixes_equal_runtime_slugs() -> None:
    for locale in ("en", "ru"):
        text = DOCS[locale].read_text(encoding="utf-8")
        suffixes = dict(FALLBACK_SUFFIX.findall(text))
        assert suffixes, f"{locale}: no HTTP fallback rows found"
        for suffix, status in suffixes.items():
            assert suffix == _error_slug(f"HTTP_{status}"), (
                f"{locale}: fallback suffix '{suffix}' does not match "
                f"runtime slug for HTTP_{status}"
            )
        example_status = 404
        example_uri = f"{ERROR_TYPE_BASE}/{_error_slug(f'HTTP_{example_status}')}"
        assert example_uri in text
        assert HTTPStatus(example_status).phrase in text


def test_error_pages_match_generator_output() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "generate_errors", ROOT / "scripts" / "docs" / "generate_errors.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for locale in ("en", "ru"):
        assert DOCS[locale].read_text(encoding="utf-8") == module.render(locale)
