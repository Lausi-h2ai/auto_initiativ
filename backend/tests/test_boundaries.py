from __future__ import annotations

import tomllib
from pathlib import Path

from sqlmodel import SQLModel

from backend.app.core.config import Settings
from backend.app.db import models  # noqa: F401


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_no_openai_or_gmail_dependencies_declared():
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = " ".join(pyproject["project"]["dependencies"]).lower()

    assert "openai" not in dependencies
    assert "gmail" not in dependencies
    assert "google-api-python-client" not in dependencies


def test_metadata_only_contains_operational_and_phase2_domain_tables():
    assert set(SQLModel.metadata.tables) == {
        "runs",
        "imported_files",
        "validation_results",
        "audit_logs",
        "user_profile_snapshots",
        "master_cv_profile_snapshots",
        "policy_snapshots",
        "companies",
        "contacts",
        "fit_evaluations",
        "email_drafts",
        "send_intents",
        "imported_gate_results",
        "send_reservations",
        "outreach_records",
    }


def test_no_email_adapter_module_exists():
    backend_files = [path.relative_to(PROJECT_ROOT).as_posix().lower() for path in (PROJECT_ROOT / "backend").rglob("*.py")]

    assert not any("gmail" in path for path in backend_files)
    assert not any("email_adapter" in path or "send_adapter" in path for path in backend_files)


def test_no_email_adapter_configuration_exists():
    config_fields = set(Settings.model_fields)

    assert not any("gmail" in field for field in config_fields)
    assert not any("smtp" in field for field in config_fields)
    assert "email_adapter" not in config_fields
    assert "send_adapter" not in config_fields
