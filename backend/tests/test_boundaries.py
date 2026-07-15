from __future__ import annotations

import tomllib
from pathlib import Path

from sqlmodel import SQLModel

from backend.app.core.config import Settings
from backend.app.db import models  # noqa: F401


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_no_openai_dependency_declared_and_gmail_send_dependency_is_explicit():
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = " ".join(pyproject["project"]["dependencies"]).lower()

    assert "openai" not in dependencies
    assert "google-api-python-client" in dependencies
    assert "google-auth-oauthlib" in dependencies


def test_metadata_contains_operational_domain_and_guarded_send_tables():
    assert set(SQLModel.metadata.tables) == {
        "users",
        "workspaces",
        "invitations",
        "auth_sessions",
        "oauth_states",
        "gmail_connections",
        "admin_access_audits",
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
    }


def test_real_email_provider_is_confined_to_backend_email_delivery():
    backend_files = [path.relative_to(PROJECT_ROOT).as_posix().lower() for path in (PROJECT_ROOT / "backend").rglob("*.py")]

    assert not any("smtp" in path for path in backend_files)
    assert not any("send_adapter" in path for path in backend_files)


def test_email_adapter_configuration_defaults_to_disabled():
    config_fields = set(Settings.model_fields)

    assert "email_sending_enabled" in config_fields
    assert "gmail_user_id" in config_fields
    assert not any("smtp" in field for field in config_fields)
    assert "email_adapter" not in config_fields
    assert "send_adapter" not in config_fields
    assert Settings(_env_file=None).email_sending_enabled is False
