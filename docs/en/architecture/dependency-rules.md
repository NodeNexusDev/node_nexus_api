---
title: Dependency rules
status: stable
translation_key: architecture.dependency-rules
source_revision: "2026-07-30"
---

# Dependency rules

Dependencies point inward:

```text
inbound adapters -> application use cases -> DTOs / policies / ports
outbound adapters -> application ports
persistence adapters -> internal DAOs -> SQLAlchemy models
DI composition -> application contracts + concrete adapters
```

Application must not import FastAPI, Pydantic transport schemas, SQLAlchemy,
Dishka, ORM models, or concrete adapters. API modules do not import persistence
or runtime implementations. ORM-to-DTO mapping belongs to persistence adapters.
The composition root is the only place that binds a port to an adapter, using
explicit `provides=Port`. Architecture tests enforce these boundaries.

## Concrete example

```mermaid
flowchart TB
    subgraph Transport["Transport (app/api)"]
        ROUTER["FastAPI router<br/>GET /nodes/{id}"]
    end

    subgraph Application["Application (app/application)"]
        UC["GetNode use case<br/>services/node_management.py"]
        PORT["NodeManagementReader<br/>ports/node_reader.py"]
        DTO["NodeViewDTO<br/>dto/node_view.py"]
    end

    subgraph Adapter["Persistence adapter (app/adapters)"]
        GW["SqlAlchemyNodeGateway<br/>persistence/node_reader.py"]
        DAO["ScopedNodeReader<br/>persistence/dao/"]
    end

    subgraph Models["Persistence models (app/models)"]
        ORM["NodeModel<br/>models/node.py"]
    end

    subgraph DI["Composition root (app/di)"]
        BIND["@provide(provides=NodeManagementReader)"]
    end

    ROUTER -->|"FromDishka[GetNode]"| UC
    UC -->|"__init__(reader: NodeManagementReader)"| PORT
    UC -->|"returns"| DTO
    PORT -.->|"bound by"| BIND
    BIND -.->|"wires to"| GW
    GW -->|"uses sessionmaker"| DAO
    DAO -->|"maps from"| ORM
```

Each arrow crosses exactly one architectural boundary. The router never sees
ORM models; the use case never imports SQLAlchemy; the adapter never exposes
`AsyncSession` to the application layer.
