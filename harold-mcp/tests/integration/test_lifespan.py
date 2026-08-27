"""Tests for the server lifespan (pool warm-up / teardown, fail-fast)."""

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest

from harold_mcp.maude import MaudeInitError, get_maude_executor
from harold_mcp.server import server as server_module
from harold_mcp.settings import get_settings

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class FakeExecutor:
    def __init__(self) -> None:
        self.start_called = 0
        self.shutdown_called = 0
        self.fail_start = False

    def start(self) -> None:
        self.start_called += 1
        if self.fail_start:
            raise MaudeInitError()

    def shutdown(self) -> None:
        self.shutdown_called += 1


@pytest.fixture
def fake_executor(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeExecutor]:
    fake = FakeExecutor()
    monkeypatch.setattr(server_module, "get_maude_executor", lambda settings: fake)
    yield fake


def test_lifespan_starts_and_shuts_down_the_pool(fake_executor: FakeExecutor) -> None:
    async def _exercise() -> None:
        async with server_module.app_lifespan(None):
            assert fake_executor.start_called == 1
            assert fake_executor.shutdown_called == 0

    asyncio.run(_exercise())
    assert fake_executor.start_called == 1
    assert fake_executor.shutdown_called == 1


def test_lifespan_fails_fast_on_init_error(fake_executor: FakeExecutor) -> None:
    fake_executor.fail_start = True

    async def _exercise() -> None:
        async with server_module.app_lifespan(None):
            pytest.fail("lifespan must not enter when the warm-up fails")

    with pytest.raises(MaudeInitError):
        asyncio.run(_exercise())
    assert fake_executor.shutdown_called == 1  # teardown still runs on the failed pool


def test_lifespan_drives_the_real_pool() -> None:
    """The lifespan drives the real executor: warm-up spawns a worker, exit kills it."""

    async def _exercise() -> None:
        async with server_module.app_lifespan(None):
            result = get_maude_executor(get_settings()).diagnostics(str(FIXTURES_DIR / "hello.maude"))
            assert result == {"ok": True, "warnings": []}

    asyncio.run(_exercise())
