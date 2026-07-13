from collections.abc import Generator

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session as AlchemySession
from sqlmodel import Session, SQLModel, create_engine

from backend.app.auth.context import current_workspace_id
from backend.app.core.config import get_settings
from backend.app.db.models import WorkspaceOwned


def build_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_settings().database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


engine = build_engine()


@event.listens_for(AlchemySession, "do_orm_execute")
def _scope_workspace_queries(execute_state: object) -> None:
    workspace_id = current_workspace_id()
    if workspace_id is None or not getattr(execute_state, "is_select", False):
        return
    statement = execute_state.statement
    scoped_entities: set[object] = set()
    for description in getattr(statement, "column_descriptions", ()):
        entity = description.get("entity")
        entity_type = entity if isinstance(entity, type) else getattr(entity, "_aliased_insp", None)
        mapped_type = getattr(entity_type, "class_", entity_type)
        if isinstance(mapped_type, type) and issubclass(mapped_type, WorkspaceOwned) and entity not in scoped_entities:
            statement = statement.where(entity.workspace_id == workspace_id)
            scoped_entities.add(entity)
    execute_state.statement = statement


@event.listens_for(AlchemySession, "before_flush")
def _enforce_workspace_writes(session: AlchemySession, _flush_context: object, _instances: object) -> None:
    workspace_id = current_workspace_id()
    if workspace_id is None:
        return
    for record in session.new:
        if not isinstance(record, WorkspaceOwned):
            continue
        if record.workspace_id is None:
            record.workspace_id = workspace_id
        elif record.workspace_id != workspace_id:
            raise PermissionError("Cross-workspace writes are not allowed.")
    for record in session.dirty | session.deleted:
        if isinstance(record, WorkspaceOwned) and record.workspace_id != workspace_id:
            raise PermissionError("Cross-workspace mutations are not allowed.")


def init_db(db_engine: Engine | None = None) -> None:
    SQLModel.metadata.create_all(db_engine or engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
