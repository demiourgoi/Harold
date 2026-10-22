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
    """Harold configuration (flat; field prefixes group settings by subsystem).

    - `HAROLD_MAUDE_WORKERS`: number of Maude worker processes. Default: half the
      logical CPUs, capped at 3. Workers are transient (`max_tasks_per_child=1`),
      so this caps concurrent per-call interpreters instead of warm workers.
    - `HAROLD_DIAGNOSTICS_TIMEOUT_SECS`: seconds to wait for each diagnostics call
      before failing it (default `60`); also the worker subsystem's default timeout
      for its own calls (the fail-fast initialization pings). Renamed from
      `HAROLD_MAUDE_WORKER_TIMEOUT_SECS` (pre-1.0 breaking change).
    - `HAROLD_INTERPRETER_TIMEOUT_SECS`: default timeout for interpreter sessions
      (default `60`); the tool can override it per call.
    - `HAROLD_INTERPRETER_MAX_STEPS`: maximum steps per interpreter session
      (default `200`).
    - `HAROLD_INTERPRETER_MAX_REWRITE_BOUND`: maximum accepted rewrite bound per
      step (default `1000`).
    - `HAROLD_INTERPRETER_MAX_SOLUTIONS`: maximum search solutions / match
      substitutions returned per step (default `200`).
    - `HAROLD_INTERPRETER_MAX_TERM_LENGTH`: maximum characters of a term, pattern
      or subject input (default `100000`).
    - `HAROLD_INTERPRETER_MAX_RESULT_LENGTH`: maximum characters of any returned
      term (default `1000000`); longer results are reported as too large, never
      truncated.
    - `HAROLD_INTERPRETER_MAX_OUTPUT_LENGTH`: maximum characters of each captured
      stream (stdout and stderr separately) returned per phase (default
      `1000000`); longer captures are truncated and marked.
    """

    model_config = SettingsConfigDict(env_prefix="HAROLD_")

    maude_workers: int = Field(default_factory=_default_maude_workers, gt=0)
    diagnostics_timeout_secs: int = Field(default=60, gt=0)
    interpreter_timeout_secs: int = Field(default=60, gt=0)
    interpreter_max_steps: int = Field(default=200, gt=0)
    interpreter_max_rewrite_bound: int = Field(default=1000, gt=0)
    interpreter_max_solutions: int = Field(default=200, gt=0)
    interpreter_max_term_length: int = Field(default=100_000, gt=0)
    interpreter_max_result_length: int = Field(default=1_000_000, gt=0)
    interpreter_max_output_length: int = Field(default=1_000_000, gt=0)


settings = Settings()


def get_settings() -> Settings:
    """Return the process-wide settings singleton (env read once at import)."""
    return settings
