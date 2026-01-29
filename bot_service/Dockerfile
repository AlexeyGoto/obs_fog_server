# OBS Fog Server - Telegram Bot Dockerfile
# Handles user interactions and admin approvals

FROM python:3.12-slim

WORKDIR /app

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    python-telegram-bot[job-queue]==21.9 \
    sqlalchemy[asyncio]==2.0.36 \
    asyncpg==0.30.0 \
    httpx==0.28.1 \
    python-dotenv==1.0.1 \
    pydantic-settings==2.7.1

# Copy bot code
COPY bot_service/main.py /app/main.py
COPY app/core /app/app/core
COPY app/models /app/app/models
COPY app/services /app/app/services

# Environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Run bot
CMD ["python", "main.py"]
