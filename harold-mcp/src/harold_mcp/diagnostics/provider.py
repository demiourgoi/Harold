"""The diagnostics provider seam: value types, error vocabulary and the contract.

Provider-agnostic and stdlib-only: nothing here imports the Maude interpreter, the
heuristic linter, FastMCP or the wire models, so every capability package can depend
on the seam without depending on another capability. Concrete providers stamp their
own `DiagnosticSource` name on every diagnostic they report.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

Severity = Literal["info", "warning", "error"]
"""Severity of a diagnostic; its exact meaning is defined per source."""

DiagnosticSource = Literal["interpreter", "heuristic-linter"]
"""Stable name of a diagnostics provider (`ProviderDiagnostic.source`)."""


@dataclass(frozen=True, slots=True)
class SourceFile:
    """One Maude source file: where it is, and its text as the rules see it.

    `path` is the platform path type (`.name`, `.suffix`, `.parent` are available to
    messages and rules); `text` is the file's content read for the text-based
    providers. The interpreter provider ignores `text` and loads from `path`, like the
    Maude CLI.
    """

    path: Path
    text: str

    @classmethod
    def from_path(cls, path: str | Path) -> SourceFile:
        """Read a Maude source file for diagnostics.

        Rejects anything that is not a regular file (missing, directory, device, FIFO,
        broken symlink) before reading, then reads with
        `Path.read_text(encoding="utf-8", errors="replace")` — lossy for undecodable
        bytes, and newline-normalizing, so lines are the file's physical lines.

        Raises:
            SourceFileNotFoundError: the path is missing, not a regular file, or
                cannot be read.
        """
        source_path = Path(path)
        if not source_path.is_file():
            raise SourceFileNotFoundError(source_path)
        try:
            text = source_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:  # permissions, races, unreadable device
            raise SourceFileNotFoundError(source_path) from exc
        return cls(path=source_path, text=text)


@dataclass(frozen=True, slots=True)
class FixEdit:
    """One replacement in the source text; `end_column` is exclusive."""

    line: int
    start_column: int
    end_column: int
    new_text: str


@dataclass(frozen=True, slots=True)
class FixSuggestion:
    """A deterministic correction: what it does, and the edits that apply it."""

    description: str
    edits: tuple[FixEdit, ...]


@dataclass(frozen=True, slots=True)
class ProviderDiagnostic:
    """A problem reported by a provider, in provider-native terms.

    Positions are 1-based provider coordinates: `line=None` means a whole-file problem,
    `column=None` means the producer reports no columns, and `end_column` (exclusive) is
    only set when the producer knows a span. The wire adapter converts them.
    """

    source: DiagnosticSource
    severity: Severity
    code: str
    message: str
    line: int | None = None
    column: int | None = None
    end_column: int | None = None
    fix: FixSuggestion | None = None

    def __post_init__(self) -> None:
        """Reject positions that cannot be interpreted.

        A rule that miscounts columns must fail loudly (in tests) instead of producing
        nonsense positions for clients.
        """
        if self.line is None and self.column is not None:
            raise ValueError("a diagnostic without a line cannot carry a column")  # noqa: TRY003 - position invariant
        if self.column is None and self.end_column is not None:
            raise ValueError("end_column requires column")  # noqa: TRY003 - position invariant
        for name, value in (("column", self.column), ("end_column", self.end_column)):
            if value is not None and value < 1:
                raise ValueError(f"{name} must be 1-based, got {value}")  # noqa: TRY003 - position invariant


class DiagnosticsError(RuntimeError):
    """Base error for failures of the diagnostics subsystem."""


class SourceFileNotFoundError(DiagnosticsError):
    """The Maude source file to diagnose is missing or unreadable."""

    path: Path

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"Maude program file not found or unreadable: {str(path)!r}")


class DiagnosticProviderError(DiagnosticsError):
    """A provider could not produce diagnostics; wraps the underlying failure."""

    def __init__(self, source: DiagnosticSource, reason: str) -> None:
        self.source = source
        self.reason = reason
        super().__init__(f"{source}: {reason}")


class DiagnosticProvider(Protocol):
    """A producer of diagnostics for one Maude source file.

    Implementations raise `DiagnosticProviderError` when they cannot produce
    diagnostics, chaining the underlying failure (`raise ... from`).
    """

    @property
    def name(self) -> DiagnosticSource:
        """Stable name of the provider, stamped on every diagnostic it reports."""
        ...

    def diagnose(self, source: SourceFile) -> list[ProviderDiagnostic]:
        """Return the diagnostics found in `source`.

        Text-based providers use `source.text`; the interpreter provider uses
        `source.path`.
        """
        ...
