from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool

from config import settings

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

_engine_kwargs: dict = {"pool_pre_ping": True}
if _is_sqlite:
    # check_same_thread=False lets the background upload worker share the engine.
    _engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
else:
    _engine_kwargs.update(
        poolclass=QueuePool,
        pool_size=10,
        max_overflow=20,
        pool_recycle=1800,
    )

engine = create_engine(settings.DATABASE_URL, **_engine_kwargs)


if _is_sqlite:

    @event.listens_for(Engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _connection_record):  # pragma: no cover - driver hook
        """WAL for concurrent reads during a write; FK enforcement for ON DELETE CASCADE."""
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
        finally:
            cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
