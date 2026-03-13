import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from utils import ENV_FILE

load_dotenv(ENV_FILE)

DEFAULT_DATABASE_URL = "sqlite:///moneyprinter.db"


class Base(DeclarativeBase):
    pass


def _database_url() -> str:
    return os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL


def _connect_args(database_url: str) -> dict:
    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


DATABASE_URL = _database_url()

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args=_connect_args(DATABASE_URL),
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def _import_models() -> None:
    from models import Artifact, GenerationEvent, GenerationJob, Project, Script  # noqa: F401


def init_db() -> None:
    _import_models()
    Base.metadata.create_all(bind=engine)
