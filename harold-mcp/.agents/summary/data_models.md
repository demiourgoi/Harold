# Data Models

<!-- tags: data-models, types -->

## Result models (the tool's output schema)

Defined in `harold_mcp.server.tools.diagnostics` (pydantic `BaseModel`s); FastMCP derives
the output JSON Schema from the return annotation and emits both `structuredContent` and a
JSON text block.

| Model | Field | Type | Notes |
| --- | --- | --- | --- |
| `MaudePosition` | `line` | `int` | 1-based; always present when a range exists |
| | `column` | `int \| None` | Maude reports no columns; reserved for future sources |
| `MaudeRange` | `start` | `MaudePosition` | required |
| | `end` | `MaudePosition \| None` | Maude reports no spans |
| `MaudeDiagnostic` | `severity` | `Literal["warning", "error"]` | "error" synthesized for `ok=False` |
| | `range` | `MaudeRange \| None` | `None` = whole-file problem |
| | `message` | `str` | free text from the Maude warning |
| `MaudeDiagnosticsSummary` | `warning` / `error` | `int` | per-severity counts |
| `MaudeProgramDiagnosticsResult` | `path` | `str` | echo of the input path as given |
| | `success` | `bool` | true iff no warnings and no errors |
| | `summary` | `MaudeDiagnosticsSummary` | |
| | `diagnostics` | `list[MaudeDiagnostic]` | in parse order |

## Worker protocol types

Defined in `harold_mcp.maude.worker` (TypedDicts; plain dicts cross the process boundary):

- `WarningDict` — `{line: int | None, message: str}`.
- `LoadDiagnosticsResult` — `{ok: bool, warnings: list[WarningDict]}`. `ok` is the
  `maude.load` return value: `True` for every parseable input (Maude recovers from
  arbitrary garbage), `False` for missing files / unrecoverable parse failures.

## Error hierarchy

Defined in `harold_mcp.maude.executor`:

| Type | Base | Attributes | Raised by |
| --- | --- | --- | --- |
| `MaudeError` | `RuntimeError` | — | base for all worker-subsystem failures |
| `MaudeInitError` | `MaudeError` | — | `MaudeExecutor.start` warm-up failure (worker init) |
| `MaudeWorkerError` | `MaudeError` | `reason: str` | base for running-call failures |
| `MaudeWorkerCrashedError` | `MaudeWorkerError` | — | broken pool (submit time) or worker death mid-task |
| `MaudeWorkerTimeoutError` | `MaudeWorkerError` | — | call exceeded the configured timeout |
| `MaudeFileNotFoundError` | `MaudeError` | `path: str` | tool pre-check: missing/unreadable input |

## Framework types in use

| Type | Origin | Used in |
| --- | --- | --- |
| `FastMCP` | `fastmcp` | `server/server.py` — the server instance |
| `Lifespan` (via `@lifespan`) | `fastmcp.server.lifespan` | `server/server.py` — the lifespan |
| `App` | `cyclopts` | `main.py` — the `harold-mcp` CLI (default + `serve` subcommand) |
| `Depends` | `fastmcp.dependencies` | tool + `get_maude_executor` (nested DI) |
| `ToolAnnotations` | `mcp.types` | tool annotations: full read-only profile (`readOnlyHint=True`, `destructiveHint=False`, `idempotentHint=True`, `openWorldHint=False`) — reaches clients over the wire |
| tags (`set[str]`) | `fastmcp` `@mcp.tool(tags=...)` | `tools/diagnostics.py` via `harold_tags` — server-side categorization only with mcp SDK 1.29 (not serialized to clients) |
| `Icon` / `Image` | `mcp.types` / `fastmcp.utilities.types` | `resources.py` — server branding |
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
- FastMCP DI defaults (`Depends(...)` in signatures) need `# noqa: B008`; the
  `@lifespan` decorator replaces the deprecated `@asynccontextmanager` +
  `AsyncIterator` annotation.

## Related documents

- `interfaces.md` — how these types cross module boundaries
- `dependencies.md` — where the types come from
- `components.md` — the behavior of the modules that define these types
