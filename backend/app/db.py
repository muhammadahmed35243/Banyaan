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


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
