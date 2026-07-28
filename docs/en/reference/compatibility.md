---
title: Compatibility and support
status: stable
translation_key: reference.compatibility
source_revision: "2026-07-29"
---

# Compatibility and support

The project follows Semantic Versioning. The `/api/v1` prefix identifies the
current major HTTP contract; additive fields and endpoints may appear in minor
versions. Removing or changing required fields, meanings, paths, or status
semantics is breaking and requires explicit contract review and a major-version
strategy.

Python 3.13 and PostgreSQL are supported. Client generators should consume the
OpenAPI artifact produced for the exact release.
