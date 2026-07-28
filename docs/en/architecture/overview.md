---
title: Architecture overview
status: stable
translation_key: architecture.overview
source_revision: "2026-07-29"
---

# Architecture overview

Node Nexus is a modular FastAPI application. HTTP and WebSocket adapters call
application services; services coordinate repositories and external connectors;
repositories own persistence access; Pydantic schemas and application DTOs are
boundary values; SQLAlchemy models remain persistence details.

Dishka creates application and request scopes. A request-scoped session is
shared by repositories and services and committed at the use-case boundary.
SSH and Docker are remote side effects and are never held inside long database
transactions.

The current deployment model uses PostgreSQL and an in-process scheduler. API
replicas are possible only when a single process owns scheduling.
