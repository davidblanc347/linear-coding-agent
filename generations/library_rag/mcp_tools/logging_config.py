"""Structured JSON logging configuration for Library RAG MCP Server.

This module provides structured JSON logging with sensitive data filtering
and tool invocation tracking.

Features:
    - JSON-formatted log output for machine parsing
    - Sensitive data filtering (API keys, passwords)
    - Tool invocation logging with timing
    - Configurable log levels via environment variable

Example:
    Configure logging at server startup::

        from mcp_tools.logging_config import setup_mcp_logging, get_tool_logger

        # Setup logging
        logger = setup_mcp_logging(log_level="INFO")

        # Get tool-specific logger
        tool_logger = get_tool_logger("search_chunks")
        tool_logger.info("Processing query", extra={"query": "justice"})
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, Generator, Literal, Optional, TypeVar, cast

# Type variable for decorator return type preservation
F = TypeVar("F", bound=Callable[..., Any])

# =============================================================================
# Sensitive Data Patterns
# =============================================================================

# Patterns to detect sensitive data in log messages
SENSITIVE_PATTERNS = [
    # API keys
    (re.compile(r'(api[_-]?key\s*[=:]\s*)["\']?[\w-]{20,}["\']?', re.I), r"\1***REDACTED***"),
    (re.compile(r'(bearer\s+)[\w-]{20,}', re.I), r"\1***REDACTED***"),
    (re.compile(r'(authorization\s*[=:]\s*)["\']?[\w-]{20,}["\']?', re.I), r"\1***REDACTED***"),
    # Mistral API key format
    (re.compile(r'(MISTRAL_API_KEY\s*[=:]\s*)["\']?[\w-]+["\']?', re.I), r"\1***REDACTED***"),
    # Generic secrets
    (re.compile(r'(password\s*[=:]\s*)["\']?[^\s"\']+["\']?', re.I), r"\1***REDACTED***"),
    (re.compile(r'(secret\s*[=:]\s*)["\']?[\w-]+["\']?', re.I), r"\1***REDACTED***"),
    (re.compile(r'(token\s*[=:]\s*)["\']?[\w-]{20,}["\']?', re.I), r"\1***REDACTED***"),
]


def redact_sensitive_data(message: str) -> str:
    """Remove sensitive data from log messages.

    Args:
        message: The log message to sanitize.

    Returns:
        Sanitized message with sensitive data redacted.

    Example:
        >>> redact_sensitive_data("api_key=sk-12345abcdef")
        "api_key=***REDACTED***"
    """
    result = message
    for pattern, replacement in SENSITIVE_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def redact_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively redact sensitive data from a dictionary.

    Args:
        data: Dictionary that may contain sensitive data.

    Returns:
        New dictionary with sensitive values redacted.
    """
    sensitive_keys = {
        "api_key", "apikey", "api-key",
        "password", "passwd", "pwd",
        "secret", "token", "auth",
        "authorization", "bearer",
        "mistral_api_key", "MISTRAL_API_KEY",
    }

    result: Dict[str, Any] = {}
    for key, value in data.items():
        key_lower = key.lower().replace("-", "_")

        if key_lower in sensitive_keys or any(s in key_lower for s in ["key", "secret", "token", "password"]):
            result[key] = "***REDACTED***"
        elif isinstance(value, dict):
            result[key] = redact_dict(value)
        elif isinstance(value, str):
            result[key] = redact_sensitive_data(value)
        else:
            result[key] = value

    return result


# =============================================================================
# JSON Log Formatter
# =============================================================================


class JSONLogFormatter(logging.Formatter):
    """JSON formatter for structured logging.

    Outputs log records as single-line JSON objects with consistent structure.
    Automatically redacts sensitive data from messages and extra fields.

    JSON Structure:
        {
            "timestamp": "2024-12-24T10:30:00.000Z",
            "level": "INFO",
            "logger": "library-rag-mcp.search_chunks",
            "message": "Processing query",
            "tool": "search_chunks",
            "duration_ms": 123,
            ...extra fields...
        }
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as JSON.

        Args:
            record: The log record to format.

        Returns:
            JSON-formatted log string.
        """
        # Base log structure
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_sensitive_data(record.getMessage()),
        }

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Add extra fields (excluding standard LogRecord attributes)
        standard_attrs = {
            "name", "msg", "args", "levelname", "levelno", "pathname",
            "filename", "module", "lineno", "funcName", "created",
            "msecs", "relativeCreated", "thread", "threadName",
            "processName", "process", "exc_info", "exc_text", "stack_info",
            "message", "taskName",
        }

        for key, value in record.__dict__.items():
            if key not in standard_attrs and not key.startswith("_"):
                if isinstance(value, dict):
                    log_entry[key] = redact_dict(value)
                elif isinstance(value, str):
                    log_entry[key] = redact_sensitive_data(value)
                else:
                    log_entry[key] = value

        return json.dumps(log_entry, default=str, ensure_ascii=False)


# =============================================================================
# Logging Setup
# =============================================================================


def setup_mcp_logging(
    log_level: str = "INFO",
    log_dir: Optional[Path] = None,
    json_format: bool = True,
) -> logging.Logger:
    """Configure structured logging for the MCP server.

    Sets up logging with JSON formatting to both file and stderr.
    Uses stderr for console output since stdout is used for MCP communication.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_dir: Directory for log files. Defaults to "logs".
        json_format: Use JSON formatting (default True).

    Returns:
        Configured logger instance for the MCP server.

    Example:
        >>> logger = setup_mcp_logging(log_level="DEBUG")
        >>> logger.info("Server started", extra={"port": 8080})
    """
    # Determine log directory
    if log_dir is None:
        log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    # Get or create the root MCP logger
    logger = logging.getLogger("library-rag-mcp")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Clear existing handlers to avoid duplicates
    logger.handlers.clear()

    # Create formatters
    if json_format:
        formatter: logging.Formatter = JSONLogFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    # File handler (JSON logs)
    file_handler = logging.FileHandler(
        log_dir / "mcp_server.log",
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)  # Log everything to file
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Stderr handler (for console output - stdout is for MCP)
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    stderr_handler.setFormatter(formatter)
    logger.addHandler(stderr_handler)

    # Prevent propagation to root logger
    logger.propagate = False

    return logger


def get_tool_logger(tool_name: str) -> logging.Logger:
    """Get a logger for a specific MCP tool.

    Creates a child logger under the main MCP logger with the tool name
    automatically included in log entries.

    Args:
        tool_name: Name of the MCP tool (e.g., "search_chunks", "parse_pdf").

    Returns:
        Logger instance for the tool.

    Example:
        >>> logger = get_tool_logger("search_chunks")
        >>> logger.info("Query processed", extra={"results": 10})
    """
    return logging.getLogger(f"library-rag-mcp.{tool_name}")


# =============================================================================
# Tool Invocation Logging
# =============================================================================


class ToolInvocationLogger:
    """Context manager for logging tool invocations with timing.

    Automatically logs tool start, success/failure, and duration.
    Handles exception logging and provides structured output.

    Example:
        >>> with ToolInvocationLogger("search_chunks", {"query": "justice"}) as inv:
        ...     result = do_search()
        ...     inv.set_result({"count": 10})
    """

    def __init__(
        self,
        tool_name: str,
        inputs: Dict[str, Any],
        logger: Optional[logging.Logger] = None,
    ) -> None:
        """Initialize the invocation logger.

        Args:
            tool_name: Name of the tool being invoked.
            inputs: Tool input parameters (will be redacted).
            logger: Logger to use. Defaults to tool-specific logger.
        """
        self.tool_name = tool_name
        self.inputs = redact_dict(inputs)
        self.logger = logger or get_tool_logger(tool_name)
        self.start_time: float = 0.0
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[Exception] = None

    def __enter__(self) -> "ToolInvocationLogger":
        """Start timing and log invocation start."""
        self.start_time = time.perf_counter()
        self.logger.info(
            f"Tool invocation started: {self.tool_name}",
            extra={
                "tool": self.tool_name,
                "event": "invocation_start",
                "inputs": self.inputs,
            },
        )
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Any,
    ) -> Literal[False]:
        """Log invocation completion with timing."""
        duration_ms = (time.perf_counter() - self.start_time) * 1000

        if exc_val is not None:
            # Log error
            self.logger.error(
                f"Tool invocation failed: {self.tool_name}",
                extra={
                    "tool": self.tool_name,
                    "event": "invocation_error",
                    "duration_ms": round(duration_ms, 2),
                    "error_type": exc_type.__name__ if exc_type else "Unknown",
                    "error_message": str(exc_val),
                },
                exc_info=True,
            )
            # Don't suppress the exception
            return False

        # Log success
        extra: Dict[str, Any] = {
            "tool": self.tool_name,
            "event": "invocation_success",
            "duration_ms": round(duration_ms, 2),
        }
        if self.result:
            extra["result_summary"] = self._summarize_result()

        self.logger.info(
            f"Tool invocation completed: {self.tool_name}",
            extra=extra,
        )
        return False

    def set_result(self, result: Dict[str, Any]) -> None:
        """Set the result for logging summary.

        Args:
            result: The tool result dictionary.
        """
        self.result = result

    def _summarize_result(self) -> Dict[str, Any]:
        """Create a summary of the result for logging.

        Returns:
            Dictionary with key result metrics (counts, success status, etc.)
        """
        if not self.result:
            return {}

        summary: Dict[str, Any] = {}

        # Common summary fields
        if "success" in self.result:
            summary["success"] = self.result["success"]
        if "total_count" in self.result:
            summary["total_count"] = self.result["total_count"]
        if "results" in self.result and isinstance(self.result["results"], list):
            summary["result_count"] = len(self.result["results"])
        if "chunks_count" in self.result:
            summary["chunks_count"] = self.result["chunks_count"]
        if "cost_total" in self.result:
            summary["cost_total"] = self.result["cost_total"]
        if "found" in self.result:
            summary["found"] = self.result["found"]
        if "error" in self.result and self.result["error"]:
            summary["error"] = self.result["error"]

        return summary


@contextmanager
def log_tool_invocation(
    tool_name: str,
    inputs: Dict[str, Any],
) -> Generator[ToolInvocationLogger, None, None]:
    """Context manager for logging tool invocations.

    Convenience function that creates and manages a ToolInvocationLogger.

    Args:
        tool_name: Name of the tool being invoked.
        inputs: Tool input parameters.

    Yields:
        ToolInvocationLogger instance for setting results.

    Example:
        >>> with log_tool_invocation("search_chunks", {"query": "test"}) as inv:
        ...     result = search(query)
        ...     inv.set_result(result)
    """
    logger_instance = ToolInvocationLogger(tool_name, inputs)
    with logger_instance as inv:
        yield inv


def log_weaviate_query(
    operation: str,
    collection: str,
    filters: Optional[Dict[str, Any]] = None,
    result_count: Optional[int] = None,
    duration_ms: Optional[float] = None,
) -> None:
    """Log a Weaviate query operation.

    Utility function for logging Weaviate database queries with consistent
    structure.

    Args:
        operation: Query operation type (fetch, near_text, aggregate, etc.).
        collection: Weaviate collection name.
        filters: Query filters applied (optional).
        result_count: Number of results returned (optional).
        duration_ms: Query duration in milliseconds (optional).

    Example:
        >>> log_weaviate_query(
        ...     operation="near_text",
        ...     collection="Chunk",
        ...     filters={"author": "Platon"},
        ...     result_count=10,
        ...     duration_ms=45.2
        ... )
    """
    logger = logging.getLogger("library-rag-mcp.weaviate")

    extra: Dict[str, Any] = {
        "event": "weaviate_query",
        "operation": operation,
        "collection": collection,
    }

    if filters:
        extra["filters"] = redact_dict(filters)
    if result_count is not None:
        extra["result_count"] = result_count
    if duration_ms is not None:
        extra["duration_ms"] = round(duration_ms, 2)

    logger.debug(f"Weaviate {operation} on {collection}", extra=extra)
