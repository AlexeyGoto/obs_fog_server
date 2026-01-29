"""
File download router for OBS profiles and setup scripts.
"""
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response, StreamingResponse

from app.core.deps import CurrentActiveUser, DbSession
from app.core.security import create_pc_token
from app.services.file_generator import FileGeneratorService
from app.services.stream import StreamService

router = APIRouter(prefix="/downloads", tags=["Downloads"])


@router.get(
    "/obs-profile/{pc_id}",
    summary="Download OBS profile",
)
async def download_obs_profile(
    pc_id: int,
    current_user: CurrentActiveUser,
    db: DbSession,
):
    """
    Download pre-configured OBS Studio profile as ZIP archive.

    Contains:
    - basic.ini: Profile settings
    - service.json: RTMP server configuration
    - README.txt: Setup instructions
    """
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

    file_generator = FileGeneratorService()
    zip_content = file_generator.generate_obs_profile(pc, current_user)

    return StreamingResponse(
        zip_content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="obs_profile_{pc.name}.zip"'
        },
    )


@router.get(
    "/steamslot-script/{pc_id}",
    summary="Download SteamSlot setup script",
)
async def download_steamslot_script(
    pc_id: int,
    current_user: CurrentActiveUser,
    db: DbSession,
):
    """
    Download PowerShell script for Steam Slot setup.

    The script will:
    - Check for existing lease
    - Request new lease if needed
    - Download and extract Steam files
    """
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

    # Generate a long-lived PC-bound token for the script
    pc_token = create_pc_token(current_user.id, pc.id)

    file_generator = FileGeneratorService()
    script_content = file_generator.generate_steamslot_ps1(pc, current_user, pc_token)

    return Response(
        content=script_content,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="steamslot_setup_{pc.name}.ps1"'
        },
    )


@router.get(
    "/obs-installer/{pc_id}",
    summary="Download OBS installer script",
)
async def download_obs_installer(
    pc_id: int,
    current_user: CurrentActiveUser,
    db: DbSession,
):
    """
    Download PowerShell script for complete OBS setup.

    The script will:
    - Install OBS Studio if not present
    - Download and configure the profile
    - Display stream settings
    """
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

    file_generator = FileGeneratorService()
    script_content = file_generator.generate_obs_installer_ps1(pc, current_user)

    return Response(
        content=script_content,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="obs_setup_{pc.name}.ps1"'
        },
    )


@router.get(
    "/stream-config/{pc_id}",
    summary="Get stream configuration",
)
async def get_stream_config(
    pc_id: int,
    current_user: CurrentActiveUser,
    db: DbSession,
) -> dict:
    """
    Get stream configuration as JSON.

    Useful for programmatic setup or custom integrations.
    """
    from app.core.config import settings

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

    return {
        "pc_name": pc.name,
        "rtmp_server": settings.rtmp_url.rsplit("/", 1)[0],
        "stream_key": pc.stream_key,
        "hls_url": f"{settings.app_base_url}/hls/{pc.stream_key}/index.m3u8",
        "encoder_settings": {
            "bitrate": 4500,
            "keyint_sec": 2,
            "preset": "veryfast",
            "profile": "main",
        },
        "video_settings": {
            "base_resolution": "1920x1080",
            "output_resolution": "1920x1080",
            "fps": 30,
        },
    }
