---
title: Обзор архитектуры
status: stable
translation_key: architecture.overview
source_revision: "2026-08-26"
---

# Обзор архитектуры

Node Nexus использует Ports & Adapters. HTTP, WebSocket и scheduler adapters
вызывают inbound application use cases. Use cases зависят от immutable DTO и
focused ports. SQLAlchemy, SSH, Docker, security и scheduler implementations
подключаются только в Dishka composition root.

Pydantic models являются transport contracts, SQLAlchemy models — деталями
persistence; оба типа не пересекают application boundary. APP gateways хранят
sessionmaker, request-transaction DAO — session. SSH/Docker side effects
выполняются после закрытия read session.

PostgreSQL является system of record. In-process scheduler использует
advisory-lock ownership: non-owner replicas обслуживают HTTP, но не запускают
jobs.

## Runtime flow

```mermaid
flowchart LR
    HTTP[HTTP / WebSocket] --> API[Inbound adapters]
    TIMER[APScheduler callback] --> JOB[ScheduledScriptExecutor]
    API --> UC[Application use cases]
    JOB --> UC

    UC --> PORTS[DTOs, policies, focused ports]
    PORTS --> READ[Short persistence read]
    READ --> DTO[Immutable DTO]
    DTO --> REMOTE[SSH / Docker remote I/O]
    REMOTE --> WRITE[Short persistence write]

    PORTS --> CFG[ConfigurationImporter]
    CFG --> TX[One atomic SQLAlchemy transaction]

    READ --> PG[(PostgreSQL)]
    WRITE --> PG
    TX --> PG
    REMOTE --> HOST[Remote host]

    DI[Dishka composition root] -. binds ports .-> READ
    DI -. binds ports .-> WRITE
    DI -. binds ports .-> REMOTE
    DI -. binds ports .-> CFG
```

Живая session или ORM model не пересекает границу persistence adapter перед
remote I/O. Ветка config намеренно отличается: отдельный port владеет одной
transaction, потому что полный payload является atomic business operation.

## Модель данных

```mermaid
erDiagram
    NODE {
        uuid id PK
        string name UK
        string host
        int port
        string connection_type
        string status
        string username
        text password
        text ssh_key
        string docker_host
        list tags
        datetime created_at
        datetime updated_at
    }

    COMMAND {
        uuid id PK
        string name UK
        text description
        text command
        list parameters
        list tags
        datetime created_at
        datetime updated_at
    }

    SCRIPT {
        uuid id PK
        string name UK
        text description
        json steps
        list tags
        datetime created_at
        datetime updated_at
    }

    SCRIPT_SCHEDULE {
        uuid id PK
        uuid script_id FK,UK
        string cron
        string timezone
        json node_ids
        json params
        bool enabled
        int misfire_grace_seconds
        string operational_state
        string last_error_type
        datetime last_run_at
        datetime last_success_at
        datetime last_failure_at
        datetime next_run_at
        datetime created_at
        datetime updated_at
    }

    SCRIPT_EXECUTION {
        uuid id PK
        uuid script_id FK
        uuid node_id FK
        json params
        string status
        json steps
        datetime started_at
        datetime finished_at
    }

    AUDIT_LOG {
        uuid id PK
        uuid node_id FK
        string action
        string user
        text details
        datetime created_at
    }

    AUDIT_OUTBOX {
        uuid id PK
        json payload
        string status
        int attempts
        string last_error_type
        datetime next_attempt_at
        datetime created_at
        datetime delivered_at
    }

    API_KEY {
        uuid id PK
        string name
        string key_hash UK
        string key_prefix
        bool is_active
        string scope
        datetime created_at
        datetime last_used_at
        datetime expires_at
    }

    USER {
        uuid id PK
        string email UK
        string hashed_password
        bool is_active
        bool is_superuser
        datetime created_at
        datetime updated_at
    }

    REFRESH_TOKEN {
        uuid id PK
        uuid user_id FK
        string token_hash UK
        datetime expires_at
        datetime created_at
    }

    SCRIPT ||--o{ SCRIPT_EXECUTION : "runs as"
    SCRIPT ||--|| SCRIPT_SCHEDULE : "scheduled by"
    NODE ||--o{ SCRIPT_EXECUTION : "targets"
    NODE ||--o{ AUDIT_LOG : "tracks"
    USER ||--o{ REFRESH_TOKEN : "has"
```

`COMMAND`, `AUDIT_OUTBOX`, `API_KEY` и `USER` — независимые сущности. Учётные
записи пользователей управляются через `/api/v2/users/` (только для
суперпользователя). Refresh tokens хранятся как SHA-256 hashes и используются
для ротации JWT токенов.
