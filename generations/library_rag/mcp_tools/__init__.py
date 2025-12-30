"""
MCP Tools for Library RAG Server.

This package contains all tool implementations for the Library RAG MCP server:
- Parsing tools: PDF ingestion with optimal parameters
- Retrieval tools: Semantic search and document management
- Exceptions: Custom exception classes for structured error handling
- Logging: Structured JSON logging configuration
"""

from mcp_tools.schemas import (
    ParsePdfInput,
    ParsePdfOutput,
    SearchChunksInput,
    SearchChunksOutput,
    SearchSummariesInput,
    SearchSummariesOutput,
    GetDocumentInput,
    GetDocumentOutput,
    ListDocumentsInput,
    ListDocumentsOutput,
    GetChunksByDocumentInput,
    GetChunksByDocumentOutput,
    FilterByAuthorInput,
    FilterByAuthorOutput,
    DeleteDocumentInput,
    DeleteDocumentOutput,
)

from mcp_tools.exceptions import (
    MCPToolError,
    WeaviateConnectionError,
    PDFProcessingError,
    DocumentNotFoundError,
    ValidationError,
    LLMProcessingError,
    DownloadError,
)

from mcp_tools.logging_config import (
    setup_mcp_logging,
    get_tool_logger,
    ToolInvocationLogger,
    log_tool_invocation,
    log_weaviate_query,
    redact_sensitive_data,
    redact_dict,
)

from mcp_tools.parsing_tools import parse_pdf_handler
from mcp_tools.retrieval_tools import (
    search_chunks_handler,
    search_summaries_handler,
    get_document_handler,
    list_documents_handler,
    get_chunks_by_document_handler,
    filter_by_author_handler,
    delete_document_handler,
)

__all__ = [
    # Parsing tools
    "parse_pdf_handler",
    # Retrieval tools
    "search_chunks_handler",
    "search_summaries_handler",
    "get_document_handler",
    "list_documents_handler",
    "get_chunks_by_document_handler",
    "filter_by_author_handler",
    "delete_document_handler",
    # Parsing schemas
    "ParsePdfInput",
    "ParsePdfOutput",
    # Retrieval schemas
    "SearchChunksInput",
    "SearchChunksOutput",
    "SearchSummariesInput",
    "SearchSummariesOutput",
    "GetDocumentInput",
    "GetDocumentOutput",
    "ListDocumentsInput",
    "ListDocumentsOutput",
    "GetChunksByDocumentInput",
    "GetChunksByDocumentOutput",
    "FilterByAuthorInput",
    "FilterByAuthorOutput",
    "DeleteDocumentInput",
    "DeleteDocumentOutput",
    # Exceptions
    "MCPToolError",
    "WeaviateConnectionError",
    "PDFProcessingError",
    "DocumentNotFoundError",
    "ValidationError",
    "LLMProcessingError",
    "DownloadError",
    # Logging
    "setup_mcp_logging",
    "get_tool_logger",
    "ToolInvocationLogger",
    "log_tool_invocation",
    "log_weaviate_query",
    "redact_sensitive_data",
    "redact_dict",
]
