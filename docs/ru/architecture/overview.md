---
title: Обзор архитектуры
status: stable
translation_key: architecture.overview
source_revision: "2026-07-29"
---

# Обзор архитектуры

Node Nexus — модульное FastAPI-приложение. HTTP и WebSocket adapters вызывают
application services; services координируют repositories и внешние connectors;
repositories владеют persistence access; Pydantic schemas и application DTO
служат boundary values; SQLAlchemy models остаются деталями persistence.

Dishka создаёт application и request scopes. Одна request-scoped session
используется repositories и services, commit выполняется на границе use case.
SSH и Docker — удалённые side effects, их нельзя удерживать внутри долгих DB
transactions.

Текущая модель использует PostgreSQL и in-process scheduler. API replicas
допустимы, только если scheduling принадлежит одному process.
