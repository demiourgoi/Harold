from importlib import resources
from pathlib import Path

from fastmcp.utilities.types import Image
from mcp.types import Icon

HAROLD_RESOURCES = resources.files(__name__)
HAROLD_LOGO_PATH = HAROLD_RESOURCES.joinpath(Path("assets") / "brand" / "Harold_logo.png")

HAROLD_ICON = Icon(src=Image(path=str(HAROLD_LOGO_PATH)).to_data_uri())
