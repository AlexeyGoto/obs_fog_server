"""
Streaming service for PC and session management.
"""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import generate_stream_key
from app.models.pc import PC, ClipJob, ClipStatus, SessionStatus, StreamSession
from app.models.user import User


class StreamService:
    """Streaming and PC management service."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # PC Management

    async def create_pc(self, user: User, name: str) -> PC:
        """Create a new PC for streaming."""
        # Check trial expiration
        if user.is_trial_expired:
            raise ValueError("Trial period expired. Please upgrade to continue.")

        # Check PC limit
        current_pc_count = await self.get_user_pc_count(user.id)
        if current_pc_count >= user.max_pcs:
            raise ValueError(f"PC limit reached ({user.max_pcs}). Upgrade to add more.")

        pc = PC(
            user_id=user.id,
            name=name,
            stream_key=generate_stream_key(),
        )
        self.db.add(pc)
        await self.db.commit()
        await self.db.refresh(pc)
        return pc

    async def get_user_pc_count(self, user_id: int) -> int:
        """Get count of PCs for a user."""
        result = await self.db.execute(
            select(func.count()).where(PC.user_id == user_id)
        )
        return result.scalar() or 0

    async def get_pc_by_id(self, pc_id: int) -> PC | None:
        """Get PC by ID."""
        result = await self.db.execute(
            select(PC).options(selectinload(PC.user)).where(PC.id == pc_id)
        )
        return result.scalar_one_or_none()

    async def get_pc_by_stream_key(self, stream_key: str) -> PC | None:
        """Get PC by stream key."""
        result = await self.db.execute(
            select(PC)
            .options(selectinload(PC.user))
            .where(PC.stream_key == stream_key)
        )
        return result.scalar_one_or_none()

    async def list_user_pcs(self, user_id: int) -> list[PC]:
        """List all PCs for a user."""
        result = await self.db.execute(
            select(PC).where(PC.user_id == user_id).order_by(PC.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_pc(
        self,
        pc: PC,
        name: str | None = None,
        is_active: bool | None = None,
    ) -> PC:
        """Update PC settings."""
        if name is not None:
            pc.name = name
        if is_active is not None:
            pc.is_active = is_active

        await self.db.commit()
        await self.db.refresh(pc)
        return pc

    async def regenerate_stream_key(self, pc: PC) -> PC:
        """Generate a new stream key for PC."""
        pc.stream_key = generate_stream_key()
        await self.db.commit()
        await self.db.refresh(pc)
        return pc

    async def delete_pc(self, pc: PC) -> None:
        """Delete a PC and all related data."""
        await self.db.delete(pc)
        await self.db.commit()

    # Stream Sessions

    async def start_session(self, pc: PC) -> StreamSession:
        """Start a new streaming session."""
        session = StreamSession(
            pc_id=pc.id,
            started_at=datetime.now(timezone.utc),
            status=SessionStatus.LIVE,
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def end_session(
        self,
        session: StreamSession,
        status: SessionStatus = SessionStatus.DONE,
        note: str | None = None,
    ) -> StreamSession:
        """End a streaming session."""
        session.ended_at = datetime.now(timezone.utc)
        session.status = status
        if note:
            session.note = note

        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def get_session_by_id(self, session_id: int) -> StreamSession | None:
        """Get session by ID."""
        result = await self.db.execute(
            select(StreamSession)
            .options(selectinload(StreamSession.pc).selectinload(PC.user))
            .options(selectinload(StreamSession.clip_job))
            .where(StreamSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def get_active_session(self, pc_id: int) -> StreamSession | None:
        """Get active (live) session for a PC."""
        result = await self.db.execute(
            select(StreamSession)
            .where(StreamSession.pc_id == pc_id)
            .where(StreamSession.status == SessionStatus.LIVE)
            .order_by(StreamSession.started_at.desc())
        )
        return result.scalar_one_or_none()

    async def list_pc_sessions(
        self,
        pc_id: int,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[StreamSession], int]:
        """List sessions for a PC with pagination."""
        query = select(StreamSession).where(StreamSession.pc_id == pc_id)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_query)).scalar() or 0

        # Get paginated results
        offset = (page - 1) * per_page
        query = (
            query.options(selectinload(StreamSession.clip_job))
            .order_by(StreamSession.started_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        result = await self.db.execute(query)

        return list(result.scalars().all()), total

    # Clip Jobs

    async def create_clip_job(self, session: StreamSession) -> ClipJob:
        """Create a clip job for a session."""
        clip_job = ClipJob(
            session_id=session.id,
            status=ClipStatus.PENDING,
        )
        self.db.add(clip_job)
        await self.db.commit()
        await self.db.refresh(clip_job)
        return clip_job

    async def get_pending_clip_jobs(self) -> list[ClipJob]:
        """Get pending clip jobs for processing."""
        result = await self.db.execute(
            select(ClipJob)
            .options(
                selectinload(ClipJob.session)
                .selectinload(StreamSession.pc)
                .selectinload(PC.user)
            )
            .where(ClipJob.status == ClipStatus.PENDING)
            .order_by(ClipJob.created_at.asc())
        )
        return list(result.scalars().all())

    async def update_clip_job(
        self,
        clip_job: ClipJob,
        status: ClipStatus,
        result_path: str | None = None,
        error: str | None = None,
        size_bytes: int | None = None,
    ) -> ClipJob:
        """Update clip job status."""
        clip_job.status = status
        if result_path is not None:
            clip_job.result_path = result_path
        if error is not None:
            clip_job.error = error
        if size_bytes is not None:
            clip_job.size_bytes = size_bytes

        await self.db.commit()
        await self.db.refresh(clip_job)
        return clip_job
