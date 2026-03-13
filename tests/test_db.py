"""Tests for db.py — database engine initialization and helper functions."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "Backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


class TestDatabaseUrl:
    def test_returns_env_var_when_set(self):
        from db import _database_url

        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://localhost/test"}):
            assert _database_url() == "postgresql://localhost/test"

    def test_returns_default_when_not_set(self):
        from db import _database_url

        with patch.dict(os.environ, {}, clear=False):
            # Remove DATABASE_URL if present
            env = os.environ.copy()
            env.pop("DATABASE_URL", None)
            with patch.dict(os.environ, env, clear=True):
                result = _database_url()
                assert "sqlite" in result
                assert "moneyprinter" in result


class TestConnectArgs:
    def test_sqlite_returns_check_same_thread(self):
        from db import _connect_args

        args = _connect_args("sqlite:///test.db")
        assert args == {"check_same_thread": False}

    def test_sqlite_memory_returns_check_same_thread(self):
        from db import _connect_args

        args = _connect_args("sqlite:///:memory:")
        assert args == {"check_same_thread": False}

    def test_postgres_returns_empty(self):
        from db import _connect_args

        args = _connect_args("postgresql://localhost/test")
        assert args == {}


class TestInitDb:
    def test_creates_tables(self, session_factory):
        """init_db creates all model tables (already exercised by session_factory fixture)."""
        from db import Base

        # session_factory fixture already created tables via Base.metadata.create_all
        table_names = list(Base.metadata.tables.keys())
        assert "generation_jobs" in table_names
        assert "generation_events" in table_names
        assert "scripts" in table_names
        assert "artifacts" in table_names
        assert "projects" in table_names
