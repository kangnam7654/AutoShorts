import time

from dotenv import load_dotenv

from db import SessionLocal, init_db
from pipeline import PipelineCancelled, run_generation_pipeline
from repository import (
    append_event,
    claim_next_queued_job,
    get_job,
    mark_cancelled,
    mark_completed,
    mark_failed,
)
from utils import ENV_FILE, SUBTITLES_DIR, TEMP_DIR, check_env_vars, clean_dir

POLL_SECONDS = 1.0


def _job_cancelled(job_id: str) -> bool:
    with SessionLocal() as session:
        job = get_job(session, job_id)
        if not job:
            return True
        return bool(job.cancel_requested or job.status == "cancelled")


def _log_event(job_id: str, message: str, level: str) -> None:
    with SessionLocal() as session:
        append_event(session, job_id, "log", level, str(message))
        session.commit()


def _cleanup_runtime_dirs() -> None:
    clean_dir(str(TEMP_DIR))
    clean_dir(str(SUBTITLES_DIR))


def _job_log_callback(job_id: str):
    return lambda message, level: _log_event(job_id, message, level)


def _complete_job(job_id: str, result_path: str) -> None:
    with SessionLocal() as session:
        mark_completed(session, job_id, result_path)


def _cancel_job(job_id: str, message: str) -> None:
    with SessionLocal() as session:
        mark_cancelled(session, job_id, message)


def _fail_job(job_id: str, message: str) -> None:
    with SessionLocal() as session:
        mark_failed(session, job_id, message)


def _run_job(job) -> None:
    job_id = job.id
    result_path = run_generation_pipeline(
        data=job.payload,
        is_cancelled=lambda: _job_cancelled(job_id),
        on_log=_job_log_callback(job_id),
    )
    _complete_job(job_id, result_path)


def process_next_job() -> bool:
    with SessionLocal() as session:
        job = claim_next_queued_job(session)

    if not job:
        return False

    _cleanup_runtime_dirs()

    try:
        _run_job(job)
    except PipelineCancelled as err:
        _cancel_job(job.id, str(err))
    except Exception as err:
        _fail_job(job.id, str(err))

    return True


def main() -> None:
    load_dotenv(ENV_FILE)
    check_env_vars()
    init_db()

    while True:
        if process_next_job():
            continue
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
