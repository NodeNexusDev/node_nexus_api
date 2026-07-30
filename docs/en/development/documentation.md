---
title: Documentation and translation
status: stable
translation_key: development.documentation
source_revision: "2026-07-30"
---

# Documentation and translation

Every current page has an English and Russian page at the same relative path.
English is canonical for identifiers and terminology; Russian is a complete
translation. Keep class names, paths, parameters, environment variables, error
names, and commands unchanged.

Use task-oriented headings, tested commands, relative links, and admonitions for
dangerous actions. Update `source_revision` in both pages. Security and migration
changes must update both translations in the same change. Run the documentation
quality gates before review.

## Writing standard

- Lead with the user's goal, prerequisites, and an observable result.
- Verify paths, fields, defaults, status codes, and limits against code or the
  generated OpenAPI contract.
- Prefer complete, copyable commands with explicit placeholders.
- Explain destructive, irreversible, or security-sensitive effects before the
  corresponding command.
- Keep identifiers, enum values, headers, and environment variables exactly as
  implemented.
- Do not describe planned behavior as if it already exists.

English prose should use direct sentences and active voice. Russian prose should
be idiomatic rather than a word-for-word translation. Review both rendered
pages after changing tables, admonitions, or long code blocks.

New ADRs contain `Context`, `Decision`, `Alternatives considered`, and
`Consequences`. Superseded decisions link to their replacement and use the
`superseded` status.
