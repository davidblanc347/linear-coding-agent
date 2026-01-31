"""Retrieval tools for Library RAG MCP Server.

This module implements semantic search and document retrieval tools that query
the Weaviate vector database.

Available tools:
    - search_chunks: Semantic search on text chunks
    - search_summaries: Search in chapter/section summaries
    - get_document: Retrieve document by ID
    - list_documents: List all documents with filtering
    - get_chunks_by_document: Get chunks by document ID
    - filter_by_author: Filter works by author
    - delete_document: Delete a document and all its chunks/summaries

Example:
    Search for chunks about justice::

        {
            "tool": "search_chunks",
            "arguments": {
                "query": "la justice et la vertu",
                "limit": 10,
                "author_filter": "Platon"
            }
        }
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, cast, Dict, Generator, List, Mapping, Optional

import weaviate
from weaviate import WeaviateClient
import weaviate.classes.query as wvq
from weaviate.classes.query import Filter

from mcp_tools.schemas import (
    AuthorWorkResult,
    ChunkResult,
    DeleteDocumentInput,
    DeleteDocumentOutput,
    DocumentInfo,
    DocumentSummary,
    FilterByAuthorInput,
    FilterByAuthorOutput,
    GetChunksByDocumentInput,
    GetChunksByDocumentOutput,
    GetDocumentInput,
    GetDocumentOutput,
    ListDocumentsInput,
    ListDocumentsOutput,
    SearchChunksInput,
    SearchChunksOutput,
    SearchSummariesInput,
    SearchSummariesOutput,
    SummaryResult,
    WorkInfo,
)
from mcp_tools.exceptions import (
    WeaviateConnectionError,
    DocumentNotFoundError,
)
from mcp_tools.logging_config import (
    get_tool_logger,
    log_tool_invocation,
    log_weaviate_query,
)

# GPU embedder for BGE-M3 vectorization (replaces text2vec-transformers)
from memory.core import get_embedder

# Logger for this module - uses structured logging
logger = get_tool_logger("retrieval")

# =============================================================================
# GPU Embedder Singleton (BGE-M3)
# =============================================================================

_embedder = None


def get_gpu_embedder():
    """Get or create GPU embedder singleton for BGE-M3 vectorization.

    Returns the shared GPU embedding service instance. The embedder uses
    BAAI/bge-m3 model (1024 dimensions) for semantic vectorization.

    Returns:
        GPUEmbeddingService instance.

    Note:
        This singleton pattern ensures the model is loaded only once,
        avoiding repeated GPU memory allocation.
    """
    global _embedder
    if _embedder is None:
        logger.info("Initializing GPU embedder (BGE-M3) for retrieval...")
        _embedder = get_embedder()
        logger.info(f"GPU embedder ready: {_embedder.model_name}")
    return _embedder


# =============================================================================
# Canonical Reference Extraction
# =============================================================================


def extract_canonical_reference(
    section_path: str, source_id: str, work_title: str
) -> Optional[str]:
    """Extract academic citation reference from section_path.

    Args:
        section_path: Hierarchical section path (e.g., "628. I think...")
        source_id: Document source ID (e.g., "peirce_collected_papers_fixed")
        work_title: Title of the work

    Returns:
        Canonical reference string (e.g., "CP 5.628", "Ménon 80a") or None.

    Examples:
        >>> extract_canonical_reference("628. I think...", "peirce_collected_papers_fixed", "Collected Papers")
        "CP 1.628"
        >>> extract_canonical_reference("80a. Text...", "platon_menon", "Ménon")
        "80a"
    """
    if not section_path:
        return None

    # Extract leading number/reference from section_path
    # Format: "628. Text..." or "80a. Text..." or "§128. Text..."
    import re

    # Match various formats:
    # - "628. " → "628"
    # - "80a. " → "80a"
    # - "§128. " → "128"
    # - "CP 5.628. " → "CP 5.628"
    match = re.match(r'^(?:§\s*)?(CP\s+[\d.]+|\d+[a-z]?)\.\s', section_path)
    if match:
        ref = match.group(1)

        # For Peirce Collected Papers, add volume number by matching text
        if 'peirce' in source_id.lower() and 'collected' in work_title.lower():
            if not ref.startswith('CP'):
                # Check if it's just a number (paragraph reference)
                if re.match(r'^\d+$', ref):
                    paragraph = int(ref)
                    # Use text after paragraph number to find exact TOC entry
                    text_after_number = section_path[match.end():].strip()[:50]
                    volume = get_peirce_volume_from_text(paragraph, text_after_number)
                    if volume:
                        return f"CP {volume}.{paragraph}"
                    return ref

        return ref

    return None


def get_peirce_volume_from_text(paragraph: int, text_snippet: str) -> Optional[int]:
    """Find Peirce CP volume by matching paragraph number AND text.

    Since paragraphs restart in each volume, we need to match the actual
    text to find the correct volume.

    Args:
        paragraph: Paragraph number (e.g., 42)
        text_snippet: First ~50 chars of text after paragraph number

    Returns:
        Volume number (1-8) or None if not found.

    Examples:
        >>> get_peirce_volume_from_text(42, "My philosophy resuscitates Hegel")
        5  # Found in Volume 5
    """
    import json
    import re
    from pathlib import Path

    chunks_file = Path("output/peirce_collected_papers_fixed/peirce_collected_papers_fixed_chunks.json")
    if not chunks_file.exists():
        return None

    try:
        with open(chunks_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        toc = data.get('metadata', {}).get('toc', [])
        if not toc:
            return None

        # Search for entries matching paragraph number
        # TOC structure:
        # - Level 1: "Peirce: CP X.YYY"
        # - Level 2: "YYY. Actual text content..."
        cp_pattern = re.compile(rf'Peirce:\s*CP\s+(\d+)\.{paragraph}\b')

        # Clean text_snippet for fuzzy matching
        clean_snippet = text_snippet.lower().strip()

        for i, entry in enumerate(toc):
            title = entry.get('title', '')
            cp_match = cp_pattern.search(title)

            if cp_match:
                volume = int(cp_match.group(1))

                # Check next entry (Level 2) for actual text
                if i + 1 < len(toc):
                    next_entry = toc[i + 1]
                    next_title = next_entry.get('title', '').lower()
                    next_level = next_entry.get('level', 0)

                    # Verify it's Level 2 (the content entry)
                    if next_level == 2:
                        # Fuzzy match: check if significant words appear
                        words = [w for w in clean_snippet.split() if len(w) > 3]
                        if words:
                            # If first meaningful word matches, found the right volume
                            if words[0] in next_title:
                                return volume

        # If no text match, return None (ambiguous)
        return None

    except Exception as e:
        logger.error(f"Failed to match Peirce text: {e}")
        return None


def get_peirce_volume_from_paragraph(paragraph: int) -> Optional[int]:
    """Determine Peirce Collected Papers volume from paragraph number.

    Loads TOC from cached chunks file and finds the volume for the paragraph.

    Args:
        paragraph: Paragraph number (e.g., 628)

    Returns:
        Volume number (1-8) or None if cannot be determined.

    Examples:
        >>> get_peirce_volume_from_paragraph(628)
        1  # Found "Peirce: CP 1.628" in TOC
    """
    import json
    import re
    from pathlib import Path

    # Try to load TOC from cached chunks file
    chunks_file = Path("output/peirce_collected_papers_fixed/peirce_collected_papers_fixed_chunks.json")
    if not chunks_file.exists():
        logger.warning(f"Peirce chunks file not found: {chunks_file}")
        return None

    try:
        with open(chunks_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        toc = data.get('metadata', {}).get('toc', [])
        if not toc:
            return None

        # Search for "Peirce: CP X.{paragraph}" in TOC
        # Example: "Peirce: CP 5.628"
        pattern = re.compile(rf'Peirce:\s*CP\s+(\d+)\.{paragraph}\b')

        for entry in toc:
            title = entry.get('title', '')
            match = pattern.search(title)
            if match:
                volume = int(match.group(1))
                return volume

        return None

    except Exception as e:
        logger.error(f"Failed to load Peirce TOC: {e}")
        return None


# =============================================================================
# Weaviate Connection
# =============================================================================


@contextmanager
def get_weaviate_client() -> Generator[WeaviateClient, None, None]:
    """Context manager for Weaviate connection.

    Establishes a connection to the local Weaviate instance and ensures
    proper cleanup after use.

    Yields:
        WeaviateClient instance.

    Raises:
        WeaviateConnectionError: If connection to Weaviate fails.

    Example:
        >>> with get_weaviate_client() as client:
        ...     chunks = client.collections.get("Chunk")
    """
    client: Optional[WeaviateClient] = None
    try:
        client = weaviate.connect_to_local(
            host="localhost",
            port=8080,
            grpc_port=50051,
        )
        yield client
    except Exception as e:
        logger.error(
            "Weaviate connection failed",
            extra={
                "error_type": type(e).__name__,
                "error_message": str(e),
                "host": "localhost",
                "port": 8080,
            },
        )
        raise WeaviateConnectionError(
            f"Failed to connect to Weaviate: {e}",
            details={"host": "localhost", "port": 8080, "grpc_port": 50051},
            original_error=e,
        ) from e
    finally:
        if client:
            client.close()


# =============================================================================
# Helper Functions
# =============================================================================


def safe_str(value: Any, default: str = "") -> str:
    """Safely convert a value to string.

    Args:
        value: The value to convert.
        default: Default value if conversion fails or value is None.

    Returns:
        String representation of value or default.
    """
    if value is None:
        return default
    return str(value)


def safe_int(value: Any, default: int = 0) -> int:
    """Safely convert a value to int.

    Args:
        value: The value to convert.
        default: Default value if conversion fails or value is None.

    Returns:
        Integer representation of value or default.
    """
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def get_nested_dict(props: Mapping[str, Any], key: str) -> Dict[str, Any]:
    """Safely get a nested dict from properties.

    Args:
        props: The properties mapping.
        key: The key to retrieve.

    Returns:
        Dictionary value or empty dict if not found or wrong type.
    """
    value = props.get(key)
    if isinstance(value, dict):
        return cast(Dict[str, Any], value)
    return {}


def safe_list(value: Any) -> List[str]:
    """Safely convert a value to a list of strings.

    Args:
        value: The value to convert (expected to be a list).

    Returns:
        List of strings or empty list if conversion fails.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def safe_json_parse(value: Any) -> Optional[Dict[str, Any]]:
    """Safely parse a JSON string to a dictionary.

    Args:
        value: The value to parse (expected to be a JSON string).

    Returns:
        Parsed dictionary or None if parsing fails.
    """
    import json

    if value is None:
        return None
    if isinstance(value, dict):
        return cast(Dict[str, Any], value)
    if isinstance(value, str):
        try:
            result = json.loads(value)
            if isinstance(result, dict):
                return cast(Dict[str, Any], result)
            return None
        except json.JSONDecodeError:
            return None
    return None


# =============================================================================
# search_chunks Tool
# =============================================================================


async def search_chunks_handler(input_data: SearchChunksInput) -> SearchChunksOutput:
    """Search for text chunks using semantic similarity.

    Performs a near_text query on the Weaviate Chunk collection to find
    semantically similar text passages. Supports filtering by author,
    work title, and language, as well as a minimum similarity threshold.

    Args:
        input_data: Validated input containing:
            - query: The search query text
            - limit: Maximum number of results (default 10)
            - min_similarity: Minimum similarity threshold 0-1 (default 0)
            - author_filter: Filter by author name (optional)
            - work_filter: Filter by work title (optional)
            - language_filter: Filter by language code (optional)

    Returns:
        SearchChunksOutput containing:
            - results: List of ChunkResult objects with text and metadata
            - total_count: Number of results returned
            - query: The original search query

    Example:
        >>> input_data = SearchChunksInput(query="justice", limit=5)
        >>> result = await search_chunks_handler(input_data)
        >>> len(result.results) <= 5
        True
    """
    tool_inputs = {
        "query": input_data.query,
        "limit": input_data.limit,
        "min_similarity": input_data.min_similarity,
        "author_filter": input_data.author_filter,
        "work_filter": input_data.work_filter,
        "language_filter": input_data.language_filter,
    }

    with log_tool_invocation("search_chunks", tool_inputs) as invocation:
        try:
            with get_weaviate_client() as client:
                chunks = client.collections.get("Chunk")

                # Build filters for nested object properties
                # Using type: ignore for Weaviate filter chain which has complex types
                filters: Any = None

                if input_data.author_filter:
                    filters = (
                        Filter.by_property("work")
                        .by_property("author")  # type: ignore[attr-defined]
                        .equal(input_data.author_filter)
                    )

                if input_data.work_filter:
                    work_f = (
                        Filter.by_property("work")
                        .by_property("title")  # type: ignore[attr-defined]
                        .equal(input_data.work_filter)
                    )
                    filters = (filters & work_f) if filters else work_f

                if input_data.language_filter:
                    lang_f = Filter.by_property("language").equal(
                        input_data.language_filter
                    )
                    filters = (filters & lang_f) if filters else lang_f

                # Vectorize query with GPU embedder (BGE-M3)
                embedder = get_gpu_embedder()
                query_vector = embedder.embed_single(input_data.query)

                # Perform near_vector query with timing
                query_start = time.perf_counter()
                result = chunks.query.near_vector(
                    near_vector=query_vector.tolist(),
                    limit=input_data.limit,
                    filters=filters,
                    return_metadata=wvq.MetadataQuery(distance=True),
                )
                query_duration_ms = (time.perf_counter() - query_start) * 1000

                # Log Weaviate query
                log_weaviate_query(
                    operation="near_vector",
                    collection="Chunk",
                    filters={
                        "author": input_data.author_filter,
                        "work": input_data.work_filter,
                        "language": input_data.language_filter,
                    },
                    result_count=len(result.objects),
                    duration_ms=query_duration_ms,
                )

                # Convert results to output schema
                chunk_results: List[ChunkResult] = []
                for obj in result.objects:
                    # Calculate similarity from distance (Weaviate uses cosine distance)
                    distance = obj.metadata.distance if obj.metadata else 0.0
                    similarity = 1.0 - (distance if distance else 0.0)

                    # Apply min_similarity filter
                    if similarity < input_data.min_similarity:
                        continue

                    # Extract properties with type safety
                    props = obj.properties
                    work_data = get_nested_dict(props, "work")
                    document_data = get_nested_dict(props, "document")

                    # Extract canonical reference
                    section_path = safe_str(props.get("sectionPath"), "")
                    source_id = safe_str(document_data.get("sourceId"), "unknown")
                    work_title = safe_str(work_data.get("title"), "Unknown")
                    canonical_ref = extract_canonical_reference(
                        section_path, source_id, work_title
                    )

                    chunk_result = ChunkResult(
                        text=safe_str(props.get("text"), ""),
                        similarity=round(similarity, 4),
                        source_id=source_id,
                        canonical_reference=canonical_ref,
                        section_path=section_path,
                        chapter_title=safe_str(props.get("chapterTitle")) or None,
                        work_title=work_title,
                        work_author=safe_str(work_data.get("author"), "Unknown"),
                        order_index=safe_int(props.get("orderIndex"), 0),
                    )
                    chunk_results.append(chunk_result)

                output = SearchChunksOutput(
                    results=chunk_results,
                    total_count=len(chunk_results),
                    query=input_data.query,
                )
                invocation.set_result(output.model_dump())
                return output

        except WeaviateConnectionError:
            # Re-raise connection errors (already logged)
            raise
        except Exception as e:
            logger.error(
                "Search chunks failed",
                extra={
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "query": input_data.query,
                },
                exc_info=True,
            )
            return SearchChunksOutput(
                results=[],
                total_count=0,
                query=input_data.query,
            )


# =============================================================================
# search_summaries Tool
# =============================================================================


async def search_summaries_handler(
    input_data: SearchSummariesInput,
) -> SearchSummariesOutput:
    """Search for chapter/section summaries using semantic similarity.

    Performs a near_text query on the Weaviate Summary collection to find
    semantically similar summaries. Supports filtering by hierarchy level
    (min_level, max_level) where level 1 = chapter, level 2 = section, etc.

    Args:
        input_data: Validated input containing:
            - query: The search query text
            - limit: Maximum number of results (default 10)
            - min_level: Minimum hierarchy level filter (optional, 1=chapter)
            - max_level: Maximum hierarchy level filter (optional)

    Returns:
        SearchSummariesOutput containing:
            - results: List of SummaryResult objects with text and metadata
            - total_count: Number of results returned
            - query: The original search query

    Example:
        >>> input_data = SearchSummariesInput(query="vertu", limit=5, min_level=1)
        >>> result = await search_summaries_handler(input_data)
        >>> len(result.results) <= 5
        True
    """
    tool_inputs = {
        "query": input_data.query,
        "limit": input_data.limit,
        "min_level": input_data.min_level,
        "max_level": input_data.max_level,
    }

    with log_tool_invocation("search_summaries", tool_inputs) as invocation:
        try:
            with get_weaviate_client() as client:
                summaries = client.collections.get("Summary")

                # Build filters for level constraints
                filters: Any = None

                if input_data.min_level is not None:
                    filters = Filter.by_property("level").greater_or_equal(
                        input_data.min_level
                    )

                if input_data.max_level is not None:
                    max_filter = Filter.by_property("level").less_or_equal(
                        input_data.max_level
                    )
                    filters = (filters & max_filter) if filters else max_filter

                # Vectorize query with GPU embedder (BGE-M3)
                embedder = get_gpu_embedder()
                query_vector = embedder.embed_single(input_data.query)

                # Perform near_vector query with timing
                query_start = time.perf_counter()
                result = summaries.query.near_vector(
                    near_vector=query_vector.tolist(),
                    limit=input_data.limit,
                    filters=filters,
                    return_metadata=wvq.MetadataQuery(distance=True),
                )
                query_duration_ms = (time.perf_counter() - query_start) * 1000

                # Log Weaviate query
                log_weaviate_query(
                    operation="near_vector",
                    collection="Summary",
                    filters={
                        "min_level": input_data.min_level,
                        "max_level": input_data.max_level,
                    },
                    result_count=len(result.objects),
                    duration_ms=query_duration_ms,
                )

                # Convert results to output schema
                summary_results: List[SummaryResult] = []
                for obj in result.objects:
                    # Calculate similarity from distance (Weaviate uses cosine distance)
                    distance = obj.metadata.distance if obj.metadata else 0.0
                    similarity = 1.0 - (distance if distance else 0.0)

                    # Extract properties with type safety
                    props = obj.properties
                    document_data = get_nested_dict(props, "document")

                    summary_result = SummaryResult(
                        text=safe_str(props.get("text"), ""),
                        similarity=round(similarity, 4),
                        title=safe_str(props.get("title"), ""),
                        section_path=safe_str(props.get("sectionPath"), ""),
                        level=safe_int(props.get("level"), 1),
                        concepts=safe_list(props.get("concepts")),
                        document_source_id=safe_str(
                            document_data.get("sourceId"), "Unknown"
                        ),
                    )
                    summary_results.append(summary_result)

                output = SearchSummariesOutput(
                    results=summary_results,
                    total_count=len(summary_results),
                    query=input_data.query,
                )
                invocation.set_result(output.model_dump())
                return output

        except WeaviateConnectionError:
            # Re-raise connection errors (already logged)
            raise
        except Exception as e:
            logger.error(
                "Search summaries failed",
                extra={
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "query": input_data.query,
                },
                exc_info=True,
            )
            return SearchSummariesOutput(
                results=[],
                total_count=0,
                query=input_data.query,
            )


# =============================================================================
# get_document Tool
# =============================================================================


async def get_document_handler(
    input_data: GetDocumentInput,
) -> GetDocumentOutput:
    """Retrieve a document by its sourceId with optional chunks.

    Queries the Weaviate Document collection to retrieve complete document
    metadata and optionally fetches related chunks ordered by orderIndex.

    Args:
        input_data: Validated input containing:
            - source_id: The unique document identifier
            - include_chunks: Whether to fetch related chunks (default False)
            - chunk_limit: Maximum number of chunks to return (default 50)

    Returns:
        GetDocumentOutput containing:
            - document: DocumentInfo object with metadata (or None if not found)
            - chunks: List of ChunkResult objects (if include_chunks=True)
            - chunks_total: Total number of chunks in document
            - found: Whether the document was found
            - error: Error message if document not found

    Example:
        >>> input_data = GetDocumentInput(source_id="platon-menon", include_chunks=True)
        >>> result = await get_document_handler(input_data)
        >>> result.found
        True
    """
    tool_inputs = {
        "source_id": input_data.source_id,
        "include_chunks": input_data.include_chunks,
        "chunk_limit": input_data.chunk_limit,
    }

    with log_tool_invocation("get_document", tool_inputs) as invocation:
        try:
            with get_weaviate_client() as client:
                # Use Work collection (Document was merged into Work)
                works = client.collections.get("Work")

                # Query Work by sourceId
                query_start = time.perf_counter()
                doc_filter = Filter.by_property("sourceId").equal(input_data.source_id)
                result = works.query.fetch_objects(
                    filters=doc_filter,
                    limit=1,
                )
                query_duration_ms = (time.perf_counter() - query_start) * 1000

                log_weaviate_query(
                    operation="fetch_objects",
                    collection="Work",
                    filters={"sourceId": input_data.source_id},
                    result_count=len(result.objects),
                    duration_ms=query_duration_ms,
                )

                if not result.objects:
                    logger.warning(
                        "Work not found",
                        extra={"source_id": input_data.source_id},
                    )
                    output = GetDocumentOutput(
                        document=None,
                        chunks=[],
                        chunks_total=0,
                        found=False,
                        error=f"Work not found: {input_data.source_id}",
                    )
                    invocation.set_result(output.model_dump())
                    return output

                # Extract Work properties (Document was merged into Work)
                doc_obj = result.objects[0]
                props = doc_obj.properties

                # Parse TOC and hierarchy (stored as JSON strings) - may not exist in Work
                toc_data = safe_json_parse(props.get("toc"))
                hierarchy_data = safe_json_parse(props.get("hierarchy"))

                document_info = DocumentInfo(
                    source_id=safe_str(props.get("sourceId"), input_data.source_id),
                    work_title=safe_str(props.get("title"), "Unknown"),
                    work_author=safe_str(props.get("author"), "Unknown"),
                    edition=safe_str(props.get("edition")) or None,
                    pages=safe_int(props.get("pages"), 0),
                    language=safe_str(props.get("language"), "unknown"),
                    toc=toc_data,
                    hierarchy=hierarchy_data,
                )

                # Get chunks count from document
                chunks_total = safe_int(props.get("chunksCount"), 0)

                # Optionally fetch related chunks
                chunk_results: List[ChunkResult] = []
                if input_data.include_chunks:
                    chunks_collection = client.collections.get("Chunk")

                    # Filter chunks by document.sourceId and order by orderIndex
                    chunk_filter = (
                        Filter.by_property("document")
                        .by_property("sourceId")  # type: ignore[attr-defined]
                        .equal(input_data.source_id)
                    )

                    chunk_result = chunks_collection.query.fetch_objects(
                        filters=chunk_filter,
                        limit=input_data.chunk_limit,
                        # Note: Weaviate v4 doesn't support sort in fetch_objects
                        # Results may not be ordered by orderIndex
                    )

                    for obj in chunk_result.objects:
                        chunk_props = obj.properties
                        chunk_work_data = get_nested_dict(chunk_props, "work")
                        chunk_document_data = get_nested_dict(chunk_props, "document")

                        # Extract canonical reference
                        section_path = safe_str(chunk_props.get("sectionPath"), "")
                        source_id = safe_str(chunk_document_data.get("sourceId"), input_data.source_id)
                        work_title = safe_str(chunk_work_data.get("title"), "Unknown")
                        canonical_ref = extract_canonical_reference(
                            section_path, source_id, work_title
                        )

                        chunk = ChunkResult(
                            text=safe_str(chunk_props.get("text"), ""),
                            similarity=1.0,  # Not from search, use 1.0
                            source_id=source_id,
                            canonical_reference=canonical_ref,
                            section_path=section_path,
                            chapter_title=safe_str(chunk_props.get("chapterTitle")) or None,
                            work_title=work_title,
                            work_author=safe_str(chunk_work_data.get("author"), "Unknown"),
                            order_index=safe_int(chunk_props.get("orderIndex"), 0),
                        )
                        chunk_results.append(chunk)

                    # Sort chunks by order_index
                    chunk_results.sort(key=lambda c: c.order_index)

                output = GetDocumentOutput(
                    document=document_info,
                    chunks=chunk_results,
                    chunks_total=chunks_total,
                    found=True,
                    error=None,
                )
                invocation.set_result(output.model_dump())
                return output

        except WeaviateConnectionError:
            # Re-raise connection errors (already logged)
            raise
        except Exception as e:
            logger.error(
                "Get document failed",
                extra={
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "source_id": input_data.source_id,
                },
                exc_info=True,
            )
            return GetDocumentOutput(
                document=None,
                chunks=[],
                chunks_total=0,
                found=False,
                error=str(e),
            )


# =============================================================================
# list_documents Tool
# =============================================================================


async def list_documents_handler(
    input_data: ListDocumentsInput,
) -> ListDocumentsOutput:
    """List all documents with filtering and pagination support.

    Queries the Weaviate Document collection to retrieve document summaries.
    Supports filtering by author, work title, and language, as well as
    pagination with limit and offset parameters.

    Args:
        input_data: Validated input containing:
            - author_filter: Filter by author name (optional)
            - work_filter: Filter by work title (optional)
            - language_filter: Filter by language code (optional)
            - limit: Maximum number of results (default 50, max 250)
            - offset: Offset for pagination (default 0)

    Returns:
        ListDocumentsOutput containing:
            - documents: List of DocumentSummary objects
            - total_count: Total number of documents matching filters
            - limit: Applied limit value
            - offset: Applied offset value

    Example:
        >>> input_data = ListDocumentsInput(author_filter="Platon", limit=10)
        >>> result = await list_documents_handler(input_data)
        >>> len(result.documents) <= 10
        True
    """
    tool_inputs = {
        "author_filter": input_data.author_filter,
        "work_filter": input_data.work_filter,
        "language_filter": input_data.language_filter,
        "limit": input_data.limit,
        "offset": input_data.offset,
    }

    with log_tool_invocation("list_documents", tool_inputs) as invocation:
        try:
            with get_weaviate_client() as client:
                # Use Work collection (Document was merged into Work)
                works_collection = client.collections.get("Work")

                # Build filters (Work has author/title directly, not nested)
                filters: Any = None

                if input_data.author_filter:
                    filters = Filter.by_property("author").equal(input_data.author_filter)

                if input_data.work_filter:
                    work_f = Filter.by_property("title").equal(input_data.work_filter)
                    filters = (filters & work_f) if filters else work_f

                if input_data.language_filter:
                    lang_f = Filter.by_property("language").equal(
                        input_data.language_filter
                    )
                    filters = (filters & lang_f) if filters else lang_f

                # First, get total count (requires fetching all matching objects)
                # Weaviate v4 doesn't have a direct count API, so we fetch with high limit
                query_start = time.perf_counter()
                count_result = works_collection.query.fetch_objects(
                    filters=filters,
                    limit=10000,  # High limit to get all for counting
                )
                total_count = len(count_result.objects)

                # Now fetch paginated results
                # Weaviate v4 fetch_objects doesn't support offset directly,
                # so we fetch limit + offset and slice
                fetch_limit = input_data.limit + input_data.offset
                result = works_collection.query.fetch_objects(
                    filters=filters,
                    limit=fetch_limit,
                )
                query_duration_ms = (time.perf_counter() - query_start) * 1000

                log_weaviate_query(
                    operation="fetch_objects",
                    collection="Work",
                    filters={
                        "author": input_data.author_filter,
                        "work": input_data.work_filter,
                        "language": input_data.language_filter,
                    },
                    result_count=len(result.objects),
                    duration_ms=query_duration_ms,
                )

                # Apply offset by slicing
                paginated_objects = result.objects[input_data.offset:]

                # Convert results to output schema (Work has properties directly)
                document_summaries: List[DocumentSummary] = []
                for obj in paginated_objects[:input_data.limit]:
                    props = obj.properties

                    doc_summary = DocumentSummary(
                        source_id=safe_str(props.get("sourceId"), "unknown"),
                        work_title=safe_str(props.get("title"), "Unknown"),
                        work_author=safe_str(props.get("author"), "Unknown"),
                        pages=safe_int(props.get("pages"), 0),
                        chunks_count=safe_int(props.get("chunksCount"), 0),
                        language=safe_str(props.get("language"), "unknown"),
                    )
                    document_summaries.append(doc_summary)

                output = ListDocumentsOutput(
                    documents=document_summaries,
                    total_count=total_count,
                    limit=input_data.limit,
                    offset=input_data.offset,
                )
                invocation.set_result(output.model_dump())
                return output

        except WeaviateConnectionError:
            # Re-raise connection errors (already logged)
            raise
        except Exception as e:
            logger.error(
                "List documents failed",
                extra={
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
                exc_info=True,
            )
            return ListDocumentsOutput(
                documents=[],
                total_count=0,
                limit=input_data.limit,
                offset=input_data.offset,
            )


# =============================================================================
# get_chunks_by_document Tool
# =============================================================================


async def get_chunks_by_document_handler(
    input_data: GetChunksByDocumentInput,
) -> GetChunksByDocumentOutput:
    """Retrieve all chunks for a document in sequential order.

    Queries the Weaviate Chunk collection to retrieve all chunks belonging
    to a specific document, ordered by orderIndex. Supports pagination
    and optional section filtering.

    Args:
        input_data: Validated input containing:
            - source_id: The document source ID (e.g., "platon-menon")
            - limit: Maximum number of chunks to return (default 50, max 500)
            - offset: Offset for pagination (default 0)
            - section_filter: Filter by section path prefix (optional)

    Returns:
        GetChunksByDocumentOutput containing:
            - chunks: List of ChunkResult objects ordered by orderIndex
            - total_count: Total number of chunks in document
            - document_source_id: The queried document source ID
            - limit: Applied limit value
            - offset: Applied offset value

    Example:
        >>> input_data = GetChunksByDocumentInput(source_id="platon-menon", limit=20)
        >>> result = await get_chunks_by_document_handler(input_data)
        >>> len(result.chunks) <= 20
        True
    """
    tool_inputs = {
        "source_id": input_data.source_id,
        "limit": input_data.limit,
        "offset": input_data.offset,
        "section_filter": input_data.section_filter,
    }

    with log_tool_invocation("get_chunks_by_document", tool_inputs) as invocation:
        try:
            with get_weaviate_client() as client:
                chunks_collection = client.collections.get("Chunk")

                # Build filter for document.sourceId
                filters: Any = (
                    Filter.by_property("document")
                    .by_property("sourceId")  # type: ignore[attr-defined]
                    .equal(input_data.source_id)
                )

                # Add section filter if provided
                if input_data.section_filter:
                    section_f = Filter.by_property("sectionPath").like(
                        f"{input_data.section_filter}*"
                    )
                    filters = filters & section_f

                # First, get total count
                query_start = time.perf_counter()
                count_result = chunks_collection.query.fetch_objects(
                    filters=filters,
                    limit=10000,  # High limit to count all
                )
                total_count = len(count_result.objects)

                # Fetch paginated results
                # Weaviate v4 fetch_objects doesn't support offset directly,
                # so we fetch limit + offset and slice
                fetch_limit = input_data.limit + input_data.offset
                result = chunks_collection.query.fetch_objects(
                    filters=filters,
                    limit=fetch_limit,
                )
                query_duration_ms = (time.perf_counter() - query_start) * 1000

                log_weaviate_query(
                    operation="fetch_objects",
                    collection="Chunk",
                    filters={
                        "source_id": input_data.source_id,
                        "section_filter": input_data.section_filter,
                    },
                    result_count=len(result.objects),
                    duration_ms=query_duration_ms,
                )

                # Apply offset by slicing and then limit
                paginated_objects = result.objects[input_data.offset:]

                # Convert results to output schema
                chunk_results: List[ChunkResult] = []
                for obj in paginated_objects[:input_data.limit]:
                    props = obj.properties
                    work_data = get_nested_dict(props, "work")
                    document_data = get_nested_dict(props, "document")

                    # Extract canonical reference
                    section_path = safe_str(props.get("sectionPath"), "")
                    source_id = safe_str(document_data.get("sourceId"), input_data.source_id)
                    work_title = safe_str(work_data.get("title"), "Unknown")
                    canonical_ref = extract_canonical_reference(
                        section_path, source_id, work_title
                    )

                    chunk = ChunkResult(
                        text=safe_str(props.get("text"), ""),
                        similarity=1.0,  # Not from search, use 1.0
                        source_id=source_id,
                        canonical_reference=canonical_ref,
                        section_path=section_path,
                        chapter_title=safe_str(props.get("chapterTitle")) or None,
                        work_title=work_title,
                        work_author=safe_str(work_data.get("author"), "Unknown"),
                        order_index=safe_int(props.get("orderIndex"), 0),
                    )
                    chunk_results.append(chunk)

                # Sort chunks by order_index to ensure correct order
                chunk_results.sort(key=lambda c: c.order_index)

                output = GetChunksByDocumentOutput(
                    chunks=chunk_results,
                    total_count=total_count,
                    document_source_id=input_data.source_id,
                    limit=input_data.limit,
                    offset=input_data.offset,
                )
                invocation.set_result(output.model_dump())
                return output

        except WeaviateConnectionError:
            # Re-raise connection errors (already logged)
            raise
        except Exception as e:
            logger.error(
                "Get chunks by document failed",
                extra={
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "source_id": input_data.source_id,
                },
                exc_info=True,
            )
            return GetChunksByDocumentOutput(
                chunks=[],
                total_count=0,
                document_source_id=input_data.source_id,
                limit=input_data.limit,
                offset=input_data.offset,
            )


# =============================================================================
# filter_by_author Tool
# =============================================================================


async def filter_by_author_handler(
    input_data: FilterByAuthorInput,
) -> FilterByAuthorOutput:
    """Get all works and documents by a specific author.

    Queries the Weaviate Work collection to retrieve all works by a specific
    author, along with their related documents. Optionally aggregates chunk
    counts for each work.

    Args:
        input_data: Validated input containing:
            - author: The author name to search for
            - include_chunk_counts: Whether to include chunk counts (default True)

    Returns:
        FilterByAuthorOutput containing:
            - author: The searched author name
            - works: List of AuthorWorkResult objects with work info and documents
            - total_works: Total number of works by this author
            - total_documents: Total number of documents across all works
            - total_chunks: Total number of chunks (if include_chunk_counts=True)

    Example:
        >>> input_data = FilterByAuthorInput(author="Platon")
        >>> result = await filter_by_author_handler(input_data)
        >>> result.total_works >= 0
        True
    """
    tool_inputs = {
        "author": input_data.author,
        "include_chunk_counts": input_data.include_chunk_counts,
    }

    with log_tool_invocation("filter_by_author", tool_inputs) as invocation:
        try:
            with get_weaviate_client() as client:
                # Use Work collection (Document was merged into Work)
                works_collection = client.collections.get("Work")
                chunks_collection = client.collections.get("Chunk")

                # Query Work collection by author
                query_start = time.perf_counter()
                work_filter = Filter.by_property("author").equal(input_data.author)
                works_result = works_collection.query.fetch_objects(
                    filters=work_filter,
                    limit=1000,  # High limit to get all works
                )
                query_duration_ms = (time.perf_counter() - query_start) * 1000

                log_weaviate_query(
                    operation="fetch_objects",
                    collection="Work",
                    filters={"author": input_data.author},
                    result_count=len(works_result.objects),
                    duration_ms=query_duration_ms,
                )

                # Build result structure
                author_works: List[AuthorWorkResult] = []
                total_documents = 0
                total_chunks = 0

                for work_obj in works_result.objects:
                    work_props = work_obj.properties
                    work_title = safe_str(work_props.get("title"), "Unknown")

                    # Create WorkInfo
                    work_info = WorkInfo(
                        title=work_title,
                        author=safe_str(work_props.get("author"), input_data.author),
                        year=safe_int(work_props.get("year")) or None,
                        language=safe_str(work_props.get("language"), "unknown"),
                        genre=safe_str(work_props.get("genre")) or None,
                    )

                    # Work now contains Document data (sourceId, pages, etc.)
                    # Each Work IS a document since they were merged
                    chunks_count = safe_int(work_props.get("chunksCount"), 0)

                    doc_summary = DocumentSummary(
                        source_id=safe_str(work_props.get("sourceId"), "unknown"),
                        work_title=work_title,
                        work_author=safe_str(work_props.get("author"), input_data.author),
                        pages=safe_int(work_props.get("pages"), 0),
                        chunks_count=chunks_count,
                        language=safe_str(work_props.get("language"), "unknown"),
                    )

                    # Build document summaries (one document per work now)
                    work_documents: List[DocumentSummary] = [doc_summary]
                    work_chunks_total = chunks_count

                    # If include_chunk_counts is False and we don't have chunksCount,
                    # we can optionally query the Chunk collection directly
                    if input_data.include_chunk_counts and work_chunks_total == 0:
                        # Fallback: count chunks for this work directly
                        chunk_filter = (
                            Filter.by_property("work")
                            .by_property("title")  # type: ignore[attr-defined]
                            .equal(work_title)
                        )
                        chunk_filter = (
                            chunk_filter
                            & Filter.by_property("work")
                            .by_property("author")  # type: ignore[attr-defined]
                            .equal(input_data.author)
                        )
                        chunks_result = chunks_collection.query.fetch_objects(
                            filters=chunk_filter,
                            limit=10000,
                        )
                        work_chunks_total = len(chunks_result.objects)

                    # Create AuthorWorkResult
                    author_work = AuthorWorkResult(
                        work=work_info,
                        documents=work_documents,
                        total_chunks=work_chunks_total,
                    )
                    author_works.append(author_work)

                    total_documents += len(work_documents)
                    total_chunks += work_chunks_total

                output = FilterByAuthorOutput(
                    author=input_data.author,
                    works=author_works,
                    total_works=len(author_works),
                    total_documents=total_documents,
                    total_chunks=total_chunks,
                )
                invocation.set_result(output.model_dump())
                return output

        except WeaviateConnectionError:
            # Re-raise connection errors (already logged)
            raise
        except Exception as e:
            logger.error(
                "Filter by author failed",
                extra={
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "author": input_data.author,
                },
                exc_info=True,
            )
            return FilterByAuthorOutput(
                author=input_data.author,
                works=[],
                total_works=0,
                total_documents=0,
                total_chunks=0,
            )


# =============================================================================
# delete_document Tool
# =============================================================================


async def delete_document_handler(
    input_data: DeleteDocumentInput,
) -> DeleteDocumentOutput:
    """Delete a document and all its chunks/summaries from Weaviate.

    Deletes all data associated with a document: the Document object itself,
    all Chunk objects, and all Summary objects. Requires explicit confirmation
    to prevent accidental deletions.

    Args:
        input_data: Validated input containing:
            - source_id: The document source ID to delete
            - confirm: Must be True to confirm deletion (safety check)

    Returns:
        DeleteDocumentOutput containing:
            - success: Whether deletion succeeded
            - source_id: The deleted document source ID
            - chunks_deleted: Number of chunks deleted
            - summaries_deleted: Number of summaries deleted
            - error: Error message if failed

    Raises:
        WeaviateConnectionError: If connection to Weaviate fails.

    Example:
        >>> input_data = DeleteDocumentInput(source_id="platon-menon", confirm=True)
        >>> result = await delete_document_handler(input_data)
        >>> result.success
        True

    Note:
        The confirm flag MUST be True to proceed with deletion. If confirm=False,
        the function returns immediately with success=False and an error message
        explaining that confirmation is required. This prevents accidental deletions.
    """
    tool_inputs = {
        "source_id": input_data.source_id,
        "confirm": input_data.confirm,
    }

    with log_tool_invocation("delete_document", tool_inputs) as invocation:
        # Safety check: require explicit confirmation
        if not input_data.confirm:
            logger.warning(
                "Delete document rejected: confirmation not provided",
                extra={"source_id": input_data.source_id},
            )
            output = DeleteDocumentOutput(
                success=False,
                source_id=input_data.source_id,
                chunks_deleted=0,
                summaries_deleted=0,
                error="Confirmation required: set confirm=True to delete the document",
            )
            invocation.set_result(output.model_dump())
            return output

        try:
            with get_weaviate_client() as client:
                chunks_deleted = 0
                summaries_deleted = 0

                # Delete chunks (filter on document.sourceId nested)
                query_start = time.perf_counter()
                try:
                    chunk_collection = client.collections.get("Chunk")
                    chunk_filter = (
                        Filter.by_property("document")
                        .by_property("sourceId")  # type: ignore[attr-defined]
                        .equal(input_data.source_id)
                    )
                    chunk_result = chunk_collection.data.delete_many(
                        where=chunk_filter
                    )
                    chunks_deleted = chunk_result.successful
                    logger.info(
                        f"Deleted {chunks_deleted} chunks for {input_data.source_id}",
                        extra={
                            "source_id": input_data.source_id,
                            "chunks_deleted": chunks_deleted,
                        },
                    )
                except Exception as e:
                    logger.warning(
                        f"Error deleting chunks: {e}",
                        extra={
                            "source_id": input_data.source_id,
                            "error": str(e),
                        },
                    )

                # Delete summaries (filter on document.sourceId nested)
                try:
                    summary_collection = client.collections.get("Summary")
                    summary_filter = (
                        Filter.by_property("document")
                        .by_property("sourceId")  # type: ignore[attr-defined]
                        .equal(input_data.source_id)
                    )
                    summary_result = summary_collection.data.delete_many(
                        where=summary_filter
                    )
                    summaries_deleted = summary_result.successful
                    logger.info(
                        f"Deleted {summaries_deleted} summaries for {input_data.source_id}",
                        extra={
                            "source_id": input_data.source_id,
                            "summaries_deleted": summaries_deleted,
                        },
                    )
                except Exception as e:
                    logger.warning(
                        f"Error deleting summaries: {e}",
                        extra={
                            "source_id": input_data.source_id,
                            "error": str(e),
                        },
                    )

                # Delete the document itself
                # Delete from Work collection (Document was merged into Work)
                work_deleted = False
                try:
                    work_collection = client.collections.get("Work")
                    work_filter = Filter.by_property("sourceId").equal(
                        input_data.source_id
                    )
                    work_result = work_collection.data.delete_many(where=work_filter)
                    work_deleted = work_result.successful > 0
                    if work_deleted:
                        logger.info(
                            f"Deleted work {input_data.source_id}",
                            extra={"source_id": input_data.source_id},
                        )
                except Exception as e:
                    logger.warning(
                        f"Error deleting work: {e}",
                        extra={
                            "source_id": input_data.source_id,
                            "error": str(e),
                        },
                    )

                query_duration_ms = (time.perf_counter() - query_start) * 1000

                log_weaviate_query(
                    operation="delete_many",
                    collection="Chunk,Summary,Work",
                    filters={"sourceId": input_data.source_id},
                    result_count=chunks_deleted + summaries_deleted,
                    duration_ms=query_duration_ms,
                )

                output = DeleteDocumentOutput(
                    success=True,
                    source_id=input_data.source_id,
                    chunks_deleted=chunks_deleted,
                    summaries_deleted=summaries_deleted,
                    error=None,
                )
                invocation.set_result(output.model_dump())
                return output

        except WeaviateConnectionError:
            # Re-raise connection errors (already logged)
            raise
        except Exception as e:
            logger.error(
                "Delete document failed",
                extra={
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "source_id": input_data.source_id,
                },
                exc_info=True,
            )
            return DeleteDocumentOutput(
                success=False,
                source_id=input_data.source_id,
                chunks_deleted=0,
                summaries_deleted=0,
                error=str(e),
            )
