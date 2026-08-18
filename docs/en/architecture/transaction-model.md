---
title: Transaction model
status: stable
translation_key: architecture.transaction-model
source_revision: "2026-08-18"
---

# Transaction model

Request CRUD uses one request-scoped SQLAlchemy session. The provider owns
commit and rollback; internal DAOs flush but do not commit independently.
APP-scoped gateways store an `async_sessionmaker`, never a live session.

Remote operations follow `short read -> immutable DTO -> close session ->
side effect -> short write`. Concurrent workers never receive a session, DAO,
or ORM model. Bulk operations report partial outcomes and do not promise
distributed rollback.

Multi-aggregate operations use dedicated boundaries only when atomicity is a
business requirement. Configuration import owns one transaction for the whole
payload; there is no universal application Unit of Work.

## Commit before response

For HTTP requests, `CommitOnResponseMiddleware` commits the request-scoped
transaction immediately before the application emits `http.response.start`.
This eliminates read-after-write races: a client cannot receive a successful
response and then observe stale state on the next request.

The middleware skips `/health`, `/ready`, and `/metrics`, and only commits when
the session has pending changes (`new`, `dirty`, or `deleted`). If commit fails,
the middleware rolls back and raises, so the client receives a 500 instead of a
false success.

## Request lifecycle

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
    R->>DB: SELECT (short session)
    DB-->>R: node model
    R-->>UC: NodeConnectionDTO
    Note over R,DB: session closed

    UC->>SSH: execute_command(conn_dto, command)
    SSH-->>UC: stdout, stderr, exit_code
    Note over UC,SSH: no DB session held

    UC->>W: save_result(execution_dto)
    W->>DB: INSERT (short transaction)
    DB-->>W: ok
    W-->>UC: done
    Note over W,DB: transaction committed

    UC-->>API: CommandResultDTO
    API-->>C: 200 JSON
```

The gap between the read and the remote call is intentional: no database
connection or transaction is held during SSH or Docker I/O.
