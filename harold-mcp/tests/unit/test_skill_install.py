"""Unit tests for the maude-manual skill installer and the `setup` command."""

from pathlib import Path

import pytest

from harold_mcp.skill_install import SKILL_NAME, install_skill, skill_source


@pytest.fixture
def source(tmp_path: Path) -> Path:
    """A minimal stand-in for the packaged skill."""
    src = tmp_path / "source" / SKILL_NAME
    (src / "chapters").mkdir(parents=True)
    (src / "SKILL.md").write_text("skill v1")
    (src / "chapters" / "ch01.md").write_text("chapter")
    return src


def test_fresh_install_copies_the_tree(source: Path, tmp_path: Path) -> None:
    installed = install_skill(tmp_path / "base", source)
    assert installed == tmp_path / "base" / SKILL_NAME
    assert (installed / "SKILL.md").read_text() == "skill v1"
    assert (installed / "chapters" / "ch01.md").is_file()


def test_reinstall_refreshes_and_drops_stale_files(source: Path, tmp_path: Path) -> None:
    base = tmp_path / "base"
    installed = install_skill(base, source)
    stale = installed / "stale.md"
    stale.write_text("from an older skill")
    (source / "SKILL.md").write_text("skill v2")
    assert install_skill(base, source) == installed
    assert not stale.exists()
    assert (installed / "SKILL.md").read_text() == "skill v2"


def test_reinstall_over_a_stray_file(source: Path, tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    (base / SKILL_NAME).write_text("not a directory")
    installed = install_skill(base, source)
    assert (installed / "SKILL.md").is_file()


def test_siblings_in_the_base_are_untouched(source: Path, tmp_path: Path) -> None:
    base = tmp_path / "base"
    other = base / "other-skill"
    other.mkdir(parents=True)
    (other / "SKILL.md").write_text("other")
    install_skill(base, source)
    assert (other / "SKILL.md").read_text() == "other"


def test_missing_source_raises_a_clear_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="make skills"):
        install_skill(tmp_path / "base", tmp_path / "nowhere")


def test_packaged_skill_source() -> None:
    src = skill_source()
    if not src.is_dir():  # dev checkout without `make skills`
        pytest.skip("packaged skill copy absent; run `make skills`")
    assert (src / "SKILL.md").is_file()


def test_cli_setup_directory(monkeypatch: pytest.MonkeyPatch, source: Path, tmp_path: Path) -> None:
    from harold_mcp import main

    monkeypatch.setattr(main, "install_skill", lambda base: install_skill(base, source))
    main.app(["setup", "--directory", str(tmp_path / "cli")], result_action="return_value")
    assert (tmp_path / "cli" / SKILL_NAME / "SKILL.md").is_file()


def test_cli_setup_global(monkeypatch: pytest.MonkeyPatch, source: Path, tmp_path: Path) -> None:
    from harold_mcp import main

    monkeypatch.setattr(main, "install_skill", lambda base: install_skill(base, source))
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    main.app(["setup", "-g"], result_action="return_value")
    assert (fake_home / ".agents" / "skills" / SKILL_NAME / "SKILL.md").is_file()
