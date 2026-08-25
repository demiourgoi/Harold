"""Client-side access to the Maude worker: errors and configuration.

Runs in the MCP server process. Never imports the `maude` SWIG bindings — the
interpreter lives in a dedicated worker process (see `harold_mcp.maude.worker`).
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MaudeError(RuntimeError):
    """Base error for failures in the Maude worker subsystem."""


class MaudeInitError(MaudeError):
    """Maude failed to initialize in the worker process (surfaced at warm-up)."""

    def __init__(self) -> None:
        super().__init__("Failed to initialize the Maude interpreter in the worker process")


class MaudeWorkerError(MaudeError):
    """The worker crashed or timed out during a call; the executor was replaced."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class MaudeFileNotFoundError(MaudeError):
    """The input path is missing or unreadable (raised before any worker call)."""

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"Maude program file not found or unreadable: {path!r}")


class Settings(BaseSettings):
    """Configuration for the Maude worker subsystem, from `HAROLD_*` env vars.

    - `HAROLD_MAUDE_WORKERS`: number of Maude worker processes (default `1`).
    - `HAROLD_MAUDE_WORKER_TIMEOUT_SECS`: seconds to wait for each worker call
      before failing it (default `60`).
    """

    model_config = SettingsConfigDict(env_prefix="HAROLD_")

    maude_workers: int = Field(default=1, gt=0)
    maude_worker_timeout_secs: int = Field(default=60, gt=0)


settings = Settings()
