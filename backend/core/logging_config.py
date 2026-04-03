"""Centralized logging setup for ContractGuard (console only)."""

from __future__ import annotations

import logging
import sys
import warnings

from .config import Settings


warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic_settings")


class _Colors:
    RESET = "\033[0m"
    DEBUG = "\033[36m"
    INFO = "\033[32m"
    WARNING = "\033[33m"
    ERROR = "\033[31m"
    CRITICAL = "\033[35m"
    TIMESTAMP = "\033[90m"
    NAME = "\033[34m"


class _ColoredFormatter(logging.Formatter):
    LEVEL_COLORS = {
        logging.DEBUG: _Colors.DEBUG,
        logging.INFO: _Colors.INFO,
        logging.WARNING: _Colors.WARNING,
        logging.ERROR: _Colors.ERROR,
        logging.CRITICAL: _Colors.CRITICAL,
    }

    def format(self, record: logging.LogRecord) -> str:
        level_color = self.LEVEL_COLORS.get(record.levelno, _Colors.RESET)
        timestamp = self.formatTime(record, "%H:%M:%S")

        name_parts = record.name.split(".")
        if name_parts[0] in {"uvicorn", "httpx", "httpcore"}:
            name = name_parts[0][:15].ljust(15)
        else:
            name = name_parts[-1][:15].ljust(15)

        level = record.levelname[:5].ljust(5)
        parts = [
            f"{_Colors.TIMESTAMP}{timestamp}{_Colors.RESET}",
            f"{level_color}{level}{_Colors.RESET}",
            f"{_Colors.NAME}{name}{_Colors.RESET}",
            record.getMessage(),
        ]
        return " | ".join(parts)


class _NoiseFilter(logging.Filter):
    PATTERNS = (
        "pydantic",
        "Expected 10 fields",
        "StreamingChoices",
        "PydanticSerializationUnexpectedValue",
        "yaml_file",
        "model_config",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return not any(pattern in message for pattern in self.PATTERNS)


def _replace_handlers(logger: logging.Logger, handler: logging.Handler) -> None:
    for old_handler in list(logger.handlers):
        logger.removeHandler(old_handler)
        old_handler.close()
    logger.addHandler(handler)


def configure_logging(settings: Settings) -> None:
    """Configure application logging using a centralized backend module."""
    level = getattr(logging, settings.log_level, logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(_ColoredFormatter())
    handler.addFilter(_NoiseFilter())

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.WARNING)
    _replace_handlers(root_logger, handler)

    app_logger = logging.getLogger("contractguard")
    app_logger.setLevel(level)
    app_logger.propagate = False
    _replace_handlers(app_logger, handler)

    for noisy in ("pydantic", "pydantic_settings", "httpx", "httpcore", "litellm"):
        logging.getLogger(noisy).setLevel(logging.ERROR)

    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_logger.setLevel(level)
    uvicorn_logger.propagate = False
    _replace_handlers(uvicorn_logger, handler)

    logging.getLogger("contractguard.api").info("Logging configured at %s level", settings.log_level)
