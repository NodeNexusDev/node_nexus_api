---
title: Documentation and translation
status: stable
translation_key: development.documentation
source_revision: "2026-07-29"
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
