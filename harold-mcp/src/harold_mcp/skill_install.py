"""Install the bundled ``maude-manual`` agent skill."""

from importlib.resources import files
from pathlib import Path
from shutil import copytree, rmtree

SKILL_NAME = "maude-manual"


def skill_source() -> Path:
    """Return the path of the skill bundled with the ``harold_mcp`` package."""
    return Path(str(files("harold_mcp").joinpath("skills", SKILL_NAME)))


def install_skill(destination_base: Path, source: Path | None = None) -> Path:
    """Copy the bundled skill to ``destination_base / SKILL_NAME`` and return it.

    An existing installation is removed first, so re-running this after an
    upgrade is a full refresh: files dropped from a newer skill never survive.
    Nothing else inside ``destination_base`` is touched.
    """
    src = source if source is not None else skill_source()
    if not src.is_dir():
        msg = (
            f"The {SKILL_NAME} skill is missing from this harold-mcp installation "
            f"(expected {src}); the artifact was built without 'make skills'."
        )
        raise FileNotFoundError(msg)
    destination = destination_base / SKILL_NAME
    destination_base.mkdir(parents=True, exist_ok=True)
    if destination.is_dir():
        rmtree(destination)
    elif destination.exists():
        destination.unlink()
    _ = copytree(src, destination)
    return destination
