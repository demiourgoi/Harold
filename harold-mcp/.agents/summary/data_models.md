# Data Models

<!-- tags: data-models, types -->

## Result models (the tool's output schema)

Defined in `harold_mcp.server.tools.diagnostics` (pydantic `BaseModel`s inheriting the
private `_ResultModel` base — see below); FastMCP derives the output JSON Schema from the
return annotation and emits both `structuredContent` and a JSON text block.

| Model | Field | Type | Notes |
| --- | --- | --- | --- |
| `MaudePosition` | `line` | `int` | 1-based; always present when a range exists |
| | `column` | `int \| None` | `None` when the producer reports no columns (Maude interpreter) |
| `MaudeRange` | `start` | `MaudePosition` | required |
| | `end` | `MaudePosition \| None` | exclusive; `None` when only a line is known |
| `MaudeTextEdit` | `range` | `MaudeRange` | exclusive `end`, always populated |
| | `new_text` | `str` | the replacement text |
| `MaudeFix` | `description` | `str` | short description of the correction |
| | `edits` | `list[MaudeTextEdit]` | disjoint replacements; safe to apply in any order |
| `MaudeDiagnostic` | `severity` | `Literal["info", "warning", "error"]` | `"error"` only from `ok=False`; `"info"` for non-load-affecting observations |
| | `source` | `Literal["interpreter", "heuristic-linter"]` | provenance; the seam's `DiagnosticSource` alias |
| | `code` | `str` | `"compiler"` or the heuristic rule name (open set) |
| | `range` | `MaudeRange \| None` | `None` = whole-file problem |
| | `message` | `str` | free text, with the explanation/fix hint for linter findings |
| | `fix` | `MaudeFix \| None` | report-only correction; the tool never applies it |
| `MaudeDiagnosticsSummary` | `info` / `warning` / `error` | `int` | per-severity counts |
| `MaudeProgramDiagnosticsResult` | `path` | `str` | echo of the input path as given |
| | `success` | `bool` | true iff no `warning` and no `error` (info-only succeeds) |
| | `summary` | `MaudeDiagnosticsSummary` | |
| | `diagnostics` | `list[MaudeDiagnostic]` | file order: line, provider, column; whole-file last |

### Field docs: `_ResultModel` and `use_attribute_docstrings`

All seven result models inherit from a private `_ResultModel` base (never `BaseModel`
directly), which enables pydantic's attribute docstrings:

```python
class _ResultModel(BaseModel):
    """Base for the tool result models.

    Attribute docstrings are promoted to JSON Schema field descriptions, so they
    reach MCP clients through the tool's output schema.
    """

    model_config = ConfigDict(use_attribute_docstrings=True)


class MaudeDiagnostic(_ResultModel):
    """A single problem found in a Maude source file."""

    severity: Severity
    """`"info"` for observations that do not affect the load, `"warning"` for problems that may be
    real, `"error"` for definite failures; the meaning depends on `source`."""
```

- **Effect**: the string literal that follows a field becomes that field's JSON Schema
  `description`. FastMCP inlines `$ref`/`$defs` when serving, so these descriptions reach
  MCP clients in the tool's output schema; mkdocstrings also renders them in the API docs.
  Plain trailing `#` comments (the previous style) reach neither.
- **Convention**: new result models must inherit `_ResultModel` (the config is inherited)
  and carry a docstring on the line right after each field. Pydantic extracts attribute
  docstrings by inspecting the class source, so the module must be imported normally
  (no source available — e.g. `exec`'d code — means no descriptions).
- `Field(description=...)`/`Annotated` would work too but are not used here: attribute
  docstrings keep one copy of each explanation for both docs and schema.
- The `_ResultModel` name is private, so mkdocstrings (default filters) does not render it,
  and the base itself never appears in the output schema.

## Provider seam types

Defined in `harold_mcp.diagnostics` (plain stdlib dataclasses — no pydantic, no framework
types; the tool adapts them to the wire models):

| Type | Kind | Fields / shape |
| --- | --- | --- |
| `Severity` | `Literal` alias | `"info" \| "warning" \| "error"` |
| `DiagnosticSource` | `Literal` alias | `"interpreter" \| "heuristic-linter"` |
| `SourceFile` | frozen slotted dataclass | `path: Path`, `text: str`; `from_path()` rejects non-regular files, reads `utf-8`/`errors="replace"` (lossy, newline-normalizing) |
| `FixEdit` | frozen slotted dataclass | `line`, `start_column`, exclusive `end_column`, `new_text` |
| `FixSuggestion` | frozen slotted dataclass | `description: str`, `edits: tuple[FixEdit, ...]` |
| `ProviderDiagnostic` | frozen slotted dataclass | `source`, `severity`, `code`, `message`, optional `line`/`column`/`end_column` (1-based), optional `fix`; `__post_init__` enforces position invariants |
| `ProviderFailure` | frozen slotted dataclass | `provider: DiagnosticSource`, `error: BaseException` |
| `DiagnosticProvider` | `Protocol` | `name` property + `diagnose(source) -> list[ProviderDiagnostic]` |

`ProviderDiagnostic` positions are provider-native: `line=None` means whole-file,
`column=None` means "no columns reported", and `end_column` is only set when the producer
knows a span. The tool converts them once (`_to_range`, `_to_text_edit`, `_to_fix`).

## Linter-internal types

Defined in `harold_mcp.heuristic` (plain dataclasses, no framework types):

| Type | Fields / shape |
| --- | --- |
| `CodeLine` | `number: int` (1-based), `code: str` (masked, same length as the source line) |
| `Declarations` | `variables`, `operators`, `sort_references` (frozensets) |
| `SourceView` | `lines`, `sort_declarations`, `declarations`; `from_text()`; `sort_bases` property |
| `SortDeclaration` | `name` (as written, e.g. `List{X}`), `line`, `column`, `module: str \| None` |
| `RuleFinding` | `message`, `line`, `column`, `end_column`, `fix` |
| `Rule` | `code: str`, `severity: Severity`, `detect: Callable[[SourceView], list[RuleFinding]]` |
| `PRELUDE_SORTS` | `dict[str, str]` — prelude sort name → declaring module (generated) |
| `PRELUDE_SORT_BASES` | `frozenset[str]` — the same names without parameters (generated) |

## Worker protocol types

Defined in `harold_mcp.maude.worker` (TypedDicts; plain dicts cross the process boundary):

- `WarningDict` — `{line: int | None, message: str}`.
- `LoadDiagnosticsResult` — `{ok: bool, warnings: list[WarningDict]}`. `ok` is the
  `maude.load` return value: `True` for every parseable input (Maude recovers from
  arbitrary garbage), `False` for missing files / unrecoverable parse failures.

## Error hierarchies

Two independent hierarchies meet at the interpreter provider boundary, where a
`MaudeWorkerError` is wrapped with `raise ... from` (the Maude error stays as `__cause__`).

### Diagnostics (`harold_mcp.diagnostics`)

| Type | Base | Attributes | Raised by |
| --- | --- | --- | --- |
| `DiagnosticsError` | `RuntimeError` | — | base for failures of the diagnostics subsystem |
| `SourceFileNotFoundError` | `DiagnosticsError` | `path: Path` | `SourceFile.from_path` — the tool's input is missing/unreadable |
| `DiagnosticProviderError` | `DiagnosticsError` | `source`, `reason` | a provider could not produce diagnostics (wraps the cause) |
| `DiagnosticCollectionError` | `DiagnosticsError` | `failures: tuple[ProviderFailure, ...]` | `collect_diagnostics` — at least one provider failed; the message names every failing provider |

### Maude worker (`harold_mcp.maude.executor`)

| Type | Base | Attributes | Raised by |
| --- | --- | --- | --- |
| `MaudeError` | `RuntimeError` | — | base for all worker-subsystem failures |
| `MaudeInitError` | `MaudeError` | — | `MaudeExecutor.start` warm-up failure (worker init) |
| `MaudeWorkerError` | `MaudeError` | `reason: str` | base for running-call failures |
| `MaudeWorkerCrashedError` | `MaudeWorkerError` | — | broken pool (submit time) or worker death mid-task |
| `MaudeWorkerTimeoutError` | `MaudeWorkerError` | — | call exceeded the configured timeout |

`MaudeFileNotFoundError` no longer exists (removed in 0.0.4): the tool's input error is
`SourceFileNotFoundError`, because a missing file is a diagnostics-tool concern, not an
interpreter error.

## Framework types in use

| Type | Origin | Used in |
| --- | --- | --- |
| `FastMCP` | `fastmcp` | `server/server.py` — the server instance |
| `Lifespan` (via `@lifespan`) | `fastmcp.server.lifespan` | `server/server.py` — the lifespan |
| `App` | `cyclopts` | `main.py` (server CLI) and `heuristic/prelude_extract.py` (snapshot CLI) |
| `Depends` | `fastmcp.dependencies` | tool + `get_maude_executor` (nested DI) |
| `ToolAnnotations` | `mcp.types` | tool annotations: full read-only profile (`readOnlyHint=True`, `destructiveHint=False`, `idempotentHint=True`, `openWorldHint=False`) — reaches clients over the wire |
| tags (`set[str]`) | `fastmcp` `@mcp.tool(tags=...)` | `tools/diagnostics.py` via `harold_tags` — server-side categorization only with mcp SDK 1.29 (not serialized to clients) |
| `Icon` / `Image` | `mcp.types` / `fastmcp.utilities.types` | `resources.py` — server branding |
| `BaseModel` / `ConfigDict` | `pydantic` | wire result models (`_ResultModel`) |
| `BaseSettings` / `Field` / `SettingsConfigDict` | `pydantic-settings` / `pydantic` | `settings.py` — env-var config |
| Maude `Module` / `Term` | `maude` bindings | worker process only |

## Tool-tag vocabulary

Defined in `harold_mcp.server.tags` (plain `str` constants, plus the `harold_tags` helper):

- `maude`, `programming` — domain tags, added to every tool by `harold_tags`.
- `diagnostics` — the current tool's functional category; `interpreter` and `docs` are
  reserved for the planned run/RAG tools.
- Note: tags are server-side only with mcp SDK 1.29 (visibility control via
  `mcp.enable`/`mcp.disable`); they are not part of the MCP wire format on spec 2025-06-18.

## Typing conventions

- `mypy` is the primary checker (strict: `disallow_untyped_defs = true`,
  `no_implicit_optional = true`); `basedpyright` runs a single complementary rule
  (`reportUnusedCallResult`) with everything else off.
- The `maude` bindings ship no type stubs; `pyproject.toml` overrides mypy with
  `ignore_missing_imports = true`, so Maude values are effectively `Any` — boundaries are
  narrowed explicitly (e.g. `ok = bool(maude.load(path))`; `cast` at the
  future-result boundary in `_run_task`).
- The diagnostics seam and the linter are pure stdlib: frozen slotted dataclasses for
  values, `Literal` aliases for closed vocabularies (`Severity`, `DiagnosticSource`),
  `Protocol` for the provider contract, `TypedDict` across the process boundary.
- FastMCP DI defaults (`Depends(...)` in signatures) need `# noqa: B008`; the
  `@lifespan` decorator replaces the deprecated `@asynccontextmanager` +
  `AsyncIterator` annotation.

## Related documents

- `interfaces.md` — how these types cross module boundaries
- `dependencies.md` — where the types come from
- `components.md` — the behavior of the modules that define these types
