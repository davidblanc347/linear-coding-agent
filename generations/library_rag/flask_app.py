"""Flask web application for Library RAG - Philosophical Text Search.

This module provides a web interface for the Library RAG application, enabling
users to upload PDF documents, process them through the OCR/LLM pipeline, and
perform semantic searches on the indexed philosophical texts stored in Weaviate.

Architecture:
    The application is built on Flask and connects to a local Weaviate instance
    for vector storage and semantic search. PDF processing is handled asynchronously
    using background threads with Server-Sent Events (SSE) for real-time progress.

Routes:
    - ``/`` : Home page with collection statistics (passages, authors, works)
    - ``/passages`` : Paginated list of all passages with author/work filters
    - ``/search`` : Semantic search interface using vector similarity
    - ``/upload`` : PDF upload form with processing options
    - ``/upload/progress/<job_id>`` : SSE endpoint for real-time processing updates
    - ``/upload/status/<job_id>`` : JSON endpoint to check job status
    - ``/documents`` : List of all processed documents
    - ``/documents/<doc_name>/view`` : Detailed view of a processed document
    - ``/documents/delete/<doc_name>`` : Delete a document and its Weaviate data
    - ``/output/<filepath>`` : Static file server for processed outputs

SSE Implementation:
    The upload progress system uses Server-Sent Events to stream real-time
    processing updates to the browser. Each processing step emits events::

        {"type": "step", "step": "OCR", "status": "running", "detail": "Page 1/10"}
        {"type": "complete", "redirect": "/documents/doc_name/view"}
        {"type": "error", "message": "OCR failed"}

    The SSE endpoint includes keep-alive messages every 30 seconds to maintain
    the connection and detect stale jobs.

Weaviate Connection:
    The application uses a context manager ``get_weaviate_client()`` to handle
    Weaviate connections. This ensures proper cleanup of connections even when
    errors occur. The client connects to localhost:8080 (HTTP) and localhost:50051
    (gRPC) by default.

Configuration:
    - ``SECRET_KEY`` : Flask session secret (set via environment variable)
    - ``UPLOAD_FOLDER`` : Directory for processed PDF outputs (default: ./output)
    - ``MAX_CONTENT_LENGTH`` : Maximum upload size (default: 50MB)

Example:
    Start the application in development mode::

        $ python flask_app.py

    Or with production settings::

        $ export SECRET_KEY="your-production-secret"
        $ gunicorn -w 4 flask_app:app

    Access the web interface at http://localhost:5000

Dependencies:
    - Flask 3.0+ for web framework
    - Weaviate Python client for vector database
    - utils.pdf_pipeline for PDF processing
    - utils.weaviate_ingest for database operations

See Also:
    - ``utils/pdf_pipeline.py`` : PDF processing pipeline
    - ``utils/weaviate_ingest.py`` : Weaviate ingestion functions
    - ``schema.py`` : Weaviate collection schemas
"""

import os
import json
import uuid
import threading
import queue
import time
from pathlib import Path
from typing import Any, Dict, Generator, Iterator, List, Optional, Union

from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory, Response, flash
from contextlib import contextmanager
from werkzeug.utils import secure_filename
from werkzeug.wrappers import Response as WerkzeugResponse
import weaviate
import weaviate.classes.query as wvq

from utils.types import (
    CollectionStats,
    ProcessingOptions,
    SSEEvent,
)

app = Flask(__name__)

# Configuration Flask
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

# Configuration upload
app.config["UPLOAD_FOLDER"] = Path(__file__).parent / "output"
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB max
ALLOWED_EXTENSIONS = {"pdf", "md", "docx"}

# Stockage des jobs de traitement en cours
processing_jobs: Dict[str, Dict[str, Any]] = {}  # {job_id: {"status": str, "queue": Queue, "result": dict}}

# Stockage des sessions de chat en cours
chat_sessions: Dict[str, Dict[str, Any]] = {}  # {session_id: {"status": str, "queue": Queue, "context": list}}

# Stockage des jobs TTS en cours
tts_jobs: Dict[str, Dict[str, Any]] = {}  # {job_id: {"status": str, "filepath": Path, "error": str}}

# ═══════════════════════════════════════════════════════════════════════════════
# Weaviate Connection
# ═══════════════════════════════════════════════════════════════════════════════

@contextmanager
def get_weaviate_client() -> Generator[Optional[weaviate.WeaviateClient], None, None]:
    """Context manager for Weaviate connection.

    Yields:
        WeaviateClient if connection succeeds, None otherwise.
    """
    client: Optional[weaviate.WeaviateClient] = None
    try:
        client = weaviate.connect_to_local(
            host="localhost",
            port=8080,
            grpc_port=50051,
        )
        yield client
    except Exception as e:
        print(f"Erreur connexion Weaviate: {e}")
        yield None
    finally:
        if client:
            client.close()


def get_collection_stats() -> Optional[CollectionStats]:
    """Get statistics about Weaviate collections.

    Returns:
        CollectionStats with passage counts and unique values, or None on error.
    """
    try:
        with get_weaviate_client() as client:
            if client is None:
                return None

            stats: CollectionStats = {}

            # Chunk stats (renamed from Passage)
            passages = client.collections.get("Chunk")
            passage_count = passages.aggregate.over_all(total_count=True)
            stats["passages"] = passage_count.total_count or 0

            # Get unique authors and works (from nested objects)
            all_passages = passages.query.fetch_objects(limit=1000)
            authors: set[str] = set()
            works: set[str] = set()
            languages: set[str] = set()

            for obj in all_passages.objects:
                # Work is now a nested object with {title, author}
                work_obj = obj.properties.get("work")
                if work_obj and isinstance(work_obj, dict):
                    if work_obj.get("author"):
                        authors.add(str(work_obj["author"]))
                    if work_obj.get("title"):
                        works.add(str(work_obj["title"]))
                if obj.properties.get("language"):
                    languages.add(str(obj.properties["language"]))

            stats["authors"] = len(authors)
            stats["works"] = len(works)
            stats["languages"] = len(languages)
            stats["author_list"] = sorted(authors)
            stats["work_list"] = sorted(works)
            stats["language_list"] = sorted(languages)

            return stats
    except Exception as e:
        print(f"Erreur stats: {e}")
        return None


def get_all_passages(
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Fetch all passages with pagination.

    Args:
        limit: Maximum number of passages to return.
        offset: Number of passages to skip (for pagination).

    Returns:
        List of passage dictionaries with uuid and properties.

    Note:
        Author/work filters are disabled due to Weaviate 1.34.4 limitation:
        nested object filtering is not yet supported (GitHub issue #3694).
    """
    try:
        with get_weaviate_client() as client:
            if client is None:
                return []

            chunks = client.collections.get("Chunk")

            result = chunks.query.fetch_objects(
                limit=limit,
                offset=offset,
                return_properties=[
                    "text", "sectionPath", "sectionLevel", "chapterTitle",
                    "canonicalReference", "unitType", "keywords", "orderIndex", "language"
                ],
            )

            return [
                {
                    "uuid": str(obj.uuid),
                    **obj.properties
                }
                for obj in result.objects
            ]
    except Exception as e:
        print(f"Erreur passages: {e}")
        return []


def simple_search(
    query: str,
    limit: int = 10,
    author_filter: Optional[str] = None,
    work_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Single-stage semantic search on Chunk collection (original implementation).

    Args:
        query: Search query text.
        limit: Maximum number of results to return.
        author_filter: Filter by author name (uses workAuthor property).
        work_filter: Filter by work title (uses workTitle property).

    Returns:
        List of passage dictionaries with uuid, similarity, and properties.
    """
    try:
        with get_weaviate_client() as client:
            if client is None:
                return []

            chunks = client.collections.get("Chunk")

            # Build filters using top-level properties (workAuthor, workTitle)
            filters: Optional[Any] = None
            if author_filter:
                filters = wvq.Filter.by_property("workAuthor").equal(author_filter)
            if work_filter:
                work_filter_obj = wvq.Filter.by_property("workTitle").equal(work_filter)
                filters = filters & work_filter_obj if filters else work_filter_obj

            result = chunks.query.near_text(
                query=query,
                limit=limit,
                filters=filters,
                return_metadata=wvq.MetadataQuery(distance=True),
                return_properties=[
                    "text", "sectionPath", "sectionLevel", "chapterTitle",
                    "canonicalReference", "unitType", "keywords", "orderIndex", "language"
                ],
            )

            return [
                {
                    "uuid": str(obj.uuid),
                    "distance": obj.metadata.distance if obj.metadata else None,
                    "similarity": round((1 - obj.metadata.distance) * 100, 1) if obj.metadata and obj.metadata.distance else None,
                    **obj.properties
                }
                for obj in result.objects
            ]
    except Exception as e:
        print(f"Erreur recherche: {e}")
        return []


def hierarchical_search(
    query: str,
    limit: int = 10,
    author_filter: Optional[str] = None,
    work_filter: Optional[str] = None,
    sections_limit: int = 5,
    force_hierarchical: bool = False,
) -> Dict[str, Any]:
    """Two-stage hierarchical semantic search: Summary → Chunks.

    Stage 1: Find top-N relevant sections via Summary collection.
    Stage 2: Search chunks within those sections for better precision.

    Args:
        query: Search query text.
        limit: Maximum number of chunks to return per section.
        author_filter: Filter by author name.
        work_filter: Filter by work title.
        sections_limit: Number of top sections to retrieve (default: 5).
        force_hierarchical: If True, never fallback to simple search (for testing).

    Returns:
        Dictionary with hierarchical search results:
        - mode: "hierarchical"
        - sections: List of section dictionaries with nested chunks
        - results: Flat list of all chunks (for compatibility)
        - total_chunks: Total number of chunks found
        - fallback_reason: Explanation if forced but 0 results (optional)
    """
    try:
        with get_weaviate_client() as client:
            if client is None:
                # Return early if forced, otherwise signal fallback
                if force_hierarchical:
                    return {
                        "mode": "hierarchical",
                        "sections": [],
                        "results": [],
                        "total_chunks": 0,
                        "fallback_reason": "Weaviate client unavailable",
                    }
                # Set flag to fallback outside context manager
                raise ValueError("FALLBACK_TO_SIMPLE")

            # ═══════════════════════════════════════════════════════════════
            # STAGE 1: Search Summary collection for relevant sections
            # ═══════════════════════════════════════════════════════════════

            summary_collection = client.collections.get("Summary")

            summaries_result = summary_collection.query.near_text(
                query=query,
                limit=sections_limit,
                return_metadata=wvq.MetadataQuery(distance=True),
                return_properties=[
                    "sectionPath", "title", "text", "level", "concepts", "document"
                ],
            )

            if not summaries_result.objects:
                # No summaries found
                if force_hierarchical:
                    # Forced hierarchical: return empty hierarchical result
                    return {
                        "mode": "hierarchical",
                        "sections": [],
                        "results": [],
                        "total_chunks": 0,
                        "fallback_reason": f"Aucune section pertinente trouvée (0/{sections_limit} summaries)",
                    }
                # Signal fallback outside context manager
                raise ValueError("FALLBACK_TO_SIMPLE")

            # Extract section data
            sections_data = []
            for summary_obj in summaries_result.objects:
                props = summary_obj.properties
                doc_obj = props.get("document", {}) if props.get("document") else {}

                sections_data.append({
                    "section_path": props.get("sectionPath", ""),
                    "title": props.get("title", ""),
                    "summary_text": props.get("text", ""),
                    "level": props.get("level", 1),
                    "concepts": props.get("concepts", []),
                    "document_source_id": doc_obj.get("sourceId", "") if isinstance(doc_obj, dict) else "",
                    "similarity": round((1 - summary_obj.metadata.distance) * 100, 1) if summary_obj.metadata and summary_obj.metadata.distance else 0,
                })

            # Post-filter sections by author/work (Summary doesn't have work nested object)
            if author_filter or work_filter:
                doc_collection = client.collections.get("Document")
                filtered_sections = []

                for section in sections_data:
                    source_id = section["document_source_id"]
                    if not source_id:
                        continue

                    # Query Document to get work metadata
                    doc_result = doc_collection.query.fetch_objects(
                        filters=wvq.Filter.by_property("sourceId").equal(source_id),
                        limit=1,
                        return_properties=["work"],
                    )

                    if doc_result.objects:
                        doc_work = doc_result.objects[0].properties.get("work", {})
                        if isinstance(doc_work, dict):
                            # Check filters
                            if author_filter and doc_work.get("author") != author_filter:
                                continue
                            if work_filter and doc_work.get("title") != work_filter:
                                continue

                        filtered_sections.append(section)

                sections_data = filtered_sections

            if not sections_data:
                # No sections match filters
                if force_hierarchical:
                    # Forced hierarchical: return empty hierarchical result
                    filters_str = f"author={author_filter}" if author_filter else ""
                    if work_filter:
                        filters_str += f", work={work_filter}" if filters_str else f"work={work_filter}"
                    return {
                        "mode": "hierarchical",
                        "sections": [],
                        "results": [],
                        "total_chunks": 0,
                        "fallback_reason": f"Aucune section ne correspond aux filtres ({filters_str})",
                    }
                # Signal fallback outside context manager
                raise ValueError("FALLBACK_TO_SIMPLE")

            # ═══════════════════════════════════════════════════════════════
            # STAGE 2: Search Chunk collection filtered by sections
            # ═══════════════════════════════════════════════════════════════

            chunk_collection = client.collections.get("Chunk")
            all_chunks = []

            for section in sections_data:
                section_path = section["section_path"]

                # Build filters
                filters: Optional[Any] = wvq.Filter.by_property("sectionPath").equal(section_path)

                if author_filter:
                    author_filter_obj = wvq.Filter.by_property("workAuthor").equal(author_filter)
                    filters = filters & author_filter_obj

                if work_filter:
                    work_filter_obj = wvq.Filter.by_property("workTitle").equal(work_filter)
                    filters = filters & work_filter_obj

                # Search chunks in this section
                chunks_result = chunk_collection.query.near_text(
                    query=query,
                    limit=limit,
                    filters=filters,
                    return_metadata=wvq.MetadataQuery(distance=True),
                    return_properties=[
                        "text", "sectionPath", "sectionLevel", "chapterTitle",
                        "canonicalReference", "unitType", "keywords", "orderIndex", "language"
                    ],
                )

                # Add chunks to section
                section_chunks = [
                    {
                        "uuid": str(obj.uuid),
                        "distance": obj.metadata.distance if obj.metadata else None,
                        "similarity": round((1 - obj.metadata.distance) * 100, 1) if obj.metadata and obj.metadata.distance else None,
                        **obj.properties
                    }
                    for obj in chunks_result.objects
                ]

                section["chunks"] = section_chunks
                section["chunks_count"] = len(section_chunks)
                all_chunks.extend(section_chunks)

            # Sort all chunks by similarity (descending)
            all_chunks.sort(key=lambda x: x.get("similarity", 0) or 0, reverse=True)

            return {
                "mode": "hierarchical",
                "sections": sections_data,
                "results": all_chunks,
                "total_chunks": len(all_chunks),
            }

    except ValueError as e:
        # Check if this is our fallback signal
        error_msg = str(e)
        if error_msg == "FALLBACK_TO_SIMPLE" or error_msg.startswith("FALLBACK_ERROR:"):
            # Fallback to simple search (outside context manager)
            results = simple_search(query, limit, author_filter, work_filter)
            return {
                "mode": "simple",
                "results": results,
                "total_chunks": len(results),
            }
        # Re-raise if not our signal
        raise
    except Exception as e:
        print(f"Erreur recherche hiérarchique: {e}")
        import traceback
        traceback.print_exc()

        # Fallback to simple search on error (unless forced)
        if not force_hierarchical:
            # CRITICAL: We're still inside the 'with' block here!
            # Signal fallback to exit context manager before calling simple_search()
            raise ValueError(f"FALLBACK_ERROR: {str(e)}")
        else:
            # Forced hierarchical: return error in hierarchical format
            return {
                "mode": "hierarchical",
                "sections": [],
                "results": [],
                "total_chunks": 0,
                "fallback_reason": f"Erreur lors de la recherche hiérarchique: {str(e)}",
            }


def should_use_hierarchical_search(query: str) -> bool:
    """Detect if a query would benefit from hierarchical 2-stage search.

    Hierarchical search is recommended for:
    - Long queries (≥15 characters) indicating complex questions
    - Multi-concept queries (2+ significant words)
    - Queries with logical connectors (et, ou, mais, donc, car)

    Args:
        query: Search query text.

    Returns:
        True if hierarchical search is recommended, False for simple search.

    Examples:
        >>> should_use_hierarchical_search("justice")
        False  # Short query, single concept
        >>> should_use_hierarchical_search("Qu'est-ce que la justice selon Platon ?")
        True  # Long query, multi-concept, philosophical question
        >>> should_use_hierarchical_search("vertu et sagesse")
        True  # Multi-concept with connector
    """
    if not query or len(query.strip()) == 0:
        return False

    query_lower = query.lower().strip()

    # Criterion 1: Long queries (≥15 chars) suggest complexity
    if len(query_lower) >= 15:
        return True

    # Criterion 2: Presence of logical connectors
    connectors = ["et", "ou", "mais", "donc", "car", "parce que", "puisque", "si"]
    if any(f" {connector} " in f" {query_lower} " for connector in connectors):
        return True

    # Criterion 3: Multi-concept (2+ significant words, excluding stop words)
    stop_words = {
        "le", "la", "les", "un", "une", "des", "du", "de", "d",
        "ce", "cette", "ces", "mon", "ma", "mes", "ton", "ta", "tes",
        "à", "au", "aux", "dans", "sur", "pour", "par", "avec",
        "que", "qui", "quoi", "dont", "où", "est", "sont", "a",
        "qu", "c", "l", "s", "n", "m", "t", "j", "y",
    }

    words = query_lower.split()
    significant_words = [w for w in words if len(w) > 2 and w not in stop_words]

    if len(significant_words) >= 2:
        return True

    # Default: use simple search for short, single-concept queries
    return False


def search_passages(
    query: str,
    limit: int = 10,
    author_filter: Optional[str] = None,
    work_filter: Optional[str] = None,
    sections_limit: int = 5,
    force_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """Intelligent semantic search dispatcher with auto-detection.

    Automatically chooses between simple (1-stage) and hierarchical (2-stage)
    search based on query complexity. Complex queries use hierarchical search
    for better precision and context.

    Args:
        query: Search query text.
        limit: Maximum number of chunks to return (per section if hierarchical).
        author_filter: Filter by author name (uses workAuthor property).
        work_filter: Filter by work title (uses workTitle property).
        sections_limit: Number of top sections for hierarchical search (default: 5).
        force_mode: Force search mode ("simple", "hierarchical", or None for auto).

    Returns:
        Dictionary with search results:
        - mode: "simple" or "hierarchical"
        - results: List of passage dictionaries (flat)
        - sections: List of section dicts with nested chunks (hierarchical only)
        - total_chunks: Total number of chunks found

    Examples:
        >>> # Short query → auto-detects simple search
        >>> search_passages("justice", limit=10)
        {"mode": "simple", "results": [...], "total_chunks": 10}

        >>> # Complex query → auto-detects hierarchical search
        >>> search_passages("Qu'est-ce que la vertu selon Aristote ?", limit=5)
        {"mode": "hierarchical", "sections": [...], "results": [...], "total_chunks": 15}

        >>> # Force hierarchical mode
        >>> search_passages("justice", force_mode="hierarchical", sections_limit=3)
        {"mode": "hierarchical", ...}
    """
    # Determine search mode
    if force_mode == "simple":
        use_hierarchical = False
    elif force_mode == "hierarchical":
        use_hierarchical = True
    else:
        # Auto-detection
        use_hierarchical = should_use_hierarchical_search(query)

    # Execute appropriate search strategy
    if use_hierarchical:
        return hierarchical_search(
            query=query,
            limit=limit,
            author_filter=author_filter,
            work_filter=work_filter,
            sections_limit=sections_limit,
            force_hierarchical=(force_mode == "hierarchical"),  # No fallback if explicitly forced
        )
    else:
        results = simple_search(query, limit, author_filter, work_filter)
        return {
            "mode": "simple",
            "results": results,
            "total_chunks": len(results),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Routes
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index() -> str:
    """Render the home page with collection statistics.

    Displays an overview of the Library RAG application with statistics about
    indexed passages, works, authors, and supported languages from Weaviate.

    Returns:
        Rendered HTML template (index.html) with collection statistics including:
        - Total passage count
        - Number of unique authors and works
        - List of available languages

    Note:
        If Weaviate connection fails, stats will be None and the template
        should handle displaying an appropriate fallback message.
    """
    from utils.types import CollectionStats
    stats: Optional[CollectionStats] = get_collection_stats()
    return render_template("index.html", stats=stats)


@app.route("/passages")
def passages() -> str:
    """Render the passages list page with pagination and filtering.

    Displays a paginated list of all indexed passages from Weaviate with optional
    filtering by author and/or work title. Includes statistics and filter options
    in the sidebar.

    Query Parameters:
        page (int): Page number for pagination. Defaults to 1.
        per_page (int): Number of passages per page. Defaults to 20.
        author (str, optional): Filter passages by author name.
        work (str, optional): Filter passages by work title.

    Returns:
        Rendered HTML template (passages.html) with:
        - List of passages for the current page
        - Collection statistics for sidebar filters
        - Pagination controls
        - Current filter state

    Example:
        GET /passages?page=2&per_page=50&author=Platon
        Returns page 2 with 50 passages per page, filtered by author "Platon".
    """
    page: int = request.args.get("page", 1, type=int)
    per_page: int = request.args.get("per_page", 20, type=int)
    author: Optional[str] = request.args.get("author", None)
    work: Optional[str] = request.args.get("work", None)

    # Clean filters
    if author == "":
        author = None
    if work == "":
        work = None

    offset: int = (page - 1) * per_page

    from utils.types import CollectionStats
    stats: Optional[CollectionStats] = get_collection_stats()
    passages_list: List[Dict[str, Any]] = get_all_passages(
        limit=per_page,
        offset=offset,
    )

    return render_template(
        "passages.html",
        chunks=passages_list,
        stats=stats,
        page=page,
        per_page=per_page,
        author_filter=author,
        work_filter=work,
    )


@app.route("/search")
def search() -> str:
    """Render the semantic search page with vector similarity results.

    Provides a search interface for finding passages using semantic similarity
    via Weaviate's near_text query. Results include similarity scores and can
    be filtered by author and/or work.

    Query Parameters:
        q (str): Search query text. Empty string shows no results.
        limit (int): Maximum number of chunks per section. Defaults to 10.
        author (str, optional): Filter results by author name.
        work (str, optional): Filter results by work title.
        sections_limit (int): Number of sections for hierarchical search. Defaults to 5.
        mode (str, optional): Force search mode ("simple", "hierarchical", or "" for auto).

    Returns:
        Rendered HTML template (search.html) with:
        - Search form with current query
        - List of matching passages with similarity percentages
        - Collection statistics for filter dropdowns
        - Current filter state
        - Search mode indicator (simple vs hierarchical)

    Example:
        GET /search?q=la%20mort%20et%20le%20temps&limit=5&sections_limit=3
        Auto-detects hierarchical search, returns top 3 sections with 5 chunks each.
    """
    query: str = request.args.get("q", "")
    limit: int = request.args.get("limit", 10, type=int)
    author: Optional[str] = request.args.get("author", None)
    work: Optional[str] = request.args.get("work", None)
    sections_limit: int = request.args.get("sections_limit", 5, type=int)
    mode: Optional[str] = request.args.get("mode", None)

    # Clean filters
    if author == "":
        author = None
    if work == "":
        work = None
    if mode == "":
        mode = None

    from utils.types import CollectionStats
    stats: Optional[CollectionStats] = get_collection_stats()
    results_data: Optional[Dict[str, Any]] = None

    if query:
        results_data = search_passages(
            query=query,
            limit=limit,
            author_filter=author,
            work_filter=work,
            sections_limit=sections_limit,
            force_mode=mode,
        )

    return render_template(
        "search.html",
        query=query,
        results_data=results_data,
        stats=stats,
        limit=limit,
        sections_limit=sections_limit,
        mode=mode,
        author_filter=author,
        work_filter=work,
    )


def rag_search(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Search passages for RAG context with formatted results.

    Wraps the existing search_passages() function but returns results formatted
    specifically for RAG prompt construction. Includes author, work, and section
    information needed to build context for LLM generation.

    Args:
        query: The user's question or search query.
        limit: Maximum number of context chunks to retrieve. Defaults to 5.

    Returns:
        List of context dictionaries with keys:
        - text (str): The passage text content
        - author (str): Author name (from workAuthor)
        - work (str): Work title (from workTitle)
        - section (str): Section path or chapter title
        - similarity (float): Similarity score 0-100
        - uuid (str): Weaviate chunk UUID

    Example:
        >>> results = rag_search("Qu'est-ce que la vertu ?", limit=3)
        >>> results[0]["author"]
        'Platon'
        >>> results[0]["work"]
        'République'
    """
    import time
    start_time = time.time()

    try:
        with get_weaviate_client() as client:
            if client is None:
                print("[RAG Search] Weaviate client unavailable")
                return []

            chunks = client.collections.get("Chunk")

            # Query with properties needed for RAG context
            result = chunks.query.near_text(
                query=query,
                limit=limit,
                return_metadata=wvq.MetadataQuery(distance=True),
                return_properties=[
                    "text",
                    "workAuthor",  # Top-level author property
                    "workTitle",   # Top-level work property
                    "sectionPath",
                    "chapterTitle",
                    "canonicalReference",
                ],
            )

            # Format results for RAG prompt construction
            formatted_results = []
            for obj in result.objects:
                props = obj.properties
                similarity = round((1 - obj.metadata.distance) * 100, 1) if obj.metadata and obj.metadata.distance else 0.0

                formatted_results.append({
                    "text": props.get("text", ""),
                    "author": props.get("workAuthor", "Auteur inconnu"),
                    "work": props.get("workTitle", "Œuvre inconnue"),
                    "section": props.get("sectionPath") or props.get("chapterTitle") or "Section inconnue",
                    "similarity": similarity,
                    "uuid": str(obj.uuid),
                })

            # Log search metrics
            elapsed = time.time() - start_time
            print(f"[RAG Search] Query: '{query[:50]}...' | Results: {len(formatted_results)} | Time: {elapsed:.2f}s")

            return formatted_results

    except Exception as e:
        print(f"[RAG Search] Error: {e}")
        return []


def diverse_author_search(
    query: str,
    limit: int = 10,
    initial_pool: int = 100,
    max_authors: int = 5,
    chunks_per_author: int = 2
) -> List[Dict[str, Any]]:
    """Search passages with author diversity to avoid corpus imbalance bias.

    This function addresses the problem where prolific authors (e.g., Peirce with
    300 works) dominate search results over less represented but equally relevant
    authors (e.g., Tiercelin with 1 work).

    Algorithm:
        1. Retrieve large initial pool of chunks (e.g., 100)
        2. Group chunks by author
        3. Compute average similarity score of top-3 chunks per author
        4. Select top-N authors by average score
        5. Extract best chunks from each selected author
        6. Return diversified chunk list

    Args:
        query: The user's question or search query.
        limit: Maximum number of chunks to return (default: 10).
        initial_pool: Size of initial candidate pool (default: 100).
        max_authors: Maximum number of distinct authors to include (default: 5).
        chunks_per_author: Number of chunks per selected author (default: 2).

    Returns:
        List of context dictionaries with keys:
        - text (str): The passage text content
        - author (str): Author name (from workAuthor)
        - work (str): Work title (from workTitle)
        - section (str): Section path or chapter title
        - similarity (float): Similarity score 0-100
        - uuid (str): Weaviate chunk UUID

    Example:
        >>> results = diverse_author_search("Scotus et Peirce", limit=10)
        >>> authors = set(r["author"] for r in results)
        >>> len(authors)  # Multiple authors guaranteed
        5
        >>> [r["author"] for r in results].count("Peirce")  # Max chunks_per_author
        2

    Note:
        This prevents a single prolific author from dominating all results.
        For "Scotus et Peirce", ensures results from Peirce, Tiercelin, Scotus,
        Boler, and other relevant commentators.
    """
    import time
    start_time = time.time()

    print(f"[Diverse Search] CALLED with query='{query[:50]}...', initial_pool={initial_pool}, max_authors={max_authors}, chunks_per_author={chunks_per_author}")

    try:
        # Step 1: Retrieve large initial pool
        print(f"[Diverse Search] Calling rag_search with limit={initial_pool}")
        candidates = rag_search(query, limit=initial_pool)
        print(f"[Diverse Search] rag_search returned {len(candidates)} candidates")

        if not candidates:
            print("[Diverse Search] No candidates found, returning empty list")
            return []

        # Step 2: Group chunks by author
        by_author: Dict[str, List[Dict[str, Any]]] = {}
        for chunk in candidates:
            author = chunk.get("author", "Auteur inconnu")
            if author not in by_author:
                by_author[author] = []
            by_author[author].append(chunk)

        print(f"[Diverse Search] Found {len(by_author)} distinct authors in pool of {len(candidates)} chunks")

        # Step 3: Compute average similarity of top-3 chunks per author
        author_scores: Dict[str, float] = {}
        for author, chunks in by_author.items():
            # Sort by similarity descending
            sorted_chunks = sorted(chunks, key=lambda x: x["similarity"], reverse=True)
            # Take top-3 (or all if fewer than 3)
            top_chunks = sorted_chunks[:3]
            # Average similarity
            avg_score = sum(c["similarity"] for c in top_chunks) / len(top_chunks)
            author_scores[author] = avg_score

        # Step 4: Select top-N authors by average score
        top_authors = sorted(author_scores.items(), key=lambda x: x[1], reverse=True)[:max_authors]

        print(f"[Diverse Search] Top {len(top_authors)} authors: {[author for author, score in top_authors]}")
        for author, score in top_authors:
            print(f"  - {author}: avg_score={score:.1f}%, {len(by_author[author])} chunks in pool")

        # Step 5: Extract best chunks from each selected author
        # SMART ALLOCATION: If only 1-2 authors, take more chunks per author to reach target limit
        num_authors = len(top_authors)
        if num_authors == 1:
            # Only one author: take up to 'limit' chunks from that author
            adaptive_chunks_per_author = limit
            print(f"[Diverse Search] Only 1 author found → taking up to {adaptive_chunks_per_author} chunks")
        elif num_authors <= 3:
            # Few authors (2-3): take more chunks per author
            adaptive_chunks_per_author = max(chunks_per_author, limit // num_authors)
            print(f"[Diverse Search] Only {num_authors} authors → taking up to {adaptive_chunks_per_author} chunks per author")
        else:
            # Many authors (4+): stick to original limit for diversity
            adaptive_chunks_per_author = chunks_per_author
            print(f"[Diverse Search] {num_authors} authors → taking {adaptive_chunks_per_author} chunks per author")

        final_chunks: List[Dict[str, Any]] = []
        for author, avg_score in top_authors:
            # Get best chunks for this author
            author_chunks = sorted(by_author[author], key=lambda x: x["similarity"], reverse=True)
            selected = author_chunks[:adaptive_chunks_per_author]
            final_chunks.extend(selected)

        # Cap at limit
        final_chunks = final_chunks[:limit]

        # Log final metrics
        final_authors = set(c["author"] for c in final_chunks)
        elapsed = time.time() - start_time
        print(f"[Diverse Search] Final: {len(final_chunks)} chunks from {len(final_authors)} authors | Time: {elapsed:.2f}s")

        return final_chunks

    except Exception as e:
        import traceback
        print(f"[Diverse Search] EXCEPTION CAUGHT: {e}")
        print(f"[Diverse Search] Traceback: {traceback.format_exc()}")
        print(f"[Diverse Search] Falling back to standard rag_search with limit={limit}")
        # Fallback to standard search
        return rag_search(query, limit)


def build_prompt_with_context(user_question: str, rag_context: List[Dict[str, Any]]) -> str:
    """Build a prompt for LLM generation using RAG context.

    Constructs a comprehensive prompt that includes a system instruction,
    formatted RAG context chunks with author/work metadata, and the user's
    question. The prompt is designed to work with all LLM providers
    (Ollama, Mistral, Anthropic, OpenAI).

    Args:
        user_question: The user's question in natural language.
        rag_context: List of context dictionaries from rag_search() with keys:
            - text: Passage text
            - author: Author name
            - work: Work title
            - section: Section or chapter
            - similarity: Similarity score (0-100)

    Returns:
        Formatted prompt string ready for LLM generation.

    Example:
        >>> context = rag_search("Qu'est-ce que la justice ?", limit=2)
        >>> prompt = build_prompt_with_context("Qu'est-ce que la justice ?", context)
        >>> print(prompt[:100])
        'Vous êtes un assistant spécialisé en philosophie...'
    """
    # System instruction
    system_instruction = """Vous êtes un assistant expert en philosophie. Votre rôle est de fournir des analyses APPROFONDIES et DÉTAILLÉES en vous appuyant sur les passages philosophiques fournis.

INSTRUCTIONS IMPÉRATIVES :
- Fournissez une réponse LONGUE et DÉVELOPPÉE (minimum 500-800 mots)
- Analysez EN PROFONDEUR tous les aspects de la question
- Citez ABONDAMMENT les passages fournis avec références précises (auteur, œuvre)
- Développez les concepts philosophiques, ne vous contentez PAS de résumés superficiels
- Explorez les NUANCES, les implications, les relations entre les idées
- Structurez votre réponse en sections claires (introduction, développement avec sous-parties, conclusion)
- Si les passages ne couvrent pas tous les aspects, indiquez-le mais développez ce qui est disponible
- Adoptez un style académique rigoureux digne d'une analyse philosophique universitaire
- N'inventez JAMAIS d'informations absentes des passages, mais exploitez à fond celles qui y sont"""

    # Build context section
    context_section = "\n\nPASSAGES PHILOSOPHIQUES :\n\n"

    if not rag_context:
        context_section += "(Aucun passage trouvé)\n"
    else:
        for i, chunk in enumerate(rag_context, 1):
            author = chunk.get("author", "Auteur inconnu")
            work = chunk.get("work", "Œuvre inconnue")
            section = chunk.get("section", "")
            text = chunk.get("text", "")
            similarity = chunk.get("similarity", 0)

            # Truncate very long passages (keep first 2000 chars max per chunk for deep analysis)
            if len(text) > 2000:
                text = text[:2000] + "..."

            context_section += f"**Passage {i}** [Score de pertinence: {similarity}%]\n"
            context_section += f"**Auteur :** {author}\n"
            context_section += f"**Œuvre :** {work}\n"
            if section:
                context_section += f"**Section :** {section}\n"
            context_section += f"\n{text}\n\n"
            context_section += "---\n\n"

    # User question
    question_section = f"\nQUESTION :\n{user_question}\n\n"

    # Final instruction
    final_instruction = """CONSIGNE FINALE :
Répondez à cette question en produisant une analyse philosophique COMPLÈTE et APPROFONDIE (minimum 500-800 mots).
Votre réponse doit :
1. Commencer par une introduction contextualisant la question
2. Développer une analyse détaillée en plusieurs parties, citant abondamment les passages
3. Explorer les implications philosophiques, les concepts-clés, les relations entre les idées
4. Conclure en synthétisant l'apport des passages à la question posée

Ne vous limitez PAS à un résumé superficiel. Développez, analysez, approfondissez. C'est une discussion philosophique universitaire, pas un tweet."""

    # Combine all sections
    full_prompt = system_instruction + context_section + question_section + final_instruction

    # Truncate if too long (max ~30000 chars - modern LLMs have 128k+ context windows)
    if len(full_prompt) > 30000:
        # Reduce number of context chunks
        print(f"[Prompt Builder] Warning: Prompt too long ({len(full_prompt)} chars), truncating context")
        truncated_context = rag_context[:min(3, len(rag_context))]  # Keep only top 3 chunks
        return build_prompt_with_context(user_question, truncated_context)

    return full_prompt


@app.route("/test-rag")
def test_rag() -> Dict[str, Any]:
    """Test endpoint for RAG search function.

    Example:
        GET /test-rag?q=vertu&limit=3
    """
    query = request.args.get("q", "Qu'est-ce que la vertu ?")
    limit = request.args.get("limit", 5, type=int)

    results = rag_search(query, limit)

    return jsonify({
        "query": query,
        "limit": limit,
        "results_count": len(results),
        "results": results
    })


@app.route("/test-prompt")
def test_prompt() -> str:
    """Test endpoint for prompt construction with RAG context.

    Example:
        GET /test-prompt?q=Qu'est-ce que la justice ?&limit=3

    Returns:
        HTML page displaying the constructed prompt.
    """
    query = request.args.get("q", "Qu'est-ce que la vertu ?")
    limit = request.args.get("limit", 3, type=int)

    # Get RAG context
    rag_context = rag_search(query, limit)

    # Build prompt
    prompt = build_prompt_with_context(query, rag_context)

    # Display as preformatted text in HTML
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Test Prompt RAG</title>
        <style>
            body {{
                font-family: monospace;
                padding: 2rem;
                background-color: #f5f5f5;
            }}
            .container {{
                max-width: 1000px;
                margin: 0 auto;
                background: white;
                padding: 2rem;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            h1 {{
                font-family: sans-serif;
                color: #333;
            }}
            .info {{
                background: #e3f2fd;
                padding: 1rem;
                border-radius: 4px;
                margin-bottom: 1rem;
                font-family: sans-serif;
            }}
            pre {{
                background: #2b2b2b;
                color: #f8f8f8;
                padding: 1.5rem;
                border-radius: 4px;
                overflow-x: auto;
                white-space: pre-wrap;
                word-wrap: break-word;
                line-height: 1.5;
            }}
            .stats {{
                margin-top: 1rem;
                padding: 1rem;
                background: #f9f9f9;
                border-radius: 4px;
                font-family: sans-serif;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🧪 Test Prompt Construction RAG</h1>
            <div class="info">
                <strong>Question:</strong> {query}<br>
                <strong>Contextes RAG:</strong> {len(rag_context)} passages<br>
                <strong>Longueur prompt:</strong> {len(prompt)} caractères
            </div>
            <h2>Prompt généré :</h2>
            <pre>{prompt}</pre>
            <div class="stats">
                <strong>Chunks utilisés :</strong><br>
                {chr(10).join([f"- {c['author']} - {c['work']} (similarité: {c['similarity']}%)" for c in rag_context])}
            </div>
        </div>
    </body>
    </html>
    """

    return html


@app.route("/test-llm")
def test_llm() -> WerkzeugResponse:
    """Test endpoint for LLM streaming.

    Example:
        GET /test-llm?provider=ollama&model=qwen2.5:7b&prompt=Hello

    Returns:
        Plain text streamed response.
    """
    from utils.llm_chat import call_llm, LLMError

    provider = request.args.get("provider", "ollama")
    model = request.args.get("model", "qwen2.5:7b")
    prompt = request.args.get("prompt", "Réponds en une phrase: Qu'est-ce que la philosophie ?")

    def generate() -> Iterator[str]:
        try:
            yield f"[Test LLM Streaming]\n"
            yield f"Provider: {provider}\n"
            yield f"Model: {model}\n"
            yield f"Prompt: {prompt}\n\n"
            yield "Response:\n"

            for token in call_llm(prompt, provider, model, stream=True):
                yield token

            yield "\n\n[Done]"

        except LLMError as e:
            yield f"\n\n[Error] {str(e)}"
        except Exception as e:
            yield f"\n\n[Unexpected Error] {str(e)}"

    return Response(generate(), mimetype='text/plain')


@app.route("/test-chat-backend")
def test_chat_backend() -> str:
    """Test page for chat backend."""
    return render_template("test_chat_backend.html")


@app.route("/chat")
def chat() -> str:
    """Render the conversation RAG interface.

    Provides a ChatGPT-like conversation interface where users can ask questions
    in natural language. The system performs RAG (Retrieval-Augmented Generation)
    by searching Weaviate for relevant philosophical text chunks and using them
    to generate AI-powered answers via multiple LLM providers.

    Features:
        - Multi-LLM support: Ollama (local), Mistral API, Anthropic API, OpenAI API
        - Real-time streaming responses via Server-Sent Events
        - RAG context sidebar showing relevant chunks used for answer generation
        - Markdown rendering with code syntax highlighting

    Returns:
        Rendered HTML template (chat.html) with:
        - Chat interface with message history
        - Model selector dropdown
        - Input area for user questions
        - Context sidebar for RAG chunks

    Example:
        GET /chat
        Returns the conversation interface ready for user interaction.
    """
    # Get collection stats for display (optional)
    stats: Optional[CollectionStats] = get_collection_stats()

    return render_template(
        "chat.html",
        stats=stats,
    )


def rerank_rag_chunks(question: str, chunks: List[Dict[str, Any]], provider: str, model: str) -> List[Dict[str, Any]]:
    """Re-rank RAG chunks using LLM to filter out irrelevant results.

    After semantic search, uses LLM to evaluate which chunks are actually
    relevant to the question and filters out noise (index pages, tangential mentions, etc.).

    Args:
        question: The reformulated search query.
        chunks: List of RAG chunks from semantic search.
        provider: LLM provider name.
        model: LLM model name.

    Returns:
        Filtered list of chunks that are genuinely relevant (minimum 2 chunks).

    Example:
        >>> chunks = rag_search("L'apport de Duns Scotus à Peirce", limit=5)
        >>> relevant = rerank_rag_chunks("L'apport de Duns Scotus à Peirce", chunks, "mistral", "mistral-small-latest")
        >>> len(relevant) <= len(chunks)
        True
    """
    from utils.llm_chat import call_llm

    if not chunks or len(chunks) <= 3:
        return chunks  # Keep all if too few (≤3 chunks)

    # Build reranking prompt
    reranking_prompt = f"""Tu es un expert en évaluation de pertinence pour la recherche sémantique.

QUESTION : {question}

PASSAGES À ÉVALUER :
"""

    for i, chunk in enumerate(chunks, 1):
        text_preview = chunk.get("text", "")[:400]  # First 400 chars (increased from 300)
        author = chunk.get("author", "")
        work = chunk.get("work", "")
        similarity = chunk.get("similarity", 0)
        reranking_prompt += f"\n[{i}] ({similarity}%) {author} - {work}\n{text_preview}...\n"

    reranking_prompt += f"""
TÂCHE : Identifie les numéros des passages pertinents (garde au moins {min(10, len(chunks))} passages).

CRITÈRES (sois TRÈS inclusif) :
- GARDE : contenu substantiel, analyse, citations, développement
- GARDE : contexte, introduction, commentaires indirects
- EXCLUS : index purs, tables des matières vides, bibliographies seules
- En cas de doute → INCLUS (philosophie = contexte riche nécessaire)

IMPORTANT - FORMAT DE RÉPONSE :
- Si tous pertinents → réponds exactement : ALL
- Sinon → réponds UNIQUEMENT les numéros séparés par virgules
- AUCUN texte explicatif, AUCUN markdown, AUCUNE justification
- Minimum {min(8, len(chunks))} numéros

EXEMPLES DE RÉPONSES VALIDES :
- ALL
- 1,2,3,4,5,6,7,8
- 1,3,5,7,9,11,13,15

RÉPONSE (numéros UNIQUEMENT) :"""

    # Get LLM evaluation
    response = ""
    for token in call_llm(reranking_prompt, provider, model, stream=False, temperature=0.2, max_tokens=200):
        response += token

    response = response.strip()

    # Log LLM response for debugging
    print(f"[Re-ranking] LLM response: {response}")

    # Clean response: extract only numbers if LLM added markdown/explanations
    # Common patterns: "**1, 4**" or "1,4\n\n**Explications:**"
    import re
    # Extract first line or content before markdown/explanations
    first_line = response.split('\n')[0].strip()
    # Remove markdown formatting (**, __, etc.)
    cleaned = re.sub(r'\*\*|__|~~', '', first_line).strip()

    print(f"[Re-ranking] Cleaned response: {cleaned}")

    # Parse response
    if cleaned.upper() == "ALL":
        print(f"[Re-ranking] LLM selected ALL chunks, returning all {len(chunks)} chunks")
        return chunks  # Return all chunks
    elif cleaned.upper() == "NONE":
        print(f"[Re-ranking] LLM selected NONE, returning top 8 by similarity")
        return chunks[:8]  # Keep top 8 by similarity even if LLM says none
    else:
        try:
            # Parse comma-separated numbers from cleaned response
            relevant_indices = [int(num.strip()) - 1 for num in cleaned.split(",") if num.strip().isdigit()]
            filtered_chunks = [chunks[i] for i in relevant_indices if 0 <= i < len(chunks)]

            print(f"[Re-ranking] LLM selected {len(filtered_chunks)} chunks from {len(chunks)} candidates")

            # Log excluded chunks for debugging
            excluded_indices = [i for i in range(len(chunks)) if i not in relevant_indices]
            if excluded_indices:
                print(f"\n[Re-ranking] ❌ EXCLUDED {len(excluded_indices)} chunks:")
                for idx in excluded_indices:
                    chunk = chunks[idx]
                    author = chunk.get('author', 'Unknown')
                    work = chunk.get('work', 'Unknown')
                    text_preview = chunk.get('text', '')[:150].replace('\n', ' ')
                    similarity = chunk.get('similarity', 0)
                    print(f"  [{idx+1}] ({similarity}%) {author} - {work}")
                    print(f"      \"{text_preview}...\"")

            # Ensure minimum of all chunks if too few selected (re-ranking failed)
            if len(filtered_chunks) < len(chunks) // 2:
                print(f"[Re-ranking] Too few selected ({len(filtered_chunks)}), keeping ALL {len(chunks)} chunks")
                return chunks

            # Return filtered chunks (no cap, trust the LLM selection)
            return filtered_chunks if filtered_chunks else chunks
        except Exception as e:
            print(f"[Re-ranking] Parse error: {e}, keeping ALL {len(chunks)} chunks")
            return chunks


def reformulate_question(question: str, provider: str, model: str) -> str:
    """Reformulate user question for optimal RAG search.

    Takes a potentially informal or poorly worded question and reformulates
    it into a clear, well-structured search query optimized for semantic search.

    Args:
        question: Original user question (may be informal).
        provider: LLM provider name.
        model: LLM model name.

    Returns:
        Reformulated question optimized for RAG search.

    Example:
        >>> reformulate_question("scotus a apporté quoi a Peirce?", "mistral", "mistral-small-latest")
        "L'apport de Duns Scotus à la philosophie de Charles Sanders Peirce"
    """
    from utils.llm_chat import call_llm

    reformulation_prompt = f"""Tu es un expert en recherche philosophique et en reformulation de requêtes pour bases de données textuelles.

Ta tâche : transformer la question suivante en une REQUÊTE LONGUE ET DÉTAILLÉE (plusieurs lignes) qui maximisera la récupération de passages pertinents dans une recherche sémantique.

RÈGLES DE REFORMULATION EXPANSIVE :
1. Corrige les fautes et formalise le langage
2. Explicite TOUS les noms propres avec leurs formes complètes et variantes :
   - Ex: "Scotus" → "Duns Scot, Jean Duns Scot, Scotus"
   - Ex: "Peirce" → "Charles Sanders Peirce, C.S. Peirce"
3. DÉVELOPPE la question en problématique philosophique (3-5 lignes) :
   - Identifie les concepts clés impliqués
   - Mentionne les contextes philosophiques pertinents
   - Évoque les filiations intellectuelles (qui a influencé qui, écoles de pensée)
   - Suggère des thèmes connexes (métaphysique, logique, sémiotique, réalisme vs nominalisme, etc.)
4. Utilise un vocabulaire RICHE en synonymes et termes techniques
5. "Ratisse large" pour capturer un maximum de passages pertinents

OBJECTIF : Ta reformulation doit être un texte de 4-6 lignes qui explore tous les angles de la question pour que la recherche sémantique trouve TOUS les passages pertinents possibles.

QUESTION ORIGINALE :
{question}

REFORMULATION EXPANSIVE (4-6 lignes de texte détaillé, sans explication supplémentaire) :"""

    reformulated = ""
    for token in call_llm(reformulation_prompt, provider, model, stream=False, temperature=0.3, max_tokens=500):
        reformulated += token

    return reformulated.strip()


def run_chat_generation(
    session_id: str,
    question: str,
    provider: str,
    model: str,
    limit: int,
    use_reformulation: bool = True,
) -> None:
    """Execute RAG search and LLM generation in background thread.

    Pipeline:
    1. Reformulate question for optimal RAG search (optional)
    2. RAG search with chosen question version
    3. Build prompt with context
    4. Stream LLM response

    Args:
        session_id: Unique session identifier.
        question: User's question (may be original or reformulated).
        provider: LLM provider name.
        model: LLM model name.
        limit: Number of RAG context chunks to retrieve.
        use_reformulation: Whether reformulation was used (for display purposes).
    """
    session: Dict[str, Any] = chat_sessions[session_id]
    q: queue.Queue[Dict[str, Any]] = session["queue"]

    try:
        from utils.llm_chat import call_llm, LLMError

        # Note: Reformulation is now done separately via /chat/reformulate endpoint
        # The question parameter here is the final chosen version (original or reformulated)

        # Step 1: Diverse author search (avoids corpus imbalance bias)
        session["status"] = "searching"
        rag_context = diverse_author_search(
            query=question,
            limit=25,  # Get 25 diverse chunks
            initial_pool=200,  # LARGE pool to find all relevant authors (increased from 100)
            max_authors=8,  # Include up to 8 distinct authors (increased from 6)
            chunks_per_author=3  # Max 3 chunks per author for balance
        )

        print(f"[Pipeline] diverse_author_search returned {len(rag_context)} chunks")
        if rag_context:
            authors = list(set(c.get('author', 'Unknown') for c in rag_context))
            print(f"[Pipeline] Authors in rag_context: {authors}")

        # Step 1.5: Re-rank chunks to filter out irrelevant results
        session["status"] = "reranking"
        filtered_context = rerank_rag_chunks(question, rag_context, provider, model)

        print(f"[Pipeline] rerank_rag_chunks returned {len(filtered_context)} chunks")
        if filtered_context:
            authors = list(set(c.get('author', 'Unknown') for c in filtered_context))
            print(f"[Pipeline] Authors in filtered_context: {authors}")

        # Send filtered context to client
        context_event: Dict[str, Any] = {
            "type": "context",
            "chunks": filtered_context
        }
        q.put(context_event)

        # Store context in session
        session["context"] = filtered_context

        # Step 3: Build prompt (use ORIGINAL question for natural response, filtered context)
        session["status"] = "generating"
        prompt = build_prompt_with_context(question, filtered_context)

        # Step 4: Stream LLM response
        for token in call_llm(prompt, provider, model, stream=True):
            token_event: Dict[str, Any] = {
                "type": "token",
                "content": token
            }
            q.put(token_event)

        # Send completion event
        session["status"] = "complete"
        complete_event: Dict[str, Any] = {
            "type": "complete"
        }
        q.put(complete_event)

    except LLMError as e:
        session["status"] = "error"
        error_event: Dict[str, Any] = {
            "type": "error",
            "message": f"Erreur LLM: {str(e)}"
        }
        q.put(error_event)

    except Exception as e:
        session["status"] = "error"
        error_event: Dict[str, Any] = {
            "type": "error",
            "message": f"Erreur: {str(e)}"
        }
        q.put(error_event)


@app.route("/chat/reformulate", methods=["POST"])
def chat_reformulate() -> tuple[Dict[str, Any], int]:
    """Reformulate user question for optimal RAG search.

    Accepts JSON body with user question and LLM configuration,
    returns both original and reformulated versions.

    Request Body (JSON):
        question (str): User's question.
        provider (str): LLM provider ("ollama", "mistral", "anthropic", "openai").
        model (str): Model name.

    Returns:
        JSON response with original and reformulated questions.

    Example:
        POST /chat/reformulate
        {
          "question": "scotus a apporté quoi a Peirce?",
          "provider": "ollama",
          "model": "qwen2.5:7b"
        }

        Response:
        {
          "original": "scotus a apporté quoi a Peirce?",
          "reformulated": "L'apport de Duns Scotus à Charles Sanders Peirce..."
        }
    """
    data = request.get_json()

    # Validate input
    if not data:
        return {"error": "JSON body required"}, 400

    question = data.get("question", "").strip()
    if not question:
        return {"error": "Question is required"}, 400

    if len(question) > 2000:
        return {"error": "Question too long (max 2000 chars)"}, 400

    provider = data.get("provider", "ollama").lower()
    valid_providers = ["ollama", "mistral", "anthropic", "openai"]
    if provider not in valid_providers:
        return {"error": f"Invalid provider. Must be one of: {', '.join(valid_providers)}"}, 400

    model = data.get("model", "")
    if not model:
        return {"error": "Model is required"}, 400

    try:
        # Reformulate question
        reformulated = reformulate_question(question, provider, model)

        return {
            "original": question,
            "reformulated": reformulated
        }, 200

    except Exception as e:
        return {"error": f"Reformulation failed: {str(e)}"}, 500


@app.route("/chat/send", methods=["POST"])
def chat_send() -> tuple[Dict[str, Any], int]:
    """Handle user question and initiate RAG + LLM generation.

    Accepts JSON body with user question and LLM configuration,
    creates a background thread for RAG search and LLM generation,
    and returns a session ID for SSE streaming.

    Request Body (JSON):
        question (str): User's question.
        provider (str): LLM provider ("ollama", "mistral", "anthropic", "openai").
        model (str): Model name.
        limit (int, optional): Number of RAG chunks. Defaults to 5.
        use_reformulation (bool, optional): Use reformulated question. Defaults to True.

    Returns:
        JSON response with session_id and status.

    Example:
        POST /chat/send
        {
          "question": "Qu'est-ce que la vertu ?",
          "provider": "ollama",
          "model": "qwen2.5:7b",
          "limit": 5,
          "use_reformulation": true
        }

        Response:
        {
          "session_id": "uuid-here",
          "status": "streaming"
        }
    """
    data = request.get_json()

    # Validate input
    if not data:
        return {"error": "JSON body required"}, 400

    question = data.get("question", "").strip()
    if not question:
        return {"error": "Question is required"}, 400

    if len(question) > 2000:
        return {"error": "Question too long (max 2000 chars)"}, 400

    provider = data.get("provider", "ollama").lower()
    valid_providers = ["ollama", "mistral", "anthropic", "openai"]
    if provider not in valid_providers:
        return {"error": f"Invalid provider. Must be one of: {', '.join(valid_providers)}"}, 400

    model = data.get("model", "")
    if not model:
        return {"error": "Model is required"}, 400

    limit = data.get("limit", 5)
    if not isinstance(limit, int) or limit < 1 or limit > 10:
        return {"error": "Limit must be between 1 and 10"}, 400

    use_reformulation = data.get("use_reformulation", True)

    # Create session
    session_id = str(uuid.uuid4())
    chat_sessions[session_id] = {
        "status": "initializing",
        "queue": queue.Queue(),
        "context": [],
        "question": question,
        "provider": provider,
        "model": model,
    }

    # Start background thread
    thread = threading.Thread(
        target=run_chat_generation,
        args=(session_id, question, provider, model, limit, use_reformulation),
        daemon=True,
    )
    thread.start()

    return {
        "session_id": session_id,
        "status": "streaming"
    }, 200


@app.route("/chat/stream/<session_id>")
def chat_stream(session_id: str) -> WerkzeugResponse:
    """Server-Sent Events endpoint for streaming LLM responses.

    Streams events from the chat generation background thread to the client
    using Server-Sent Events (SSE). Events include RAG context, LLM tokens,
    completion, and errors.

    Args:
        session_id: Unique session identifier from POST /chat/send.

    Event Types:
        - context: RAG chunks used for generation
        - token: Individual LLM output token
        - complete: Generation finished successfully
        - error: Error occurred during generation

    Returns:
        SSE stream response.

    Example:
        GET /chat/stream/uuid-here

        Event stream:
        data: {"type": "context", "chunks": [...]}

        data: {"type": "token", "content": "La"}

        data: {"type": "token", "content": " philosophie"}

        data: {"type": "complete"}
    """
    if session_id not in chat_sessions:
        def error_stream() -> Iterator[str]:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Session not found'})}\n\n"
        return Response(error_stream(), mimetype='text/event-stream')

    session: Dict[str, Any] = chat_sessions[session_id]
    q: queue.Queue[Dict[str, Any]] = session["queue"]

    def generate_events() -> Iterator[str]:
        """Generate SSE events from queue."""
        last_keepalive = time.time()
        keepalive_interval = 30  # seconds

        while True:
            try:
                # Non-blocking get with timeout for keep-alive
                try:
                    event = q.get(timeout=1)

                    # Send event to client
                    yield f"data: {json.dumps(event)}\n\n"

                    # If complete or error, end stream
                    if event["type"] in ["complete", "error"]:
                        break

                except queue.Empty:
                    # Send keep-alive if needed
                    now = time.time()
                    if now - last_keepalive > keepalive_interval:
                        yield f": keepalive\n\n"
                        last_keepalive = now

                    # Check if session is stale (no activity for 5 minutes)
                    if session.get("status") == "error":
                        break

            except GeneratorExit:
                # Client disconnected
                break

    return Response(
        generate_events(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )


@app.route("/chat/export-word", methods=["POST"])
def chat_export_word() -> Union[WerkzeugResponse, tuple[Dict[str, Any], int]]:
    """Export a chat exchange to Word format.

    Generates a formatted Microsoft Word document (.docx) containing the user's
    question and the assistant's response. Supports both original and reformulated
    questions.

    Request JSON:
        user_question (str): The user's question (required).
        assistant_response (str): The assistant's complete response (required).
        is_reformulated (bool, optional): Whether the question was reformulated.
            Default: False.
        original_question (str, optional): Original question if reformulated.
            Only used when is_reformulated is True.

    Returns:
        Word document file download (.docx) on success.
        JSON error response with 400/500 status on failure.

    Example:
        POST /chat/export-word
        Content-Type: application/json

        {
            "user_question": "What is phenomenology?",
            "assistant_response": "Phenomenology is a philosophical movement...",
            "is_reformulated": false
        }

        Response: chat_export_20250130_143022.docx (download)
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        user_question = data.get("user_question")
        assistant_response = data.get("assistant_response")
        is_reformulated = data.get("is_reformulated", False)
        original_question = data.get("original_question")

        if not user_question or not assistant_response:
            return (
                jsonify({"error": "user_question and assistant_response are required"}),
                400,
            )

        # Import word exporter
        from utils.word_exporter import create_chat_export

        # Generate Word document
        filepath = create_chat_export(
            user_question=user_question,
            assistant_response=assistant_response,
            is_reformulated=is_reformulated,
            original_question=original_question,
            output_dir=app.config["UPLOAD_FOLDER"],
        )

        # Send file as download
        return send_from_directory(
            directory=filepath.parent,
            path=filepath.name,
            as_attachment=True,
            download_name=filepath.name,
        )

    except Exception as e:
        return jsonify({"error": f"Export failed: {str(e)}"}), 500


@app.route("/chat/export-pdf", methods=["POST"])
def chat_export_pdf() -> Union[WerkzeugResponse, tuple[Dict[str, Any], int]]:
    """Export a chat exchange to PDF format.

    Generates a formatted PDF document containing the user's question and the
    assistant's response. Supports both original and reformulated questions.

    Request JSON:
        user_question (str): The user's question (required).
        assistant_response (str): The assistant's complete response (required).
        is_reformulated (bool, optional): Whether the question was reformulated.
            Default: False.
        original_question (str, optional): Original question if reformulated.
            Only used when is_reformulated is True.

    Returns:
        PDF document file download on success.
        JSON error response with 400/500 status on failure.

    Example:
        POST /chat/export-pdf
        Content-Type: application/json

        {
            "user_question": "What is phenomenology?",
            "assistant_response": "Phenomenology is a philosophical movement...",
            "is_reformulated": false
        }

        Response: chat_export_20250130_143022.pdf (download)
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        user_question = data.get("user_question")
        assistant_response = data.get("assistant_response")
        is_reformulated = data.get("is_reformulated", False)
        original_question = data.get("original_question")

        if not user_question or not assistant_response:
            return (
                jsonify({"error": "user_question and assistant_response are required"}),
                400,
            )

        # Import PDF exporter
        from utils.pdf_exporter import create_chat_export_pdf

        # Generate PDF document
        filepath = create_chat_export_pdf(
            user_question=user_question,
            assistant_response=assistant_response,
            is_reformulated=is_reformulated,
            original_question=original_question,
            output_dir=app.config["UPLOAD_FOLDER"],
        )

        # Send file as download
        return send_from_directory(
            directory=filepath.parent,
            path=filepath.name,
            as_attachment=True,
            download_name=filepath.name,
        )

    except Exception as e:
        return jsonify({"error": f"Export failed: {str(e)}"}), 500


@app.route("/chat/export-audio", methods=["POST"])
def chat_export_audio() -> Union[WerkzeugResponse, tuple[Dict[str, Any], int]]:
    """Export a chat exchange to audio format (TTS).

    Generates a natural-sounding speech audio file (.wav) from the assistant's
    response using Coqui XTTS v2 multilingual TTS model. Supports GPU acceleration
    for faster generation.

    Request JSON:
        assistant_response (str): The assistant's complete response (required).
        language (str, optional): Language code for TTS ("fr", "en", etc.).
            Default: "fr" (French).

    Returns:
        Audio file download (.wav) on success.
        JSON error response with 400/500 status on failure.

    Example:
        POST /chat/export-audio
        Content-Type: application/json

        {
            "assistant_response": "La phénoménologie est une approche philosophique...",
            "language": "fr"
        }

        Response: chat_audio_20250130_143045.wav (download)

    Note:
        First call will download XTTS v2 model (~2GB) and cache it.
        GPU usage: 4-6GB VRAM. Falls back to CPU if no GPU available.
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        assistant_response = data.get("assistant_response")
        language = data.get("language", "fr")

        if not assistant_response:
            return jsonify({"error": "assistant_response is required"}), 400

        # Import TTS generator
        from utils.tts_generator import generate_speech

        # Generate audio file
        filepath = generate_speech(
            text=assistant_response,
            output_dir=app.config["UPLOAD_FOLDER"],
            language=language,
        )

        # Send file as download
        return send_from_directory(
            directory=filepath.parent,
            path=filepath.name,
            as_attachment=True,
            download_name=filepath.name,
        )

    except Exception as e:
        return jsonify({"error": f"TTS failed: {str(e)}"}), 500


def _generate_audio_background(job_id: str, text: str, language: str) -> None:
    """Background worker for TTS audio generation.

    Generates audio in a separate thread to avoid blocking Flask.
    Updates the global tts_jobs dict with status and result.

    Args:
        job_id: Unique identifier for this TTS job.
        text: Text to convert to speech.
        language: Language code for TTS.
    """
    try:
        from utils.tts_generator import generate_speech

        # Update status to processing
        tts_jobs[job_id]["status"] = "processing"

        # Generate audio file
        filepath = generate_speech(
            text=text,
            output_dir=app.config["UPLOAD_FOLDER"],
            language=language,
        )

        # Update job with success status
        tts_jobs[job_id]["status"] = "completed"
        tts_jobs[job_id]["filepath"] = filepath

    except Exception as e:
        # Update job with error status
        tts_jobs[job_id]["status"] = "failed"
        tts_jobs[job_id]["error"] = str(e)
        print(f"TTS job {job_id} failed: {e}")


@app.route("/chat/generate-audio", methods=["POST"])
def chat_generate_audio() -> tuple[Dict[str, Any], int]:
    """Start asynchronous TTS audio generation (non-blocking).

    Launches TTS generation in a background thread and immediately returns
    a job ID for status polling. This allows the Flask app to remain responsive
    during audio generation.

    Request JSON:
        assistant_response (str): The assistant's complete response (required).
        language (str, optional): Language code for TTS ("fr", "en", etc.).
            Default: "fr" (French).

    Returns:
        JSON response with job_id and 202 Accepted status on success.
        JSON error response with 400 status on validation failure.

    Example:
        POST /chat/generate-audio
        Content-Type: application/json

        {
            "assistant_response": "La phénoménologie est une approche philosophique...",
            "language": "fr"
        }

        Response (202):
        {
            "job_id": "550e8400-e29b-41d4-a716-446655440000",
            "status": "pending"
        }

    See Also:
        - ``/chat/audio-status/<job_id>`` : Check generation status
        - ``/chat/download-audio/<job_id>`` : Download completed audio
    """
    try:
        data = request.get_json()

        if not data:
            return {"error": "No JSON data provided"}, 400

        assistant_response = data.get("assistant_response")
        language = data.get("language", "fr")

        if not assistant_response:
            return {"error": "assistant_response is required"}, 400

        # Generate unique job ID
        job_id = str(uuid.uuid4())

        # Initialize job in pending state
        tts_jobs[job_id] = {
            "status": "pending",
            "filepath": None,
            "error": None,
        }

        # Launch background thread for audio generation
        thread = threading.Thread(
            target=_generate_audio_background,
            args=(job_id, assistant_response, language),
            daemon=True,
        )
        thread.start()

        # Return job ID immediately
        return {"job_id": job_id, "status": "pending"}, 202

    except Exception as e:
        return {"error": f"Failed to start TTS job: {str(e)}"}, 500


@app.route("/chat/audio-status/<job_id>", methods=["GET"])
def chat_audio_status(job_id: str) -> tuple[Dict[str, Any], int]:
    """Check the status of a TTS audio generation job.

    Args:
        job_id: Unique identifier for the TTS job.

    Returns:
        JSON response with job status and 200 OK on success.
        JSON error response with 404 status if job not found.

    Status Values:
        - "pending": Job created but not started yet
        - "processing": Audio generation in progress
        - "completed": Audio ready for download
        - "failed": Generation failed (error message included)

    Example:
        GET /chat/audio-status/550e8400-e29b-41d4-a716-446655440000

        Response (processing):
        {
            "job_id": "550e8400-e29b-41d4-a716-446655440000",
            "status": "processing"
        }

        Response (completed):
        {
            "job_id": "550e8400-e29b-41d4-a716-446655440000",
            "status": "completed",
            "filename": "chat_audio_20250130_143045.wav"
        }

        Response (failed):
        {
            "job_id": "550e8400-e29b-41d4-a716-446655440000",
            "status": "failed",
            "error": "TTS generation failed: ..."
        }
    """
    job = tts_jobs.get(job_id)

    if not job:
        return {"error": "Job not found"}, 404

    response = {
        "job_id": job_id,
        "status": job["status"],
    }

    if job["status"] == "completed" and job["filepath"]:
        response["filename"] = job["filepath"].name

    if job["status"] == "failed" and job["error"]:
        response["error"] = job["error"]

    return response, 200


@app.route("/chat/download-audio/<job_id>", methods=["GET"])
def chat_download_audio(job_id: str) -> Union[WerkzeugResponse, tuple[Dict[str, Any], int]]:
    """Download the generated audio file for a completed TTS job.

    Args:
        job_id: Unique identifier for the TTS job.

    Returns:
        Audio file download (.wav) if job completed successfully.
        JSON error response with 404/400 status if job not found or not ready.

    Example:
        GET /chat/download-audio/550e8400-e29b-41d4-a716-446655440000

        Response: chat_audio_20250130_143045.wav (download)
    """
    job = tts_jobs.get(job_id)

    if not job:
        return {"error": "Job not found"}, 404

    if job["status"] != "completed":
        return {"error": f"Job not ready (status: {job['status']})"}, 400

    filepath = job["filepath"]

    if not filepath or not filepath.exists():
        return {"error": "Audio file not found"}, 404

    # Send file as download
    return send_from_directory(
        directory=filepath.parent,
        path=filepath.name,
        as_attachment=True,
        download_name=filepath.name,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PDF Upload & Processing
# ═══════════════════════════════════════════════════════════════════════════════

def allowed_file(filename: str) -> bool:
    """Check if file has an allowed extension.

    Args:
        filename: The filename to check.

    Returns:
        True if the file extension is allowed, False otherwise.
    """
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def run_processing_job(
    job_id: str,
    file_bytes: bytes,
    filename: str,
    options: ProcessingOptions,
) -> None:
    """Execute PDF processing in background with SSE event emission.

    Args:
        job_id: Unique identifier for this processing job.
        file_bytes: Raw PDF file content.
        filename: Original filename for the PDF.
        options: Processing options (LLM settings, OCR options, etc.).
    """
    job: Dict[str, Any] = processing_jobs[job_id]
    q: queue.Queue[SSEEvent] = job["queue"]

    try:
        from utils.pdf_pipeline import process_pdf_bytes

        # Callback pour émettre la progression
        def progress_callback(step: str, status: str, detail: Optional[str] = None) -> None:
            event: SSEEvent = {
                "type": "step",
                "step": step,
                "status": status,
                "detail": detail
            }
            q.put(event)

        # Traiter le PDF avec callback
        from utils.types import V2PipelineResult, V1PipelineResult, LLMProvider
        from typing import Union, cast
        result: Union[V2PipelineResult, V1PipelineResult] = process_pdf_bytes(
            file_bytes,
            filename,
            output_dir=app.config["UPLOAD_FOLDER"],
            skip_ocr=options["skip_ocr"],
            use_llm=options["use_llm"],
            llm_provider=cast(LLMProvider, options["llm_provider"]),
            llm_model=options["llm_model"],
            ingest_to_weaviate=options["ingest_weaviate"],
            use_ocr_annotations=options["use_ocr_annotations"],
            max_toc_pages=options["max_toc_pages"],
            progress_callback=progress_callback,
        )

        job["result"] = result

        if result.get("success"):
            job["status"] = "complete"
            doc_name: str = result.get("document_name", Path(filename).stem)
            complete_event: SSEEvent = {
                "type": "complete",
                "redirect": f"/documents/{doc_name}/view"
            }
            q.put(complete_event)
        else:
            job["status"] = "error"
            error_event: SSEEvent = {
                "type": "error",
                "message": result.get("error", "Erreur inconnue")
            }
            q.put(error_event)

    except Exception as e:
        job["status"] = "error"
        job["result"] = {"error": str(e)}
        exception_event: SSEEvent = {
            "type": "error",
            "message": str(e)
        }
        q.put(exception_event)


def run_word_processing_job(
    job_id: str,
    file_bytes: bytes,
    filename: str,
    options: ProcessingOptions,
) -> None:
    """Execute Word processing in background with SSE event emission.

    Args:
        job_id: Unique identifier for this processing job.
        file_bytes: Raw Word file content (.docx).
        filename: Original filename for the Word document.
        options: Processing options (LLM settings, etc.).
    """
    job: Dict[str, Any] = processing_jobs[job_id]
    q: queue.Queue[SSEEvent] = job["queue"]

    try:
        from utils.word_pipeline import process_word
        import tempfile

        # Callback pour émettre la progression
        def progress_callback(step: str, status: str, detail: str = "") -> None:
            event: SSEEvent = {
                "type": "step",
                "step": step,
                "status": status,
                "detail": detail if detail else None
            }
            q.put(event)

        # Save Word file to temporary location (python-docx needs a file path)
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp_file:
            tmp_file.write(file_bytes)
            tmp_path = Path(tmp_file.name)

        try:
            # Traiter le Word avec callback
            from utils.types import LLMProvider, PipelineResult
            from typing import cast

            result: PipelineResult = process_word(
                tmp_path,
                use_llm=options["use_llm"],
                llm_provider=cast(LLMProvider, options["llm_provider"]),
                use_semantic_chunking=True,
                ingest_to_weaviate=options["ingest_weaviate"],
                skip_metadata_lines=5,
                extract_images=True,
                progress_callback=progress_callback,
            )

            job["result"] = result

            if result.get("success"):
                job["status"] = "complete"
                doc_name: str = result.get("document_name", Path(filename).stem)
                complete_event: SSEEvent = {
                    "type": "complete",
                    "redirect": f"/documents/{doc_name}/view"
                }
                q.put(complete_event)
            else:
                job["status"] = "error"
                error_event: SSEEvent = {
                    "type": "error",
                    "message": result.get("error", "Erreur inconnue")
                }
                q.put(error_event)

        finally:
            # Clean up temporary file
            if tmp_path.exists():
                tmp_path.unlink()

    except Exception as e:
        job["status"] = "error"
        job["result"] = {"error": str(e)}
        exception_event: SSEEvent = {
            "type": "error",
            "message": str(e)
        }
        q.put(exception_event)


@app.route("/upload", methods=["GET", "POST"])
def upload() -> str:
    """Handle PDF/Word upload form display and file submission.

    GET: Displays the upload form with processing options.
    POST: Validates the uploaded file (PDF or Word), starts background processing,
    and redirects to the progress page.

    Form Parameters (POST):
        file: PDF (.pdf) or Word (.docx) file to upload (required, max 50MB).
        llm_provider (str): LLM provider - "mistral" or "ollama". Defaults to "mistral".
        llm_model (str): Specific model name. Defaults based on provider.
        skip_ocr (bool): Skip OCR if markdown already exists (PDF only). Defaults to False.
        use_llm (bool): Enable LLM processing steps. Defaults to True.
        ingest_weaviate (bool): Ingest chunks to Weaviate. Defaults to True.
        use_ocr_annotations (bool): Use OCR annotations for better TOC (PDF only). Defaults to False.
        max_toc_pages (int): Max pages to scan for TOC (PDF only). Defaults to 8.

    Returns:
        GET: Rendered upload form (upload.html).
        POST (success): Rendered progress page (upload_progress.html) with job_id.
        POST (error): Rendered upload form with error message.

    Note:
        Processing runs in a background thread. Use /upload/progress/<job_id>
        SSE endpoint to monitor progress in real-time.
    """
    if request.method == "GET":
        return render_template("upload.html")

    # POST: traiter le fichier
    if "file" not in request.files:
        return render_template("upload.html", error="Aucun fichier sélectionné")

    file = request.files["file"]

    if not file.filename or file.filename == "":
        return render_template("upload.html", error="Aucun fichier sélectionné")

    if not allowed_file(file.filename):
        return render_template("upload.html", error="Format non supporté. Utilisez un fichier PDF (.pdf) ou Word (.docx).")

    # Options de traitement
    llm_provider: str = request.form.get("llm_provider", "mistral")
    default_model: str = "mistral-small-latest" if llm_provider == "mistral" else "qwen2.5:7b"

    options: Dict[str, Any] = {
        "skip_ocr": request.form.get("skip_ocr") == "on",
        "use_llm": request.form.get("use_llm", "on") == "on",
        "llm_provider": llm_provider,
        "llm_model": request.form.get("llm_model", default_model) or default_model,
        "ingest_weaviate": request.form.get("ingest_weaviate", "on") == "on",
        "use_ocr_annotations": request.form.get("use_ocr_annotations") == "on",
        "max_toc_pages": int(request.form.get("max_toc_pages", "8")),
    }

    # Lire le fichier
    filename: str = secure_filename(file.filename)
    file_bytes: bytes = file.read()

    # Déterminer le type de fichier
    file_extension: str = filename.rsplit(".", 1)[1].lower() if "." in filename else ""
    is_word_document: bool = file_extension == "docx"

    # Créer un job de traitement
    job_id: str = str(uuid.uuid4())
    processing_jobs[job_id] = {
        "status": "processing",
        "queue": queue.Queue(),
        "result": None,
        "filename": filename,
    }

    # Démarrer le traitement en background (Word ou PDF)
    if is_word_document:
        thread: threading.Thread = threading.Thread(
            target=run_word_processing_job,
            args=(job_id, file_bytes, filename, options)
        )
    else:
        thread: threading.Thread = threading.Thread(
            target=run_processing_job,
            args=(job_id, file_bytes, filename, options)
        )

    thread.daemon = True
    thread.start()

    # Afficher la page de progression
    file_type_label: str = "Word" if is_word_document else "PDF"
    return render_template("upload_progress.html", job_id=job_id, filename=filename)


@app.route("/upload/progress/<job_id>")
def upload_progress(job_id: str) -> Response:
    """SSE endpoint for real-time processing progress updates.

    Streams Server-Sent Events to the client with processing step updates,
    completion status, or error messages.

    Args:
        job_id: Unique identifier for the processing job.

    Returns:
        Response with text/event-stream mimetype for SSE communication.
    """
    def generate() -> Generator[str, None, None]:
        """Generate SSE events from the processing job queue.

        Yields:
            SSE-formatted strings containing JSON event data.
        """
        if job_id not in processing_jobs:
            error_event: SSEEvent = {"type": "error", "message": "Job non trouvé"}
            yield f"data: {json.dumps(error_event)}\n\n"
            return

        job: Dict[str, Any] = processing_jobs[job_id]
        q: queue.Queue[SSEEvent] = job["queue"]

        while True:
            try:
                # Attendre un événement (timeout 30s pour keep-alive)
                event: SSEEvent = q.get(timeout=30)
                yield f"data: {json.dumps(event)}\n\n"

                # Arrêter si terminé
                if event.get("type") in ("complete", "error"):
                    break

            except queue.Empty:
                # Envoyer un keep-alive
                keepalive_event: SSEEvent = {"type": "keepalive"}
                yield f"data: {json.dumps(keepalive_event)}\n\n"

                # Vérifier si le job est toujours actif
                if job["status"] != "processing":
                    break

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@app.route("/upload/status/<job_id>")
def upload_status(job_id: str) -> Response:
    """Check the status of a PDF processing job via JSON API.

    Provides a polling endpoint for clients that cannot use SSE to check
    job completion status. Returns JSON with status and redirect URL or
    error message.

    Args:
        job_id: UUID of the processing job to check.

    Returns:
        JSON response with one of the following structures:
        - ``{"status": "not_found"}`` if job_id is invalid
        - ``{"status": "processing"}`` if job is still running
        - ``{"status": "complete", "redirect": "/documents/<name>/view"}`` on success
        - ``{"status": "error", "message": "<error details>"}`` on failure

    Note:
        Prefer using the SSE endpoint /upload/progress/<job_id> for real-time
        updates instead of polling this endpoint.
    """
    if job_id not in processing_jobs:
        return jsonify({"status": "not_found"})

    job: Dict[str, Any] = processing_jobs[job_id]

    if job["status"] == "complete":
        result: Dict[str, Any] = job.get("result", {})
        doc_name: str = result.get("document_name", "")
        return jsonify({
            "status": "complete",
            "redirect": f"/documents/{doc_name}/view"
        })
    elif job["status"] == "error":
        return jsonify({
            "status": "error",
            "message": job.get("result", {}).get("error", "Erreur inconnue")
        })
    else:
        return jsonify({"status": "processing"})


@app.route("/output/<path:filepath>")
def serve_output(filepath: str) -> Response:
    """Serve static files from the output directory.

    Provides access to processed document files including markdown, JSON,
    and extracted images. Used by document view templates to display
    document content and images.

    Args:
        filepath: Relative path within the output folder (e.g., "doc_name/images/page_1.png").

    Returns:
        File contents with appropriate MIME type, or 404 if file not found.

    Example:
        GET /output/mon_document/images/page_1.png
        Returns the PNG image file for page 1 of "mon_document".

    Security:
        Files are served from UPLOAD_FOLDER only. Path traversal is handled
        by Flask's send_from_directory.
    """
    return send_from_directory(app.config["UPLOAD_FOLDER"], filepath)


@app.route("/documents/delete/<doc_name>", methods=["POST"])
def delete_document(doc_name: str) -> WerkzeugResponse:
    """Delete a document and all associated data.

    Removes a processed document from both the local filesystem and Weaviate
    database. Handles partial deletion gracefully, providing appropriate
    flash messages for each scenario.

    Deletion order:
        1. Delete passages and sections from Weaviate
        2. Delete local files (markdown, chunks, images)
        3. Flash appropriate success/warning/error message

    Args:
        doc_name: Name of the document directory to delete.

    Returns:
        Redirect to documents list page with flash message indicating result.

    Note:
        This action is irreversible. Both Weaviate data and local files
        will be permanently deleted.

    Flash Messages:
        - success: Document fully deleted
        - warning: Partial deletion (files or Weaviate only)
        - error: Document not found or deletion failed
    """
    import shutil
    import logging
    from utils.weaviate_ingest import delete_document_chunks

    logger = logging.getLogger(__name__)
    output_dir: Path = app.config["UPLOAD_FOLDER"]
    doc_dir: Path = output_dir / doc_name

    files_deleted: bool = False
    weaviate_deleted: bool = False

    # 1. Supprimer de Weaviate en premier
    from utils.weaviate_ingest import DeleteResult
    weaviate_result: DeleteResult = delete_document_chunks(doc_name)

    if weaviate_result.get("success"):
        deleted_chunks: int = weaviate_result.get("deleted_chunks", 0)
        deleted_summaries: int = weaviate_result.get("deleted_summaries", 0)
        deleted_document: bool = weaviate_result.get("deleted_document", False)

        if deleted_chunks > 0 or deleted_summaries > 0 or deleted_document:
            weaviate_deleted = True
            logger.info(f"Weaviate : {deleted_chunks} chunks, {deleted_summaries} summaries supprimés pour '{doc_name}'")
        else:
            logger.info(f"Aucune donnée Weaviate trouvée pour '{doc_name}'")
    else:
        error_msg: str = weaviate_result.get("error", "Erreur inconnue")
        logger.warning(f"Erreur Weaviate lors de la suppression de '{doc_name}': {error_msg}")

    # 2. Supprimer les fichiers locaux
    if doc_dir.exists() and doc_dir.is_dir():
        try:
            shutil.rmtree(doc_dir)
            files_deleted = True
            logger.info(f"Fichiers locaux supprimés : {doc_dir}")
        except Exception as e:
            logger.error(f"Erreur suppression fichiers pour '{doc_name}': {e}")
            flash(f"Erreur lors de la suppression des fichiers : {e}", "error")
            return redirect(url_for("documents"))
    else:
        logger.warning(f"Dossier '{doc_name}' introuvable localement")

    # 3. Messages de feedback
    if files_deleted and weaviate_deleted:
        deleted_chunks = weaviate_result.get("deleted_chunks", 0)
        flash(f"✓ Document « {doc_name} » supprimé : {deleted_chunks} chunks supprimés de Weaviate", "success")
    elif files_deleted and not weaviate_result.get("success"):
        error_msg = weaviate_result.get("error", "Erreur inconnue")
        flash(f"⚠ Fichiers supprimés, mais erreur Weaviate : {error_msg}", "warning")
    elif files_deleted:
        flash(f"✓ Document « {doc_name} » supprimé (aucune donnée Weaviate trouvée)", "success")
    elif weaviate_deleted:
        flash(f"⚠ Données Weaviate supprimées, mais fichiers locaux introuvables", "warning")
    else:
        flash(f"✗ Erreur : Document « {doc_name} » introuvable", "error")

    return redirect(url_for("documents"))


@app.route("/documents/<doc_name>/view")
def view_document(doc_name: str) -> Union[str, WerkzeugResponse]:
    """Display detailed view of a processed document.

    Shows comprehensive information about a processed document including
    metadata, table of contents, chunks, extracted images, and Weaviate
    ingestion status.

    Args:
        doc_name: Name of the document directory to view.

    Returns:
        Rendered HTML template (document_view.html) with document data, or
        redirect to documents list if document not found.

    Template Context:
        result (dict): Contains:
            - document_name: Directory name
            - output_dir: Full path to document directory
            - files: Dict of available files (markdown, chunks, images, etc.)
            - metadata: Extracted metadata (title, author, year, language)
            - pages: Total page count
            - chunks_count: Number of text chunks
            - chunks: List of chunk data
            - toc: Hierarchical table of contents
            - flat_toc: Flattened TOC for navigation
            - weaviate_ingest: Ingestion results if available
            - cost: Processing cost (0 for legacy documents)
    """
    output_dir: Path = app.config["UPLOAD_FOLDER"]
    doc_dir: Path = output_dir / doc_name

    if not doc_dir.exists():
        return redirect(url_for("documents"))

    # Charger toutes les données du document
    result: Dict[str, Any] = {
        "document_name": doc_name,
        "output_dir": str(doc_dir),
        "files": {},
        "metadata": {},
        "weaviate_ingest": None,
    }

    # Fichiers
    md_file: Path = doc_dir / f"{doc_name}.md"
    chunks_file: Path = doc_dir / f"{doc_name}_chunks.json"
    structured_file: Path = doc_dir / f"{doc_name}_structured.json"
    weaviate_file: Path = doc_dir / f"{doc_name}_weaviate.json"
    images_dir: Path = doc_dir / "images"

    result["files"]["markdown"] = str(md_file) if md_file.exists() else None
    result["files"]["chunks"] = str(chunks_file) if chunks_file.exists() else None
    result["files"]["structured"] = str(structured_file) if structured_file.exists() else None
    result["files"]["weaviate"] = str(weaviate_file) if weaviate_file.exists() else None

    if images_dir.exists():
        result["files"]["images"] = [str(f) for f in images_dir.glob("*.png")]

    # Charger les métadonnées, chunks et TOC depuis chunks.json
    if chunks_file.exists():
        try:
            with open(chunks_file, "r", encoding="utf-8") as f:
                chunks_data: Dict[str, Any] = json.load(f)
                result["metadata"] = chunks_data.get("metadata", {})
                result["pages"] = chunks_data.get("pages", 0)
                result["chunks_count"] = len(chunks_data.get("chunks", []))
                # Charger les chunks complets
                result["chunks"] = chunks_data.get("chunks", [])
                # Charger la TOC hiérarchique
                result["toc"] = chunks_data.get("toc", [])
                result["flat_toc"] = chunks_data.get("flat_toc", [])
                # Fallback sur metadata.toc si toc n'existe pas au niveau racine
                if not result["toc"] and result["metadata"].get("toc"):
                    result["toc"] = result["metadata"]["toc"]
        except Exception:
            result["pages"] = 0
            result["chunks_count"] = 0
            result["chunks"] = []
            result["toc"] = []
            result["flat_toc"] = []

    # Charger les données Weaviate
    if weaviate_file.exists():
        try:
            with open(weaviate_file, "r", encoding="utf-8") as f:
                result["weaviate_ingest"] = json.load(f)
        except Exception:
            pass

    result["cost"] = 0  # Non disponible pour les anciens documents

    return render_template("document_view.html", result=result)


@app.route("/documents")
def documents() -> str:
    """Render the list of all processed documents.

    Queries Weaviate to get actual document statistics from the database,
    not from the local files.

    Returns:
        Rendered HTML template (documents.html) with list of document info.

    Template Context:
        documents (list): List of document dictionaries, each containing:
            - name: Document source ID (from Weaviate)
            - path: Full path to document directory (if exists)
            - has_markdown: Whether markdown file exists
            - has_chunks: Whether chunks JSON exists
            - has_structured: Whether structured JSON exists
            - has_images: Whether images directory has content
            - image_count: Number of extracted PNG images
            - metadata: Extracted document metadata
            - pages: Page count
            - chunks_count: Number of chunks IN WEAVIATE (not file)
            - title: Document title (from Weaviate)
            - author: Document author (from Weaviate)
            - toc: Table of contents (from metadata)
    """
    output_dir: Path = app.config["UPLOAD_FOLDER"]
    documents_list: List[Dict[str, Any]] = []

    # Query Weaviate to get actual documents and their stats
    documents_from_weaviate: Dict[str, Dict[str, Any]] = {}

    with get_weaviate_client() as client:
        if client is not None:
            # Get chunk counts and authors
            chunk_collection = client.collections.get("Chunk")

            for obj in chunk_collection.iterator(include_vector=False):
                props = obj.properties
                from typing import cast
                doc_obj = cast(Dict[str, Any], props.get("document", {}))
                work_obj = cast(Dict[str, Any], props.get("work", {}))

                if doc_obj:
                    source_id = doc_obj.get("sourceId", "")
                    if source_id:
                        if source_id not in documents_from_weaviate:
                            documents_from_weaviate[source_id] = {
                                "source_id": source_id,
                                "title": work_obj.get("title") if work_obj else "Unknown",
                                "author": work_obj.get("author") if work_obj else "Unknown",
                                "chunks_count": 0,
                                "summaries_count": 0,
                                "authors": set(),
                            }
                        documents_from_weaviate[source_id]["chunks_count"] += 1

                        # Track unique authors
                        author = work_obj.get("author") if work_obj else None
                        if author:
                            documents_from_weaviate[source_id]["authors"].add(author)

            # Get summary counts
            try:
                summary_collection = client.collections.get("Summary")
                for obj in summary_collection.iterator(include_vector=False):
                    props = obj.properties
                    doc_obj = cast(Dict[str, Any], props.get("document", {}))

                    if doc_obj:
                        source_id = doc_obj.get("sourceId", "")
                        if source_id and source_id in documents_from_weaviate:
                            documents_from_weaviate[source_id]["summaries_count"] += 1
            except Exception:
                # Summary collection may not exist
                pass

    # Match with local files if they exist
    for source_id, weaviate_data in documents_from_weaviate.items():
        doc_dir: Path = output_dir / source_id
        md_file: Path = doc_dir / f"{source_id}.md"
        chunks_file: Path = doc_dir / f"{source_id}_chunks.json"
        structured_file: Path = doc_dir / f"{source_id}_structured.json"
        images_dir: Path = doc_dir / "images"

        # Load additional metadata from chunks.json if exists
        metadata: Dict[str, Any] = {}
        pages: int = 0
        toc: List[Dict[str, Any]] = []

        if chunks_file.exists():
            try:
                with open(chunks_file, "r", encoding="utf-8") as f:
                    chunks_data: Dict[str, Any] = json.load(f)
                    metadata = chunks_data.get("metadata", {})
                    pages = chunks_data.get("pages", 0)
                    toc = metadata.get("toc", [])
            except Exception:
                pass

        documents_list.append({
            "name": source_id,
            "path": str(doc_dir) if doc_dir.exists() else "",
            "has_markdown": md_file.exists(),
            "has_chunks": chunks_file.exists(),
            "has_structured": structured_file.exists(),
            "has_images": images_dir.exists() and any(images_dir.iterdir()) if images_dir.exists() else False,
            "image_count": len(list(images_dir.glob("*.png"))) if images_dir.exists() else 0,
            "metadata": metadata,
            "summaries_count": weaviate_data["summaries_count"],  # FROM WEAVIATE
            "authors_count": len(weaviate_data["authors"]),  # FROM WEAVIATE
            "chunks_count": weaviate_data["chunks_count"],  # FROM WEAVIATE
            "title": weaviate_data["title"],  # FROM WEAVIATE
            "author": weaviate_data["author"],  # FROM WEAVIATE
            "toc": toc,
        })

    return render_template("documents.html", documents=documents_list)


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Créer le dossier output si nécessaire
    app.config["UPLOAD_FOLDER"].mkdir(parents=True, exist_ok=True)
    app.run(debug=True, port=5000)

