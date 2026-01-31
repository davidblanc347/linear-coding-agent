"""
Library RAG MCP Server - PDF Ingestion & Semantic Retrieval.

This module provides an MCP (Model Context Protocol) server that exposes
Library RAG capabilities as tools for LLMs. It provides:

- 1 parsing tool: parse_pdf (PDF ingestion with optimal parameters)
- 7 retrieval tools: semantic search and document management

The server uses stdio transport for communication with LLM clients
like Claude Desktop.

Example:
    Run the server directly::

        python mcp_server.py

    Or configure in Claude Desktop claude_desktop_config.json::

        {
            "mcpServers": {
                "library-rag": {
                    "command": "python",
                    "args": ["path/to/mcp_server.py"],
                    "env": {"MISTRAL_API_KEY": "your-key"}
                }
            }
        }
"""

import logging
import signal
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict

# Add the library_rag directory to sys.path for proper imports
# This is needed when the script is run from a different working directory
_script_dir = Path(__file__).parent.resolve()
if str(_script_dir) not in sys.path:
    sys.path.insert(0, str(_script_dir))

from mcp.server.fastmcp import FastMCP

from mcp_config import MCPConfig
from mcp_tools import (
    ParsePdfInput,
    parse_pdf_handler,
    SearchChunksInput,
    search_chunks_handler,
    SearchSummariesInput,
    search_summaries_handler,
    GetDocumentInput,
    get_document_handler,
    ListDocumentsInput,
    list_documents_handler,
    GetChunksByDocumentInput,
    get_chunks_by_document_handler,
    FilterByAuthorInput,
    filter_by_author_handler,
    DeleteDocumentInput,
    delete_document_handler,
    # Logging utilities
    setup_mcp_logging,
    # Exception types for error handling
    WeaviateConnectionError,
    PDFProcessingError,
)

# Memory MCP Tools (added for unified Memory + Library system)
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from memory.mcp import (
    # Thought tools
    AddThoughtInput,
    SearchThoughtsInput,
    add_thought_handler,
    search_thoughts_handler,
    get_thought_handler,
    # Message tools
    AddMessageInput,
    GetMessagesInput,
    SearchMessagesInput,
    add_message_handler,
    get_messages_handler,
    search_messages_handler,
    # Conversation tools
    GetConversationInput,
    SearchConversationsInput,
    ListConversationsInput,
    get_conversation_handler,
    search_conversations_handler,
    list_conversations_handler,
    # Unified tools (cross-collection search and analysis)
    SearchMemoriesInput,
    TraceConceptEvolutionInput,
    CheckConsistencyInput,
    UpdateThoughtEvolutionStageInput,
    search_memories_handler,
    trace_concept_evolution_handler,
    check_consistency_handler,
    update_thought_evolution_stage_handler,
)

# =============================================================================
# Logging Configuration
# =============================================================================

# Note: We use setup_mcp_logging from mcp_tools.logging_config for structured
# JSON logging. The function is imported at the top of this file.


# =============================================================================
# Global State
# =============================================================================

# Configuration loaded at startup
config: MCPConfig | None = None
logger: logging.Logger | None = None


# =============================================================================
# Server Lifecycle
# =============================================================================


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[None]:
    """
    Manage server lifecycle - startup and shutdown.

    This context manager handles:
    - Loading configuration from environment
    - Validating configuration
    - Setting up logging
    - Graceful shutdown cleanup

    Args:
        server: The FastMCP server instance.

    Yields:
        None during server runtime.

    Raises:
        ValueError: If configuration is invalid or missing required values.
    """
    global config, logger

    # Startup
    try:
        # Load and validate configuration
        config = MCPConfig.from_env()
        config.validate()

        # Setup structured JSON logging with configured level
        logger = setup_mcp_logging(
            log_level=config.log_level,
            log_dir=Path("logs"),
            json_format=True,
        )
        logger.info(
            "Library RAG MCP Server starting",
            extra={
                "event": "server_startup",
                "weaviate_url": config.weaviate_url,
                "output_dir": str(config.output_dir),
                "llm_provider": config.default_llm_provider,
                "log_level": config.log_level,
            },
        )

        yield

    except ValueError as e:
        # Configuration error - log and re-raise
        if logger:
            logger.error(
                "Configuration error",
                extra={
                    "event": "config_error",
                    "error_message": str(e),
                },
            )
        else:
            print(f"Configuration error: {e}", file=sys.stderr)
        raise

    finally:
        # Shutdown
        if logger:
            logger.info(
                "Library RAG MCP Server shutting down",
                extra={"event": "server_shutdown"},
            )


# =============================================================================
# MCP Server Initialization
# =============================================================================

# Create the MCP server with lifespan management
mcp = FastMCP(
    name="library-rag",
    lifespan=server_lifespan,
)


# =============================================================================
# Tool Registration (placeholders - to be implemented in separate modules)
# =============================================================================


@mcp.tool()
async def ping() -> str:
    """
    Health check tool to verify server is running.

    Returns:
        Success message with server status.
    """
    return "Library RAG MCP Server is running!"


@mcp.tool()
async def parse_pdf(pdf_path: str) -> Dict[str, Any]:
    """
    Process a PDF document with optimal pre-configured parameters.

    Ingests a PDF file into the Library RAG system using Mistral OCR and LLM
    for intelligent processing. The document is automatically chunked,
    vectorized, and stored in Weaviate for semantic search.

    Fixed optimal parameters used:
    - LLM: Mistral API (mistral-medium-latest)
    - OCR: With annotations (better TOC extraction)
    - Chunking: Semantic LLM-based (argumentative units)
    - Ingestion: Automatic Weaviate vectorization

    Args:
        pdf_path: Local file path or URL to the PDF document.

    Returns:
        Dictionary containing:
        - success: Whether processing succeeded
        - document_name: Name of the processed document
        - source_id: Unique identifier for retrieval
        - pages: Number of pages processed
        - chunks_count: Number of chunks created
        - cost_ocr: OCR cost in EUR
        - cost_llm: LLM cost in EUR
        - cost_total: Total processing cost
        - output_dir: Directory with output files
        - metadata: Extracted document metadata
        - error: Error message if failed
    """
    input_data = ParsePdfInput(pdf_path=pdf_path)
    result = await parse_pdf_handler(input_data)
    return result.model_dump(mode='json')




@mcp.tool()
async def search_chunks(
    query: str,
    limit: int = 10,
    min_similarity: float = 0.0,
    author_filter: str | None = None,
    work_filter: str | None = None,
    language_filter: str | None = None,
) -> Dict[str, Any]:
    """
    Search for text chunks using semantic similarity.

    Performs a near_text query on the Weaviate Chunk collection to find
    semantically similar text passages from the indexed philosophical texts.

    Args:
        query: The search query text (e.g., "la justice et la vertu").
        limit: Maximum number of results to return (1-100, default 10).
        min_similarity: Minimum similarity threshold 0-1 (default 0).
        author_filter: Filter by author name (e.g., "Platon").
        work_filter: Filter by work title (e.g., "La Republique").
        language_filter: Filter by language code (e.g., "fr", "en").

    Returns:
        Dictionary containing:
        - results: List of matching chunks with text and metadata
        - total_count: Number of results returned
        - query: The original search query
    """
    input_data = SearchChunksInput(
        query=query,
        limit=limit,
        min_similarity=min_similarity,
        author_filter=author_filter,
        work_filter=work_filter,
        language_filter=language_filter,
    )
    result = await search_chunks_handler(input_data)
    return result.model_dump(mode='json')


@mcp.tool()
async def search_summaries(
    query: str,
    limit: int = 10,
    min_level: int | None = None,
    max_level: int | None = None,
) -> Dict[str, Any]:
    """
    Search for chapter/section summaries using semantic similarity.

    Performs a near_text query on the Weaviate Summary collection to find
    semantically similar summaries from indexed philosophical texts.

    Hierarchy levels:
    - Level 1: Chapters (highest level)
    - Level 2: Sections
    - Level 3: Subsections
    - etc.

    Args:
        query: The search query text (e.g., "la vertu et l'education").
        limit: Maximum number of results to return (1-100, default 10).
        min_level: Minimum hierarchy level filter (1=chapter, optional).
        max_level: Maximum hierarchy level filter (optional).

    Returns:
        Dictionary containing:
        - results: List of matching summaries with text and metadata
        - total_count: Number of results returned
        - query: The original search query

    Example:
        Search for summaries about virtue at chapter level only::

            search_summaries(
                query="la vertu",
                limit=5,
                min_level=1,
                max_level=1
            )
    """
    input_data = SearchSummariesInput(
        query=query,
        limit=limit,
        min_level=min_level,
        max_level=max_level,
    )
    result = await search_summaries_handler(input_data)
    return result.model_dump(mode='json')


@mcp.tool()
async def get_document(
    source_id: str,
    include_chunks: bool = False,
    chunk_limit: int = 50,
) -> Dict[str, Any]:
    """
    Retrieve a document by its source ID with optional chunks.

    Fetches complete document metadata and optionally related text chunks
    from the Weaviate database.

    Args:
        source_id: Document source ID (e.g., "platon-menon").
        include_chunks: Include document chunks in response (default False).
        chunk_limit: Maximum chunks to return if include_chunks=True (1-500, default 50).

    Returns:
        Dictionary containing:
        - document: Document metadata (title, author, pages, TOC, hierarchy)
        - chunks: List of chunks (if include_chunks=True)
        - chunks_total: Total number of chunks in document
        - found: Whether document was found
        - error: Error message if not found

    Example:
        Get document metadata only::

            get_document(source_id="platon-menon")

        Get document with first 20 chunks::

            get_document(
                source_id="platon-menon",
                include_chunks=True,
                chunk_limit=20
            )
    """
    input_data = GetDocumentInput(
        source_id=source_id,
        include_chunks=include_chunks,
        chunk_limit=chunk_limit,
    )
    result = await get_document_handler(input_data)
    return result.model_dump(mode='json')


@mcp.tool()
async def list_documents(
    author_filter: str | None = None,
    work_filter: str | None = None,
    language_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    List all documents with filtering and pagination support.

    Retrieves a list of all documents stored in the Library RAG system.
    Supports filtering by author, work title, and language, as well as
    pagination with limit and offset parameters.

    Args:
        author_filter: Filter by author name (e.g., "Platon").
        work_filter: Filter by work title (e.g., "La Republique").
        language_filter: Filter by language code (e.g., "fr", "en").
        limit: Maximum number of results to return (1-250, default 50).
        offset: Number of results to skip for pagination (default 0).

    Returns:
        Dictionary containing:
        - documents: List of document summaries (source_id, title, author, pages, chunks_count, language)
        - total_count: Total number of documents matching filters
        - limit: Applied limit value
        - offset: Applied offset value

    Example:
        List all French documents::

            list_documents(language_filter="fr")

        Paginate through results::

            list_documents(limit=10, offset=0)  # First 10
            list_documents(limit=10, offset=10)  # Next 10
    """
    input_data = ListDocumentsInput(
        author_filter=author_filter,
        work_filter=work_filter,
        language_filter=language_filter,
        limit=limit,
        offset=offset,
    )
    result = await list_documents_handler(input_data)
    return result.model_dump(mode='json')


@mcp.tool()
async def get_chunks_by_document(
    source_id: str,
    limit: int = 50,
    offset: int = 0,
    section_filter: str | None = None,
) -> Dict[str, Any]:
    """
    Retrieve all chunks for a document in sequential order.

    Fetches all text chunks belonging to a specific document, ordered by
    their position in the document (orderIndex). Supports pagination and
    optional filtering by section path.

    Args:
        source_id: Document source ID (e.g., "platon-menon").
        limit: Maximum number of chunks to return (1-500, default 50).
        offset: Number of chunks to skip for pagination (default 0).
        section_filter: Filter by section path prefix (e.g., "Chapter 1").

    Returns:
        Dictionary containing:
        - chunks: List of chunks in document order
        - total_count: Total number of chunks in document
        - document_source_id: The queried document source ID
        - limit: Applied limit value
        - offset: Applied offset value

    Example:
        Get first 20 chunks::

            get_chunks_by_document(source_id="platon-menon", limit=20)

        Get chunks from a specific section::

            get_chunks_by_document(
                source_id="platon-menon",
                section_filter="Chapter 3"
            )

        Paginate through chunks::

            get_chunks_by_document(source_id="platon-menon", limit=50, offset=0)
            get_chunks_by_document(source_id="platon-menon", limit=50, offset=50)
    """
    input_data = GetChunksByDocumentInput(
        source_id=source_id,
        limit=limit,
        offset=offset,
        section_filter=section_filter,
    )
    result = await get_chunks_by_document_handler(input_data)
    return result.model_dump(mode='json')


@mcp.tool()
async def filter_by_author(
    author: str,
    include_chunk_counts: bool = True,
) -> Dict[str, Any]:
    """
    Get all works and documents by a specific author.

    Retrieves all works associated with an author, along with their related
    documents. Optionally includes total chunk counts for each work.

    Args:
        author: The author name to search for (e.g., "Platon", "Aristotle").
        include_chunk_counts: Whether to include chunk counts (default True).

    Returns:
        Dictionary containing:
        - author: The searched author name
        - works: List of works with work info and documents
        - total_works: Total number of works by this author
        - total_documents: Total number of documents across all works
        - total_chunks: Total number of chunks (if include_chunk_counts=True)

    Example:
        Get all works by Platon::

            filter_by_author(author="Platon")

        Get works without chunk counts (faster)::

            filter_by_author(author="Platon", include_chunk_counts=False)
    """
    input_data = FilterByAuthorInput(
        author=author,
        include_chunk_counts=include_chunk_counts,
    )
    result = await filter_by_author_handler(input_data)
    return result.model_dump(mode='json')


@mcp.tool()
async def delete_document(
    source_id: str,
    confirm: bool = False,
) -> Dict[str, Any]:
    """
    Delete a document and all its chunks/summaries from Weaviate.

    Removes all data associated with a document: the Document object itself,
    all Chunk objects, and all Summary objects. Requires explicit confirmation
    to prevent accidental deletions.

    IMPORTANT: This operation is irreversible. Use with caution.

    Args:
        source_id: Document source ID to delete (e.g., "platon-menon").
        confirm: Must be True to confirm deletion (safety check, default False).

    Returns:
        Dictionary containing:
        - success: Whether deletion succeeded
        - source_id: The deleted document source ID
        - chunks_deleted: Number of chunks deleted
        - summaries_deleted: Number of summaries deleted
        - error: Error message if failed

    Example:
        Delete a document (requires confirmation)::

            delete_document(
                source_id="platon-menon",
                confirm=True
            )

        Without confirm=True, the operation will fail with an error message::

            delete_document(source_id="platon-menon")
            # Returns: {"success": false, "error": "Confirmation required..."}
    """
    input_data = DeleteDocumentInput(
        source_id=source_id,
        confirm=confirm,
    )
    result = await delete_document_handler(input_data)
    return result.model_dump(mode='json')


# =============================================================================
# Memory Tools (Thoughts, Messages, Conversations)
# =============================================================================


@mcp.tool()
async def add_thought(
    content: str,
    thought_type: str = "reflection",
    trigger: str = "",
    concepts: list[str] | None = None,
    privacy_level: str = "private",
) -> Dict[str, Any]:
    """
    Add a new thought to the Memory system.

    Args:
        content: The thought content.
        thought_type: Type (reflection, question, intuition, observation, etc.).
        trigger: What triggered this thought (optional).
        concepts: Related concepts/tags (optional).
        privacy_level: Privacy level (private, shared, public).

    Returns:
        Dictionary containing:
        - success: Whether thought was added successfully
        - uuid: UUID of the created thought
        - content: Preview of the thought content
        - thought_type: The thought type
    """
    input_data = AddThoughtInput(
        content=content,
        thought_type=thought_type,
        trigger=trigger,
        concepts=concepts or [],
        privacy_level=privacy_level,
    )
    result = await add_thought_handler(input_data)
    return result


@mcp.tool()
async def search_thoughts(
    query: str,
    limit: int = 10,
    thought_type_filter: str | None = None,
) -> Dict[str, Any]:
    """
    Search thoughts using semantic similarity.

    Args:
        query: Search query text.
        limit: Maximum number of results (1-100, default 10).
        thought_type_filter: Filter by thought type (optional).

    Returns:
        Dictionary containing:
        - success: Whether search succeeded
        - query: The original search query
        - results: List of matching thoughts
        - count: Number of results returned
    """
    input_data = SearchThoughtsInput(
        query=query,
        limit=limit,
        thought_type_filter=thought_type_filter,
    )
    result = await search_thoughts_handler(input_data)
    return result


@mcp.tool()
async def get_thought(uuid: str) -> Dict[str, Any]:
    """
    Get a specific thought by UUID.

    Args:
        uuid: Thought UUID.

    Returns:
        Dictionary containing complete thought data or error message.
    """
    result = await get_thought_handler(uuid)
    return result


@mcp.tool()
async def add_message(
    content: str,
    role: str,
    conversation_id: str,
    order_index: int = 0,
) -> Dict[str, Any]:
    """
    Add a new message to a conversation.

    Args:
        content: Message content.
        role: Role (user, assistant, system).
        conversation_id: Conversation identifier.
        order_index: Position in conversation (default 0).

    Returns:
        Dictionary containing:
        - success: Whether message was added successfully
        - uuid: UUID of the created message
        - content: Preview of the message content
        - role: The message role
        - conversation_id: The conversation ID
    """
    input_data = AddMessageInput(
        content=content,
        role=role,
        conversation_id=conversation_id,
        order_index=order_index,
    )
    result = await add_message_handler(input_data)
    return result


@mcp.tool()
async def get_messages(
    conversation_id: str,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Get all messages from a conversation in order.

    Args:
        conversation_id: Conversation identifier.
        limit: Maximum messages to return (1-500, default 50).

    Returns:
        Dictionary containing:
        - success: Whether query succeeded
        - conversation_id: The conversation ID
        - messages: List of messages in order
        - count: Number of messages returned
    """
    input_data = GetMessagesInput(
        conversation_id=conversation_id,
        limit=limit,
    )
    result = await get_messages_handler(input_data)
    return result


@mcp.tool()
async def search_messages(
    query: str,
    limit: int = 10,
    conversation_id_filter: str | None = None,
) -> Dict[str, Any]:
    """
    Search messages using semantic similarity.

    Args:
        query: Search query text.
        limit: Maximum number of results (1-100, default 10).
        conversation_id_filter: Filter by conversation ID (optional).

    Returns:
        Dictionary containing:
        - success: Whether search succeeded
        - query: The original search query
        - results: List of matching messages
        - count: Number of results returned
    """
    input_data = SearchMessagesInput(
        query=query,
        limit=limit,
        conversation_id_filter=conversation_id_filter,
    )
    result = await search_messages_handler(input_data)
    return result


@mcp.tool()
async def get_conversation(conversation_id: str) -> Dict[str, Any]:
    """
    Get a specific conversation by ID.

    Args:
        conversation_id: Conversation identifier.

    Returns:
        Dictionary containing:
        - success: Whether conversation was found
        - conversation_id: The conversation ID
        - category: Conversation category
        - summary: Conversation summary
        - timestamp_start: Start time
        - timestamp_end: End time
        - participants: List of participants
        - tags: Semantic tags
        - message_count: Number of messages
    """
    input_data = GetConversationInput(conversation_id=conversation_id)
    result = await get_conversation_handler(input_data)
    return result


@mcp.tool()
async def search_conversations(
    query: str,
    limit: int = 10,
    category_filter: str | None = None,
) -> Dict[str, Any]:
    """
    Search conversations using semantic similarity.

    Args:
        query: Search query text.
        limit: Maximum number of results (1-50, default 10).
        category_filter: Filter by category (optional).

    Returns:
        Dictionary containing:
        - success: Whether search succeeded
        - query: The original search query
        - results: List of matching conversations
        - count: Number of results returned
    """
    input_data = SearchConversationsInput(
        query=query,
        limit=limit,
        category_filter=category_filter,
    )
    result = await search_conversations_handler(input_data)
    return result


@mcp.tool()
async def list_conversations(
    limit: int = 20,
    category_filter: str | None = None,
) -> Dict[str, Any]:
    """
    List all conversations with optional filtering.

    Args:
        limit: Maximum conversations to return (1-100, default 20).
        category_filter: Filter by category (optional).

    Returns:
        Dictionary containing:
        - success: Whether query succeeded
        - conversations: List of conversations
        - count: Number of conversations returned
    """
    input_data = ListConversationsInput(
        limit=limit,
        category_filter=category_filter,
    )
    result = await list_conversations_handler(input_data)
    return result


# =============================================================================
# Unified Memory Tools (Cross-Collection Search and Analysis)
# =============================================================================


@mcp.tool()
async def search_memories(
    query: str,
    n_results: int = 5,
    filter_type: str | None = None,
    since: str | None = None,
    before: str | None = None,
    sort_by: str = "relevance",
) -> Dict[str, Any]:
    """
    Search across both Thoughts and Conversations (unified memory search).

    This is the primary search tool for finding relevant memories across
    all memory types. Use this when you need to search broadly.

    Args:
        query: Search query text (can be empty "" to list all).
        n_results: Number of results to return (1-20, default 5).
        filter_type: Filter to 'thoughts' or 'conversations' only (optional).
        since: Filter after date - ISO 8601 or relative (7d, 3h, 1w, 30m).
        before: Filter before date - ISO 8601 only.
        sort_by: Sort order - 'relevance', 'date_desc', 'date_asc' (default: relevance).

    Returns:
        Dictionary containing:
        - success: Whether search succeeded
        - query: The search query
        - results: List of matching memories (thoughts and conversations)
        - count: Number of results
        - filter_type: Applied filter

    Example:
        Search all memories about consciousness::

            search_memories(query="conscience", n_results=10)

        List recent thoughts only::

            search_memories(query="", filter_type="thoughts", since="7d", sort_by="date_desc")
    """
    input_data = SearchMemoriesInput(
        query=query,
        n_results=n_results,
        filter_type=filter_type,
        since=since,
        before=before,
        sort_by=sort_by,
    )
    result = await search_memories_handler(input_data)
    return result


@mcp.tool()
async def trace_concept_evolution(
    concept: str,
    limit: int = 10,
) -> Dict[str, Any]:
    """
    Trace the evolution of a concept through thoughts and conversations over time.

    Use this tool to understand how a concept has developed, what thoughts
    and conversations have shaped it, and how your understanding has evolved.

    Args:
        concept: The concept to trace (e.g., "conscience", "liberté", "identité").
        limit: Maximum timeline points to return (1-50, default 10).

    Returns:
        Dictionary containing:
        - success: Whether tracing succeeded
        - concept: The traced concept
        - timeline: Chronological list of relevant thoughts and conversations
        - count: Number of timeline points

    Example:
        Trace how understanding of consciousness evolved::

            trace_concept_evolution(concept="conscience", limit=15)
    """
    input_data = TraceConceptEvolutionInput(
        concept=concept,
        limit=limit,
    )
    result = await trace_concept_evolution_handler(input_data)
    return result


@mcp.tool()
async def check_consistency(
    statement: str,
) -> Dict[str, Any]:
    """
    Check if a statement is consistent with existing thoughts and conversations.

    Use this tool to verify if a new thought or statement aligns with
    what has been said or thought before. Helps identify potential
    contradictions or evolutions in thinking.

    Args:
        statement: The statement or thought to check for consistency.

    Returns:
        Dictionary containing:
        - success: Whether check succeeded
        - statement: The checked statement
        - consistency_score: 0-1 score (1 = highly consistent)
        - analysis: Textual analysis of consistency
        - related_content: List of related thoughts/conversations
        - count: Number of related items found

    Example:
        Check if a statement aligns with past thinking::

            check_consistency(statement="La conscience est un phénomène émergent")
    """
    input_data = CheckConsistencyInput(
        statement=statement,
    )
    result = await check_consistency_handler(input_data)
    return result


@mcp.tool()
async def update_thought_evolution_stage(
    thought_id: str,
    new_stage: str,
) -> Dict[str, Any]:
    """
    Update the evolution stage of an existing thought.

    Use this to track how thoughts develop over time. Stages represent
    the maturity and status of a thought.

    Args:
        thought_id: ID of the thought (format: thought_YYYY-MM-DDTHH:MM:SS or UUID).
        new_stage: New evolution stage:
            - 'nascent': Initial, forming thought
            - 'developing': Being refined and explored
            - 'mature': Well-developed and stable
            - 'revised': Has been updated/corrected
            - 'abandoned': No longer held or relevant

    Returns:
        Dictionary containing:
        - success: Whether update succeeded
        - thought_id: The thought ID
        - new_stage: The new stage
        - message: Confirmation message

    Example:
        Mark a thought as mature::

            update_thought_evolution_stage(
                thought_id="thought_2025-01-15T10:30:00",
                new_stage="mature"
            )
    """
    input_data = UpdateThoughtEvolutionStageInput(
        thought_id=thought_id,
        new_stage=new_stage,
    )
    result = await update_thought_evolution_stage_handler(input_data)
    return result


# =============================================================================
# Signal Handlers
# =============================================================================


def handle_shutdown(signum: int, frame: object) -> None:
    """
    Handle shutdown signals gracefully.

    Args:
        signum: Signal number received.
        frame: Current stack frame (unused).
    """
    if logger:
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    sys.exit(0)


# =============================================================================
# Main Entry Point
# =============================================================================


def main() -> None:
    """
    Main entry point for the MCP server.

    Sets up signal handlers and runs the server with stdio transport.
    """
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    # Run the server with stdio transport (default for MCP)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
