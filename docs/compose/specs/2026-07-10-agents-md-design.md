# AGENTS.md Design Specification

## [S1] Project Overview

**node_nexus_api** — REST API for managing server nodes with multiple connection methods.

**Tech Stack:**
- Framework: FastAPI
- Database: PostgreSQL
- ORM: SQLAlchemy 2.0 + Alembic
- DI Container: dishka
- Tools: uv, ruff, ty
- Testing: pytest
- Documentation: Google-style docstrings
- Commits: Conventional Commits

## [S2] Coding Standards

**Language and Style:**
- Python 3.13+
- Type hints everywhere (functions, variables, return values)
- Google-style docstrings for public functions/classes
- snake_case for variables/functions, PascalCase for classes
- Max line length: 88 characters (ruff default)

**Imports:**
- Standard library → third-party → local (ruff sorts)
- Absolute imports (`from app.services.node import ...`)

**Async/Await:**
- async/await for I/O-bound operations (SSH, HTTP, DB)
- Never block event loop with synchronous operations

**Error Handling:**
- Custom exceptions in `core/exceptions.py`
- Don't catch generic Exception without necessity
- Error logging via structlog or logging

## [S3] Project Structure

```
node_nexus_api/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, lifespan, dishka setup
│   ├── api/
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── nodes.py     # /api/v1/nodes endpoints
│   │       └── health.py    # /api/v1/health
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py        # Settings, env vars
│   │   ├── exceptions.py    # Custom exceptions
│   │   ├── security.py      # Auth, tokens
│   │   └── connectors/
│   │       ├── __init__.py
│   │       ├── base.py      # NodeConnector Protocol
│   │       └── ssh.py       # asyncssh implementation
│   ├── models/
│   │   ├── __init__.py
│   │   ├── base.py          # SQLAlchemy Base, mixins
│   │   └── node.py          # Node model
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── node.py          # Pydantic schemas
│   └── services/
│       ├── __init__.py
│       └── node/
│           ├── __init__.py
│           └── service.py   # Node business logic
├── alembic/
│   └── versions/
├── tests/
│   ├── conftest.py
│   ├── api/
│   ├── services/
│   └── connectors/
├── alembic.ini
├── pyproject.toml
└── AGENTS.md
```

**Principles:**
- `app/` — application root
- API versioning via `api/v1/`
- Dependencies injected via dishka container
- Connectors isolated in `core/connectors/`

## [S4] Testing Standards

**Test Structure:**
```
tests/
├── conftest.py          # Common fixtures (session, async client, etc.)
├── api/                 # API integration tests
│   └── test_nodes.py
├── services/            # Service unit tests
│   └── test_node_service.py
└── connectors/          # Connector unit tests
    └── test_ssh.py
```

**Principles:**
- async tests via `pytest-asyncio`
- Fixtures for DB (transactions with rollback) and test client
- Mock external calls (SSH, HTTP) via `unittest.mock` or `pytest-mock`
- Coverage minimum 80% for services and connectors

**Run:**
```bash
uv run pytest                    # All tests
uv run pytest --cov=app         # With coverage
uv run pytest tests/api/        # Only API tests
```

## [S5] DevOps and Tools

**Package Management:**
```bash
uv add fastapi sqlalchemy asyncssh    # Add dependencies
uv add --dev pytest ruff ty           # Dev dependencies
uv run python main.py                 # Run
```

**Linting and Formatting:**
```bash
uvx ruff check app/ --fix             # Fix errors
uvx ruff format app/                  # Format
uvx ruff check --select I app/        # Import sorting
uvx ty check app/                     # Type check
```

**Migrations (Alembic):**
```bash
uv run alembic revision --autogenerate -m "description"
uv run alembic upgrade head
```

**Docker:**
```bash
docker compose up -d                  # Start services
docker compose down                   # Stop
docker compose logs -f api            # Logs
```

**Dockerfile (multi-stage):**
- Stage 1: build dependencies
- Stage 2: runtime (minimal image)
- Non-root user for security

**Commits (Conventional Commits):**
```
feat(nodes): add SSH connection handler
fix(api): handle node not found error
chore(deps): update fastapi to 0.115
docs(readme): add setup instructions
```

**Pre-commit (recommended):**
- ruff check + format + import sorting
- ty check
- pytest (fast tests)

## [S6] Workflow Rules

**When working with code:**
1. Always start with `git pull` and `uv sync`
2. Create feature branches: `feat/node-ssh-connection`
3. Write tests before or during implementation (TDD recommended)
4. Run `ruff check` and `ty check` before committing
5. Make small commits with clear messages

**When adding a new connector:**
1. Define interface in `core/connectors/base.py`
2. Implement in `core/connectors/<type>.py`
3. Register in dishka container
4. Write unit tests in `tests/connectors/`
5. Add integration test in `tests/api/`

**When changing API:**
1. Update/create schema in `schemas/`
2. Add/modify endpoint in `api/v1/`
3. Add service method if business logic needed
4. Write tests for new endpoint
5. Update Alembic migration if DB changes

**Code Review:**
- All PRs must pass type checking (ty)
- Test coverage not lower than 80% for new code
- Don't merge without all tests passing
