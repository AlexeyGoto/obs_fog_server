"""
SteamSlot router for account and lease management.
"""
from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response

from app.core.deps import CurrentActiveUser, CurrentAdminUser, CurrentPC, DbSession
from app.models.steamslot import LeaseStatus
from app.schemas.common import MessageResponse
from app.schemas.steamslot import (
    FileUploadResponse,
    SteamAccountCreate,
    SteamAccountListResponse,
    SteamAccountResponse,
    SteamAccountUpdate,
    SteamLeaseCreate,
    SteamLeaseListResponse,
    SteamLeaseResponse,
)
from app.services.steamslot import SteamSlotService
from app.services.stream import StreamService

router = APIRouter(prefix="/steamslot", tags=["SteamSlot"])


# Account Management (Admin only)


@router.post(
    "/accounts",
    response_model=SteamAccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Steam account (admin)",
)
async def create_account(
    data: SteamAccountCreate,
    admin: CurrentAdminUser,
    db: DbSession,
) -> SteamAccountResponse:
    """Create a new Steam account for slot assignment."""
    service = SteamSlotService(db)

    # Check if name exists
    existing = await service.get_account_by_name(data.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account name already exists",
        )

    account = await service.create_account(
        name=data.name,
        max_slots=data.max_slots,
        notes=data.notes,
    )

    return SteamAccountResponse(
        id=account.id,
        name=account.name,
        max_slots=account.max_slots,
        enabled=account.enabled,
        has_file=account.file_data is not None,
        file_name=account.file_name,
        file_encrypted=account.file_encrypted,
        file_updated_at=account.file_updated_at,
        active_lease_count=account.active_lease_count,
        available_slots=account.available_slots,
        notes=account.notes,
        created_at=account.created_at,
    )


@router.get(
    "/accounts",
    response_model=SteamAccountListResponse,
    summary="List Steam accounts (admin)",
)
async def list_accounts(
    admin: CurrentAdminUser,
    db: DbSession,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    enabled_only: bool = False,
) -> SteamAccountListResponse:
    """List all Steam accounts."""
    service = SteamSlotService(db)
    accounts, total = await service.list_accounts(
        enabled_only=enabled_only,
        page=page,
        per_page=per_page,
    )

    items = []
    for account in accounts:
        items.append(
            SteamAccountResponse(
                id=account.id,
                name=account.name,
                max_slots=account.max_slots,
                enabled=account.enabled,
                has_file=account.file_data is not None,
                file_name=account.file_name,
                file_encrypted=account.file_encrypted,
                file_updated_at=account.file_updated_at,
                active_lease_count=account.active_lease_count,
                available_slots=account.available_slots,
                notes=account.notes,
                created_at=account.created_at,
            )
        )

    return SteamAccountListResponse(items=items, total=total)


@router.get(
    "/accounts/{account_id}",
    response_model=SteamAccountResponse,
    summary="Get Steam account (admin)",
)
async def get_account(
    account_id: int,
    admin: CurrentAdminUser,
    db: DbSession,
) -> SteamAccountResponse:
    """Get Steam account details."""
    service = SteamSlotService(db)
    account = await service.get_account_by_id(account_id)

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    return SteamAccountResponse(
        id=account.id,
        name=account.name,
        max_slots=account.max_slots,
        enabled=account.enabled,
        has_file=account.file_data is not None,
        file_name=account.file_name,
        file_encrypted=account.file_encrypted,
        file_updated_at=account.file_updated_at,
        active_lease_count=account.active_lease_count,
        available_slots=account.available_slots,
        notes=account.notes,
        created_at=account.created_at,
    )


@router.patch(
    "/accounts/{account_id}",
    response_model=SteamAccountResponse,
    summary="Update Steam account (admin)",
)
async def update_account(
    account_id: int,
    data: SteamAccountUpdate,
    admin: CurrentAdminUser,
    db: DbSession,
) -> SteamAccountResponse:
    """Update Steam account settings."""
    service = SteamSlotService(db)
    account = await service.get_account_by_id(account_id)

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    account = await service.update_account(
        account,
        name=data.name,
        max_slots=data.max_slots,
        enabled=data.enabled,
        notes=data.notes,
    )

    return SteamAccountResponse(
        id=account.id,
        name=account.name,
        max_slots=account.max_slots,
        enabled=account.enabled,
        has_file=account.file_data is not None,
        file_name=account.file_name,
        file_encrypted=account.file_encrypted,
        file_updated_at=account.file_updated_at,
        active_lease_count=account.active_lease_count,
        available_slots=account.available_slots,
        notes=account.notes,
        created_at=account.created_at,
    )


@router.delete(
    "/accounts/{account_id}",
    response_model=MessageResponse,
    summary="Delete Steam account (admin)",
)
async def delete_account(
    account_id: int,
    admin: CurrentAdminUser,
    db: DbSession,
) -> MessageResponse:
    """Delete a Steam account and all its leases."""
    service = SteamSlotService(db)
    account = await service.get_account_by_id(account_id)

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    await service.delete_account(account)
    return MessageResponse(message="Account deleted")


@router.post(
    "/accounts/{account_id}/upload",
    response_model=FileUploadResponse,
    summary="Upload account file (admin)",
)
async def upload_file(
    account_id: int,
    admin: CurrentAdminUser,
    db: DbSession,
    file: UploadFile = File(...),
    encrypt: bool = True,
) -> FileUploadResponse:
    """Upload and encrypt a file for the Steam account."""
    service = SteamSlotService(db)
    account = await service.get_account_by_id(account_id)

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    # Read file content
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large (max 10MB)",
        )

    account = await service.upload_file(
        account,
        file_name=file.filename or "unknown",
        file_data=content,
        content_type=file.content_type or "application/octet-stream",
        encrypt=encrypt,
    )

    return FileUploadResponse(
        success=True,
        file_name=account.file_name or "",
        file_size=len(content),
        sha256=account.file_sha256 or "",
        encrypted=account.file_encrypted,
    )


# Lease Management


@router.post(
    "/leases",
    response_model=SteamLeaseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create lease",
)
async def create_lease(
    data: SteamLeaseCreate,
    current_user: CurrentActiveUser,
    db: DbSession,
) -> SteamLeaseResponse:
    """Create a new lease for a PC."""
    # Check SteamSlot access
    if not current_user.can_use_steamslot:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SteamSlot requires Premium subscription",
        )

    # Verify PC ownership
    stream_service = StreamService(db)
    pc = await stream_service.get_pc_by_id(data.pc_id)

    if not pc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PC not found",
        )

    if pc.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    # Get account
    service = SteamSlotService(db)
    account = await service.get_account_by_id(data.account_id)

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )

    if not account.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account is disabled",
        )

    # Check for existing lease
    existing = await service.get_active_lease_for_pc(data.pc_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PC already has an active lease",
        )

    try:
        lease = await service.create_lease(
            account,
            data.pc_id,
            data.duration_hours,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return SteamLeaseResponse(
        id=lease.id,
        account_id=lease.account_id,
        account_name=account.name,
        pc_id=lease.pc_id,
        pc_name=pc.name,
        token=lease.token,
        status=lease.status,
        expires_at=lease.expires_at,
        released_at=lease.released_at,
        message=lease.message,
        created_at=lease.created_at,
    )


@router.get(
    "/leases/active",
    response_model=SteamLeaseResponse | None,
    summary="Get active lease for PC",
)
async def get_active_lease(
    current_user: CurrentActiveUser,
    db: DbSession,
    pc_id: int = Query(...),
) -> SteamLeaseResponse | None:
    """Get active lease for a specific PC."""
    # Verify PC ownership
    stream_service = StreamService(db)
    pc = await stream_service.get_pc_by_id(pc_id)

    if not pc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PC not found",
        )

    if pc.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    service = SteamSlotService(db)
    lease = await service.get_active_lease_for_pc(pc_id)

    if not lease:
        return None

    return SteamLeaseResponse(
        id=lease.id,
        account_id=lease.account_id,
        account_name=lease.account.name,
        pc_id=lease.pc_id,
        pc_name=pc.name,
        token=lease.token,
        status=lease.status,
        expires_at=lease.expires_at,
        released_at=lease.released_at,
        message=lease.message,
        created_at=lease.created_at,
    )


@router.get(
    "/leases",
    response_model=SteamLeaseListResponse,
    summary="List leases (admin)",
)
async def list_leases(
    admin: CurrentAdminUser,
    db: DbSession,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    account_id: int | None = None,
    pc_id: int | None = None,
    status: LeaseStatus | None = None,
) -> SteamLeaseListResponse:
    """List all leases with filters."""
    service = SteamSlotService(db)
    leases, total = await service.list_leases(
        account_id=account_id,
        pc_id=pc_id,
        status=status,
        page=page,
        per_page=per_page,
    )

    items = []
    for lease in leases:
        items.append(
            SteamLeaseResponse(
                id=lease.id,
                account_id=lease.account_id,
                account_name=lease.account.name if lease.account else "Unknown",
                pc_id=lease.pc_id,
                pc_name=lease.pc.name if lease.pc else "Unknown",
                token=lease.token,
                status=lease.status,
                expires_at=lease.expires_at,
                released_at=lease.released_at,
                message=lease.message,
                created_at=lease.created_at,
            )
        )

    return SteamLeaseListResponse(items=items, total=total)


@router.post(
    "/leases/{lease_id}/release",
    response_model=SteamLeaseResponse,
    summary="Release lease",
)
async def release_lease(
    lease_id: int,
    current_user: CurrentActiveUser,
    db: DbSession,
    message: str | None = None,
) -> SteamLeaseResponse:
    """Release an active lease."""
    service = SteamSlotService(db)
    lease = await service.get_lease_by_id(lease_id)

    if not lease:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lease not found",
        )

    # Verify ownership (unless admin)
    if lease.pc.user_id != current_user.id and current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    if lease.status != LeaseStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lease is not active",
        )

    lease = await service.release_lease(lease, message)

    return SteamLeaseResponse(
        id=lease.id,
        account_id=lease.account_id,
        account_name=lease.account.name if lease.account else "Unknown",
        pc_id=lease.pc_id,
        pc_name=lease.pc.name if lease.pc else "Unknown",
        token=lease.token,
        status=lease.status,
        expires_at=lease.expires_at,
        released_at=lease.released_at,
        message=lease.message,
        created_at=lease.created_at,
    )


@router.get(
    "/leases/download",
    summary="Download Steam files for lease",
)
async def download_lease_files(
    db: DbSession,
    token: str = Query(...),
):
    """Download Steam files using lease token."""
    service = SteamSlotService(db)
    lease = await service.get_lease_by_token(token)

    if not lease:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid token",
        )

    if lease.status != LeaseStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lease is not active",
        )

    # Get file from account
    result = await service.download_file(lease.account)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No file available",
        )

    data, filename, content_type = result

    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/available-accounts",
    response_model=list[SteamAccountResponse],
    summary="List available accounts",
)
async def list_available_accounts(
    current_user: CurrentActiveUser,
    db: DbSession,
) -> list[SteamAccountResponse]:
    """List accounts with available slots for leasing."""
    # Check SteamSlot access
    if not current_user.can_use_steamslot:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SteamSlot requires Premium subscription",
        )

    service = SteamSlotService(db)
    accounts, _ = await service.list_accounts(enabled_only=True, per_page=100)

    available = []
    for account in accounts:
        if account.available_slots > 0:
            available.append(
                SteamAccountResponse(
                    id=account.id,
                    name=account.name,
                    max_slots=account.max_slots,
                    enabled=account.enabled,
                    has_file=account.file_data is not None,
                    file_name=account.file_name,
                    file_encrypted=account.file_encrypted,
                    file_updated_at=account.file_updated_at,
                    active_lease_count=account.active_lease_count,
                    available_slots=account.available_slots,
                    notes=None,  # Don't expose notes to non-admins
                    created_at=account.created_at,
                )
            )

    return available


# Script-friendly endpoints using PC tokens
# These endpoints use PC-bound tokens instead of user authentication
# for PowerShell scripts that need to authenticate without user interaction


@router.get(
    "/script/active-lease",
    response_model=SteamLeaseResponse | None,
    summary="Get active lease for PC (script auth)",
)
async def script_get_active_lease(
    pc: CurrentPC,
    db: DbSession,
) -> SteamLeaseResponse | None:
    """
    Get active lease for the PC using PC-bound token.
    Used by PowerShell scripts.
    """
    service = SteamSlotService(db)
    lease = await service.get_active_lease_for_pc(pc.id)

    if not lease:
        return None

    return SteamLeaseResponse(
        id=lease.id,
        account_id=lease.account_id,
        account_name=lease.account.name if lease.account else "Unknown",
        pc_id=lease.pc_id,
        pc_name=pc.name,
        token=lease.token,
        status=lease.status,
        expires_at=lease.expires_at,
        released_at=lease.released_at,
        message=lease.message,
        created_at=lease.created_at,
    )


@router.post(
    "/script/lease",
    response_model=SteamLeaseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create lease (script auth)",
)
async def script_create_lease(
    pc: CurrentPC,
    db: DbSession,
    duration_hours: int = Query(24, ge=1, le=168),
) -> SteamLeaseResponse:
    """
    Create a new lease for the PC using PC-bound token.
    Automatically selects an available account.
    Used by PowerShell scripts.
    """
    # Check SteamSlot access (PC owner must have Premium)
    if not pc.user.can_use_steamslot:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SteamSlot requires Premium subscription",
        )

    service = SteamSlotService(db)

    # Check for existing lease
    existing = await service.get_active_lease_for_pc(pc.id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PC already has an active lease",
        )

    # Find available account
    accounts, _ = await service.list_accounts(enabled_only=True, per_page=100)
    available_account = None
    for account in accounts:
        if account.available_slots > 0 and account.file_data is not None:
            available_account = account
            break

    if not available_account:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No available Steam accounts",
        )

    try:
        lease = await service.create_lease(
            available_account,
            pc.id,
            duration_hours,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return SteamLeaseResponse(
        id=lease.id,
        account_id=lease.account_id,
        account_name=available_account.name,
        pc_id=lease.pc_id,
        pc_name=pc.name,
        token=lease.token,
        status=lease.status,
        expires_at=lease.expires_at,
        released_at=lease.released_at,
        message=lease.message,
        created_at=lease.created_at,
    )
