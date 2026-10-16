from sqlmodel import SQLModel, create_engine

from .config import settings
from . import models  # noqa: F401  (registers tables)

_url = settings.sqlalchemy_url
if _url.startswith("sqlite"):
    engine = create_engine(_url, connect_args={"check_same_thread": False})
else:
    # Supavisor transaction pooling: no server-side prepared statements, and
    # NullPool because the pooler (not this serverless process) owns pooling.
    from sqlalchemy.pool import NullPool

    engine = create_engine(_url, poolclass=NullPool, connect_args={"prepare_threshold": None})


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
