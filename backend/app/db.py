from sqlmodel import SQLModel, create_engine

from .config import settings
from . import models  # noqa: F401  (registers tables)

engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
