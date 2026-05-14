from collections.abc import Generator

from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from backend.app.core.config import get_settings


def build_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_settings().database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


engine = build_engine()


def init_db(db_engine: Engine | None = None) -> None:
    SQLModel.metadata.create_all(db_engine or engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session

