# Dependency Rules

## Allowed dependencies

```text
api         → application, services, schemas, core errors
application → application ports and DTOs, core
services    → application ports and DTOs, repositories during migration, core
repositories→ application ports and DTOs, models
models      → SQLAlchemy and standard library
schemas     → Pydantic and standard library
core        → standard library and infrastructure libraries
di          → all modules required by the composition root
```

`app/di` is the composition root and is the only module allowed to know concrete
implementations across all layers.

## Forbidden dependencies

- `api → repositories`
- `api → models`
- `api → di.container`
- `application → FastAPI`
- `application → SQLAlchemy`
- `models → services`
- `repositories → API`
- `core → API`

## Boundary types

- HTTP input and output use Pydantic schemas from `app/schemas`.
- Application and infrastructure boundaries use immutable DTOs from
  `app/application/dto`.
- ORM models never cross into API adapters.
- Secrets may be carried only by internal connection DTOs and must be excluded
  from their representation.

## Exceptions

Temporary exceptions during migration must be documented in an architecture
test waiver. A waiver includes an owner, rationale, affected import, and removal
condition.

## Enforcement

The architecture is enforced by automated tests. New reverse dependencies
must fail CI rather than rely on code-review memory.

The Docker compatibility facade is limited to 200 lines and cannot contain
`_legacy_*` implementations. Docker routers must delegate domain exceptions to
the global handler.
