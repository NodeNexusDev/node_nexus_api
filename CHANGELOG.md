# Changelog

All notable changes to this project are documented here. For a full
compatibility and support matrix, see [Compatibility](docs/en/reference/compatibility.md).

## 0.15.1 — 2026-08-18

### Fixed

- Eliminated read-after-write race in HTTP CRUD operations by committing the
  request-scoped transaction before sending the response headers
  (`CommitOnResponseMiddleware`).
- Removed minute-boundary race in scheduler restart tests by using a far-future
  cron and relying on `trigger-now` for deterministic execution.

### Internal

- Added a pre-commit hook that auto-updates the OpenAPI contract hash when the
  generated schema changes.

## 0.15.0 — 2026-08-17

### Added

- Internal scheduler `trigger-now` endpoint for deterministic test execution.
- Failed status propagation for scheduled script execution.

### Changed

- E2E suite refactored with shared settings and factory helpers.
- CI hardened with immutable GitHub Actions releases and Docker image publishing
  to GHCR.

## 0.14.0 — 2026-08-17

### Security

- Replaced SHA-256 with HMAC-SHA-256 for API-key hashing.
- Made `ENCRYPTION_SALT` required in production.
- Restricted CORS origins.

### Changed

- Removed deprecated WebSocket query-string token authentication.
- Added `group_by` validation for dashboard metrics.

## 0.13.0 — 2026-08-15

### Added

- Favorites, notes, and tag management.
- Command and script cloning.
- Dashboard metrics, global search, execution statistics.
- SSE event stream and audit export (JSON/CSV).

## 0.11.0 — 2026-08-13

### Added

- Dry-run mode for configuration import.
- Node credential validation endpoint.

## 0.10.0 — 2026-08-12

### Added

- Real Docker container statistics on the dashboard.

## 0.9.0 — 2026-08-12

### Added

- Dashboard endpoint.
- Audit log filters by user and date range.
- Bulk script execution by tags.
