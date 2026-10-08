"""Application configuration, read from `HAROLD_*` environment variables."""

import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_maude_workers() -> int:
    """Half the logical CPUs, capped at 3 (enough for single-agent IDE use).

    Workers are transient (each task runs in a fresh process), so this bounds how
    many interpreters may spawn concurrently (≈100 MB each), not standing memory.
    `os.cpu_count()` may return `None`; the floor of 1 keeps the `gt=0` invariant.
    """
    return max(1, min(3, (os.cpu_count() or 0) // 2))


class Settings(BaseSettings):
    """Harold configuration (flat for now; `maude_`-prefixed fields group by purpose).

    - `HAROLD_MAUDE_WORKERS`: number of Maude worker processes. Default: half the
      logical CPUs, capped at 3. Workers are transient (`max_tasks_per_child=1`),
      so this caps concurrent per-call interpreters instead of warm workers.
    - `HAROLD_MAUDE_WORKER_TIMEOUT_SECS`: seconds to wait for each worker call
      before failing it (default `60`).
    """

    model_config = SettingsConfigDict(env_prefix="HAROLD_")

    maude_workers: int = Field(default_factory=_default_maude_workers, gt=0)
    maude_worker_timeout_secs: int = Field(default=60, gt=0)


settings = Settings()


def get_settings() -> Settings:
    """Return the process-wide settings singleton (env read once at import)."""
    return settings
