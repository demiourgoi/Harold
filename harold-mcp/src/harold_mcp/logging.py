import logging

from fastmcp.utilities.logging import get_logger

__all__ = ["Logging", "get_logger"]


class Logging:
    """Adds a `_log` property that provides a logger for the concrete class."""

    @property
    def _log(self) -> logging.Logger:
        """The logger for this class"""
        return get_logger(self.__class__.__name__)
