import os
from typing import Any

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from sqlalchemy import and_, case, select

from legacy.db import SessionLocal, init_db
from gpt import list_models
from logstream import log
from legacy.repository import create_job, get_job, list_job_events, request_cancel
from utils import ENV_FILE, SONGS_DIR, check_env_vars, clean_dir

load_dotenv(ENV_FILE)
check_env_vars()
init_db()

app = Flask(__name__)
CORS(app)

HOST = "0.0.0.0"
PORT = 8080
DEFAULT_OLLAMA_MODEL = "llama3.1:8b"


def _success(payload: dict[str, Any], status_code: int = 200):
    return jsonify({"status": "success", **payload}), status_code


def _error(message: str, status_code: int = 400, **extra: Any):
    return jsonify({"status": "error", "message": message, **extra}), status_code


def _default_model_payload() -> dict[str, Any]:
    model_name = os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
    return {"models": [model_name], "default": model_name}


def _serialize_job(job) -> dict[str, Any]:
    return {
        "id": job.id,
        "state": job.status,
        "cancelRequested": job.cancel_requested,
        "resultPath": job.result_path,
        "errorMessage": job.error_message,
        "createdAt": job.created_at.isoformat() if job.created_at else None,
        "startedAt": job.started_at.isoformat() if job.started_at else None,
        "completedAt": job.completed_at.isoformat() if job.completed_at else None,
    }


def _serialize_event(event) -> dict[str, Any]:
    return {
        "id": event.id,
        "type": event.event_type,
        "level": event.level,
        "message": event.message,
        "payload": event.payload,
        "timestamp": event.created_at.timestamp() if event.created_at else None,
    }


def _active_job_query():
    from legacy.models import GenerationJob

    return (
        select(GenerationJob)
        .where(and_(GenerationJob.status.in_(["queued", "running"])))
        .order_by(
            case((GenerationJob.status == "running", 0), else_=1),
            GenerationJob.created_at.desc(),
        )
        .limit(1)
    )


def _uploaded_mp3_files():
    return request.files.getlist("songs")


def _save_uploaded_songs(files) -> int:
    clean_dir(str(SONGS_DIR))
    saved_count = 0

    for file_item in files:
        filename = file_item.filename or ""
        if not filename.lower().endswith(".mp3"):
            continue

        safe_name = os.path.basename(filename)
        file_item.save(str(SONGS_DIR / safe_name))
        saved_count += 1

    return saved_count


@app.route("/api/models", methods=["GET"])
def models():
    try:
        available_models, default_model = list_models()
        return _success(
            {
                "models": available_models,
                "default": default_model,
            }
        )
    except Exception as err:
        log(f"[-] Error fetching Ollama models: {err}", "error")
        return _error(
            "Could not fetch Ollama models. Is Ollama running?",
            status_code=200,
            **_default_model_payload(),
        )


@app.route("/api/generate", methods=["POST"])
def generate():
    data = request.get_json() or {}
    if not data.get("videoSubject"):
        return _error("videoSubject is required.")

    with SessionLocal() as session:
        job = create_job(session, payload=data)

    return _success(
        {
            "message": "Video generation queued.",
            "jobId": job.id,
        }
    )


@app.route("/api/jobs/<job_id>", methods=["GET"])
def get_job_status(job_id: str):
    with SessionLocal() as session:
        job = get_job(session, job_id)
        if not job:
            return _error("Job not found.", status_code=404)

        return _success({"job": _serialize_job(job)})


@app.route("/api/jobs/<job_id>/events", methods=["GET"])
def get_events(job_id: str):
    after_id = request.args.get("after", default=0, type=int)

    with SessionLocal() as session:
        job = get_job(session, job_id)
        if not job:
            return _error("Job not found.", status_code=404)

        events = list_job_events(session, job_id, after_id=after_id)
        return _success({"events": [_serialize_event(event) for event in events]})


@app.route("/api/jobs/<job_id>/cancel", methods=["POST"])
def cancel_job(job_id: str):
    with SessionLocal() as session:
        cancelled = request_cancel(session, job_id)
        if not cancelled:
            return _error("Job not found.", status_code=404)

    return _success({"message": "Cancellation requested."})


@app.route("/api/upload-songs", methods=["POST"])
def upload_songs():
    try:
        files = _uploaded_mp3_files()
        if not files:
            return _error("No files uploaded.")

        saved_count = _save_uploaded_songs(files)
        if saved_count == 0:
            return _error("No MP3 files found.")

        log(f"[+] Uploaded {saved_count} song(s) to {SONGS_DIR}", "success")
        return _success({"message": f"Uploaded {saved_count} song(s)."})
    except Exception as err:
        log(f"[-] Error uploading songs: {err}", "error")
        return _error(str(err), status_code=500)


@app.route("/api/cancel", methods=["POST"])
def cancel_latest_running_job():
    with SessionLocal() as session:
        latest_job = session.scalars(_active_job_query()).first()
        if not latest_job:
            return _error("No active job found.", status_code=404)

        request_cancel(session, latest_job.id)

    return _success(
        {
            "message": "Cancellation requested.",
            "jobId": latest_job.id,
        }
    )


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true", host=HOST, port=PORT, threaded=True)
