"""
Rate limiting configuration using slowapi.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

# Determine storage URI
# Use Redis if configured, otherwise use in-memory storage
_storage_uri = None
if settings.redis_url and settings.redis_url.strip():
    _storage_uri = settings.redis_url

# Create limiter instance
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[
        f"{settings.rate_limit_requests}/{settings.rate_limit_window_seconds}seconds"
    ],
    storage_uri=_storage_uri,
    strategy="fixed-window",
)


# Specific rate limits for different endpoints
RATE_LIMIT_AUTH = "5/minute"  # Login/register attempts
RATE_LIMIT_API = "100/minute"  # General API calls
RATE_LIMIT_WEBHOOK = "200/minute"  # Webhooks (RTMP hooks, payments)
RATE_LIMIT_DOWNLOAD = "10/minute"  # File downloads
