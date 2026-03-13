from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import and_, select, text
from sqlalchemy.orm import Session

from models import GenerationEvent, GenerationJob


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def append_event(
    session: Session,
    job_id: str,
    event_type: str,
    level: str,
    message: str,
    payload: Optional[dict] = None,
) -> GenerationEvent:
    event = GenerationEvent(
        job_id=job_id,
        event_type=event_type,
        level=level,
        message=message,
        payload=payload,
    )
    session.add(event)
    session.flush()
    return event


def _update_job_timestamp(job: GenerationJob) -> None:
    job.updated_at = utcnow()


def _commit_and_refresh(session: Session, job: GenerationJob) -> GenerationJob:
    session.commit()
    session.refresh(job)
    return job


def create_job(session: Session, payload: dict, max_attempts: int = 1) -> GenerationJob:
    job = GenerationJob(
        id=str(uuid4()),
        status="queued",
        payload=payload,
        max_attempts=max_attempts,
        cancel_requested=False,
    )
    session.add(job)
    session.flush()
    append_event(session, job.id, "queued", "info", "Job queued.")
    return _commit_and_refresh(session, job)


def get_job(session: Session, job_id: str) -> Optional[GenerationJob]:
    return session.get(GenerationJob, job_id)


def list_job_events(
    session: Session,
    job_id: str,
    after_id: int = 0,
    limit: int = 200,
) -> list[GenerationEvent]:
    stmt = (
        select(GenerationEvent)
        .where(
            and_(
                GenerationEvent.job_id == job_id,
                GenerationEvent.id > after_id,
            )
        )
        .order_by(GenerationEvent.id.asc())
        .limit(limit)
    )
    return list(session.scalars(stmt).all())


def _mark_cancel_requested(session: Session, job: GenerationJob) -> None:
    job.cancel_requested = True
    _update_job_timestamp(job)
    append_event(
        session,
        job.id,
        "cancel_requested",
        "warning",
        "Cancellation requested.",
    )


def _cancel_queued_job(session: Session, job: GenerationJob) -> None:
    job.status = "cancelled"
    job.completed_at = utcnow()
    append_event(
        session,
        job.id,
        "cancelled",
        "warning",
        "Job cancelled before execution.",
    )


def request_cancel(session: Session, job_id: str) -> bool:
    job = get_job(session, job_id)
    if not job:
        return False

    if job.status in ("completed", "failed", "cancelled"):
        return True

    _mark_cancel_requested(session, job)
    if job.status == "queued":
        _cancel_queued_job(session, job)

    session.commit()
    return True


def _claim_next_postgres_job(session: Session) -> Optional[GenerationJob]:
    row = session.execute(
        text(
            """
            SELECT id
            FROM generation_jobs
            WHERE status = 'queued' AND cancel_requested = false
            ORDER BY created_at ASC
            FOR UPDATE SKIP LOCKED
            LIMIT 1
            """
        )
    ).first()
    if not row:
        return None
    return get_job(session, row[0])


def _claim_next_generic_job(session: Session) -> Optional[GenerationJob]:
    stmt = (
        select(GenerationJob)
        .where(
            and_(
                GenerationJob.status == "queued",
                GenerationJob.cancel_requested.is_(False),
            )
        )
        .order_by(GenerationJob.created_at.asc())
        .limit(1)
    )
    return session.scalars(stmt).first()


def _start_job(session: Session, job: GenerationJob) -> GenerationJob:
    job.status = "running"
    job.attempt_count = (job.attempt_count or 0) + 1
    job.started_at = utcnow()
    _update_job_timestamp(job)
    append_event(session, job.id, "running", "info", "Job started.")
    return _commit_and_refresh(session, job)


def claim_next_queued_job(session: Session) -> Optional[GenerationJob]:
    dialect_name = session.bind.dialect.name if session.bind else ""

    if dialect_name == "postgresql":
        job = _claim_next_postgres_job(session)
    else:
        job = _claim_next_generic_job(session)

    if not job:
        return None

    return _start_job(session, job)


def _complete_job(
    session: Session,
    job: GenerationJob,
    *,
    status: str,
    event_type: str,
    level: str,
    message: str,
    payload: Optional[dict] = None,
    error_message: Optional[str] = None,
    result_path: Optional[str] = None,
) -> None:
    job.status = status
    job.result_path = result_path
    job.error_message = error_message
    job.completed_at = utcnow()
    _update_job_timestamp(job)
    append_event(session, job.id, event_type, level, message, payload)
    session.commit()


def mark_completed(session: Session, job_id: str, result_path: str) -> None:
    job = get_job(session, job_id)
    if not job:
        return

    _complete_job(
        session,
        job,
        status="completed",
        event_type="complete",
        level="success",
        message="Video generated successfully.",
        payload={"path": result_path},
        result_path=result_path,
    )


def mark_cancelled(
    session: Session,
    job_id: str,
    reason: str = "Job cancelled.",
) -> None:
    job = get_job(session, job_id)
    if not job:
        return

    _complete_job(
        session,
        job,
        status="cancelled",
        event_type="cancelled",
        level="warning",
        message=reason,
    )


def mark_failed(session: Session, job_id: str, error_message: str) -> None:
    job = get_job(session, job_id)
    if not job:
        return

    _complete_job(
        session,
        job,
        status="failed",
        event_type="error",
        level="error",
        message=error_message,
        error_message=error_message,
    )
