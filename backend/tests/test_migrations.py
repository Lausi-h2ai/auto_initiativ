from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from backend.app.core.config import get_settings


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CURRENT_HEAD = "20260719_0009"
EXPECTED_TABLES = {
    "alembic_version",
    "runs",
    "imported_files",
    "validation_results",
    "audit_logs",
    "user_profile_snapshots",
    "master_cv_profile_snapshots",
    "profile_assets",
    "master_cv_document_snapshots",
    "master_cv_builder_sessions",
    "policy_snapshots",
    "companies",
    "contacts",
    "fit_evaluations",
    "email_drafts",
    "send_intents",
    "imported_gate_results",
    "send_reservations",
    "outreach_records",
    "company_identities",
    "company_identity_aliases",
    "send_approval_snapshots",
    "sent_messages",
    "users",
    "workspaces",
    "invitations",
    "auth_sessions",
    "oauth_states",
    "gmail_connections",
    "admin_access_audits",
    "campaigns",
    "onboarding_sessions",
    "campaign_companies",
    "job_postings",
    "campaign_jobs",
    "job_fit_evaluations",
    "job_application_packages",
    "job_source_trust",
    "agent_tasks",
    "review_exceptions",
    "documents",
    "research_plans",
    "research_targets",
    "research_search_attempts",
    "research_discoveries",
}


def _alembic_config() -> Config:
    return Config(str(PROJECT_ROOT / "alembic.ini"))


def test_alembic_upgrade_head_creates_operational_and_phase2_domain_tables(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'migration-smoke.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()

    command.upgrade(_alembic_config(), "head")

    engine = create_engine(database_url)
    table_names = set(inspect(engine).get_table_names())

    assert EXPECTED_TABLES.issubset(table_names)


def test_alembic_version_table_records_current_head(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'migration-current.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()

    config = _alembic_config()
    command.upgrade(config, "head")

    engine = create_engine(database_url)
    with engine.connect() as connection:
        version = connection.execute(text("select version_num from alembic_version")).scalar_one()

    assert version == CURRENT_HEAD


def test_migration_downgrade_is_not_destructive(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'migration-no-downgrade.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()

    config = _alembic_config()
    command.upgrade(config, "head")

    with pytest.raises(NotImplementedError, match="Destructive downgrade"):
        command.downgrade(config, "base")
