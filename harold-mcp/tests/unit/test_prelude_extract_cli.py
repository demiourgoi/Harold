"""Unit tests for the `harold-update-prelude-sorts` CLI (run in-process)."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from harold_mcp.heuristic.prelude_extract import app


def _synthetic_prelude(names: int = 60) -> str:
    declarations = " ".join(f"Sort{index}" for index in range(names))
    return f"fmod SAMPLE is\n    sorts {declarations} .\nendfm\n"


def _load(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"snapshot_{path.stem}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(*args: str) -> None:
    """Run the CLI in-process and assert it succeeded (cyclopts exits 0 after the command)."""
    with pytest.raises(SystemExit) as exc_info:
        app(list(args))
    assert exc_info.value.code in (None, 0)


def test_cli_writes_a_loadable_snapshot(tmp_path: Path) -> None:
    prelude = tmp_path / "Maude-3.5.1-linux-x86_64" / "prelude.maude"
    prelude.parent.mkdir()
    _ = prelude.write_text(_synthetic_prelude())
    output = tmp_path / "prelude_sorts.py"

    _run(str(prelude), "--output", str(output))

    module = _load(output)
    assert len(module.PRELUDE_SORTS) == 60
    assert module.PRELUDE_SORTS["Sort0"] == "SAMPLE"
    assert frozenset(f"Sort{index}" for index in range(60)) == module.PRELUDE_SORT_BASES
    header = output.read_text(encoding="utf-8")
    assert "Maude version: 3.5.1" in header  # inferred from the path
    assert "Content: 60 sort names declared by 1 modules" in header


def test_cli_records_an_explicit_maude_version(tmp_path: Path) -> None:
    prelude = tmp_path / "prelude.maude"
    _ = prelude.write_text(_synthetic_prelude())
    output = tmp_path / "prelude_sorts.py"

    _run(str(prelude), "--output", str(output), "--maude-version", "9.9.9")

    assert "Maude version: 9.9.9" in output.read_text(encoding="utf-8")


def test_cli_regeneration_is_byte_stable(tmp_path: Path) -> None:
    prelude = tmp_path / "prelude.maude"
    _ = prelude.write_text(_synthetic_prelude())
    output = tmp_path / "prelude_sorts.py"
    _run(str(prelude), "--output", str(output))
    first = output.read_bytes()

    _run(str(prelude), "--output", str(output))

    assert output.read_bytes() == first


def test_cli_check_passes_on_a_fresh_snapshot(tmp_path: Path) -> None:
    prelude = tmp_path / "prelude.maude"
    _ = prelude.write_text(_synthetic_prelude())
    output = tmp_path / "prelude_sorts.py"
    _run(str(prelude), "--output", str(output))

    _run(str(prelude), "--output", str(output), "--check")


def test_cli_check_fails_on_a_modified_snapshot(tmp_path: Path) -> None:
    prelude = tmp_path / "prelude.maude"
    _ = prelude.write_text(_synthetic_prelude())
    output = tmp_path / "prelude_sorts.py"
    _run(str(prelude), "--output", str(output))
    _ = output.write_text("PRELUDE_SORTS: dict[str, str] = {}\nPRELUDE_SORT_BASES: frozenset[str] = frozenset()\n")

    with pytest.raises(SystemExit, match="is out of date"):
        app([str(prelude), "--output", str(output), "--check"])


def test_cli_refuses_a_junk_extraction(tmp_path: Path) -> None:
    prelude = tmp_path / "junk.maude"
    _ = prelude.write_text("fmod SAMPLE is\n    sorts OnlyOne .\nendfm\n")
    output = tmp_path / "prelude_sorts.py"

    with pytest.raises(SystemExit, match="Refusing a snapshot with only 1 sort names"):
        app([str(prelude), "--output", str(output)])

    assert not output.exists()


def test_cli_rejects_a_missing_prelude(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="Not a Maude prelude file"):
        app([str(tmp_path / "nope.maude"), "--output", str(tmp_path / "out.py")])
