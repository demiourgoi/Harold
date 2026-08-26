"""Application configuration, read from `HAROLD_*` environment variables."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Harold configuration (flat for now; `maude_`-prefixed fields group by purpose).

    - `HAROLD_MAUDE_WORKERS`: number of Maude worker processes (default `1`).
    - `HAROLD_MAUDE_WORKER_TIMEOUT_SECS`: seconds to wait for each worker call
      before failing it (default `60`).
    """

    model_config = SettingsConfigDict(env_prefix="HAROLD_")

    maude_workers: int = Field(default=1, gt=0)
    maude_worker_timeout_secs: int = Field(default=60, gt=0)


settings = Settings()


def get_settings() -> Settings:
    """Return the process-wide settings singleton (env read once at import)."""
    return settings
