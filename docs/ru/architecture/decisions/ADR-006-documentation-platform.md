---
title: "ADR-006: Платформа документации"
status: accepted
translation_key: architecture.decisions.006
source_revision: "2026-07-30"
---

# ADR-006: Платформа документации

Canonical record: English version.

## Решение

Использовать MkDocs Material, общую inherited configuration и отдельный strict
build для каждого языка.

## Последствия

Markdown хранится в repository, build воспроизводим, publication создаёт static
site. MkDocs dependencies зафиксированы.
