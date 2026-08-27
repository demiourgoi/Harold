"""Harold MCP server: the FastMCP instance and its lifecycle.

Importing this module builds the `mcp` instance but does **not** initialize
Maude: the interpreter lives in a worker process managed by the server
lifespan (see `harold_mcp.maude`).
"""

import os
import signal
from collections.abc import AsyncGenerator
from types import FrameType
from typing import Any, NoReturn

from fastmcp import FastMCP
from fastmcp.server.lifespan import lifespan

from harold_mcp.logging import get_logger
from harold_mcp.maude import get_maude_executor
from harold_mcp.resources import HAROLD_ICON
from harold_mcp.settings import get_settings

_LOG = get_logger(__name__)


@lifespan
async def app_lifespan(_server: FastMCP) -> AsyncGenerator[dict[str, Any] | None]:
    """Warm up the Maude worker pool at startup and tear it down at exit.

    Fails fast: if Maude cannot initialize in the worker, `MaudeInitError`
    aborts server startup. Teardown always runs, even if the warm-up was
    interrupted.
    """
    executor = get_maude_executor(get_settings())
    try:
        executor.start()
        _LOG.info("Harold initialized with success!")
        yield None
    finally:
        executor.shutdown()


mcp = FastMCP(
    name="Harold",
    instructions="""Harold provides MCP tools for AI-assisted programming with the Maude specification and verification language, for LLM agents not sufficiently trained in Maude.
Its tools cover three areas:
- Diagnosing Maude programs (linters and other static checks)
- Running Maude programs
- Searching the Maude documentation via a vector index to support retrieval-augmented generation
Use Harold's tools whenever working with Maude code; consult each tool's description for how to call it.""",
    website_url="https://demiourgoi.github.io",
    icons=[HAROLD_ICON],
    lifespan=app_lifespan,
)


def _handle_shutdown_signal(_signum: int, _frame: FrameType | None) -> NoReturn:
    """Turn SIGTERM into KeyboardInterrupt so the running task is cancelled.

    FastMCP's `mcp.run()` installs no signal handling. Raising here makes the
    asyncio runner cancel the server task, which runs the lifespan's `finally`
    (pool teardown) before exiting.
    """
    raise KeyboardInterrupt


def run() -> None:
    """Run the MCP server over stdio."""
    _LOG.info("Initializing Harold...")
    _ = signal.signal(signal.SIGTERM, _handle_shutdown_signal)
    try:
        mcp.run()
    except KeyboardInterrupt:
        _LOG.info("Shutdown signal received")
        # The lifespan's finally has already torn the pool down. Exit hard:
        # FastMCP's stdio transport leaves a non-daemon worker thread blocked
        # reading stdin, and a normal interpreter shutdown would hang forever
        # joining it while the client is still connected.
        os._exit(0)
