---
title: Architecture overview
status: stable
translation_key: architecture.overview
source_revision: "2026-09-02"
---

# Architecture overview

Node Nexus uses Ports & Adapters. HTTP, WebSocket, and scheduler adapters call
inbound application use cases. Use cases depend on immutable DTOs and focused
ports. SQLAlchemy, SSH, Docker, security, and scheduler implementations are
outbound adapters connected only by the Dishka composition root.

Pydantic models are transport contracts and SQLAlchemy models are persistence
details; neither crosses the application boundary. Dishka creates APP and
REQUEST scopes. APP gateways own a sessionmaker, while request-transaction DAOs
own a session. SSH and Docker side effects run after the read session closes.

PostgreSQL is the system of record. The in-process scheduler uses advisory-lock
ownership so non-owner replicas can serve HTTP without executing jobs.

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

No live session or ORM model crosses from a persistence adapter into remote
I/O. The config branch is deliberately different: its dedicated port owns one
transaction because the complete payload is one atomic business operation.

## Data model

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
        text description
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
        uuid template_pack_id FK
        datetime created_at
        datetime updated_at
    }

    SCRIPT {
        uuid id PK
        string name UK
        text description
        json steps
        list tags
        uuid template_pack_id FK
        datetime created_at
        datetime updated_at
    }

    COMPOSE_PROJECTS {
        uuid id PK
        uuid node_id FK
        string project_name
        text compose
        json env
        uuid template_pack_id FK
        datetime created_at
        datetime updated_at
    }

    TEMPLATE_REGISTRIES {
        uuid id PK
        string owner
        string name
        text github_token_encrypted
        string default_branch
        datetime last_synced_at
        datetime created_at
        datetime updated_at
    }

    TEMPLATE_PACKS {
        uuid id PK
        uuid registry_id FK
        string pack_id
        string name
        text description
        string version
        string author
        list tags
        string manifest_sha
        text readme
        datetime created_at
        datetime updated_at
    }

    TEMPLATE_ASSETS {
        uuid id PK
        uuid pack_id FK
        string path
        text content
        int size
        string sha
        datetime created_at
        datetime updated_at
    }

    TEMPLATE_INSTALLATIONS {
        uuid id PK
        uuid pack_id FK
        string entity_type
        uuid entity_id FK
        datetime created_at
    }

    COMMAND_EXECUTION {
        uuid id PK
        uuid batch_id
        uuid node_id FK
        uuid command_id FK
        string command_fingerprint
        int exit_code
        text stdout
        text stderr
        datetime started_at
        datetime finished_at
        datetime created_at
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
    NODE ||--o{ COMPOSE_PROJECTS : "hosts"
    TEMPLATE_REGISTRIES ||--o{ TEMPLATE_PACKS : "provides"
    TEMPLATE_PACKS ||--o{ TEMPLATE_ASSETS : "contains"
    TEMPLATE_PACKS ||--o{ TEMPLATE_INSTALLATIONS : "installed as"
    COMMAND ||--o{ COMMAND_EXECUTION : "executed as"
    NODE ||--o{ COMMAND_EXECUTION : "runs on"
```

`COMMAND`, `AUDIT_OUTBOX`, `API_KEY`, and `USER` are standalone entities. User
accounts are managed through `/api/v2/users/` (superuser-only). Refresh tokens
are stored as SHA-256 hashes and used for JWT token rotation.

`NOTES` table was removed in 2.0 (migration `b1c2d3e4f5g6`); use `NODE.description`
instead. `COMMAND` and `SCRIPT` now carry `template_pack_id` for pack traceability.
`COMPOSE_PROJECTS` is keyed by `(node_id, project_name)` and stores `compose`,
`env`, and optional `template_pack_id`. Template subsystem uses
`TEMPLATE_REGISTRIES`, `TEMPLATE_PACKS`, `TEMPLATE_ASSETS`, and
`TEMPLATE_INSTALLATIONS`.

Indexes and migrations:

- `ix_command_executions_command_id` on `command_executions.command_id`
  (migration `90156a878bb9`).
- `ix_nodes_name` unique on `nodes.name`, `ix_commands_name` on `commands.name`,
  GIN indexes on `tags` arrays.

Bulk and pagination conventions (v2):

- Bulk operations return a `BulkResult<T>` envelope
  `{total, succeeded, failed, results:[{id,status:"success"|"error",error?,output?}]}`
  with `200` on full success, `207 Multi-Status` when `succeeded>0 && failed>0`,
  and `422` when all fail.
- Collection listings use cursor pagination
  `GET /api/v2/nodes/?cursor=<base64>&limit=20 → {items,next_cursor,has_more,limit}`
  (`cursor` encodes `{"offset": n}` or `{"ts": "...", "id": "..."}`); invalid cursor
  → `422`.
- `BulkCommandRequestDTO.timeout` (optional `int`) is wired from the API request
  through `NodeBulkCommandService.execute(..., timeout=data.timeout)` to the SSH
  executor per node.
