---
title: Модель транзакций
status: stable
translation_key: architecture.transaction-model
source_revision: "2026-07-30"
---

# Модель транзакций

Request CRUD использует одну request-scoped SQLAlchemy session. Provider владеет
commit и rollback; внутренние DAO выполняют flush без самостоятельного commit.
APP-scoped gateway хранит `async_sessionmaker`, но не живую session.

Remote flow: `short read -> immutable DTO -> close session -> side effect ->
short write`. Concurrent workers не получают session, DAO или ORM model. Bulk
operations возвращают частичные результаты без distributed rollback.

Multi-aggregate operation получает отдельную boundary только при бизнес-требовании
atomicity. Config import владеет одной transaction для всего payload;
универсального application Unit of Work нет.
