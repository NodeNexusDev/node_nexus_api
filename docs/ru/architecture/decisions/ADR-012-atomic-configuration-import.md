---
title: "ADR-012: Atomic configuration import"
status: accepted
translation_key: architecture.decisions.012
source_revision: "2026-07-30"
---

# ADR-012: Atomic configuration import

Canonical record: English version.

## Решение

Считать config import одной multi-aggregate atomic operation. Application
проверяет format compatibility и вызывает отдельный `ConfigurationImporter`
port с полным immutable transfer DTO.

`SqlAlchemyConfigGateway` открывает одну transaction для nodes, commands и
scripts, применяет duplicate-name policy и возвращает immutable result. Port не
раскрывает repositories или `AsyncSession`. Config export использует отдельный
query port и bounded pagination.

Не вводить универсальный application Unit of Work ради этого требования.

## Последствия

Поздняя persistence failure откатывает ранние writes того же payload.
Transaction может быть больше обычного CRUD, но её ownership и scope явно
ограничены config transfer.
