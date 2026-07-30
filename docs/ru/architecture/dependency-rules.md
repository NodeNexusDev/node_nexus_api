---
title: Правила зависимостей
status: stable
translation_key: architecture.dependency-rules
source_revision: "2026-07-30"
---

# Правила зависимостей

Зависимости направлены внутрь:

```text
inbound adapters -> application use cases -> DTOs / policies / ports
outbound adapters -> application ports
persistence adapters -> internal DAO -> SQLAlchemy models
DI composition -> application contracts + concrete adapters
```

Application не импортирует FastAPI, Pydantic transport schemas, SQLAlchemy,
Dishka, ORM models или concrete adapters. API modules не импортируют
persistence/runtime implementations. ORM-to-DTO mapping выполняется в
persistence adapter. Только composition root связывает port с adapter через
явный `provides=Port`. Границы проверяются architecture tests.

## Конкретный пример

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
    UC -->|"возвращает"| DTO
    PORT -.->|"связан через"| BIND
    BIND -.->|"подключает"| GW
    GW -->|"использует sessionmaker"| DAO
    DAO -->|"маппит из"| ORM
```

Каждая стрелка пересекает ровно одну архитектурную границу. Router никогда не
видит ORM-модели; use case не импортирует SQLAlchemy; adapter не раскрывает
`AsyncSession` в application layer.
