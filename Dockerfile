# Stage 1: Build React Frontend
FROM node:18-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Build FastAPI Backend
FROM python:3.11-slim AS backend-builder
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY src/ ./src/
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Stage 3: Production Runtime
FROM python:3.11-slim
WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

# Copy from builder stages
COPY --from=backend-builder /root/.local /home/appuser/.local
COPY --from=backend-builder /app/src ./src
COPY --from=backend-builder /app/frontend/dist ./frontend/dist

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser
RUN chown -R appuser:appuser /app

USER appuser

# Add local pip packages to PATH
ENV PATH="/home/appuser/.local/bin:${PATH}"

# Expose port 80 for Azure App Service
EXPOSE 80
ENV PORT=80

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -sf http://localhost:${PORT}/health/live || exit 1

# Run uvicorn with production settings
CMD ["sh", "-c", "uvicorn src.app:app --host 0.0.0.0 --port ${PORT} --workers 1 --access-log"]