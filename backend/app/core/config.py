from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.app.core.agent_models import agent_model_for


REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", populate_by_name=True)

    dry_run: bool = Field(default=True, validation_alias="DRY_RUN")
    database_url: str = Field(
        default=f"sqlite:///{REPO_ROOT / 'backend' / 'dev.db'}",
        validation_alias="DATABASE_URL",
    )
    runs_root: Path = Field(default=REPO_ROOT / "runs", validation_alias="RUNS_ROOT")
    schemas_root: Path = Field(default=REPO_ROOT / "schemas", validation_alias="SCHEMAS_ROOT")
    public_base_url: str = Field(default="http://127.0.0.1:8000", validation_alias="PUBLIC_BASE_URL")
    auth_required: bool = Field(default=True, validation_alias="AUTH_REQUIRED")
    bootstrap_admin_email: str | None = Field(default=None, validation_alias="BOOTSTRAP_ADMIN_EMAIL")
    google_oauth_client_id: str | None = Field(default=None, validation_alias="GOOGLE_OAUTH_CLIENT_ID")
    google_oauth_client_secret: str | None = Field(default=None, validation_alias="GOOGLE_OAUTH_CLIENT_SECRET")
    auth_session_days: int = Field(default=14, validation_alias="AUTH_SESSION_DAYS")
    credential_encryption_key: str | None = Field(default=None, validation_alias="CREDENTIAL_ENCRYPTION_KEY")
    secure_cookies: bool = Field(default=False, validation_alias="SECURE_COOKIES")
    workflow_worker_enabled: bool = Field(default=True, validation_alias="WORKFLOW_WORKER_ENABLED")
    dev_auth_bypass_email: str | None = Field(default=None, validation_alias="DEV_AUTH_BYPASS_EMAIL")
    issue_log_path: Path = Field(default=REPO_ROOT / "logs" / "issues.ndjson", validation_alias="ISSUE_LOG_PATH")
    codex_exec_binary: str = Field(default="codex", validation_alias="CODEX_EXEC_BINARY")
    codex_exec_timeout_seconds: float = Field(default=900, validation_alias="CODEX_EXEC_TIMEOUT_SECONDS")
    codex_exec_sandbox: str = Field(default="read-only", validation_alias="CODEX_EXEC_SANDBOX")
    codex_exec_json_events: bool = Field(default=True, validation_alias="CODEX_EXEC_JSON_EVENTS")
    pi_rpc_binary: str = Field(default="pi", validation_alias="PI_RPC_BINARY")
    pi_rpc_onboarding_provider: str = Field(default="openai-codex", validation_alias="PI_RPC_ONBOARDING_PROVIDER")
    pi_rpc_onboarding_model: str = Field(
        default=agent_model_for("onboarding"),
        validation_alias="PI_RPC_ONBOARDING_MODEL",
    )
    pi_rpc_onboarding_thinking: str = Field(default="medium", validation_alias="PI_RPC_ONBOARDING_THINKING")
    pi_rpc_onboarding_timeout_seconds: float = Field(
        default=180,
        validation_alias="PI_RPC_ONBOARDING_TIMEOUT_SECONDS",
    )
    pi_rpc_onboarding_finish_timeout_seconds: float = Field(
        default=600,
        validation_alias="PI_RPC_ONBOARDING_FINISH_TIMEOUT_SECONDS",
    )
    pi_rpc_research_provider: str = Field(default="openai-codex", validation_alias="PI_RPC_RESEARCH_PROVIDER")
    pi_rpc_research_model: str = Field(
        default=agent_model_for("company_research"),
        validation_alias="PI_RPC_RESEARCH_MODEL",
    )
    pi_rpc_research_thinking: str = Field(default="medium", validation_alias="PI_RPC_RESEARCH_THINKING")
    pi_rpc_research_timeout_seconds: float = Field(default=3600, validation_alias="PI_RPC_RESEARCH_TIMEOUT_SECONDS")
    pi_rpc_job_verification_model: str = Field(
        default=agent_model_for("job_verification"),
        validation_alias="PI_RPC_JOB_VERIFICATION_MODEL",
    )
    onboarding_artifact_repair_attempts: int = Field(default=2, validation_alias="ONBOARDING_ARTIFACT_REPAIR_ATTEMPTS")
    pi_rpc_extension_path: Path = Field(
        default=REPO_ROOT / "backend" / "pi_extensions" / "onboarding_artifacts.ts",
        validation_alias="PI_RPC_EXTENSION_PATH",
    )
    pi_rpc_research_extension_path: Path = Field(
        default=REPO_ROOT / "backend" / "pi_extensions" / "company_research.ts",
        validation_alias="PI_RPC_RESEARCH_EXTENSION_PATH",
    )
    pi_rpc_job_verification_extension_path: Path = Field(
        default=REPO_ROOT / "backend" / "pi_extensions" / "job_verification.ts",
        validation_alias="PI_RPC_JOB_VERIFICATION_EXTENSION_PATH",
    )
    pi_rpc_application_draft_extension_path: Path = Field(
        default=REPO_ROOT / "backend" / "pi_extensions" / "application_draft.ts",
        validation_alias="PI_RPC_APPLICATION_DRAFT_EXTENSION_PATH",
    )
    pi_rpc_application_draft_provider: str = Field(
        default="openai-codex",
        validation_alias="PI_RPC_APPLICATION_DRAFT_PROVIDER",
    )
    pi_rpc_application_draft_model: str = Field(
        default=agent_model_for("application_draft"),
        validation_alias="PI_RPC_APPLICATION_DRAFT_MODEL",
    )
    pi_rpc_application_draft_thinking: str = Field(
        default="medium",
        validation_alias="PI_RPC_APPLICATION_DRAFT_THINKING",
    )
    pi_rpc_application_draft_timeout_seconds: float = Field(
        default=1800,
        validation_alias="PI_RPC_APPLICATION_DRAFT_TIMEOUT_SECONDS",
    )
    application_draft_allow_contact_research: bool = Field(
        default=False,
        validation_alias="APPLICATION_DRAFT_ALLOW_CONTACT_RESEARCH",
    )
    email_sending_enabled: bool = Field(default=False, validation_alias="EMAIL_SENDING_ENABLED")
    email_provider: str = Field(default="gmail_sandbox", validation_alias="EMAIL_PROVIDER")
    email_allow_real_recipients: bool = Field(default=False, validation_alias="EMAIL_ALLOW_REAL_RECIPIENTS")
    gmail_sandbox_recipient: str | None = Field(default=None, validation_alias="GMAIL_SANDBOX_RECIPIENT")
    gmail_user_id: str = Field(default="me", validation_alias="GMAIL_USER_ID")
    gmail_oauth_client_secrets_path: Path | None = Field(default=None, validation_alias="GMAIL_OAUTH_CLIENT_SECRETS_PATH")
    gmail_oauth_token_path: Path | None = Field(default=None, validation_alias="GMAIL_OAUTH_TOKEN_PATH")
    gmail_oauth_scopes: list[str] = Field(
        default_factory=lambda: ["https://www.googleapis.com/auth/gmail.send"],
        validation_alias="GMAIL_OAUTH_SCOPES",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
