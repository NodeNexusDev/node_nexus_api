---
title: Обзор архитектуры
status: stable
translation_key: architecture.overview
source_revision: "2026-07-30"
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
