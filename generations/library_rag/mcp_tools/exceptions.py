"""Custom exception classes for Library RAG MCP Server.

This module defines custom exception classes used throughout the MCP server
for structured error handling and consistent error responses.

Exception Hierarchy:
    MCPToolError (base)
    ├── WeaviateConnectionError - Database connection failures
    ├── PDFProcessingError - PDF parsing/OCR failures
    ├── DocumentNotFoundError - Document/chunk retrieval failures
    └── ValidationError - Input validation failures

Example:
    Raise and catch custom exceptions::

        from mcp_tools.exceptions import WeaviateConnectionError

        try:
            client = connect_to_weaviate()
        except Exception as e:
            raise WeaviateConnectionError("Failed to connect") from e
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class MCPToolError(Exception):
    """Base exception for all MCP tool errors.

    This is the base class for all custom exceptions in the MCP server.
    It provides structured error information that can be converted to
    MCP error responses.

    Attributes:
        message: Human-readable error description.
        error_code: Machine-readable error code for categorization.
        details: Additional context about the error.
        original_error: The underlying exception if this wraps another error.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "MCP_ERROR",
        details: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None,
    ) -> None:
        """Initialize the MCPToolError.

        Args:
            message: Human-readable error description.
            error_code: Machine-readable error code (default: "MCP_ERROR").
            details: Additional context about the error (optional).
            original_error: The underlying exception if wrapping (optional).
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.original_error = original_error

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to a dictionary for JSON serialization.

        Returns:
            Dictionary with error information suitable for MCP responses.
        """
        result: Dict[str, Any] = {
            "error": True,
            "error_code": self.error_code,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        if self.original_error:
            result["original_error"] = str(self.original_error)
        return result

    def __str__(self) -> str:
        """Return string representation of the error."""
        if self.original_error:
            return f"[{self.error_code}] {self.message} (caused by: {self.original_error})"
        return f"[{self.error_code}] {self.message}"


class WeaviateConnectionError(MCPToolError):
    """Raised when Weaviate database connection fails.

    This exception is raised when the MCP server cannot establish or
    maintain a connection to the Weaviate vector database.

    Example:
        >>> raise WeaviateConnectionError(
        ...     "Cannot connect to Weaviate at localhost:8080",
        ...     details={"host": "localhost", "port": 8080}
        ... )
    """

    def __init__(
        self,
        message: str = "Failed to connect to Weaviate",
        *,
        details: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None,
    ) -> None:
        """Initialize WeaviateConnectionError.

        Args:
            message: Error description (default: "Failed to connect to Weaviate").
            details: Additional context (host, port, etc.).
            original_error: The underlying connection exception.
        """
        super().__init__(
            message,
            error_code="WEAVIATE_CONNECTION_ERROR",
            details=details,
            original_error=original_error,
        )


class PDFProcessingError(MCPToolError):
    """Raised when PDF processing fails.

    This exception is raised when the MCP server encounters an error
    during PDF parsing, OCR, or any step in the PDF ingestion pipeline.

    Example:
        >>> raise PDFProcessingError(
        ...     "OCR failed for page 5",
        ...     details={"page": 5, "pdf_path": "/docs/test.pdf"}
        ... )
    """

    def __init__(
        self,
        message: str = "PDF processing failed",
        *,
        details: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None,
    ) -> None:
        """Initialize PDFProcessingError.

        Args:
            message: Error description (default: "PDF processing failed").
            details: Additional context (pdf_path, page, step, etc.).
            original_error: The underlying processing exception.
        """
        super().__init__(
            message,
            error_code="PDF_PROCESSING_ERROR",
            details=details,
            original_error=original_error,
        )


class DocumentNotFoundError(MCPToolError):
    """Raised when a requested document or chunk is not found.

    This exception is raised when a retrieval operation cannot find
    the requested document, chunk, or summary in Weaviate.

    Example:
        >>> raise DocumentNotFoundError(
        ...     "Document not found",
        ...     details={"source_id": "platon-menon"}
        ... )
    """

    def __init__(
        self,
        message: str = "Document not found",
        *,
        details: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None,
    ) -> None:
        """Initialize DocumentNotFoundError.

        Args:
            message: Error description (default: "Document not found").
            details: Additional context (source_id, query, etc.).
            original_error: The underlying exception if any.
        """
        super().__init__(
            message,
            error_code="DOCUMENT_NOT_FOUND",
            details=details,
            original_error=original_error,
        )


class ValidationError(MCPToolError):
    """Raised when input validation fails.

    This exception is raised when user input does not meet the
    required validation criteria (e.g., invalid paths, bad parameters).

    Example:
        >>> raise ValidationError(
        ...     "Invalid PDF path",
        ...     details={"path": "/nonexistent/file.pdf", "reason": "File not found"}
        ... )
    """

    def __init__(
        self,
        message: str = "Validation failed",
        *,
        details: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None,
    ) -> None:
        """Initialize ValidationError.

        Args:
            message: Error description (default: "Validation failed").
            details: Additional context (field, value, reason, etc.).
            original_error: The underlying validation exception.
        """
        super().__init__(
            message,
            error_code="VALIDATION_ERROR",
            details=details,
            original_error=original_error,
        )


class LLMProcessingError(MCPToolError):
    """Raised when LLM processing fails.

    This exception is raised when the LLM (Mistral or Ollama) fails
    to process content during metadata extraction, chunking, or other
    LLM-based operations.

    Example:
        >>> raise LLMProcessingError(
        ...     "LLM timeout during metadata extraction",
        ...     details={"provider": "ollama", "model": "mistral", "step": "metadata"}
        ... )
    """

    def __init__(
        self,
        message: str = "LLM processing failed",
        *,
        details: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None,
    ) -> None:
        """Initialize LLMProcessingError.

        Args:
            message: Error description (default: "LLM processing failed").
            details: Additional context (provider, model, step, etc.).
            original_error: The underlying LLM exception.
        """
        super().__init__(
            message,
            error_code="LLM_PROCESSING_ERROR",
            details=details,
            original_error=original_error,
        )


class DownloadError(MCPToolError):
    """Raised when file download from URL fails.

    This exception is raised when the MCP server cannot download
    a PDF file from a provided URL.

    Example:
        >>> raise DownloadError(
        ...     "Failed to download PDF",
        ...     details={"url": "https://example.com/doc.pdf", "status_code": 404}
        ... )
    """

    def __init__(
        self,
        message: str = "File download failed",
        *,
        details: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None,
    ) -> None:
        """Initialize DownloadError.

        Args:
            message: Error description (default: "File download failed").
            details: Additional context (url, status_code, etc.).
            original_error: The underlying HTTP exception.
        """
        super().__init__(
            message,
            error_code="DOWNLOAD_ERROR",
            details=details,
            original_error=original_error,
        )
