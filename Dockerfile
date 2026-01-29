# OBS Fog Server - Multi-stage Dockerfile
# Optimized for production with minimal image size

# Build stage
FROM python:3.12-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt

# Production stage
FROM python:3.12-slim as production

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user
RUN useradd -m -u 1000 appuser

# Copy wheels from builder
COPY --from=builder /app/wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

# Copy application code
COPY --chown=appuser:appuser app /app/app
COPY --chown=appuser:appuser alembic /app/alembic
COPY --chown=appuser:appuser alembic.ini /app/
COPY --chown=appuser:appuser entrypoint.sh /app/

# Create data directories
RUN mkdir -p /data/videos /data/hls && chown -R appuser:appuser /data

# Switch to non-root user
USER appuser

# Environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/healthz || exit 1

# Expose port
EXPOSE 8000

# Run with entrypoint (migrations + uvicorn)
CMD ["bash", "/app/entrypoint.sh"]
