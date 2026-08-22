# Data Models

<!-- tags: data-models, types -->

## Domain models

The project is in its early stages; the first domain types are the `harold_mcp.maude` error hierarchy:

| Type | Base | Attributes | Raised by |
| --- | --- | --- | --- |
| `MaudeError` | `RuntimeError` | — | base for all runtime wrapper failures |
| `MaudeInitError` | `MaudeError` | — | `init_maude()` when the interpreter fails to initialize |
| `MaudeLoadError` | `MaudeError` | `program_path: str` | `MaudeRuntime.load_program` when a program fails to load |
| `MaudeModuleNotFoundError` | `MaudeError` | `module_name: str` | `MaudeRuntime.get_module` when a module is not loaded |

Other data handled today: the Maude term produced in the `greet` tool, and the process-wide `MaudeRuntime` singleton (state-free; it only holds the interpreter lock).

## Framework types in use

| Type | Origin | Used in |
| --- | --- | --- |
| `FastMCP` | `fastmcp` | `server.py` — the server instance |
| `Icon` | `mcp.types` | `resources.py` — server branding |
| `Image` | `fastmcp.utilities.types` | `resources.py` — converts the logo to a data URI |
| Maude `Module` / `Term` | `maude` bindings | `harold_mcp.maude` / `server.py` — `getModule("NAT")`, `parseTerm(...)`, `reduce()` |

## Typing conventions

- `mypy` is configured strictly (`disallow_untyped_defs = true`, `no_implicit_optional = true`); all new functions and methods require full type annotations.
- The `maude` bindings ship no type stubs; `pyproject.toml` contains a mypy override with `ignore_missing_imports = true` for the `maude` module, so Maude-related code is effectively untyped from mypy's perspective (`get_module`/`load_module` return `Any`).

## Related documents

- `interfaces.md` — how these types cross module boundaries
- `dependencies.md` — where the types come from
- `components.md` — the behavior of `harold_mcp.maude`, which defines these types
