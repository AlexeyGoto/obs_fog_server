"""
User service for profile management and admin operations.
"""
from datetime import datetime, timezone, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import ApprovalStatus, User, UserRole


class UserService:
    """User management service."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, user_id: int) -> User | None:
        """Get user by ID."""
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """Get user by email."""
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_telegram_id(self, tg_chat_id: int) -> User | None:
        """Get user by Telegram chat ID."""
        result = await self.db.execute(
            select(User).where(User.tg_chat_id == tg_chat_id)
        )
        return result.scalar_one_or_none()

    async def list_users(
        self,
        page: int = 1,
        per_page: int = 20,
        role: UserRole | None = None,
        approval_status: ApprovalStatus | None = None,
    ) -> tuple[list[User], int]:
        """
        List users with pagination and filters.

        Returns:
            Tuple of (users list, total count)
        """
        query = select(User)

        if role:
            query = query.where(User.role == role)
        if approval_status:
            query = query.where(User.approval_status == approval_status)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_query)).scalar() or 0

        # Get paginated results
        offset = (page - 1) * per_page
        query = query.order_by(User.created_at.desc()).offset(offset).limit(per_page)
        result = await self.db.execute(query)

        return list(result.scalars().all()), total

    async def list_pending_approval(self) -> list[User]:
        """Get users pending approval."""
        result = await self.db.execute(
            select(User)
            .where(User.approval_status == ApprovalStatus.PENDING)
            .order_by(User.approval_requested_at.asc())
        )
        return list(result.scalars().all())

    async def approve_user(
        self,
        user: User,
        admin_id: int,
        note: str | None = None,
    ) -> User:
        """Approve a user."""
        user.is_approved = True
        user.approval_status = ApprovalStatus.APPROVED
        user.approval_decided_at = datetime.now(timezone.utc)
        user.approval_decided_by = admin_id
        user.approval_note = note

        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def deny_user(
        self,
        user: User,
        admin_id: int,
        note: str | None = None,
    ) -> User:
        """Deny a user."""
        user.is_approved = False
        user.approval_status = ApprovalStatus.DENIED
        user.approval_decided_at = datetime.now(timezone.utc)
        user.approval_decided_by = admin_id
        user.approval_note = note

        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def link_telegram(self, user: User, tg_chat_id: int) -> User:
        """Link Telegram account to user."""
        user.tg_chat_id = tg_chat_id
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def unlink_telegram(self, user: User) -> User:
        """Unlink Telegram account from user."""
        user.tg_chat_id = None
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def set_role(self, user: User, role: UserRole) -> User:
        """Set user role."""
        user.role = role
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def grant_premium(self, user: User, days: int = 30) -> User:
        """Grant premium subscription."""
        user.role = UserRole.PREMIUM

        if user.premium_until and user.premium_until > datetime.now(timezone.utc):
            # Extend existing subscription
            user.premium_until = user.premium_until + timedelta(days=days)
        else:
            # New subscription
            user.premium_until = datetime.now(timezone.utc) + timedelta(days=days)

        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def revoke_premium(self, user: User) -> User:
        """Revoke premium subscription."""
        user.role = UserRole.USER
        user.premium_until = None
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def deactivate_user(self, user: User) -> User:
        """Deactivate user account."""
        user.is_active = False
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def activate_user(self, user: User) -> User:
        """Activate user account."""
        user.is_active = True
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def update_email(self, user: User, new_email: str) -> User:
        """Update user email."""
        # Check if email is taken
        existing = await self.get_by_email(new_email)
        if existing and existing.id != user.id:
            raise ValueError("Email already taken")

        user.email = new_email
        await self.db.commit()
        await self.db.refresh(user)
        return user
