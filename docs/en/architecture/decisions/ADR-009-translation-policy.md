---
title: "ADR-009: Translation parity policy"
status: accepted
translation_key: architecture.decisions.009
source_revision: "2026-07-29"
---

# ADR-009: Translation parity policy

## Decision

English defines canonical technical terminology and page identifiers. Russian
is a complete localization. Every current page has a pair and translation
metadata.

## Consequences

CI compares paths and metadata. Security and migration documentation cannot use
a delayed translation; other follow-ups require an explicit release-blocking
policy exception.
