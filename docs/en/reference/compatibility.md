---
title: Compatibility and support
status: stable
translation_key: reference.compatibility
source_revision: "2026-08-17"
---

# Compatibility and support

The project follows Semantic Versioning. The `/api/v1` prefix identifies the
current major HTTP contract; additive fields and endpoints may appear in minor
versions. Removing or changing required fields, meanings, paths, or status
semantics is breaking and requires explicit contract review and a major-version
strategy.

Python 3.13 and PostgreSQL are supported. Client generators should consume the
OpenAPI artifact produced for the exact release.

## API versioning

The API supports header-based versioning through `X-API-Version`. The default
version is `1`. Unsupported versions return `400 Bad Request`. Health, readiness,
and metrics endpoints are excluded from version enforcement.

## Changelog

| Version | Date | Type | Highlights |
|---------|------|------|------------|
| 0.15.0 | 2026-08-17 | Minor | Scheduler trigger-now endpoint, failed status propagation, E2E refactoring with shared settings, CI hardening |
| 0.14.0 | 2026-08-17 | Minor | HMAC-SHA-256 API key hashing, ENCRYPTION_SALT required, CORS restriction, dashboard group_by validation, WebSocket token auth cleanup |
| 0.13.4 | 2026-08-17 | Patch | OpenAPI snapshot and tag_manager bindparam fixes |
| 0.13.3 | 2026-08-17 | Patch | Resolve unit test failures from DTO refactor |
| 0.13.2 | 2026-08-17 | Patch | Typed result DTOs, suppress bandit B608 warnings |
| 0.13.1 | 2026-08-17 | Patch | Fix Stage F E2E test failures, SQLAlchemy cache key issues |
| 0.13.0 | 2026-08-15 | Minor | Favorites, notes, tag management, clone, dashboard metrics, global search, execution statistics, SSE stream, audit export |
| 0.11.0 | 2026-08-13 | Minor | Dry-run config import, validate-credentials endpoint |
| 0.10.0 | 2026-08-12 | Minor | Real Docker container stats on dashboard |
| 0.9.0 | 2026-08-12 | Minor | Dashboard endpoint, audit user/date filters, bulk execute by tags |
| 0.8.0 | 2026-08-11 | Minor | Docker create/image build, bulk by tags, detailed readiness, request id in errors, API versioning |
| 0.7.1 | 2026-07-30 | Patch | Documentation fixes |
| 0.7.0 | 2026-07-29 | Minor |
| 0.6.4 | 2026-07-29 | Patch |
| 0.6.3 | 2026-07-29 | Patch |
| 0.6.2 | 2026-07-28 | Patch |
| 0.6.1 | 2026-07-26 | Patch |
| 0.6.0 | 2026-07-26 | Minor |
| 0.5.0 | 2026-07-26 | Minor |
| 0.4.0 | 2026-07-25 | Minor |
| 0.3.0 | 2026-07-25 | Minor |
| 0.2.1 | 2026-07-19 | Patch |
| 0.2.0 | 2026-07-19 | Minor |
| 0.1.0 | 2026-07-15 | Minor |
| 0.0.1 | 2026-07-15 | Initial |
