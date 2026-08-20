# Data Models

<!-- tags: data-models, types -->

## Domain models

None yet. The project is in its early stages; there are no business/domain data structures. The only data handled today is the Maude term produced in the `greet` tool.

## Framework types in use

| Type | Origin | Used in |
| --- | --- | --- |
| `FastMCP` | `fastmcp` | `server.py` — the server instance |
| `Icon` | `mcp.types` | `resources.py` — server branding |
| `Image` | `fastmcp.utilities.types` | `resources.py` — converts the logo to a data URI |
| Maude `Module` / `Term` | `maude` bindings | `server.py` — `getModule("NAT")`, `parseTerm(...)`, `reduce()` |

## Typing conventions

- `mypy` is configured strictly (`disallow_untyped_defs = true`, `no_implicit_optional = true`); all new functions and methods require full type annotations.
- The `maude` bindings ship no type stubs; `pyproject.toml` contains a mypy override with `ignore_missing_imports = true` for the `maude` module, so Maude-related code is effectively untyped from mypy's perspective.

## Related documents

- `interfaces.md` — how these types cross module boundaries
- `dependencies.md` — where the types come from
