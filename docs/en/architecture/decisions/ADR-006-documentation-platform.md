---
title: "ADR-006: Documentation platform"
status: accepted
translation_key: architecture.decisions.006
source_revision: "2026-07-29"
---

# ADR-006: Documentation platform

## Decision

Use MkDocs with Material, a shared inherited configuration, and one strict build
per language.

## Consequences

Documentation remains Markdown in the repository, builds are reproducible, and
publication produces a static site. MkDocs dependencies are pinned.
