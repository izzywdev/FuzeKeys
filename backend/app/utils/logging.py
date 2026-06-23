import os
import sys
from pathlib import Path
from loguru import logger
from typing import Dict, Any


def setup_logging():
    """Setup application logging configuration."""
    
    # Remove default logger
    logger.remove()
    
    # Get log level from environment
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    
    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Console logging format
    console_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )
    
    # File logging format
    file_format = (
        "{time:YYYY-MM-DD HH:mm:ss} | "
        "{level: <8} | "
        "{name}:{function}:{line} | "
        "{message}"
    )
    
    # Add console handler
    logger.add(
        sys.stdout,
        format=console_format,
        level=log_level,
        colorize=True,
        diagnose=True,
    )
    
    # Add file handler for general logs
    logger.add(
        log_dir / "fuzekeys.log",
        format=file_format,
        level=log_level,
        rotation="10 MB",
        retention="30 days",
        compression="zip",
        diagnose=True,
    )
    
    # Add separate file handler for errors
    logger.add(
        log_dir / "errors.log",
        format=file_format,
        level="ERROR",
        rotation="10 MB",
        retention="90 days",
        compression="zip",
        diagnose=True,
        backtrace=True,
    )
    
    # Add separate file handler for automation logs
    logger.add(
        log_dir / "automation.log",
        format=file_format,
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
        compression="zip",
        filter=lambda record: "automation" in record["extra"],
    )
    
    logger.info("Logging initialized", level=log_level)


def get_logger(name: str):
    """Get a logger instance with the given name."""
    return logger.bind(name=name)


def log_automation_event(event_type: str, details: Dict[str, Any], website: str = None):
    """Log automation-specific events."""
    logger.bind(automation=True).info(
        f"Automation {event_type}",
        event_type=event_type,
        website=website,
        details=details
    )


def log_security_event(event_type: str, user_id: int = None, details: Dict[str, Any] = None):
    """Log security-related events."""
    logger.warning(
        f"Security event: {event_type}",
        event_type=event_type,
        user_id=user_id,
        details=details or {}
    )


def log_api_request(method: str, endpoint: str, user_id: int = None, response_time: float = None):
    """Log API request information."""
    logger.info(
        f"API {method} {endpoint}",
        method=method,
        endpoint=endpoint,
        user_id=user_id,
        response_time=response_time
    )


def log_database_error(operation: str, table: str, error: Exception):
    """Log database operation errors."""
    logger.error(
        f"Database error in {operation} on {table}",
        operation=operation,
        table=table,
        error_type=type(error).__name__,
        error_message=str(error)
    )


def log_encryption_error(operation: str, error: Exception):
    """Log encryption/decryption errors."""
    logger.error(
        f"Encryption error in {operation}",
        operation=operation,
        error_type=type(error).__name__,
        error_message=str(error)
    ) 