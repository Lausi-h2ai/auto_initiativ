from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    dry_run: bool = Field(default=True, validation_alias="DRY_RUN")
    database_url: str = Field(
        default=f"sqlite:///{REPO_ROOT / 'backend' / 'dev.db'}",
        validation_alias="DATABASE_URL",
    )
    runs_root: Path = Field(default=REPO_ROOT / "runs", validation_alias="RUNS_ROOT")
    schemas_root: Path = Field(default=REPO_ROOT / "schemas", validation_alias="SCHEMAS_ROOT")
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
    pi_rpc_timeout_seconds: float = Field(default=180, validation_alias="PI_RPC_TIMEOUT_SECONDS")
    pi_rpc_no_builtin_tools: bool = Field(default=True, validation_alias="PI_RPC_NO_BUILTIN_TOOLS")
    onboarding_artifact_repair_attempts: int = Field(default=2, validation_alias="ONBOARDING_ARTIFACT_REPAIR_ATTEMPTS")
    pi_rpc_extension_path: Path = Field(
        default=REPO_ROOT / "backend" / "pi_extensions" / "onboarding_artifacts.ts",
        validation_alias="PI_RPC_EXTENSION_PATH",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
