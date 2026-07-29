---
title: Обзор архитектуры
status: stable
translation_key: architecture.overview
source_revision: "2026-07-30"
---

# Обзор архитектуры

Node Nexus использует Ports & Adapters. HTTP, WebSocket и scheduler adapters
вызывают inbound application use cases. Use cases зависят от immutable DTO и
focused ports. SQLAlchemy, SSH, Docker, security и scheduler implementations
подключаются только в Dishka composition root.

Pydantic models являются transport contracts, SQLAlchemy models — деталями
persistence; оба типа не пересекают application boundary. APP gateways хранят
sessionmaker, request-transaction DAO — session. SSH/Docker side effects
выполняются после закрытия read session.

PostgreSQL является system of record. In-process scheduler использует
advisory-lock ownership: non-owner replicas обслуживают HTTP, но не запускают
jobs.
