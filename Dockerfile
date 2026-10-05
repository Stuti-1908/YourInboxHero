# Backend-only image. The frontend is deployed separately on Vercel and
# talks to this API over HTTPS (see frontend/src/api/invoice.ts API_BASE),
# so this image no longer builds or serves any frontend assets.

FROM python:3.11-slim AS backend-builder
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini .
COPY templates/ ./templates/

# Production runtime
FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r appuser && useradd -r -g appuser appuser

COPY --from=backend-builder /root/.local /home/appuser/.local
COPY --from=backend-builder /app/src ./src
COPY --from=backend-builder /app/alembic ./alembic
COPY --from=backend-builder /app/alembic.ini .
COPY --from=backend-builder /app/templates ./templates

# Pre-create the uploads mount point owned by appuser before the volume
# attaches — Docker initializes a fresh named volume by copying in the
# image's existing directory at that path (including ownership), so this
# is what makes the volume writable by the non-root user at first run.
# A chown here does NOT retroactively fix an already-existing volume
# that was first created root-owned (e.g. before this directory existed
# in the image) — that needs a one-off `docker exec -u root ... chown`.
RUN mkdir -p /app/uploads && chown -R appuser:appuser /app
USER appuser

ENV PATH="/home/appuser/.local/bin:${PATH}"

# 8000, not 80 — this container runs as a non-root user, and binding <1024
# requires root or CAP_NET_BIND_SERVICE. Caddy (or whatever reverse proxy
# sits in front on the host) maps 443 -> 8000.
EXPOSE 8000
ENV PORT=8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -sf http://localhost:${PORT}/health/live || exit 1

CMD ["sh", "-c", "uvicorn src.app:app --host 0.0.0.0 --port ${PORT} --workers 1 --access-log"]
