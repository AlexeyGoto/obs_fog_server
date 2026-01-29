"""
Authentication router: login, register, password change, token refresh.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession
from app.core.rate_limit import limiter, RATE_LIMIT_AUTH
from app.schemas.auth import (
    LoginRequest,
    PasswordChangeRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.common import MessageResponse
from app.schemas.user import UserResponse
from app.services.auth import AuthService
from app.services.telegram import TelegramService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new user",
)
@limiter.limit(RATE_LIMIT_AUTH)
async def register(
    request: Request,
    data: RegisterRequest,
    db: DbSession,
) -> UserResponse:
    """
    Register a new user account.

    - Email must be unique
    - Password must be at least 8 characters
    - If approval is required, account will be pending until admin approves
    """
    if not data.passwords_match():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match",
        )

    auth_service = AuthService(db)

    try:
        user = await auth_service.register(data.email, data.password)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # Send approval request to admin if required
    if settings.approval_required and settings.telegram_admin_id:
        telegram = TelegramService()
        await telegram.send_approval_request(
            settings.telegram_admin_id,
            user.email,
            user.id,
        )

    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and get tokens",
)
@limiter.limit(RATE_LIMIT_AUTH)
async def login(
    request: Request,
    data: LoginRequest,
    response: Response,
    db: DbSession,
) -> TokenResponse:
    """
    Authenticate user and return JWT tokens.

    - Returns access_token (short-lived) and refresh_token (long-lived)
    - Also sets session cookie for web interface
    """
    auth_service = AuthService(db)
    user = await auth_service.authenticate(data.email, data.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    tokens = auth_service.create_tokens(user)

    # Set session cookie
    response.set_cookie(
        key=settings.session_cookie_name,
        value=tokens.access_token,
        max_age=settings.jwt_access_token_expire_minutes * 60,
        httponly=True,
        secure=settings.session_secure,
        samesite="lax",
    )

    return tokens


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Logout user",
)
async def logout(response: Response) -> MessageResponse:
    """
    Logout user by clearing session cookie.
    """
    response.delete_cookie(
        key=settings.session_cookie_name,
        httponly=True,
        secure=settings.session_secure,
        samesite="lax",
    )
    return MessageResponse(message="Logged out successfully")


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token",
)
async def refresh_token(
    data: RefreshTokenRequest,
    response: Response,
    db: DbSession,
) -> TokenResponse:
    """
    Get new access token using refresh token.
    """
    auth_service = AuthService(db)
    tokens = await auth_service.refresh_tokens(data.refresh_token)

    if not tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    # Update session cookie
    response.set_cookie(
        key=settings.session_cookie_name,
        value=tokens.access_token,
        max_age=settings.jwt_access_token_expire_minutes * 60,
        httponly=True,
        secure=settings.session_secure,
        samesite="lax",
    )

    return tokens


@router.post(
    "/password",
    response_model=MessageResponse,
    summary="Change password",
)
async def change_password(
    data: PasswordChangeRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> MessageResponse:
    """
    Change current user's password.

    - Requires current password for verification
    - New password must be at least 8 characters
    """
    if not data.passwords_match():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New passwords do not match",
        )

    auth_service = AuthService(db)
    success = await auth_service.change_password(
        current_user,
        data.current_password,
        data.new_password,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    return MessageResponse(message="Password changed successfully")


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user",
)
async def get_me(current_user: CurrentUser) -> UserResponse:
    """
    Get current authenticated user's profile.
    """
    return UserResponse.model_validate(current_user)
