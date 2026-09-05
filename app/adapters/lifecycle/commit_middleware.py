"""Request-scoped DB commit middleware (infrastructure)."""

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class CommitOnResponseMiddleware:
    """Commit the request-scoped DB transaction before sending HTTP headers.

    This middleware wraps the outgoing ASGI ``send`` callable and commits the
    request transaction when the application emits ``http.response.start``.
    Committing before the response leaves the server guarantees that clients
    cannot observe stale state after a successful write.
    """

    EXCLUDED_PATHS = frozenset({"/health", "/ready", "/metrics"})

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if scope.get("path") in self.EXCLUDED_PATHS:
            await self.app(scope, receive, send)
            return

        committed = False

        async def send_with_commit(message: Message) -> None:
            nonlocal committed

            if not committed and message.get("type") == "http.response.start":
                request = Request(scope, receive=receive, send=send)
                container = request.state.dishka_container
                session = await container.get(AsyncSession)

                if session.new or session.dirty or session.deleted:
                    try:
                        await session.commit()
                    except Exception:
                        await session.rollback()
                        raise

                committed = True

            await send(message)

        await self.app(scope, receive, send_with_commit)
