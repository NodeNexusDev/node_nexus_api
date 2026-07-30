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

## Жизненный цикл запроса

```mermaid
sequenceDiagram
    participant C as Client
    participant API as FastAPI router
    participant AUTH as Auth middleware
    participant UC as Application use case
    participant R as Persistence reader
    participant DB as PostgreSQL
    participant SSH as Remote host
    participant W as Persistence writer

    C->>API: POST /nodes/{id}/execute
    API->>AUTH: validate X-API-Key
    AUTH-->>API: API key + scope
    API->>UC: execute(command_dto)

    UC->>R: get_connection(node_id)
    R->>DB: SELECT (короткая сессия)
    DB-->>R: node model
    R-->>UC: NodeConnectionDTO
    Note over R,DB: сессия закрыта

    UC->>SSH: execute_command(conn_dto, command)
    SSH-->>UC: stdout, stderr, exit_code
    Note over UC,SSH: без удержания сессии БД

    UC->>W: save_result(execution_dto)
    W->>DB: INSERT (короткая транзакция)
    DB-->>W: ok
    W-->>UC: done
    Note over W,DB: транзакция зафиксирована

    UC-->>API: CommandResultDTO
    API-->>C: 200 JSON
```

Разрыв между чтением и удалённым вызовом — намеренный: соединение с БД и
транзакция не удерживаются во время SSH или Docker I/O.
