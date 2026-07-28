---
title: Модель транзакций
status: stable
translation_key: architecture.transaction-model
source_revision: "2026-07-29"
---

# Модель транзакций

Один request scope владеет одной async SQLAlchemy session. Граница service/use
case владеет commit и rollback; repositories выполняют flush, если нужен
identifier, но не делают самостоятельный commit.

Короткий CRUD выполняется в одной transaction. Для SSH и Docker сначала
читаются данные, завершается DB work, выполняется side effect, затем результат
при необходимости сохраняется новой короткой transaction. Bulk operations
возвращают частичные результаты без distributed rollback.
