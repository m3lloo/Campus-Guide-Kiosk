"""
Logging configuration for Campus Guide Kiosk.
Provides structured logging with rotating file handlers and console output.
"""

import logging
import logging.handlers
import os
from config import config


def setup_logging(log_file: str = "logs/app.log") -> logging.Logger:
    """
    Configure centralized logging for the application.

    Args:
        log_file: Path to log file. Creates logs directory if needed.

    Returns:
        Configured logger instance.
    """
    # Create logs directory if it doesn't exist
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    # Create logger
    logger = logging.getLogger("campus_guide_kiosk")
    logger.setLevel(getattr(logging, config.app.log_level, logging.INFO))

    # Prevent duplicate handlers
    if logger.handlers:
        return logger

    # Format for log messages
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler (always show) - UTF-8 encoding for emoji support
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    if hasattr(console_handler, "stream") and hasattr(
        console_handler.stream, "reconfigure"
    ):
        try:
            console_handler.stream.reconfigure(encoding="utf-8")
        except:
            pass
    logger.addHandler(console_handler)

    # File handler with rotation (max 10MB per file, keep 5 backups) - UTF-8 encoding
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"  # 10MB
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except (IOError, OSError) as e:
        logger.warning(f"Could not create file handler for {log_file}: {e}")

    return logger


# Create global logger
logger = setup_logging()


def get_logger(name: str = "campus_guide_kiosk") -> logging.Logger:
    """Get logger instance."""
    return logging.getLogger(name)


def log_api_call(
    endpoint: str,
    method: str,
    status_code: int,
    duration_ms: float,
    user_query: str = None,
):
    """Log API calls with metrics."""
    msg = f"API {method} {endpoint} - Status: {status_code} - Duration: {duration_ms:.2f}ms"
    if user_query:
        msg += f" - Query: {user_query[:50]}..."
    logger.info(msg)


def log_error(error_type: str, error_msg: str, details: str = None):
    """Log errors with context."""
    msg = f"ERROR [{error_type}]: {error_msg}"
    if details:
        msg += f" - Details: {details}"
    logger.error(msg)
