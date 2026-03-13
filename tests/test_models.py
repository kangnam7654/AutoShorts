"""Tests for models.py — ORM model definitions and relationships."""

import sys
from pathlib import Path
from uuid import uuid4

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


class TestGenerationJob:
    def test_create_job(self, session):
        from models import GenerationJob

        job_id = str(uuid4())
        job = GenerationJob(
            id=job_id,
            status="queued",
            payload={"videoSubject": "cats"},
        )
        session.add(job)
        session.commit()

        fetched = session.get(GenerationJob, job_id)
        assert fetched is not None
        assert fetched.status == "queued"
        assert fetched.payload == {"videoSubject": "cats"}
        assert fetched.cancel_requested is False
        assert fetched.attempt_count == 0
        assert fetched.max_attempts == 1

    def test_default_values(self, session):
        from models import GenerationJob

        job_id = str(uuid4())
        job = GenerationJob(
            id=job_id,
            status="queued",
            payload={},
        )
        session.add(job)
        session.commit()

        fetched = session.get(GenerationJob, job_id)
        assert fetched.cancel_requested is False
        assert fetched.attempt_count == 0
        assert fetched.result_path is None
        assert fetched.error_message is None


class TestGenerationEvent:
    def test_create_event_linked_to_job(self, session):
        from models import GenerationEvent, GenerationJob

        job_id = str(uuid4())
        job = GenerationJob(id=job_id, status="running", payload={})
        session.add(job)
        session.commit()

        event = GenerationEvent(
            job_id=job_id,
            event_type="log",
            level="info",
            message="Processing started",
        )
        session.add(event)
        session.commit()

        fetched = session.get(GenerationEvent, event.id)
        assert fetched.message == "Processing started"
        assert fetched.job_id == job_id

    def test_job_events_relationship(self, session):
        from models import GenerationEvent, GenerationJob

        job_id = str(uuid4())
        job = GenerationJob(id=job_id, status="running", payload={})
        session.add(job)
        session.commit()

        for i in range(3):
            session.add(GenerationEvent(
                job_id=job_id,
                event_type="log",
                level="info",
                message=f"Event {i}",
            ))
        session.commit()

        session.refresh(job)
        assert len(job.events) == 3

    def test_cascade_delete(self, session):
        from models import GenerationEvent, GenerationJob

        job_id = str(uuid4())
        job = GenerationJob(id=job_id, status="running", payload={})
        session.add(job)
        session.commit()

        session.add(GenerationEvent(
            job_id=job_id, event_type="log", level="info", message="test"
        ))
        session.commit()

        session.delete(job)
        session.commit()

        remaining = session.query(GenerationEvent).filter_by(job_id=job_id).all()
        assert remaining == []


class TestScript:
    def test_create_script(self, session):
        from models import GenerationJob, Script

        job_id = str(uuid4())
        job = GenerationJob(id=job_id, status="completed", payload={})
        session.add(job)
        session.commit()

        script = Script(
            job_id=job_id,
            model_name="llama3.1:8b",
            content="A cat sits on a mat.",
        )
        session.add(script)
        session.commit()

        fetched = session.get(Script, script.id)
        assert fetched.content == "A cat sits on a mat."
        assert fetched.model_name == "llama3.1:8b"


class TestArtifact:
    def test_create_artifact(self, session):
        from models import Artifact, GenerationJob

        job_id = str(uuid4())
        job = GenerationJob(id=job_id, status="completed", payload={})
        session.add(job)
        session.commit()

        artifact = Artifact(
            job_id=job_id,
            artifact_type="video",
            path="/output/video.mp4",
            metadata_json={"duration": 15.0},
        )
        session.add(artifact)
        session.commit()

        fetched = session.get(Artifact, artifact.id)
        assert fetched.artifact_type == "video"
        assert fetched.path == "/output/video.mp4"
        assert fetched.metadata_json == {"duration": 15.0}


class TestProject:
    def test_create_project(self, session):
        from models import Project

        project = Project(name="test-project")
        session.add(project)
        session.commit()

        fetched = session.query(Project).filter_by(name="test-project").first()
        assert fetched is not None
        assert fetched.name == "test-project"

    def test_unique_name(self, session):
        from models import Project
        from sqlalchemy.exc import IntegrityError

        session.add(Project(name="unique"))
        session.commit()

        session.add(Project(name="unique"))
        with pytest.raises(IntegrityError):
            session.commit()
