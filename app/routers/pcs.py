"""
PC and streaming session management router.
"""
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.deps import CurrentActiveUser, DbSession
from app.schemas.common import MessageResponse
from app.schemas.pc import (
    PCCreate,
    PCDetailResponse,
    PCListResponse,
    PCResponse,
    PCUpdate,
    StreamSessionDetailResponse,
    StreamSessionListResponse,
    StreamSessionResponse,
)
from app.services.stream import StreamService

router = APIRouter(prefix="/pcs", tags=["PCs"])


@router.post(
    "",
    response_model=PCResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create new PC",
)
async def create_pc(
    data: PCCreate,
    current_user: CurrentActiveUser,
    db: DbSession,
) -> PCResponse:
    """Create a new PC for streaming."""
    stream_service = StreamService(db)
    try:
        pc = await stream_service.create_pc(current_user, data.name)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    return PCResponse.model_validate(pc)


@router.get(
    "",
    response_model=PCListResponse,
    summary="List user's PCs",
)
async def list_pcs(
    current_user: CurrentActiveUser,
    db: DbSession,
) -> PCListResponse:
    """Get all PCs for the current user."""
    stream_service = StreamService(db)
    pcs = await stream_service.list_user_pcs(current_user.id)

    # Check which PCs have active sessions
    items = []
    for pc in pcs:
        active_session = await stream_service.get_active_session(pc.id)
        pc_response = PCResponse(
            id=pc.id,
            user_id=pc.user_id,
            name=pc.name,
            stream_key=pc.stream_key,
            is_active=pc.is_active,
            is_live=active_session is not None,
            created_at=pc.created_at,
        )
        items.append(pc_response)

    return PCListResponse(items=items, total=len(pcs))


@router.get(
    "/{pc_id}",
    response_model=PCDetailResponse,
    summary="Get PC details",
)
async def get_pc(
    pc_id: int,
    current_user: CurrentActiveUser,
    db: DbSession,
) -> PCDetailResponse:
    """Get PC details with stream URLs."""
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

    # Count sessions and check if live
    sessions, total = await stream_service.list_pc_sessions(pc_id, per_page=1)
    active_session = await stream_service.get_active_session(pc_id)

    return PCDetailResponse(
        id=pc.id,
        user_id=pc.user_id,
        name=pc.name,
        stream_key=pc.stream_key,
        is_active=pc.is_active,
        is_live=active_session is not None,
        created_at=pc.created_at,
        rtmp_url=f"{settings.rtmp_url}/{pc.stream_key}",
        hls_url=f"{settings.app_base_url}/hls/{pc.stream_key}/index.m3u8",
        sessions_count=total,
    )


@router.patch(
    "/{pc_id}",
    response_model=PCResponse,
    summary="Update PC",
)
async def update_pc(
    pc_id: int,
    data: PCUpdate,
    current_user: CurrentActiveUser,
    db: DbSession,
) -> PCResponse:
    """Update PC settings."""
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

    pc = await stream_service.update_pc(pc, name=data.name, is_active=data.is_active)
    return PCResponse.model_validate(pc)


@router.post(
    "/{pc_id}/regenerate-key",
    response_model=PCResponse,
    summary="Regenerate stream key",
)
async def regenerate_stream_key(
    pc_id: int,
    current_user: CurrentActiveUser,
    db: DbSession,
) -> PCResponse:
    """Generate a new stream key for the PC."""
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

    pc = await stream_service.regenerate_stream_key(pc)
    return PCResponse.model_validate(pc)


@router.delete(
    "/{pc_id}",
    response_model=MessageResponse,
    summary="Delete PC",
)
async def delete_pc(
    pc_id: int,
    current_user: CurrentActiveUser,
    db: DbSession,
) -> MessageResponse:
    """Delete a PC and all its sessions."""
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

    await stream_service.delete_pc(pc)
    return MessageResponse(message="PC deleted")


# Session endpoints


@router.get(
    "/{pc_id}/sessions",
    response_model=StreamSessionListResponse,
    summary="List PC sessions",
)
async def list_sessions(
    pc_id: int,
    current_user: CurrentActiveUser,
    db: DbSession,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
) -> StreamSessionListResponse:
    """List streaming sessions for a PC."""
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

    sessions, total = await stream_service.list_pc_sessions(
        pc_id, page=page, per_page=per_page
    )

    return StreamSessionListResponse(
        items=[StreamSessionResponse.model_validate(s) for s in sessions],
        total=total,
    )


@router.get(
    "/{pc_id}/sessions/{session_id}",
    response_model=StreamSessionDetailResponse,
    summary="Get session details",
)
async def get_session(
    pc_id: int,
    session_id: int,
    current_user: CurrentActiveUser,
    db: DbSession,
) -> StreamSessionDetailResponse:
    """Get details of a specific streaming session."""
    stream_service = StreamService(db)
    session = await stream_service.get_session_by_id(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    if session.pc_id != pc_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    if session.pc.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    response = StreamSessionDetailResponse(
        id=session.id,
        pc_id=session.pc_id,
        started_at=session.started_at,
        ended_at=session.ended_at,
        status=session.status,
        note=session.note,
        created_at=session.created_at,
    )

    if session.clip_job:
        response.clip_status = session.clip_job.status
        response.clip_path = session.clip_job.result_path
        response.clip_size_bytes = session.clip_job.size_bytes
        response.clip_error = session.clip_job.error

    return response


@router.get(
    "/{pc_id}/sessions/{session_id}/clip",
    summary="Download session clip",
)
async def download_clip(
    pc_id: int,
    session_id: int,
    current_user: CurrentActiveUser,
    db: DbSession,
):
    """Download the MP4 clip for a session."""
    stream_service = StreamService(db)
    session = await stream_service.get_session_by_id(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    if session.pc_id != pc_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    if session.pc.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    if not session.clip_job or not session.clip_job.result_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clip not available",
        )

    import os

    if not os.path.exists(session.clip_job.result_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clip file not found",
        )

    return FileResponse(
        session.clip_job.result_path,
        media_type="video/mp4",
        filename=f"clip_session_{session_id}.mp4",
    )
