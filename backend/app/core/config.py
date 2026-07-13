from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    codex_wsl_distro: str = Field(default="Ubuntu-24.04-bonsai-vllm", validation_alias="CODEX_WSL_DISTRO")
    codex_tmux_session: str = Field(default="codex", validation_alias="CODEX_TMUX_SESSION")
    codex_tmux_window: int = Field(default=0, validation_alias="CODEX_TMUX_WINDOW")
    codex_tmux_pane: int = Field(default=0, validation_alias="CODEX_TMUX_PANE")
    codex_workdir: str = Field(default="/mnt/f/auto_initiativ", validation_alias="CODEX_WORKDIR")
    codex_chat_reply_wait_seconds: float = Field(default=2, validation_alias="CODEX_CHAT_REPLY_WAIT_SECONDS")
    codex_exec_binary: str = Field(default="codex", validation_alias="CODEX_EXEC_BINARY")
    codex_exec_timeout_seconds: float = Field(default=900, validation_alias="CODEX_EXEC_TIMEOUT_SECONDS")
    codex_exec_sandbox: str = Field(default="read-only", validation_alias="CODEX_EXEC_SANDBOX")
    codex_exec_json_events: bool = Field(default=True, validation_alias="CODEX_EXEC_JSON_EVENTS")
    onboarding_chat_runtime: str = Field(default="tmux", validation_alias="ONBOARDING_CHAT_RUNTIME")
    pi_rpc_binary: str = Field(default="pi", validation_alias="PI_RPC_BINARY")
    pi_rpc_provider: str | None = Field(default=None, validation_alias="PI_RPC_PROVIDER")
    pi_rpc_model: str | None = Field(default=None, validation_alias="PI_RPC_MODEL")
    pi_rpc_thinking: str | None = Field(default=None, validation_alias="PI_RPC_THINKING")
    pi_rpc_research_provider: str | None = Field(default="openai-codex", validation_alias="PI_RPC_RESEARCH_PROVIDER")
    pi_rpc_research_model: str | None = Field(default="gpt-5.5", validation_alias="PI_RPC_RESEARCH_MODEL")
    pi_rpc_research_thinking: str | None = Field(default="medium", validation_alias="PI_RPC_RESEARCH_THINKING")
    pi_rpc_timeout_seconds: float = Field(default=180, validation_alias="PI_RPC_TIMEOUT_SECONDS")
    pi_rpc_research_timeout_seconds: float = Field(default=3600, validation_alias="PI_RPC_RESEARCH_TIMEOUT_SECONDS")
    pi_rpc_no_builtin_tools: bool = Field(default=True, validation_alias="PI_RPC_NO_BUILTIN_TOOLS")
    onboarding_artifact_repair_attempts: int = Field(default=2, validation_alias="ONBOARDING_ARTIFACT_REPAIR_ATTEMPTS")
    pi_rpc_extension_path: Path = Field(
        default=REPO_ROOT / "backend" / "pi_extensions" / "onboarding_artifacts.ts",
        validation_alias="PI_RPC_EXTENSION_PATH",
    )
    pi_rpc_research_extension_path: Path = Field(
        default=REPO_ROOT / "backend" / "pi_extensions" / "company_research.ts",
        validation_alias="PI_RPC_RESEARCH_EXTENSION_PATH",
    )
    pi_rpc_application_draft_extension_path: Path = Field(
        default=REPO_ROOT / "backend" / "pi_extensions" / "application_draft.ts",
        validation_alias="PI_RPC_APPLICATION_DRAFT_EXTENSION_PATH",
    )
    pi_rpc_application_draft_provider: str | None = Field(
        default="openai-codex",
        validation_alias="PI_RPC_APPLICATION_DRAFT_PROVIDER",
    )
    pi_rpc_application_draft_model: str | None = Field(
        default="gpt-5.4-mini",
        validation_alias="PI_RPC_APPLICATION_DRAFT_MODEL",
    )
    pi_rpc_application_draft_thinking: str | None = Field(
        default="low",
        validation_alias="PI_RPC_APPLICATION_DRAFT_THINKING",
    )
    pi_rpc_application_draft_timeout_seconds: float = Field(
        default=1800,
        validation_alias="PI_RPC_APPLICATION_DRAFT_TIMEOUT_SECONDS",
    )
    application_draft_master_cv_html_path: Path = Field(
        default=Path(r"C:\Users\laure\OneDrive\Documents\Bewerbungsunterlagen\Lebenslauf\Switzerland\de\master\de_ch_master.html"),
        validation_alias="APPLICATION_DRAFT_MASTER_CV_HTML_PATH",
    )
    application_draft_handoff_dir: Path = Field(
        default=Path(r"C:\Users\laure\OneDrive\Documents\Bewerbungsunterlagen\agent-handoff"),
        validation_alias="APPLICATION_DRAFT_HANDOFF_DIR",
    )
    application_draft_include_handoff_docs: bool = Field(
        default=False,
        validation_alias="APPLICATION_DRAFT_INCLUDE_HANDOFF_DOCS",
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
