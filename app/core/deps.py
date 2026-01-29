"""
FastAPI dependencies for authentication, authorization, and database access.
"""
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_pc_token, decode_token
from app.models.pc import PC
from app.models.user import User, UserRole

# HTTP Bearer token scheme
security = HTTPBearer(auto_error=False)


async def get_current_user_from_token(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(security)
    ] = None,
) -> User:
    """
    Get current user from JWT token (Bearer or Cookie).

    Checks:
    1. Authorization header (Bearer token)
    2. Session cookie

    Raises:
        HTTPException 401: If not authenticated
        HTTPException 401: If token is invalid
        HTTPException 401: If user not found
    """
    token = None

    # Try Bearer token first
    if credentials:
        token = credentials.credentials
    # Fall back to cookie (use configurable name from settings)
    else:
        token = request.cookies.get(settings.session_cookie_name)

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is disabled",
        )

    return user


async def get_current_user_optional(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(security)
    ] = None,
) -> User | None:
    """
    Get current user if authenticated, None otherwise.
    Does not raise exceptions for missing/invalid tokens.
    """
    token = None

    if credentials:
        token = credentials.credentials
    else:
        token = request.cookies.get(settings.session_cookie_name)

    if not token:
        return None

    payload = decode_token(token)
    if not payload:
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if user and user.is_active:
        return user
    return None


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user_from_token)],
) -> User:
    """Get current active user (verified and approved)."""
    if not current_user.is_approved:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is pending approval",
        )
    return current_user


async def get_current_premium_user(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    """Get current user with premium or admin role."""
    if current_user.role not in [UserRole.PREMIUM, UserRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Premium subscription required",
        )
    return current_user


async def get_current_admin_user(
    current_user: Annotated[User, Depends(get_current_user_from_token)],
) -> User:
    """Get current admin user."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


# Type aliases for cleaner annotations
CurrentUser = Annotated[User, Depends(get_current_user_from_token)]
CurrentActiveUser = Annotated[User, Depends(get_current_active_user)]
CurrentPremiumUser = Annotated[User, Depends(get_current_premium_user)]
CurrentAdminUser = Annotated[User, Depends(get_current_admin_user)]
OptionalUser = Annotated[User | None, Depends(get_current_user_optional)]
DbSession = Annotated[AsyncSession, Depends(get_db)]


def require_approval(user: User) -> None:
    """
    Check if user is approved. Raises HTTPException if not.
    Use this in routes that require approval.
    """
    if not user.is_approved:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account pending approval",
        )


async def get_pc_from_token(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(security)
    ] = None,
) -> PC:
    """
    Get PC from a PC-bound token.

    Used for SteamSlot and other PC-specific scripts that need
    to authenticate without user interaction.

    Raises:
        HTTPException 401: If token is missing or invalid
        HTTPException 404: If PC not found
        HTTPException 403: If user doesn't own the PC
    """
    token = None

    if credentials:
        token = credentials.credentials

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_pc_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired PC token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    pc_id = payload.get("pc_id")

    if not user_id or not pc_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get PC
    result = await db.execute(select(PC).where(PC.id == pc_id))
    pc = result.scalar_one_or_none()

    if not pc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PC not found",
        )

    # Verify ownership
    if pc.user_id != int(user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    if not pc.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="PC is disabled",
        )

    return pc


# Type alias for PC token auth
CurrentPC = Annotated[PC, Depends(get_pc_from_token)]
