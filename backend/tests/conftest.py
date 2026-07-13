from __future__ import annotations

import shutil
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_ROOT = PROJECT_ROOT / "backend" / "tests" / "fixtures"


def copy_valid_run(runs_root: Path, run_id: str) -> Path:
    output_path = runs_root / run_id / "output"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(FIXTURES_ROOT / "valid_run" / "output", output_path)
    return output_path


@pytest.fixture()
def runs_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "runs"
    monkeypatch.setenv("RUNS_ROOT", str(root))
    monkeypatch.setenv("EMAIL_SENDING_ENABLED", "false")
    monkeypatch.setenv("EMAIL_PROVIDER", "gmail_sandbox")
    monkeypatch.setenv("EMAIL_ALLOW_REAL_RECIPIENTS", "false")
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    monkeypatch.setenv("DEV_AUTH_BYPASS_EMAIL", "")
    monkeypatch.setenv("WORKFLOW_WORKER_ENABLED", "false")
    monkeypatch.setenv("ISSUE_LOG_PATH", str(tmp_path / "issues.ndjson"))
    monkeypatch.delenv("GMAIL_SANDBOX_RECIPIENT", raising=False)
    return root


@pytest.fixture()
def schemas_root(monkeypatch: pytest.MonkeyPatch) -> Path:
    root = PROJECT_ROOT / "schemas"
    monkeypatch.setenv("SCHEMAS_ROOT", str(root))
    return root


@pytest.fixture()
def database_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    url = f"sqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    return url


@pytest.fixture()
def db_session(database_url: str, runs_root: Path, schemas_root: Path) -> Generator[Session, None, None]:
    from backend.app.core.config import get_settings
    from backend.app.db.session import build_engine

    get_settings.cache_clear()
    engine = build_engine(database_url)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture()
def client(database_url: str, runs_root: Path, schemas_root: Path) -> Generator[TestClient, None, None]:
    from backend.app.core.config import get_settings
    from backend.app.db import session as db_session_module
    from backend.app.db.session import get_session
    from backend.app.main import create_app

    get_settings.cache_clear()
    db_session_module.engine = db_session_module.build_engine(database_url)
    SQLModel.metadata.create_all(db_session_module.engine)

    app = create_app()

    def override_get_session() -> Generator[Session, None, None]:
        with Session(db_session_module.engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
