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
            try:
                client.close()
            except Exception as e:
                print(f"Erreur fermeture client Weaviate: {e}")


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
    with get_weaviate_client() as client:
        if client is None:
            # Return empty result - let caller decide fallback
            return {
                "mode": "hierarchical" if force_hierarchical else "error",
                "sections": [],
                "results": [],
                "total_chunks": 0,
                "fallback_reason": "Weaviate client unavailable",
            }

        try:
            # ═══════════════════════════════════════════════════════════════
            # STAGE 1: Search Summary collection for relevant sections
            # ═══════════════════════════════════════════════════════════════

            summary_collection = client.collections.get("Summary")

            summaries_result = summary_collection.query.near_text(
                query=query,
                limit=sections_limit,
                return_metadata=wvq.MetadataQuery(distance=True),
                # Note: Don't specify return_properties - let Weaviate return all properties
                # including nested objects like "document" which we need for source_id
            )

            if not summaries_result.objects:
                # No summaries found - return empty result
                return {
                    "mode": "hierarchical" if force_hierarchical else "error",
                    "sections": [],
                    "results": [],
                    "total_chunks": 0,
                    "fallback_reason": f"Aucune section pertinente trouvée (0/{sections_limit} summaries)",
                }

            # Extract section data
            sections_data = []
            for summary_obj in summaries_result.objects:
                props = summary_obj.properties

                # Try to get document.sourceId if available (nested object might still be returned)
                doc_obj = props.get("document")
                source_id = ""
                if doc_obj and isinstance(doc_obj, dict):
                    source_id = doc_obj.get("sourceId", "")

                sections_data.append({
                    "section_path": props.get("sectionPath", ""),
                    "title": props.get("title", ""),
                    "summary_text": props.get("text", ""),
                    "level": props.get("level", 1),
                    "concepts": props.get("concepts", []),
                    "document_source_id": source_id,
                    "summary_uuid": str(summary_obj.uuid),  # Keep UUID for later retrieval if needed
                    "similarity": round((1 - summary_obj.metadata.distance) * 100, 1) if summary_obj.metadata and summary_obj.metadata.distance else 0,
                })

            # Post-filter sections by author/work (Summary doesn't have work nested object)
            if author_filter or work_filter:
                print(f"[HIERARCHICAL] Post-filtering {len(sections_data)} sections by work='{work_filter}'")
                doc_collection = client.collections.get("Document")
                filtered_sections = []

                for section in sections_data:
                    source_id = section["document_source_id"]
                    if not source_id:
                        print(f"[HIERARCHICAL] Section '{section['section_path'][:40]}...' SKIPPED (no sourceId)")
                        continue

                    # Query Document to get work metadata
                    # Note: 'work' is a nested object, so we don't specify it in return_properties
                    # Weaviate should return it automatically
                    doc_result = doc_collection.query.fetch_objects(
                        filters=wvq.Filter.by_property("sourceId").equal(source_id),
                        limit=1,
                    )

                    if doc_result.objects:
                        doc_work = doc_result.objects[0].properties.get("work", {})
                        print(f"[HIERARCHICAL] Section '{section['section_path'][:40]}...' doc_work type={type(doc_work)}, value={doc_work}")
                        if isinstance(doc_work, dict):
                            work_title = doc_work.get("title", "N/A")
                            work_author = doc_work.get("author", "N/A")
                            # Check filters
                            if author_filter and work_author != author_filter:
                                print(f"[HIERARCHICAL] Section '{section['section_path'][:40]}...' FILTERED (author '{work_author}' != '{author_filter}')")
                                continue
                            if work_filter and work_title != work_filter:
                                print(f"[HIERARCHICAL] Section '{section['section_path'][:40]}...' FILTERED (work '{work_title}' != '{work_filter}')")
                                continue

                            print(f"[HIERARCHICAL] Section '{section['section_path'][:40]}...' KEPT (work='{work_title}')")
                            filtered_sections.append(section)
                        else:
                            print(f"[HIERARCHICAL] Section '{section['section_path'][:40]}...' SKIPPED (doc_work not a dict)")
                    else:
                        print(f"[HIERARCHICAL] Section '{section['section_path'][:40]}...' SKIPPED (no doc found for sourceId='{source_id}')")

                sections_data = filtered_sections
                print(f"[HIERARCHICAL] After filtering: {len(sections_data)} sections remaining")

            if not sections_data:
                # No sections match filters - return empty result
                filters_str = f"author={author_filter}" if author_filter else ""
                if work_filter:
                    filters_str += f", work={work_filter}" if filters_str else f"work={work_filter}"
                return {
                    "mode": "hierarchical" if force_hierarchical else "error",
                    "sections": [],
                    "results": [],
                    "total_chunks": 0,
                    "fallback_reason": f"Aucune section ne correspond aux filtres ({filters_str})",
                }

            # ═══════════════════════════════════════════════════════════════
            # STAGE 2: Search chunks for EACH section (grouped display)
            # ═══════════════════════════════════════════════════════════════
            # For each section, search chunks using the section's summary text
            # This groups chunks under their relevant sections

            chunk_collection = client.collections.get("Chunk")

            # Build base filters (author/work only)
            base_filters: Optional[Any] = None
            if author_filter:
                base_filters = wvq.Filter.by_property("workAuthor").equal(author_filter)
            if work_filter:
                work_filter_obj = wvq.Filter.by_property("workTitle").equal(work_filter)
                base_filters = base_filters & work_filter_obj if base_filters else work_filter_obj

            all_chunks = []
            chunks_per_section = max(3, limit // len(sections_data))  # Distribute chunks across sections

            for section in sections_data:
                # Use section's summary text as query to find relevant chunks
                # This ensures chunks are semantically related to the section
                section_query = section["summary_text"] or section["title"] or query

                # Build filters: base filters (author/work) + sectionPath filter
                # Use .like() to match hierarchical sections (e.g., "Chapter 1*" matches "Chapter 1 > Section A")
                # This ensures each chunk only appears in its own section hierarchy
                section_path_pattern = f"{section['section_path']}*"
                section_filters = wvq.Filter.by_property("sectionPath").like(section_path_pattern)
                if base_filters:
                    section_filters = base_filters & section_filters

                chunks_result = chunk_collection.query.near_text(
                    query=section_query,
                    limit=chunks_per_section,
                    filters=section_filters,
                    return_metadata=wvq.MetadataQuery(distance=True),
                )

                # Convert to list and attach to section
                section_chunks = [
                    {
                        "uuid": str(obj.uuid),
                        "distance": obj.metadata.distance if obj.metadata else None,
                        "similarity": round((1 - obj.metadata.distance) * 100, 1) if obj.metadata and obj.metadata.distance else None,
                        **obj.properties
                    }
                    for obj in chunks_result.objects
                ]

                print(f"[HIERARCHICAL] Section '{section['section_path'][:50]}...' filter='{section_path_pattern[:50]}...' -> {len(section_chunks)} chunks")

                section["chunks"] = section_chunks
                section["chunks_count"] = len(section_chunks)
                all_chunks.extend(section_chunks)

            print(f"[HIERARCHICAL] Got {len(all_chunks)} chunks total across {len(sections_data)} sections")
            print(f"[HIERARCHICAL] Average {len(all_chunks) / len(sections_data):.1f} chunks per section")

            # Sort all chunks globally by similarity for the flat results list
            all_chunks.sort(key=lambda x: x.get("similarity", 0) or 0, reverse=True)

            return {
                "mode": "hierarchical",
                "sections": sections_data,
                "results": all_chunks,
                "total_chunks": len(all_chunks),
            }

        except Exception as e:
            # Handle errors within the try block (inside 'with')
            print(f"Erreur recherche hiérarchique: {e}")
            import traceback
            traceback.print_exc()

            # Return empty result (don't call simple_search here!)
            return {
                "mode": "hierarchical" if force_hierarchical else "error",
                "sections": [],
                "results": [],
                "total_chunks": 0,
                "fallback_reason": f"Erreur lors de la recherche: {str(e)}",
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


def summary_only_search(
    query: str,
    limit: int = 10,
    author_filter: Optional[str] = None,
    work_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Summary-only semantic search on Summary collection (90% visibility).

    Searches high-level section summaries instead of detailed chunks. Offers
    90% visibility of rich documents vs 10% for direct chunk search due to
    Peirce chunk dominance (5,068/5,230 = 97% of chunks).

    Args:
        query: Search query text.
        limit: Maximum number of summary results to return.
        author_filter: Filter by author name (uses document.author property).
        work_filter: Filter by work title (uses document.title property).

    Returns:
        List of summary dictionaries formatted as "results" with:
        - uuid, similarity, text, title, concepts, doc_icon, doc_name
        - author, year, chunks_count, section_path
    """
    try:
        with get_weaviate_client() as client:
            if client is None:
                return []

            summaries = client.collections.get("Summary")

            # Note: Cannot filter by nested document properties directly in Weaviate v4
            # Must fetch all and filter in Python if author/work filters are present

            # Semantic search
            results = summaries.query.near_text(
                query=query,
                limit=limit * 3 if (author_filter or work_filter) else limit,  # Fetch more if filtering
                return_metadata=wvq.MetadataQuery(distance=True)
            )

            # Format and filter results
            formatted_results: List[Dict[str, Any]] = []
            for obj in results.objects:
                props = obj.properties
                similarity = 1 - obj.metadata.distance

                # Apply filters (Python-side since nested properties)
                if author_filter and props["document"].get("author", "") != author_filter:
                    continue
                if work_filter and props["document"].get("title", "") != work_filter:
                    continue

                # Determine document icon and name
                doc_id = props["document"]["sourceId"].lower()
                if "tiercelin" in doc_id:
                    doc_icon = "🟡"
                    doc_name = "Tiercelin"
                elif "platon" in doc_id or "menon" in doc_id:
                    doc_icon = "🟢"
                    doc_name = "Platon"
                elif "haugeland" in doc_id:
                    doc_icon = "🟣"
                    doc_name = "Haugeland"
                elif "logique" in doc_id:
                    doc_icon = "🔵"
                    doc_name = "Logique"
                else:
                    doc_icon = "⚪"
                    doc_name = "Peirce"

                # Format result (compatible with existing template expectations)
                result = {
                    "uuid": str(obj.uuid),
                    "similarity": round(similarity * 100, 1),  # Convert to percentage
                    "text": props.get("text", ""),
                    "title": props["title"],
                    "concepts": props.get("concepts", []),
                    "doc_icon": doc_icon,
                    "doc_name": doc_name,
                    "author": props["document"].get("author", ""),
                    "year": props["document"].get("year", 0),
                    "chunks_count": props.get("chunksCount", 0),
                    "section_path": props.get("sectionPath", ""),
                    "sectionPath": props.get("sectionPath", ""),  # Alias for template compatibility
                    # Add work info for template compatibility
                    "work": {
                        "title": props["document"].get("title", ""),
                        "author": props["document"].get("author", ""),
                    },
                }

                formatted_results.append(result)

                # Stop if we have enough results after filtering
                if len(formatted_results) >= limit:
                    break

            return formatted_results

    except Exception as e:
        print(f"Error in summary_only_search: {e}")
        return []


def search_passages(
    query: str,
    limit: int = 10,
    author_filter: Optional[str] = None,
    work_filter: Optional[str] = None,
    sections_limit: int = 5,
    force_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """Intelligent semantic search dispatcher with auto-detection.

    Automatically chooses between simple (1-stage), hierarchical (2-stage),
    or summary-only search based on query complexity or user selection.

    Args:
        query: Search query text.
        limit: Maximum number of chunks to return (per section if hierarchical).
        author_filter: Filter by author name (uses workAuthor property).
        work_filter: Filter by work title (uses workTitle property).
        sections_limit: Number of top sections for hierarchical search (default: 5).
        force_mode: Force search mode ("simple", "hierarchical", "summary", or None for auto).

    Returns:
        Dictionary with search results:
        - mode: "simple", "hierarchical", or "summary"
        - results: List of passage/summary dictionaries (flat)
        - sections: List of section dicts with nested chunks (hierarchical only)
        - total_chunks: Total number of chunks/summaries found

    Examples:
        >>> # Short query → auto-detects simple search
        >>> search_passages("justice", limit=10)
        {"mode": "simple", "results": [...], "total_chunks": 10}

        >>> # Complex query → auto-detects hierarchical search
        >>> search_passages("Qu'est-ce que la vertu selon Aristote ?", limit=5)
        {"mode": "hierarchical", "sections": [...], "results": [...], "total_chunks": 15}

        >>> # Force summary-only mode (90% visibility, high-level overviews)
        >>> search_passages("What is the Turing test?", force_mode="summary", limit=10)
        {"mode": "summary", "results": [...], "total_chunks": 7}
    """
    # Handle summary-only mode
    if force_mode == "summary":
        results = summary_only_search(query, limit, author_filter, work_filter)
        return {
            "mode": "summary",
            "results": results,
            "total_chunks": len(results),
        }

    # Determine search mode for simple vs hierarchical
    if force_mode == "simple":
        use_hierarchical = False
    elif force_mode == "hierarchical":
        use_hierarchical = True
    else:
        # Auto-detection
        use_hierarchical = should_use_hierarchical_search(query)

    # Execute appropriate search strategy
    if use_hierarchical:
        result = hierarchical_search(
            query=query,
            limit=limit,
            author_filter=author_filter,
            work_filter=work_filter,
            sections_limit=sections_limit,
            force_hierarchical=(force_mode == "hierarchical"),  # No fallback if explicitly forced
        )

        # If hierarchical search failed and wasn't forced, fallback to simple search
        if result.get("mode") == "error" and force_mode != "hierarchical":
            results = simple_search(query, limit, author_filter, work_filter)
            return {
                "mode": "simple",
                "results": results,
                "total_chunks": len(results),
            }

        return result
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

