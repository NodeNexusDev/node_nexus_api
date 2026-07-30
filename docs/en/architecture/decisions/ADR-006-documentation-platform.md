---
title: "ADR-006: Documentation platform"
status: accepted
translation_key: architecture.decisions.006
source_revision: "2026-07-30"
---

# ADR-006: Documentation platform

## Decision

Use MkDocs with Material, a shared inherited configuration, and one strict build
per language.

## Alternatives considered

### Sphinx (reStructuredText)

- **Rejected because:** rST syntax is more verbose than Markdown, the Python
  doc ecosystem bias toward Sphinx does not apply to an API project where docs
  are written by developers, not generated from docstrings. MkDocs Material
  provides a more modern, searchable UX out of the box.

### Docusaurus / Vitepress

- **Rejected because:** both are Node-based. Adding a Node dependency chain
  for documentation would complicate CI and local setup without proportional
  benefit. MkDocs Material matches or exceeds both on search, navigation, and
  theming for API documentation use cases.

## Consequences

Documentation remains Markdown in the repository, builds are reproducible, and
publication produces a static site. MkDocs dependencies are pinned.
