# Build stage
FROM python:3.13-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app/ ./app/
RUN uv sync --frozen --no-dev

# Runtime stage
FROM python:3.13-slim

WORKDIR /app

RUN groupadd -r appuser && useradd -r -g appuser appuser

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/app /app/app
COPY alembic/ ./alembic/
COPY alembic.ini .
COPY main.py .

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request, os; req = urllib.request.Request('http://localhost:8000/health', headers={'X-API-Key': os.environ.get('MASTER_API_KEY','')}); urllib.request.urlopen(req, timeout=5)" || exit 1

CMD ["python", "main.py"]
