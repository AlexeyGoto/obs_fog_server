# OBS Fog Server - Worker Service Dockerfile
# Processes clip jobs from HLS to MP4

FROM python:3.12-slim

WORKDIR /app

# Install FFmpeg and other dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir \
    sqlalchemy[asyncio]==2.0.36 \
    asyncpg==0.30.0 \
    httpx==0.28.1 \
    python-dotenv==1.0.1 \
    pydantic-settings==2.7.1

# Copy worker code
COPY worker_service/main.py /app/main.py
COPY app/core /app/app/core
COPY app/models /app/app/models
COPY app/services /app/app/services

# Environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Create data directories
RUN mkdir -p /data/videos /data/hls

# Run worker
CMD ["python", "main.py"]
