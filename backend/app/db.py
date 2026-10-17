from sqlmodel import SQLModel, create_engine

from .config import settings
from . import models  # noqa: F401  (registers tables)

_url = settings.sqlalchemy_url
if _url.startswith("sqlite"):
    engine = create_engine(_url, connect_args={"check_same_thread": False})
else:
    # Supavisor transaction pooling: no server-side prepared statements. A small per-process
    # pool avoids a TLS handshake per query; the pooler multiplexes the real connections.
    engine = create_engine(_url, pool_size=5, max_overflow=5, pool_recycle=240, pool_pre_ping=True,
                           connect_args={"prepare_threshold": None})


# Columns added after a table first shipped (create_all never alters an existing table).
_ADDED_COLUMNS = [("watches", "forward_to", "VARCHAR"), ("watches", "service", "VARCHAR"),
                  ("watches", "request", "VARCHAR"), ("watches", "seen", "JSON"),
                  ("watches", "interval_sec", "INTEGER")]


def init_db() -> None:
    from sqlalchemy import inspect, text

    SQLModel.metadata.create_all(engine)
    insp = inspect(engine)
    for table, col, typ in _ADDED_COLUMNS:
        if col not in {c["name"] for c in insp.get_columns(table)}:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {typ}"))
