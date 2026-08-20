# Interfaces

<!-- tags: interfaces, api, entry-points, mcp -->

## External interfaces

### MCP server (stdio)

- **Transport**: stdio (FastMCP default via `mcp.run()`).
- **Server name**: `Harold`, with the packaged logo as icon.
- **Tools**:
  - `greet(name: str) -> str` — hello-world tool; loads Maude module `NAT`, parses `2 * 3`, reduces it, and returns `Result = <term>`.

```mermaid
sequenceDiagram
    participant C as MCP client<br>(IDE / AI agent)
    participant S as harold_mcp.server<br>(FastMCP over stdio)
    participant M as Maude runtime
    C->>S: tool call: greet(name)
    S->>M: getModule("NAT")
    S->>M: parseTerm("2 * 3") / reduce()
    M-->>S: reduced term
    S-->>C: "Result = 6"
```

### Console script

- **`harold-mcp`** → `harold_mcp.main:run` (declared in `pyproject.toml` `[project.scripts]`).
- Intended for installation as a command for MCP clients (Zed, opencode, Cline configuration examples live in `README.md`).

## Internal Python interfaces

- `harold_mcp.server.mcp` — the shared `FastMCP` instance. Modules register tools on it via `@mcp.tool`.
- `harold_mcp.resources.HAROLD_ICON` — `mcp.types.Icon` used for server branding.
- `harold_mcp.logging.get_logger` — re-exported logging helper (module-level loggers like `_LOG = get_logger(__name__)`).
- `harold_mcp.logging.Logging` — base class providing a per-class `_log` property.

## Import-time side effects (important)

Importing `harold_mcp.server`:

1. Initializes the Maude runtime (`maude.init()`).
2. Constructs the global `mcp` server instance.
3. Registers the `greet` tool.

Any code that imports `harold_mcp.server` triggers all three; keep Maude-related imports inside `server.py` or be aware of this cost.

## Related documents

- `components.md` — module responsibilities
- `workflows.md` — end-to-end flows
