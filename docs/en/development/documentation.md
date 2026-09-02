---
title: Documentation and translation
status: stable
translation_key: development.documentation
source_revision: "2026-09-02"
---

# Documentation and translation

Every current page has an English and Russian page at the same relative path.
English is canonical for identifiers and terminology; Russian is a complete,
idiomatic translation — not a word-for-word copy. Keep class names, paths, parameters, environment variables, error
names, and commands unchanged.

Use task-oriented headings, tested commands, relative links, and admonitions for
dangerous actions. Security and migration
changes must update both translations in the same change. Run the documentation
quality gates before review.

## `source_revision` bump requirement

Both `docs/en/...` and `docs/ru/...` pages share the same `translation_key`. When you change the English page, you **must** bump `source_revision` in **both** files (e.g., to `2026-09-02`) and update the Russian translation in the same commit. Do not leave `source_revision` stale — it signals that the translation is out of sync.

## Writing standard

- Lead with the user's goal, prerequisites, and an observable result.
- Verify paths, fields, defaults, status codes, and limits against code or the
  generated OpenAPI contract (`openapi.json` / `scripts/openapi.snapshot.json`).
- Prefer complete, copyable commands with explicit placeholders.
- Explain destructive, irreversible, or security-sensitive effects before the
  corresponding command.
- Keep identifiers, enum values, headers, and environment variables exactly as
  implemented.
- Do not describe planned behavior as if it already exists.

English is canonical: use direct sentences and active voice. Russian should be idiomatic rather than a word-for-word translation. Review both rendered
pages after changing tables, admonitions, or long code blocks.

## Building

Validate documentation before review with strict builds:

```bash
uv run mkdocs build --strict -f mkdocs.en.yml
uv run mkdocs build --strict -f mkdocs.ru.yml
uv run python scripts/docs/check_docs.py
```

`--strict` fails on warnings (broken links, missing pages). Fix all warnings before merging. Coverage guard `tests/e2e/test_endpoint_coverage_e2e.py` (with `branch=true`, `fail_under=95`) and `scripts/openapi.snapshot.json` (gitignored cache) are separate from docs builds but should stay in sync when endpoints change — run `make generate-openapi` and `make update-e2e-coverage`.

New ADRs contain `Context`, `Decision`, `Alternatives considered`, and
`Consequences`. Superseded decisions link to their replacement and use the
`superseded` status.
