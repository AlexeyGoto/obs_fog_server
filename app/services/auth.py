"""
Authentication service for user registration, login, and token management.
"""
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import ApprovalStatus, User, UserRole
from app.schemas.auth import TokenResponse


class AuthService:
    """Authentication service."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(self, email: str, password: str) -> User:
        """
        Register a new user.

        Args:
            email: User email
            password: Plain text password

        Returns:
            Created user

        Raises:
            ValueError: If email already exists
        """
        # Normalize email to lowercase
        email = email.lower().strip()

        # Check if email exists
        result = await self.db.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none():
            raise ValueError("Email already registered")

        # Create user with 14-day trial
        trial_days = 14
        user = User(
            email=email,
            password_hash=hash_password(password),
            role=UserRole.TRIAL,
            trial_ends_at=datetime.now(timezone.utc) + timedelta(days=trial_days),
            is_approved=not settings.approval_required,
            approval_status=(
                ApprovalStatus.APPROVED
                if not settings.approval_required
                else ApprovalStatus.PENDING
            ),
        )

        if settings.approval_required:
            user.approval_requested_at = datetime.now(timezone.utc)

        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)

        return user

    async def authenticate(self, email: str, password: str) -> User | None:
        """
        Authenticate user with email and password.

        Args:
            email: User email
            password: Plain text password

        Returns:
            User if authenticated, None otherwise
        """
        email = email.lower().strip()
        result = await self.db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            return None

        if not verify_password(password, user.password_hash):
            return None

        if not user.is_active:
            return None

        return user

    def create_tokens(self, user: User) -> TokenResponse:
        """
        Create access and refresh tokens for user.

        Args:
            user: User instance

        Returns:
            TokenResponse with both tokens
        """
        access_token = create_access_token(
            data={"sub": str(user.id)},
            expires_delta=timedelta(minutes=settings.jwt_access_token_expire_minutes),
        )

        refresh_token = create_refresh_token(
            data={"sub": str(user.id)},
            expires_delta=timedelta(days=settings.jwt_refresh_token_expire_days),
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
        )

    async def refresh_tokens(self, refresh_token: str) -> TokenResponse | None:
        """
        Refresh access token using refresh token.

        Args:
            refresh_token: Valid refresh token

        Returns:
            New TokenResponse or None if invalid
        """
        payload = decode_token(refresh_token)
        if not payload:
            return None

        if payload.get("type") != "refresh":
            return None

        user_id = payload.get("sub")
        if not user_id:
            return None

        result = await self.db.execute(select(User).where(User.id == int(user_id)))
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            return None

        return self.create_tokens(user)

    async def change_password(
        self,
        user: User,
        current_password: str,
        new_password: str,
    ) -> bool:
        """
        Change user password.

        Args:
            user: User instance
            current_password: Current password for verification
            new_password: New password

        Returns:
            True if password changed, False if current password invalid
        """
        if not verify_password(current_password, user.password_hash):
            return False

        user.password_hash = hash_password(new_password)
        await self.db.commit()

        return True

    async def get_user_by_email(self, email: str) -> User | None:
        """Get user by email."""
        email = email.lower().strip()
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: int) -> User | None:
        """Get user by ID."""
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()
