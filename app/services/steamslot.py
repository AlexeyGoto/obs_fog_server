"""
SteamSlot service for account and lease management.
"""
import hashlib
import secrets
from datetime import datetime, timezone, timedelta

from cryptography.fernet import Fernet
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.security import generate_api_key
from app.models.steamslot import LeaseStatus, SteamAccount, SteamLease


class SteamSlotService:
    """Service for Steam account and lease management."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._fernet: Fernet | None = None

    @property
    def fernet(self) -> Fernet | None:
        """Get Fernet instance for encryption."""
        if self._fernet is None and settings.file_encryption_key:
            try:
                self._fernet = Fernet(settings.file_encryption_key.encode())
            except Exception:
                pass
        return self._fernet

    # Account Management

    async def create_account(
        self,
        name: str,
        max_slots: int = 1,
        notes: str | None = None,
    ) -> SteamAccount:
        """Create a new Steam account."""
        account = SteamAccount(
            name=name,
            max_slots=max_slots,
            notes=notes,
        )
        self.db.add(account)
        await self.db.commit()
        await self.db.refresh(account)
        return account

    async def get_account_by_id(self, account_id: int) -> SteamAccount | None:
        """Get account by ID."""
        result = await self.db.execute(
            select(SteamAccount)
            .options(selectinload(SteamAccount.leases))
            .where(SteamAccount.id == account_id)
        )
        return result.scalar_one_or_none()

    async def get_account_by_name(self, name: str) -> SteamAccount | None:
        """Get account by name."""
        result = await self.db.execute(
            select(SteamAccount).where(SteamAccount.name == name)
        )
        return result.scalar_one_or_none()

    async def list_accounts(
        self,
        enabled_only: bool = False,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[SteamAccount], int]:
        """List all accounts with pagination."""
        query = select(SteamAccount).options(selectinload(SteamAccount.leases))

        if enabled_only:
            query = query.where(SteamAccount.enabled == True)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_query)).scalar() or 0

        # Get paginated results
        offset = (page - 1) * per_page
        query = query.order_by(SteamAccount.name).offset(offset).limit(per_page)
        result = await self.db.execute(query)

        return list(result.scalars().all()), total

    async def update_account(
        self,
        account: SteamAccount,
        name: str | None = None,
        max_slots: int | None = None,
        enabled: bool | None = None,
        notes: str | None = None,
    ) -> SteamAccount:
        """Update account settings."""
        if name is not None:
            account.name = name
        if max_slots is not None:
            account.max_slots = max_slots
        if enabled is not None:
            account.enabled = enabled
        if notes is not None:
            account.notes = notes

        await self.db.commit()
        await self.db.refresh(account)
        return account

    async def delete_account(self, account: SteamAccount) -> None:
        """Delete an account."""
        await self.db.delete(account)
        await self.db.commit()

    async def upload_file(
        self,
        account: SteamAccount,
        file_name: str,
        file_data: bytes,
        content_type: str,
        encrypt: bool = True,
    ) -> SteamAccount:
        """
        Upload and optionally encrypt a file for the account.

        Args:
            account: Target account
            file_name: Original filename
            file_data: Raw file bytes
            content_type: MIME type
            encrypt: Whether to encrypt (default True)
        """
        # Calculate hash of original data
        sha256 = hashlib.sha256(file_data).hexdigest()

        # Encrypt if requested and key is available
        if encrypt and self.fernet:
            file_data = self.fernet.encrypt(file_data)
            encrypted = True
        else:
            encrypted = False

        account.file_name = file_name
        account.file_data = file_data
        account.file_content_type = content_type
        account.file_sha256 = sha256
        account.file_encrypted = encrypted
        account.file_updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(account)
        return account

    async def download_file(
        self,
        account: SteamAccount,
    ) -> tuple[bytes, str, str] | None:
        """
        Download and decrypt file from account.

        Returns:
            Tuple of (data, filename, content_type) or None
        """
        if not account.file_data:
            return None

        data = account.file_data

        # Decrypt if encrypted
        if account.file_encrypted and self.fernet:
            try:
                data = self.fernet.decrypt(data)
            except Exception:
                return None

        return (
            data,
            account.file_name or "unknown",
            account.file_content_type or "application/octet-stream",
        )

    # Lease Management

    async def create_lease(
        self,
        account: SteamAccount,
        pc_id: int,
        duration_hours: int = 24,
    ) -> SteamLease:
        """
        Create a new lease for a PC.

        Args:
            account: Steam account to lease
            pc_id: Target PC ID
            duration_hours: Lease duration

        Raises:
            ValueError: If no slots available
        """
        if account.available_slots <= 0:
            raise ValueError("No available slots for this account")

        lease = SteamLease(
            account_id=account.id,
            pc_id=pc_id,
            token=generate_api_key(32),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=duration_hours),
            status=LeaseStatus.ACTIVE,
        )
        self.db.add(lease)
        await self.db.commit()
        await self.db.refresh(lease)
        return lease

    async def get_lease_by_id(self, lease_id: int) -> SteamLease | None:
        """Get lease by ID."""
        result = await self.db.execute(
            select(SteamLease)
            .options(selectinload(SteamLease.account))
            .options(selectinload(SteamLease.pc))
            .where(SteamLease.id == lease_id)
        )
        return result.scalar_one_or_none()

    async def get_lease_by_token(self, token: str) -> SteamLease | None:
        """Get lease by token."""
        result = await self.db.execute(
            select(SteamLease)
            .options(selectinload(SteamLease.account))
            .options(selectinload(SteamLease.pc))
            .where(SteamLease.token == token)
        )
        return result.scalar_one_or_none()

    async def get_active_lease_for_pc(self, pc_id: int) -> SteamLease | None:
        """Get active lease for a PC."""
        result = await self.db.execute(
            select(SteamLease)
            .options(selectinload(SteamLease.account))
            .where(SteamLease.pc_id == pc_id)
            .where(SteamLease.status == LeaseStatus.ACTIVE)
            .where(SteamLease.expires_at > datetime.now(timezone.utc))
        )
        return result.scalar_one_or_none()

    async def list_leases(
        self,
        account_id: int | None = None,
        pc_id: int | None = None,
        status: LeaseStatus | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[SteamLease], int]:
        """List leases with filters and pagination."""
        query = (
            select(SteamLease)
            .options(selectinload(SteamLease.account))
            .options(selectinload(SteamLease.pc))
        )

        if account_id:
            query = query.where(SteamLease.account_id == account_id)
        if pc_id:
            query = query.where(SteamLease.pc_id == pc_id)
        if status:
            query = query.where(SteamLease.status == status)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_query)).scalar() or 0

        # Get paginated results
        offset = (page - 1) * per_page
        query = query.order_by(SteamLease.created_at.desc()).offset(offset).limit(per_page)
        result = await self.db.execute(query)

        return list(result.scalars().all()), total

    async def release_lease(
        self,
        lease: SteamLease,
        message: str | None = None,
    ) -> SteamLease:
        """Release an active lease."""
        lease.status = LeaseStatus.RELEASED
        lease.released_at = datetime.now(timezone.utc)
        if message:
            lease.message = message

        await self.db.commit()
        await self.db.refresh(lease)
        return lease

    async def expire_old_leases(self) -> int:
        """Mark expired leases. Returns count of expired leases."""
        result = await self.db.execute(
            select(SteamLease)
            .where(SteamLease.status == LeaseStatus.ACTIVE)
            .where(SteamLease.expires_at <= datetime.now(timezone.utc))
        )
        leases = result.scalars().all()

        for lease in leases:
            lease.status = LeaseStatus.EXPIRED

        await self.db.commit()
        return len(leases)

    async def get_available_account(self) -> SteamAccount | None:
        """Get first available account with free slots."""
        accounts, _ = await self.list_accounts(enabled_only=True, per_page=100)

        for account in accounts:
            if account.available_slots > 0:
                return account

        return None
