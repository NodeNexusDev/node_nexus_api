# Runtime Lifecycle

## Application startup

```text
configure logging
→ optionally run migrations
→ create application-scoped resources
→ start in-process scheduler
→ perform startup maintenance
→ serve requests
```

## Application shutdown

```text
stop scheduler
→ close Dishka container
→ dispose SQLAlchemy engine
→ close telemetry resources
```

Resource finalization must run even when startup or request processing fails.

## DI scopes

- `APP`: settings, SQLAlchemy engine, sessionmaker, connector factories,
  scheduler, short-scope persistence gateways.
- `SESSION`: one WebSocket connection.
- `REQUEST`: one HTTP request, one scheduled invocation, or one nested WebSocket
  message operation.

## Scheduler

The scheduler is application-scoped and owned by the DI container. It is started
once and stopped once. Jobs execute in a fresh nested scope.

Schedules are currently in memory:

- they are lost on process restart;
- only a single API process is supported;
- persistence and multi-process coordination are intentionally deferred.

## Database engine

The SQLAlchemy engine is an application-scoped managed resource. Its provider
must call `AsyncEngine.dispose()` during finalization.
