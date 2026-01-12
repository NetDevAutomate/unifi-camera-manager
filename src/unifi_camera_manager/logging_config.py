"""Logging configuration for UniFi Camera Manager.

This module provides file-based logging configuration. When logging is enabled
(via --log-file or log level), logs are written only to the specified file,
not to stdout/stderr.
"""

import logging
from pathlib import Path


def setup_logging(
    log_file: Path | str | None = None,
    log_level: str = "INFO",
    name: str = "ucam",
) -> logging.Logger:
    """Configure logging to file only (not stdout).

    Args:
        log_file: Path to log file. If None, logging is disabled.
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        name: Logger name.

    Returns:
        Configured logger instance.

    Example:
        >>> logger = setup_logging(log_file="/tmp/ucam.log", log_level="DEBUG")
        >>> logger.info("Camera operation started")
    """
    logger = logging.getLogger(name)

    # Remove any existing handlers
    logger.handlers.clear()

    if log_file is None:
        # Logging disabled - add null handler to prevent "No handler" warnings
        logger.addHandler(logging.NullHandler())
        logger.setLevel(logging.WARNING)
        return logger

    # Convert to Path if string
    if isinstance(log_file, str):
        log_file = Path(log_file)

    # Ensure parent directory exists
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # Set log level
    level = getattr(logging, log_level.upper(), logging.INFO)
    logger.setLevel(level)

    # Create file handler (not stdout)
    file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    file_handler.setLevel(level)

    # Create formatter with timestamp, level, and message
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)

    # Add handler to logger
    logger.addHandler(file_handler)

    # Don't propagate to root logger (prevents stdout output)
    logger.propagate = False

    return logger


def get_logger(name: str = "ucam") -> logging.Logger:
    """Get existing logger by name.

    Args:
        name: Logger name.

    Returns:
        Logger instance (may be unconfigured if setup_logging not called).
    """
    return logging.getLogger(name)


# Global logger instance (configured on first use)
_logger: logging.Logger | None = None


def configure_global_logger(
    log_file: Path | str | None = None,
    log_level: str = "INFO",
) -> logging.Logger:
    """Configure the global logger instance.

    Args:
        log_file: Path to log file. If None, logging is disabled.
        log_level: Log level string.

    Returns:
        Configured global logger.
    """
    global _logger
    _logger = setup_logging(log_file=log_file, log_level=log_level)
    return _logger


def log_debug(message: str) -> None:
    """Log debug message if logging is configured."""
    if _logger:
        _logger.debug(message)


def log_info(message: str) -> None:
    """Log info message if logging is configured."""
    if _logger:
        _logger.info(message)


def log_warning(message: str) -> None:
    """Log warning message if logging is configured."""
    if _logger:
        _logger.warning(message)


def log_error(message: str) -> None:
    """Log error message if logging is configured."""
    if _logger:
        _logger.error(message)


def log_exception(message: str) -> None:
    """Log exception with traceback if logging is configured."""
    if _logger:
        _logger.exception(message)
