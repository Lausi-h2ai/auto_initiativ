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


@lru_cache
def get_settings() -> Settings:
    return Settings()

