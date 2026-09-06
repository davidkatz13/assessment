import logging
import sys

from core.config import settings


def configure_logging() -> None:
    """Set up the root logger once, at process start."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(settings.log_level)


def get_logger(name: str) -> logging.Logger:
    """Return a module-scoped logger. Call configure_logging() once at startup first."""
    return logging.getLogger(name)
