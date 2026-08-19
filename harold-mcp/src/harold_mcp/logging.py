import logging
from typing import Protocol

from fastmcp.utilities.logging import get_logger


class Logging(Protocol):  # pylint: disable=too-few-public-methods
    """Adds a `log` property for the class logger to classes
    that extend this Protocol."""

    @property
    def _log(self) -> logging.Logger:
        """The logger for this class"""
        return get_logger(self.__class__.__name__)
