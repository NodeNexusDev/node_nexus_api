# Node Nexus API Implementation Plan

> [!NOTE]
> This document may not reflect the current implementation.
> See the final report for up-to-date state:
> [Final Report](../reports/node-nexus-api.md)

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Реализовать REST API для управления серверными нодами с поддержкой SSH подключений

**Architecture:** Layered architecture с разделением на API, Services, Repositories, Domain Models, Core, Connectors. Зависимости строго сверху вниз.

**Tech Stack:** Python 3.13+, FastAPI, PostgreSQL 18, SQLAlchemy 2.0 (async), Alembic, Pydantic v2, dishka, asyncssh, uv, ruff, mypy, pytest

## Global Constraints
- Python 3.13+
- Все операции I/O должны быть асинхронными
- Зависимости строго сверху вниз
- Type hints обязательны для публичных функций
- Google style docstrings
- Conventional Commits
- Покрытие тестами: 80% общий, 90% для бизнес-логики

---

### Task 1: Project Setup

**Covers:** [S3, S4]

**Files:**
- Create: `pyproject.toml`
- Create: `app/__init__.py`
- Create: `app/main.py`
- Create: `.env.example`
- Create: `.gitignore`

**Interfaces:**
- Consumes: None
- Produces: Базовая структура проекта

- [ ] **Step 1: Update pyproject.toml with dependencies**

```toml
[project]
name = "node-nexus-api"
version = "0.1.0"
description = "REST API for managing server nodes"
readme = "README.md"
requires-python = ">=3.13"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "sqlalchemy[asyncio]>=2.0.30",
    "asyncpg>=0.29.0",
    "alembic>=1.13.0",
    "pydantic>=2.7.0",
    "pydantic-settings>=2.3.0",
    "dishka>=1.1.0",
    "asyncssh>=2.17.0",
    "structlog>=24.1.0",
    "httpx>=0.27.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.2.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=5.0.0",
    "pytest-mock>=3.14.0",
    "ruff>=0.4.0",
    "mypy>=1.10.0",
    "aiosqlite>=0.20.0",
]

[tool.ruff]
target-version = "py313"
line-length = 88

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.mypy]
python_version = "3.13"
strict = true
warn_return_any = true
warn_unused_configs = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create app/__init__.py**

```python
"""Node Nexus API - REST API for managing server nodes."""
```

- [ ] **Step 3: Create app/main.py**

```python
"""FastAPI application entry point."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Node Nexus API",
        description="REST API for managing server nodes",
        version="0.1.0",
    )
    return app


app = create_app()
```

- [ ] **Step 4: Create .env.example**

```bash
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/node_nexus
SECRET_KEY=your-secret-key-here
DEBUG=true
LOG_LEVEL=INFO
```

- [ ] **Step 5: Create .gitignore**

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
.venv/

# Environment
.env

# IDE
.vscode/
.idea/
*.swp
*.swo

# Testing
.pytest_cache/
htmlcov/
.coverage
.coverage.*

# mypy
.mypy_cache/

# ruff
.ruff_cache/

# Alembic
alembic/versions/*.pyc
```

- [ ] **Step 6: Install dependencies**

Run: `uv sync`

- [ ] **Step 7: Run linter**

Run: `uv run ruff check .`

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml app/ .env.example .gitignore
git commit -m "chore: initialize project structure with dependencies"
```

---

### Task 2: Core Configuration

**Covers:** [S8]

**Files:**
- Create: `app/core/__init__.py`
- Create: `app/core/config.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Consumes: None
- Produces: `Settings` class

- [ ] **Step 1: Write the failing test**

Create `tests/test_config.py`:

```python
"""Tests for core configuration."""

from app.core.config import Settings


def test_settings_default_values():
    """Test that settings have correct default values."""
    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://test:test@localhost/test",
        SECRET_KEY="test-secret",
    )
    assert settings.DEBUG is False
    assert settings.LOG_LEVEL == "INFO"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`

- [ ] **Step 3: Write minimal implementation**

Create `app/core/__init__.py`:

```python
"""Core module - configuration, exceptions, interfaces."""
```

Create `app/core/config.py`:

```python
"""Application configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str
    SECRET_KEY: str
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"


settings = Settings()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/core/ tests/test_config.py
git commit -m "feat(core): add configuration management with Pydantic Settings"
```

---

### Task 3: Domain Exceptions

**Covers:** [S5]

**Files:**
- Create: `app/core/exceptions.py`
- Modify: `tests/test_config.py`

**Interfaces:**
- Consumes: None
- Produces: `DomainError` hierarchy

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py`:

```python
"""Tests for core configuration and exceptions."""

from app.core.config import Settings
from app.core.exceptions import (
    ConnectionFailedError,
    DomainError,
    NodeNotFoundError,
)


def test_settings_default_values():
    """Test that settings have correct default values."""
    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://test:test@localhost/test",
        SECRET_KEY="test-secret",
    )
    assert settings.DEBUG is False
    assert settings.LOG_LEVEL == "INFO"


def test_domain_error_hierarchy():
    """Test that domain errors inherit from DomainError."""
    assert issubclass(NodeNotFoundError, DomainError)
    assert issubclass(ConnectionFailedError, DomainError)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`

- [ ] **Step 3: Write minimal implementation**

Create `app/core/exceptions.py`:

```python
"""Domain exceptions for the application."""


class DomainError(Exception):
    """Base exception for domain errors."""


class NodeNotFoundError(DomainError):
    """Raised when a node is not found."""


class ConnectionFailedError(DomainError):
    """Raised when a connection to a node fails."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/core/exceptions.py tests/test_config.py
git commit -m "feat(core): add domain exception hierarchy"
```

---

### Task 4: Database Models

**Covers:** [S5]

**Files:**
- Create: `app/models/__init__.py`
- Create: `app/models/base.py`
- Create: `app/models/node.py`
- Create: `tests/test_models.py`

**Interfaces:**
- Consumes: None
- Produces: `NodeModel` SQLAlchemy model

- [ ] **Step 1: Write the failing test**

Create `tests/test_models.py`:

```python
"""Tests for database models."""

import uuid
from datetime import datetime, timezone

from app.models.node import NodeModel


def test_node_model_creation():
    """Test that NodeModel can be created with required fields."""
    node = NodeModel(
        id=uuid.uuid4(),
        name="test-node",
        host="192.168.1.100",
        port=22,
        connection_type="ssh",
        status="active",
    )
    assert node.name == "test-node"
    assert node.host == "192.168.1.100"
    assert node.port == 22
    assert node.connection_type == "ssh"
    assert node.status == "active"
    assert isinstance(node.id, uuid.UUID)
    assert isinstance(node.created_at, datetime)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models.py -v`

- [ ] **Step 3: Write minimal implementation**

Create `app/models/__init__.py`:

```python
"""Database models."""
```

Create `app/models/base.py`:

```python
"""Base SQLAlchemy model."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
```

Create `app/models/node.py`:

```python
"""Node database model."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class NodeModel(Base):
    """Node database model."""

    __tablename__ = "nodes"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255))
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer, default=22)
    connection_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50), default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_models.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/models/ tests/test_models.py
git commit -m "feat(models): add Node database model"
```

---

### Task 5: Pydantic Schemas

**Covers:** [S5]

**Files:**
- Create: `app/schemas/__init__.py`
- Create: `app/schemas/node.py`
- Create: `tests/test_schemas.py`

**Interfaces:**
- Consumes: `NodeModel` from Task 4
- Produces: `NodeCreate`, `NodeUpdate`, `NodeResponse` schemas

- [ ] **Step 1: Write the failing test**

Create `tests/test_schemas.py`:

```python
"""Tests for Pydantic schemas."""

import uuid
from datetime import datetime, timezone

from app.schemas.node import NodeCreate, NodeResponse, NodeUpdate


def test_node_create_schema():
    """Test NodeCreate schema validation."""
    data = {"name": "test-node", "host": "192.168.1.100", "connection_type": "ssh"}
    node = NodeCreate(**data)
    assert node.name == "test-node"
    assert node.host == "192.168.1.100"
    assert node.port == 22


def test_node_update_schema():
    """Test NodeUpdate schema validation."""
    data = {"name": "updated-node"}
    node = NodeUpdate(**data)
    assert node.name == "updated-node"
    assert node.host is None


def test_node_response_schema():
    """Test NodeResponse schema from model dict."""
    data = {
        "id": uuid.uuid4(),
        "name": "test-node",
        "host": "192.168.1.100",
        "port": 22,
        "connection_type": "ssh",
        "status": "active",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    node = NodeResponse(**data)
    assert node.name == "test-node"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_schemas.py -v`

- [ ] **Step 3: Write minimal implementation**

Create `app/schemas/__init__.py`:

```python
"""Pydantic schemas for API request/response models."""
```

Create `app/schemas/node.py`:

```python
"""Node schemas for API."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class NodeCreate(BaseModel):
    """Schema for creating a node."""

    name: str
    host: str
    port: int = 22
    connection_type: str


class NodeUpdate(BaseModel):
    """Schema for updating a node."""

    name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    connection_type: Optional[str] = None
    status: Optional[str] = None


class NodeResponse(BaseModel):
    """Schema for node response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    host: str
    port: int
    connection_type: str
    status: str
    created_at: datetime
    updated_at: datetime
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_schemas.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/schemas/ tests/test_schemas.py
git commit -m "feat(schemas): add Pydantic schemas for Node API"
```

---

### Task 6: Base Repository Interface

**Covers:** [S9]

**Files:**
- Create: `app/repositories/__init__.py`
- Create: `app/repositories/base.py`
- Create: `tests/test_repositories.py`

**Interfaces:**
- Consumes: None
- Produces: `IRepository` abstract interface

- [ ] **Step 1: Write the failing test**

Create `tests/test_repositories.py`:

```python
"""Tests for repository interfaces."""

from app.repositories.base import IRepository


def test_repository_interface_has_required_methods():
    """Test that IRepository defines required abstract methods."""
    assert hasattr(IRepository, "get_by_id")
    assert hasattr(IRepository, "get_all")
    assert hasattr(IRepository, "create")
    assert hasattr(IRepository, "update")
    assert hasattr(IRepository, "delete")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_repositories.py -v`

- [ ] **Step 3: Write minimal implementation**

Create `app/repositories/__init__.py`:

```python
"""Repository layer for data access."""
```

Create `app/repositories/base.py`:

```python
"""Base repository interface."""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar
from uuid import UUID

ModelType = TypeVar("ModelType")


class IRepository(ABC, Generic[ModelType]):
    """Abstract base repository interface."""

    @abstractmethod
    async def get_by_id(self, id: UUID) -> ModelType | None:
        """Get a record by ID."""

    @abstractmethod
    async def get_all(self, skip: int = 0, limit: int = 100) -> list[ModelType]:
        """Get all records with pagination."""

    @abstractmethod
    async def create(self, data: dict) -> ModelType:
        """Create a new record."""

    @abstractmethod
    async def update(self, id: UUID, data: dict) -> ModelType | None:
        """Update an existing record."""

    @abstractmethod
    async def delete(self, id: UUID) -> bool:
        """Delete a record by ID."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_repositories.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/repositories/ tests/test_repositories.py
git commit -m "feat(repositories): add base repository interface"
```

---

### Task 7: Node Repository Implementation

**Covers:** [S9]

**Files:**
- Create: `app/repositories/node_repo.py`
- Modify: `tests/test_repositories.py`

**Interfaces:**
- Consumes: `IRepository`, `NodeModel`, `AsyncSession`
- Produces: `NodeRepository` implementation

- [ ] **Step 1: Write the failing test**

Add to `tests/test_repositories.py`:

```python
"""Tests for repository interfaces and implementations."""

from app.repositories.base import IRepository
from app.repositories.node_repo import NodeRepository


def test_repository_interface_has_required_methods():
    """Test that IRepository defines required abstract methods."""
    assert hasattr(IRepository, "get_by_id")
    assert hasattr(IRepository, "get_all")
    assert hasattr(IRepository, "create")
    assert hasattr(IRepository, "update")
    assert hasattr(IRepository, "delete")


def test_node_repository_inherits_from_base():
    """Test that NodeRepository implements IRepository."""
    assert issubclass(NodeRepository, IRepository)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_repositories.py -v`

- [ ] **Step 3: Write minimal implementation**

Create `app/repositories/node_repo.py`:

```python
"""Node repository implementation."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.node import NodeModel
from app.repositories.base import IRepository


class NodeRepository(IRepository[NodeModel]):
    """Node repository for database operations."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, id: UUID) -> NodeModel | None:
        """Get a node by ID."""
        result = await self._session.execute(
            select(NodeModel).where(NodeModel.id == id)
        )
        return result.scalar_one_or_none()

    async def get_all(self, skip: int = 0, limit: int = 100) -> list[NodeModel]:
        """Get all nodes with pagination."""
        result = await self._session.execute(
            select(NodeModel).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    async def create(self, data: dict) -> NodeModel:
        """Create a new node."""
        node = NodeModel(**data)
        self._session.add(node)
        await self._session.flush()
        return node

    async def update(self, id: UUID, data: dict) -> NodeModel | None:
        """Update an existing node."""
        node = await self.get_by_id(id)
        if node is None:
            return None
        for key, value in data.items():
            setattr(node, key, value)
        await self._session.flush()
        return node

    async def delete(self, id: UUID) -> bool:
        """Delete a node by ID."""
        node = await self.get_by_id(id)
        if node is None:
            return False
        await self._session.delete(node)
        await self._session.flush()
        return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_repositories.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/repositories/node_repo.py tests/test_repositories.py
git commit -m "feat(repositories): implement NodeRepository"
```

---

### Task 8: Node Service

**Covers:** [S6]

**Files:**
- Create: `app/services/__init__.py`
- Create: `app/services/node_service.py`
- Create: `tests/test_services.py`

**Interfaces:**
- Consumes: `INodeRepository`, `NodeCreate`, `NodeUpdate`
- Produces: `NodeService` with business logic

- [ ] **Step 1: Write the failing test**

Create `tests/test_services.py`:

```python
"""Tests for services."""

import uuid
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import NodeNotFoundError
from app.schemas.node import NodeCreate, NodeUpdate
from app.services.node_service import NodeService


@pytest.fixture
def mock_repository():
    """Create a mock node repository."""
    return AsyncMock()


@pytest.fixture
def node_service(mock_repository):
    """Create a NodeService with mock repository."""
    return NodeService(repository=mock_repository)


async def test_get_node_found(node_service, mock_repository):
    """Test getting an existing node."""
    node_id = uuid.uuid4()
    mock_repository.get_by_id.return_value = {"id": node_id, "name": "test"}

    result = await node_service.get_node(node_id)

    assert result["id"] == node_id
    mock_repository.get_by_id.assert_called_once_with(node_id)


async def test_get_node_not_found(node_service, mock_repository):
    """Test getting a non-existent node raises exception."""
    node_id = uuid.uuid4()
    mock_repository.get_by_id.return_value = None

    with pytest.raises(NodeNotFoundError):
        await node_service.get_node(node_id)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_services.py -v`

- [ ] **Step 3: Write minimal implementation**

Create `app/services/__init__.py`:

```python
"""Service layer for business logic."""
```

Create `app/services/node_service.py`:

```python
"""Node service for business logic."""

from uuid import UUID

from app.core.exceptions import NodeNotFoundError
from app.repositories.node_repo import NodeRepository
from app.schemas.node import NodeCreate, NodeUpdate


class NodeService:
    """Service for node operations."""

    def __init__(self, repository: NodeRepository):
        self._repository = repository

    async def get_node(self, node_id: UUID) -> dict:
        """Get a node by ID."""
        node = await self._repository.get_by_id(node_id)
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")
        return {
            "id": node.id,
            "name": node.name,
            "host": node.host,
            "port": node.port,
            "connection_type": node.connection_type,
            "status": node.status,
            "created_at": node.created_at,
            "updated_at": node.updated_at,
        }

    async def get_all_nodes(self, skip: int = 0, limit: int = 100) -> list[dict]:
        """Get all nodes."""
        nodes = await self._repository.get_all(skip=skip, limit=limit)
        return [
            {
                "id": node.id,
                "name": node.name,
                "host": node.host,
                "port": node.port,
                "connection_type": node.connection_type,
                "status": node.status,
                "created_at": node.created_at,
                "updated_at": node.updated_at,
            }
            for node in nodes
        ]

    async def create_node(self, data: NodeCreate) -> dict:
        """Create a new node."""
        node = await self._repository.create(data.model_dump())
        return {
            "id": node.id,
            "name": node.name,
            "host": node.host,
            "port": node.port,
            "connection_type": node.connection_type,
            "status": node.status,
            "created_at": node.created_at,
            "updated_at": node.updated_at,
        }

    async def update_node(self, node_id: UUID, data: NodeUpdate) -> dict:
        """Update an existing node."""
        update_data = data.model_dump(exclude_unset=True)
        node = await self._repository.update(node_id, update_data)
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")
        return {
            "id": node.id,
            "name": node.name,
            "host": node.host,
            "port": node.port,
            "connection_type": node.connection_type,
            "status": node.status,
            "created_at": node.created_at,
            "updated_at": node.updated_at,
        }

    async def delete_node(self, node_id: UUID) -> bool:
        """Delete a node."""
        result = await self._repository.delete(node_id)
        if not result:
            raise NodeNotFoundError(f"Node {node_id} not found")
        return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_services.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/services/ tests/test_services.py
git commit -m "feat(services): implement NodeService with business logic"
```

---

### Task 9: API Router

**Covers:** [S6]

**Files:**
- Create: `app/api/__init__.py`
- Create: `app/api/v1/__init__.py`
- Create: `app/api/v1/nodes.py`
- Create: `app/api/v1/health.py`
- Create: `tests/test_api.py`

**Interfaces:**
- Consumes: `NodeService`, `NodeCreate`, `NodeUpdate`, `NodeResponse`
- Produces: FastAPI routers

- [ ] **Step 1: Write the failing test**

Create `tests/test_api.py`:

```python
"""Tests for API endpoints."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_get_nodes(client):
    """Test get nodes endpoint."""
    with patch("app.api.v1.nodes.NodeService") as mock_service:
        mock_service.return_value.get_all_nodes = AsyncMock(return_value=[])
        response = client.get("/api/v1/nodes")
        assert response.status_code == 200
        assert response.json() == []


def test_create_node(client):
    """Test create node endpoint."""
    node_id = uuid.uuid4()
    with patch("app.api.v1.nodes.NodeService") as mock_service:
        mock_service.return_value.create_node = AsyncMock(
            return_value={
                "id": node_id,
                "name": "test-node",
                "host": "192.168.1.100",
                "port": 22,
                "connection_type": "ssh",
                "status": "active",
                "created_at": "2025-01-01T00:00:00",
                "updated_at": "2025-01-01T00:00:00",
            }
        )
        response = client.post(
            "/api/v1/nodes",
            json={"name": "test-node", "host": "192.168.1.100", "connection_type": "ssh"},
        )
        assert response.status_code == 201
        assert response.json()["name"] == "test-node"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api.py -v`

- [ ] **Step 3: Write minimal implementation**

Create `app/api/__init__.py`:

```python
"""API layer for HTTP endpoints."""
```

Create `app/api/v1/__init__.py`:

```python
"""API v1 endpoints."""
```

Create `app/api/v1/health.py`:

```python
"""Health check endpoint."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "healthy"}
```

Create `app/api/v1/nodes.py`:

```python
"""Node API endpoints."""

import uuid

from fastapi import APIRouter, HTTPException

from app.schemas.node import NodeCreate, NodeResponse, NodeUpdate
from app.services.node_service import NodeService

router = APIRouter(prefix="/nodes", tags=["nodes"])


@router.get("/", response_model=list[NodeResponse])
async def get_nodes(skip: int = 0, limit: int = 100) -> list[NodeResponse]:
    """Get all nodes."""
    service = NodeService(repository=None)  # TODO: inject via DI
    nodes = await service.get_all_nodes(skip=skip, limit=limit)
    return nodes


@router.get("/{node_id}", response_model=NodeResponse)
async def get_node(node_id: uuid.UUID) -> NodeResponse:
    """Get a node by ID."""
    service = NodeService(repository=None)  # TODO: inject via DI
    try:
        node = await service.get_node(node_id)
        return node
    except Exception:
        raise HTTPException(status_code=404, detail="Node not found")


@router.post("/", response_model=NodeResponse, status_code=201)
async def create_node(data: NodeCreate) -> NodeResponse:
    """Create a new node."""
    service = NodeService(repository=None)  # TODO: inject via DI
    node = await service.create_node(data)
    return node


@router.put("/{node_id}", response_model=NodeResponse)
async def update_node(node_id: uuid.UUID, data: NodeUpdate) -> NodeResponse:
    """Update an existing node."""
    service = NodeService(repository=None)  # TODO: inject via DI
    try:
        node = await service.update_node(node_id, data)
        return node
    except Exception:
        raise HTTPException(status_code=404, detail="Node not found")


@router.delete("/{node_id}", status_code=204)
async def delete_node(node_id: uuid.UUID) -> None:
    """Delete a node."""
    service = NodeService(repository=None)  # TODO: inject via DI
    try:
        await service.delete_node(node_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Node not found")
```

- [ ] **Step 4: Update main.py to include routers**

Modify `app/main.py`:

```python
"""FastAPI application entry point."""

from fastapi import FastAPI

from app.api.v1.health import router as health_router
from app.api.v1.nodes import router as nodes_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Node Nexus API",
        description="REST API for managing server nodes",
        version="0.1.0",
    )
    app.include_router(health_router)
    app.include_router(nodes_router, prefix="/api/v1")
    return app


app = create_app()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_api.py -v`

- [ ] **Step 6: Commit**

```bash
git add app/api/ app/main.py tests/test_api.py
git commit -m "feat(api): add Node CRUD endpoints"
```

---

### Task 10: SSH Connector

**Covers:** [S7]

**Files:**
- Create: `app/core/connectors/__init__.py`
- Create: `app/core/connectors/base.py`
- Create: `app/core/connectors/ssh.py`
- Create: `tests/test_ssh_connector.py`

**Interfaces:**
- Consumes: `ConnectionFailedError`
- Produces: `BaseConnector`, `SSHConnector`

- [ ] **Step 1: Write the failing test**

Create `tests/test_ssh_connector.py`:

```python
"""Tests for SSH connector."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.connectors.ssh import SSHConnector


@pytest.fixture
def ssh_connector():
    """Create an SSHConnector instance."""
    return SSHConnector(
        host="192.168.1.100",
        port=22,
        username="testuser",
        password="testpass",
    )


async def test_ssh_connector_context_manager(ssh_connector):
    """Test SSHConnector as context manager."""
    with patch("app.core.connectors.ssh.asyncssh") as mock_ssh:
        mock_connection = AsyncMock()
        mock_ssh.connect.return_value = mock_connection

        async with ssh_connector as conn:
            assert conn is not None

        mock_connection.close.assert_called_once()


async def test_ssh_connector_execute_command(ssh_connector):
    """Test executing a command via SSH."""
    with patch("app.core.connectors.ssh.asyncssh") as mock_ssh:
        mock_connection = AsyncMock()
        mock_process = AsyncMock()
        mock_process.output = "test output"
        mock_connection.run.return_value = mock_process
        mock_ssh.connect.return_value = mock_connection

        async with ssh_connector as conn:
            result = await conn.execute_command("echo test")

        assert result == "test output"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ssh_connector.py -v`

- [ ] **Step 3: Write minimal implementation**

Create `app/core/connectors/__init__.py`:

```python
"""Connectors for external systems."""
```

Create `app/core/connectors/base.py`:

```python
"""Base connector interface."""

from abc import ABC, abstractmethod
from typing import Any


class BaseConnector(ABC):
    """Abstract base connector interface."""

    @abstractmethod
    async def connect(self) -> Any:
        """Establish connection."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection."""

    @abstractmethod
    async def execute_command(self, command: str) -> str:
        """Execute a command on the remote system."""

    async def __aenter__(self):
        """Enter async context manager."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context manager."""
        await self.disconnect()
```

Create `app/core/connectors/ssh.py`:

```python
"""SSH connector implementation."""

import asyncssh

from app.core.connectors.base import BaseConnector


class SSHConnector(BaseConnector):
    """SSH connector for remote command execution."""

    def __init__(
        self,
        host: str,
        port: int = 22,
        username: str | None = None,
        password: str | None = None,
        timeout: int = 30,
    ):
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._timeout = timeout
        self._connection: asyncssh.SSHClientConnection | None = None

    async def connect(self) -> None:
        """Establish SSH connection."""
        self._connection = await asyncssh.connect(
            self._host,
            port=self._port,
            username=self._username,
            password=self._password,
            timeout=self._timeout,
        )

    async def disconnect(self) -> None:
        """Close SSH connection."""
        if self._connection:
            self._connection.close()
            await self._connection.wait_closed()
            self._connection = None

    async def execute_command(self, command: str) -> str:
        """Execute a command on the remote system."""
        if not self._connection:
            raise RuntimeError("Not connected")
        result = await self._connection.run(command, timeout=self._timeout)
        return result.output
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ssh_connector.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/core/connectors/ tests/test_ssh_connector.py
git commit -m "feat(connectors): implement SSH connector with asyncssh"
```

---

### Task 11: Dependency Injection Setup

**Covers:** [S7]

**Files:**
- Create: `app/di/__init__.py`
- Create: `app/di/providers.py`
- Modify: `app/main.py`

**Interfaces:**
- Consumes: `NodeRepository`, `NodeService`, `AsyncSession`
- Produces: DI container

- [ ] **Step 1: Write the failing test**

Create `tests/test_di.py`:

```python
"""Tests for dependency injection."""

import pytest
from dishka import make_async_container

from app.di.providers import AppProvider
from app.repositories.node_repo import NodeRepository
from app.services.node_service import NodeService


async def test_di_container_creates_services():
    """Test that DI container can create services."""
    container = make_async_container(AppProvider())
    async with container() as request_container:
        service = await request_container.get(NodeService)
        assert service is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_di.py -v`

- [ ] **Step 3: Write minimal implementation**

Create `app/di/__init__.py`:

```python
"""Dependency injection configuration."""
```

Create `app/di/providers.py`:

```python
"""DI providers for the application."""

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.node_repo import NodeRepository
from app.services.node_service import NodeService


class DbProvider(Provider):
    """Database session provider."""

    @provide(scope=Scope.REQUEST)
    async def get_session(self, sessionmaker: async_sessionmaker) -> AsyncSession:
        """Get a database session."""
        async with sessionmaker() as session:
            yield session


class RepositoryProvider(Provider):
    """Repository providers."""

    @provide
    def get_node_repository(self, session: AsyncSession) -> NodeRepository:
        """Get node repository."""
        return NodeRepository(session)


class ServiceProvider(Provider):
    """Service providers."""

    @provide
    def get_node_service(self, repository: NodeRepository) -> NodeService:
        """Get node service."""
        return NodeService(repository=repository)


class AppProvider(Provider):
    """Main application provider."""
    pass
```

- [ ] **Step 4: Update main.py to use DI**

Modify `app/main.py`:

```python
"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from dishka import make_async_container
from fastapi import FastAPI

from app.api.v1.health import router as health_router
from app.api.v1.nodes import router as nodes_router
from app.di.providers import AppProvider


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    container = make_async_container(AppProvider())
    app.state.container = container
    yield
    await container.close()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Node Nexus API",
        description="REST API for managing server nodes",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(health_router)
    app.include_router(nodes_router, prefix="/api/v1")
    return app


app = create_app()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_di.py -v`

- [ ] **Step 6: Commit**

```bash
git add app/di/ app/main.py tests/test_di.py
git commit -m "feat(di): set up dependency injection with dishka"
```

---

### Task 12: Alembic Setup

**Covers:** [S5]

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako`
- Create: `alembic/versions/`

**Interfaces:**
- Consumes: `NodeModel`, `Base`
- Produces: Alembic migrations

- [ ] **Step 1: Initialize Alembic**

Run: `uv run alembic init alembic`

- [ ] **Step 2: Configure alembic.ini**

Modify `alembic.ini`:

```ini
[alembic]
script_location = alembic
prepend_sys_path = .
sqlalchemy.url = postgresql+asyncpg://user:password@localhost:5432/node_nexus

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 3: Update alembic/env.py**

```python
"""Alembic environment configuration."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.models.base import Base
from app.models.node import NodeModel  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with a connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in async mode."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    import asyncio
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4: Generate initial migration**

Run: `uv run alembic revision --autogenerate -m "initial migration"`

- [ ] **Step 5: Commit**

```bash
git add alembic/
git commit -m "chore(alembic): set up database migrations"
```

---

### Task 13: Docker Configuration

**Covers:** [S10]

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`

**Interfaces:**
- Consumes: None
- Produces: Docker configuration

- [ ] **Step 1: Create Dockerfile**

```dockerfile
# Build stage
FROM python:3.13-slim as builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir --prefix=/install .

# Runtime stage
FROM python:3.13-slim

WORKDIR /app

RUN groupadd -r appuser && useradd -r -g appuser appuser

COPY --from=builder /install /usr/local
COPY app/ ./app/

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Create docker-compose.yml**

```yaml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/node_nexus
      - SECRET_KEY=dev-secret-key
      - DEBUG=true
      - LOG_LEVEL=INFO
    depends_on:
      - db

  db:
    image: postgres:18
    environment:
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
      - POSTGRES_DB=node_nexus
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

- [ ] **Step 3: Commit**

```bash
git add Dockerfile docker-compose.yml
git commit -m "chore(docker): add Dockerfile and docker-compose"
```

---

### Task 14: Integration Tests

**Covers:** [S9]

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/integration/test_api_integration.py`

**Interfaces:**
- Consumes: All previous tasks
- Produces: Integration tests

- [ ] **Step 1: Write the failing test**

Create `tests/conftest.py`:

```python
"""Test fixtures."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    """Create an async test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
```

Create `tests/integration/__init__.py`:

```python
"""Integration tests."""
```

Create `tests/integration/test_api_integration.py`:

```python
"""Integration tests for API endpoints."""

import pytest


@pytest.mark.asyncio
async def test_health_check_integration(client):
    """Test health check endpoint integration."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


@pytest.mark.asyncio
async def test_get_nodes_integration(client):
    """Test get nodes endpoint integration."""
    response = await client.get("/api/v1/nodes")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/ -v`

- [ ] **Step 3: Fix test setup**

Create `tests/__init__.py`:

```python
"""Tests package."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/ -v`

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test(integration): add API integration tests"
```

---

### Task 15: Final Verification

**Covers:** [S9]

**Files:**
- None (verification only)

**Interfaces:**
- Consumes: All previous tasks
- Produces: Verification of all components

- [ ] **Step 1: Run all tests**

Run: `uv run pytest`

- [ ] **Step 2: Run linter**

Run: `uv run ruff check .`

- [ ] **Step 3: Run formatter**

Run: `uv run ruff format .`

- [ ] **Step 4: Run type checker**

Run: `uv run mypy app tests`

- [ ] **Step 5: Verify coverage**

Run: `uv run pytest --cov=app --cov-report=term-missing`

- [ ] **Step 6: Commit final state**

```bash
git add .
git commit -m "chore: complete initial implementation of Node Nexus API"
```

---

## Execution Handoff

Plan saved. How would you like to execute it?

**Options:**
1. **Subagent, always** - Fresh subagent per task — remember for future sessions
2. **Subagent, this time** - Fresh subagent per task — just this once
3. **Inline, always** - Execute in this session — remember for future sessions
4. **Inline, this time** - Execute in this session — just this once

**Recommendation:** Given 15 tasks with clear boundaries, **Subagent, this time** would be efficient. Each task is independent and can be parallelized where possible.