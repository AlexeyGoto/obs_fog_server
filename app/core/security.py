"""
Security utilities: JWT tokens, password hashing, and authentication helpers.
"""
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any

import jwt
from passlib.context import CryptContext

from app.core.config import settings

# Password hashing context using bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """
    Create a JWT access token.

    Args:
        data: Payload data (typically {"sub": user_id})
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.jwt_access_token_expire_minutes
        )

    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    })

    return jwt.encode(
        to_encode,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def create_refresh_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """
    Create a JWT refresh token with longer expiration.

    Args:
        data: Payload data (typically {"sub": user_id})
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            days=settings.jwt_refresh_token_expire_days
        )

    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
    })

    return jwt.encode(
        to_encode,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str) -> dict[str, Any] | None:
    """
    Decode and validate a JWT token.

    Args:
        token: JWT token string

    Returns:
        Decoded payload dict or None if invalid
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def generate_stream_key(length: int = 32) -> str:
    """Generate a secure random stream key."""
    return secrets.token_urlsafe(length)


def generate_api_key(length: int = 32) -> str:
    """Generate a secure random API key."""
    return secrets.token_urlsafe(length)


def create_pc_token(user_id: int, pc_id: int, expires_days: int = 365) -> str:
    """
    Create a long-lived JWT token bound to a specific PC.

    Used for PowerShell scripts (SteamSlot, OBS installer) that need
    to authenticate without user interaction.

    Args:
        user_id: Owner user ID
        pc_id: PC ID this token is valid for
        expires_days: Token validity in days (default 1 year)

    Returns:
        Encoded JWT token string
    """
    expire = datetime.now(timezone.utc) + timedelta(days=expires_days)

    payload = {
        "sub": str(user_id),
        "pc_id": pc_id,
        "type": "pc_token",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }

    return jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def decode_pc_token(token: str) -> dict[str, Any] | None:
    """
    Decode and validate a PC-bound token.

    Args:
        token: JWT token string

    Returns:
        Decoded payload with 'sub' (user_id) and 'pc_id', or None if invalid
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        # Verify it's a PC token
        if payload.get("type") != "pc_token":
            return None
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def verify_telegram_webhook_hash(
    bot_token: str,
    data_check_string: str,
    received_hash: str,
) -> bool:
    """
    Verify Telegram webhook data authenticity.

    Args:
        bot_token: Telegram bot token
        data_check_string: Sorted key=value pairs joined by newline
        received_hash: Hash received from Telegram

    Returns:
        True if hash is valid
    """
    import hashlib
    import hmac

    secret_key = hashlib.sha256(bot_token.encode()).digest()
    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(calculated_hash, received_hash)


def verify_payment_signature(
    payload: bytes,
    signature: str,
    secret: str,
) -> bool:
    """
    Verify payment webhook signature.

    Args:
        payload: Raw request body
        signature: Signature from header
        secret: Webhook secret

    Returns:
        True if signature is valid
    """
    import hashlib
    import hmac

    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)
