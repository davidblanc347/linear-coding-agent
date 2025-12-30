"""Weaviate document ingestion module for the Library RAG pipeline.

This module handles the ingestion of processed documents (chunks, metadata,
summaries) into the Weaviate vector database. It supports the V3.0 schema
with nested objects for efficient semantic search.

Architecture:
    The module uses four Weaviate collections:

    - **Work**: Represents a literary/philosophical work (title, author, year)
    - **Document**: A specific edition/version of a work (sourceId, pages, TOC)
    - **Chunk**: Text chunks with vectorized content for semantic search
    - **Summary**: Section summaries with vectorized concepts

    Chunks and Summaries use nested objects to reference their parent
    Work and Document, avoiding data duplication while enabling
    efficient filtering.

Batch Operations:
    The module uses Weaviate insert_many() for efficient batch insertion.
    Chunks are prepared as a list and inserted in a single operation,
    which is significantly faster than individual insertions.

Nested Objects:
    Each Chunk contains nested work and document objects::

        {
            "text": "La justice est une vertu...",
            "work": {"title": "La Republique", "author": "Platon"},
            "document": {"sourceId": "platon_republique", "edition": "GF"}
        }

    This enables filtering like: document.sourceId == "platon_republique"

Typical Usage:
    >>> from utils.weaviate_ingest import ingest_document, delete_document_chunks
    >>>
    >>> # Ingest a processed document
    >>> result = ingest_document(
    ...     doc_name="platon_republique",
    ...     chunks=[{"text": "La justice est...", "section": "Livre I"}],
    ...     metadata={"title": "La Republique", "author": "Platon"},
    ...     language="fr",
    ... )
    >>> print(f"Ingested {result['count']} chunks")

Connection:
    The module connects to a local Weaviate instance using:

    - HTTP port: 8080
    - gRPC port: 50051

    Ensure Weaviate is running via: docker-compose up -d

See Also:
    - schema.py: Weaviate schema definitions
    - pdf_pipeline.py: Document processing pipeline
    - flask_app.py: Web interface for search
"""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional, TypedDict

import weaviate
from weaviate import WeaviateClient
from weaviate.collections import Collection
import weaviate.classes.query as wvq

# Import type definitions from central types module
from utils.types import WeaviateIngestResult as IngestResult

# Import TOC enrichment functions
from .toc_enricher import enrich_chunks_with_toc


# =============================================================================
# Type Definitions (module-specific, not exported to utils.types)
# =============================================================================


class SummaryObject(TypedDict):
    """Weaviate Summary object structure for section summaries.

    This TypedDict defines the structure of Summary objects stored in Weaviate.
    Summaries are vectorized and can be searched semantically.

    Attributes:
        sectionPath: Full hierarchical path (e.g., "Livre I > Chapitre 2").
        title: Section title.
        level: Hierarchy level (1 = top level, 2 = subsection, etc.).
        text: Summary text content (vectorized for search).
        concepts: List of key concepts extracted from the section.
        chunksCount: Number of chunks in this section.
        document: Nested object with document reference (sourceId).
    """

    sectionPath: str
    title: str
    level: int
    text: str
    concepts: List[str]
    chunksCount: int
    document: Dict[str, str]


class ChunkObject(TypedDict, total=False):
    """Weaviate Chunk object structure for text chunks.

    This TypedDict defines the structure of Chunk objects stored in Weaviate.
    The text and keywords fields are vectorized for semantic search.

    Attributes:
        text: Chunk text content (vectorized for search).
        sectionPath: Full hierarchical path (e.g., "Livre I > Chapitre 2").
        sectionLevel: Hierarchy level (1 = top level).
        chapterTitle: Title of the containing chapter.
        canonicalReference: Canonical academic reference (e.g., "CP 1.628", "Ménon 80a").
        unitType: Type of argumentative unit (main_content, exposition, etc.).
        keywords: List of keywords/concepts (vectorized for search).
        language: Language code (e.g., "fr", "en").
        orderIndex: Position in document for ordering.
        work: Nested object with work metadata (title, author).
        document: Nested object with document reference (sourceId, edition).

    Note:
        Uses total=False because some fields are optional during creation.
    """

    text: str
    sectionPath: str
    sectionLevel: int
    chapterTitle: str
    canonicalReference: str
    unitType: str
    keywords: List[str]
    language: str
    orderIndex: int
    work: Dict[str, str]
    document: Dict[str, str]


class InsertedChunkSummary(TypedDict):
    """Summary of an inserted chunk for display purposes.

    This TypedDict provides a preview of inserted chunks, useful for
    displaying ingestion results to users.

    Attributes:
        chunk_id: Generated chunk identifier.
        sectionPath: Hierarchical path of the chunk.
        work: Title of the work.
        author: Author name.
        text_preview: First 150 characters of chunk text.
        unitType: Type of argumentative unit.
    """

    chunk_id: str
    sectionPath: str
    work: str
    author: str
    text_preview: str
    unitType: str


# Note: IngestResult is imported from utils.types as WeaviateIngestResult


class DeleteResult(TypedDict, total=False):
    """Result from document deletion operation.

    This TypedDict contains the result of a deletion operation,
    including counts of deleted objects from each collection.

    Attributes:
        success: Whether deletion succeeded.
        error: Error message if deletion failed.
        deleted_chunks: Number of chunks deleted from Chunk collection.
        deleted_summaries: Number of summaries deleted from Summary collection.
        deleted_document: Whether the Document object was deleted.

    Example:
        >>> result = delete_document_chunks("platon_republique")
        >>> print(f"Deleted {result['deleted_chunks']} chunks")
    """

    success: bool
    error: str
    deleted_chunks: int
    deleted_summaries: int
    deleted_document: bool


class DocumentStats(TypedDict, total=False):
    """Document statistics from Weaviate.

    This TypedDict contains statistics about a document stored in Weaviate,
    retrieved by querying the Chunk collection.

    Attributes:
        success: Whether stats retrieval succeeded.
        error: Error message if retrieval failed.
        sourceId: Document identifier.
        chunks_count: Total number of chunks for this document.
        work: Title of the work (from first chunk).
        author: Author name (from first chunk).

    Example:
        >>> stats = get_document_stats("platon_republique")
        >>> print(f"Document has {stats['chunks_count']} chunks")
    """

    success: bool
    error: str
    sourceId: str
    chunks_count: int
    work: Optional[str]
    author: Optional[str]


# Logger
logger: logging.Logger = logging.getLogger(__name__)


@contextmanager
def get_weaviate_client() -> Generator[Optional[WeaviateClient], None, None]:
    """Context manager for Weaviate connection with automatic cleanup.

    Creates a connection to the local Weaviate instance and ensures
    proper cleanup when the context exits. Handles connection errors
    gracefully by yielding None instead of raising.

    Yields:
        Connected WeaviateClient instance, or None if connection failed.

    Example:
        >>> with get_weaviate_client() as client:
        ...     if client is not None:
        ...         chunks = client.collections.get("Chunk")
        ...         # Perform operations...
        ...     else:
        ...         print("Connection failed")

    Note:
        Connects to localhost:8080 (HTTP) and localhost:50051 (gRPC).
        Ensure Weaviate is running via docker-compose up -d.
    """
    client: Optional[WeaviateClient] = None
    try:
        # Increased timeout for long text vectorization (e.g., Peirce CP 3.403, CP 8.388, Menon chunk 10)
        # Default is 60s, increased to 600s (10 minutes) for exceptionally large texts
        from weaviate.classes.init import AdditionalConfig, Timeout

        client = weaviate.connect_to_local(
            host="localhost",
            port=8080,
            grpc_port=50051,
            additional_config=AdditionalConfig(
                timeout=Timeout(init=30, query=600, insert=600)  # 10 min for insert/query
            )
        )
        yield client
    except Exception as e:
        logger.error(f"Erreur connexion Weaviate: {e}")
        yield None
    finally:
        if client:
            client.close()


def ingest_document_metadata(
    client: WeaviateClient,
    doc_name: str,
    metadata: Dict[str, Any],
    toc: List[Dict[str, Any]],
    hierarchy: Dict[str, Any],
    chunks_count: int,
    pages: int,
) -> Optional[str]:
    """Insert document metadata into the Document collection.

    Creates a Document object containing metadata about a processed document,
    including its table of contents, hierarchy structure, and statistics.

    Args:
        client: Active Weaviate client connection.
        doc_name: Unique document identifier (sourceId).
        metadata: Extracted metadata dict with keys: title, author, language.
        toc: Table of contents as a hierarchical list of dicts.
        hierarchy: Complete document hierarchy structure.
        chunks_count: Total number of chunks in the document.
        pages: Number of pages in the source PDF.

    Returns:
        UUID string of the created Document object, or None if insertion failed.

    Example:
        >>> with get_weaviate_client() as client:
        ...     uuid = ingest_document_metadata(
        ...         client,
        ...         doc_name="platon_republique",
        ...         metadata={"title": "La Republique", "author": "Platon"},
        ...         toc=[{"title": "Livre I", "level": 1}],
        ...         hierarchy={},
        ...         chunks_count=150,
        ...         pages=300,
        ...     )

    Note:
        The TOC and hierarchy are serialized to JSON strings for storage.
        The createdAt field is set to the current timestamp.
    """
    try:
        doc_collection: Collection[Any, Any] = client.collections.get("Document")
    except Exception as e:
        logger.warning(f"Collection Document non trouvée: {e}")
        return None

    try:
        doc_obj: Dict[str, Any] = {
            "sourceId": doc_name,
            "title": metadata.get("title") or doc_name,
            "author": metadata.get("author") or "Inconnu",
            "toc": json.dumps(toc, ensure_ascii=False) if toc else "[]",
            "hierarchy": json.dumps(hierarchy, ensure_ascii=False) if hierarchy else "{}",
            "pages": pages,
            "chunksCount": chunks_count,
            "language": metadata.get("language", "fr"),
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }

        result = doc_collection.data.insert(doc_obj)
        logger.info(f"Document metadata ingéré: {doc_name}")
        return str(result)

    except Exception as e:
        logger.warning(f"Erreur ingestion document metadata: {e}")
        return None


def ingest_summaries(
    client: WeaviateClient,
    doc_name: str,
    toc: List[Dict[str, Any]],
    summaries_content: Dict[str, str],
) -> int:
    """Insert section summaries into the Summary collection.

    Creates Summary objects for each entry in the table of contents,
    with optional summary text content. Summaries are vectorized and
    can be searched semantically.

    Args:
        client: Active Weaviate client connection.
        doc_name: Document identifier for linking summaries.
        toc: Hierarchical table of contents list.
        summaries_content: Mapping of section titles to summary text.
            If a title is not in this dict, the title itself is used as text.

    Returns:
        Number of summaries successfully inserted.

    Example:
        >>> with get_weaviate_client() as client:
        ...     count = ingest_summaries(
        ...         client,
        ...         doc_name="platon_republique",
        ...         toc=[{"title": "Livre I", "level": 1}],
        ...         summaries_content={"Livre I": "Discussion sur la justice..."},
        ...     )
        ...     print(f"Inserted {count} summaries")

    Note:
        Uses batch insertion via insert_many() for efficiency.
        Recursively processes nested TOC entries (children).
    """
    try:
        summary_collection: Collection[Any, Any] = client.collections.get("Summary")
    except Exception as e:
        logger.warning(f"Collection Summary non trouvée: {e}")
        return 0

    summaries_to_insert: List[SummaryObject] = []

    def process_toc(items: List[Dict[str, Any]], parent_path: str = "") -> None:
        for item in items:
            title: str = item.get("title", "")
            level: int = item.get("level", 1)
            path: str = f"{parent_path} > {title}" if parent_path else title

            summary_obj: SummaryObject = {
                "sectionPath": path,
                "title": title,
                "level": level,
                "text": summaries_content.get(title, title),
                "concepts": item.get("concepts", []),
                "chunksCount": 0,
                "document": {
                    "sourceId": doc_name,
                },
            }
            summaries_to_insert.append(summary_obj)

            if "children" in item:
                process_toc(item["children"], path)

    process_toc(toc)

    if not summaries_to_insert:
        return 0

    # Insérer par petits lots pour éviter les timeouts
    BATCH_SIZE = 50
    total_inserted = 0

    try:
        logger.info(f"Ingesting {len(summaries_to_insert)} summaries in batches of {BATCH_SIZE}...")

        for batch_start in range(0, len(summaries_to_insert), BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, len(summaries_to_insert))
            batch = summaries_to_insert[batch_start:batch_end]

            try:
                summary_collection.data.insert_many(batch)
                total_inserted += len(batch)
                logger.info(f"  Batch {batch_start//BATCH_SIZE + 1}: Inserted {len(batch)} summaries ({total_inserted}/{len(summaries_to_insert)})")
            except Exception as batch_error:
                logger.warning(f"  Batch {batch_start//BATCH_SIZE + 1} failed: {batch_error}")
                continue

        logger.info(f"{total_inserted} résumés ingérés pour {doc_name}")
        return total_inserted
    except Exception as e:
        logger.warning(f"Erreur ingestion résumés: {e}")
        return 0


def ingest_document(
    doc_name: str,
    chunks: List[Dict[str, Any]],
    metadata: Dict[str, Any],
    language: str = "fr",
    toc: Optional[List[Dict[str, Any]]] = None,
    hierarchy: Optional[Dict[str, Any]] = None,
    pages: int = 0,
    ingest_document_collection: bool = True,
    ingest_summary_collection: bool = False,
) -> IngestResult:
    """Ingest document chunks into Weaviate with nested objects.

    Main ingestion function that inserts chunks into the Chunk collection
    with nested Work and Document references. Optionally also creates
    entries in the Document and Summary collections.

    This function uses batch insertion for optimal performance and
    constructs proper nested objects for filtering capabilities.

    Args:
        doc_name: Unique document identifier (used as sourceId).
        chunks: List of chunk dicts, each containing at minimum:
            - text: The chunk text content
            - section (optional): Section path string
            - hierarchy (optional): Dict with part/chapter/section
            - type (optional): Argumentative unit type
            - concepts/keywords (optional): List of keywords
        metadata: Document metadata dict with keys:
            - title: Work title
            - author: Author name
            - edition (optional): Edition identifier
        language: ISO language code. Defaults to "fr".
        toc: Optional table of contents for Document/Summary collections.
        hierarchy: Optional complete document hierarchy structure.
        pages: Number of pages in source document. Defaults to 0.
        ingest_document_collection: If True, also insert into Document
            collection. Defaults to True.
        ingest_summary_collection: If True, also insert into Summary
            collection (requires toc). Defaults to False.

    Returns:
        IngestResult dict containing:
            - success: True if ingestion succeeded
            - count: Number of chunks inserted
            - inserted: Preview of first 10 inserted chunks
            - work: Work title
            - author: Author name
            - document_uuid: UUID of Document object (if created)
            - all_objects: Complete list of inserted ChunkObjects
            - error: Error message (if failed)

    Raises:
        No exceptions are raised; errors are returned in the result dict.

    Example:
        >>> result = ingest_document(
        ...     doc_name="platon_republique",
        ...     chunks=[{"text": "La justice est...", "section": "Livre I"}],
        ...     metadata={"title": "La Republique", "author": "Platon"},
        ...     language="fr",
        ...     pages=450,
        ... )
        >>> if result["success"]:
        ...     print(f"Ingested {result['count']} chunks")

    Note:
        Empty chunks (no text or whitespace-only) are automatically skipped.
        The function logs progress and errors using the module logger.
    """
    try:
        with get_weaviate_client() as client:
            if client is None:
                return IngestResult(
                    success=False,
                    error="Connexion Weaviate impossible",
                    inserted=[],
                )

            # Récupérer la collection Chunk
            try:
                chunk_collection: Collection[Any, Any] = client.collections.get("Chunk")
            except Exception as e:
                return IngestResult(
                    success=False,
                    error=f"Collection Chunk non trouvée: {e}",
                    inserted=[],
                )

            # Insérer les métadonnées du document (optionnel)
            doc_uuid: Optional[str] = None
            if ingest_document_collection:
                doc_uuid = ingest_document_metadata(
                    client, doc_name, metadata, toc or [], hierarchy or {},
                    len(chunks), pages
                )

            # Insérer les résumés (optionnel)
            if ingest_summary_collection and toc:
                ingest_summaries(client, doc_name, toc, {})

            # NOUVEAU : Enrichir chunks avec métadonnées TOC si disponibles
            if toc and hierarchy:
                logger.info(f"Enriching {len(chunks)} chunks with TOC metadata...")
                chunks = enrich_chunks_with_toc(chunks, toc, hierarchy)
            else:
                logger.info("No TOC/hierarchy available, using basic metadata")

            # Préparer les objets Chunk à insérer avec nested objects
            objects_to_insert: List[ChunkObject] = []

            title: str = metadata.get("title") or metadata.get("work") or doc_name
            author: str = metadata.get("author") or "Inconnu"
            edition: str = metadata.get("edition", "")

            for idx, chunk in enumerate(chunks):
                # Extraire le texte du chunk
                text: str = chunk.get("text", "")
                if not text or not text.strip():
                    continue

                # Utiliser sectionPath enrichi si disponible, sinon fallback vers logique existante
                section_path: str = chunk.get("sectionPath", "")
                if not section_path:
                    section_path = chunk.get("section", "")
                    if not section_path:
                        chunk_hierarchy: Dict[str, Any] = chunk.get("hierarchy", {})
                        section_parts: List[str] = []
                        if chunk_hierarchy.get("part"):
                            section_parts.append(chunk_hierarchy["part"])
                        if chunk_hierarchy.get("chapter"):
                            section_parts.append(chunk_hierarchy["chapter"])
                        if chunk_hierarchy.get("section"):
                            section_parts.append(chunk_hierarchy["section"])
                        section_path = " > ".join(section_parts) if section_parts else chunk.get("title", f"Section {idx}")

                # Utiliser chapterTitle enrichi si disponible
                chapter_title: str = chunk.get("chapterTitle", chunk.get("chapter_title", ""))

                # Utiliser canonicalReference enrichi si disponible
                canonical_ref: str = chunk.get("canonicalReference", "")

                # Créer l objet Chunk avec nested objects
                chunk_obj: ChunkObject = {
                    "text": text,
                    "sectionPath": section_path,
                    "sectionLevel": chunk.get("section_level", chunk.get("level", 1)),
                    "chapterTitle": chapter_title,
                    "canonicalReference": canonical_ref,
                    "unitType": chunk.get("type", "main_content"),
                    "keywords": chunk.get("concepts", chunk.get("keywords", [])),
                    "language": language,
                    "orderIndex": idx,
                    "work": {
                        "title": title,
                        "author": author,
                    },
                    "document": {
                        "sourceId": doc_name,
                        "edition": edition,
                    },
                }

                objects_to_insert.append(chunk_obj)

            if not objects_to_insert:
                return IngestResult(
                    success=True,
                    message="Aucun chunk à insérer",
                    inserted=[],
                    count=0,
                )

            # Insérer les objets par petits lots pour éviter les timeouts
            BATCH_SIZE = 50  # Process 50 chunks at a time
            total_inserted = 0

            logger.info(f"Ingesting {len(objects_to_insert)} chunks in batches of {BATCH_SIZE}...")

            for batch_start in range(0, len(objects_to_insert), BATCH_SIZE):
                batch_end = min(batch_start + BATCH_SIZE, len(objects_to_insert))
                batch = objects_to_insert[batch_start:batch_end]

                try:
                    _response = chunk_collection.data.insert_many(objects=batch)
                    total_inserted += len(batch)
                    logger.info(f"  Batch {batch_start//BATCH_SIZE + 1}: Inserted {len(batch)} chunks ({total_inserted}/{len(objects_to_insert)})")
                except Exception as batch_error:
                    logger.error(f"  Batch {batch_start//BATCH_SIZE + 1} failed: {batch_error}")
                    # Continue with next batch instead of failing completely
                    continue

            # Préparer le résumé des objets insérés
            inserted_summary: List[InsertedChunkSummary] = []
            for i, obj in enumerate(objects_to_insert[:10]):
                text_content: str = obj.get("text", "")
                work_obj: Dict[str, str] = obj.get("work", {})
                inserted_summary.append(InsertedChunkSummary(
                    chunk_id=f"chunk_{i:05d}",
                    sectionPath=obj.get("sectionPath", ""),
                    work=work_obj.get("title", ""),
                    author=work_obj.get("author", ""),
                    text_preview=text_content[:150] + "..." if len(text_content) > 150 else text_content,
                    unitType=obj.get("unitType", ""),
                ))

            logger.info(f"Ingestion réussie: {total_inserted} chunks insérés pour {doc_name}")

            return IngestResult(
                success=True,
                count=total_inserted,
                inserted=inserted_summary,
                work=title,
                author=author,
                document_uuid=doc_uuid,
                all_objects=objects_to_insert,
            )

    except Exception as e:
        logger.error(f"Erreur ingestion: {e}")
        return IngestResult(
            success=False,
            error=str(e),
            inserted=[],
        )


def delete_document_chunks(doc_name: str) -> DeleteResult:
    """Delete all data for a document from Weaviate collections.

    Removes chunks, summaries, and the document metadata from their
    respective collections. Uses nested object filtering to find
    related objects.

    This function is useful for re-processing a document after changes
    to the processing pipeline or to clean up test data.

    Args:
        doc_name: Document identifier (sourceId) to delete.

    Returns:
        DeleteResult dict containing:
            - success: True if deletion succeeded (even if no objects found)
            - deleted_chunks: Number of Chunk objects deleted
            - deleted_summaries: Number of Summary objects deleted
            - deleted_document: True if Document object was deleted
            - error: Error message (if failed)

    Example:
        >>> result = delete_document_chunks("platon_republique")
        >>> if result["success"]:
        ...     print(f"Deleted {result['deleted_chunks']} chunks")
        ...     # Now safe to re-ingest
        ...     ingest_document("platon_republique", new_chunks, metadata)

    Note:
        Uses delete_many() with filters on nested object properties.
        Continues even if some collections fail (logs warnings).
    """
    try:
        with get_weaviate_client() as client:
            if client is None:
                return DeleteResult(success=False, error="Connexion Weaviate impossible")

            deleted_chunks: int = 0
            deleted_summaries: int = 0
            deleted_document: bool = False

            # Supprimer les chunks (filtrer sur document.sourceId nested)
            try:
                chunk_collection: Collection[Any, Any] = client.collections.get("Chunk")
                result = chunk_collection.data.delete_many(
                    where=wvq.Filter.by_property("document.sourceId").equal(doc_name)
                )
                deleted_chunks = result.successful
            except Exception as e:
                logger.warning(f"Erreur suppression chunks: {e}")

            # Supprimer les summaries (filtrer sur document.sourceId nested)
            try:
                summary_collection: Collection[Any, Any] = client.collections.get("Summary")
                result = summary_collection.data.delete_many(
                    where=wvq.Filter.by_property("document.sourceId").equal(doc_name)
                )
                deleted_summaries = result.successful
            except Exception as e:
                logger.warning(f"Erreur suppression summaries: {e}")

            # Supprimer le document
            try:
                doc_collection: Collection[Any, Any] = client.collections.get("Document")
                result = doc_collection.data.delete_many(
                    where=wvq.Filter.by_property("sourceId").equal(doc_name)
                )
                deleted_document = result.successful > 0
            except Exception as e:
                logger.warning(f"Erreur suppression document: {e}")

            logger.info(f"Suppression: {deleted_chunks} chunks, {deleted_summaries} summaries pour {doc_name}")

            return DeleteResult(
                success=True,
                deleted_chunks=deleted_chunks,
                deleted_summaries=deleted_summaries,
                deleted_document=deleted_document,
            )

    except Exception as e:
        logger.error(f"Erreur suppression: {e}")
        return DeleteResult(success=False, error=str(e))


def get_document_stats(doc_name: str) -> DocumentStats:
    """Retrieve statistics for a document from Weaviate.

    Queries the Chunk collection to count chunks and extract work
    metadata for a given document identifier.

    Args:
        doc_name: Document identifier (sourceId) to query.

    Returns:
        DocumentStats dict containing:
            - success: True if query succeeded
            - sourceId: The queried document identifier
            - chunks_count: Number of chunks found
            - work: Work title (from first chunk, if any)
            - author: Author name (from first chunk, if any)
            - error: Error message (if failed)

    Example:
        >>> stats = get_document_stats("platon_republique")
        >>> if stats["success"]:
        ...     print(f"Document: {stats['work']} by {stats['author']}")
        ...     print(f"Chunks: {stats['chunks_count']}")

    Note:
        Limited to 1000 chunks for counting. For documents with more
        chunks, consider using Weaviate's aggregate queries.
    """
    try:
        with get_weaviate_client() as client:
            if client is None:
                return DocumentStats(success=False, error="Connexion Weaviate impossible")

            # Compter les chunks (filtrer sur document.sourceId nested)
            chunk_collection: Collection[Any, Any] = client.collections.get("Chunk")
            chunks = chunk_collection.query.fetch_objects(
                filters=wvq.Filter.by_property("document.sourceId").equal(doc_name),
                limit=1000,
            )

            chunks_count: int = len(chunks.objects)

            # Récupérer les infos du premier chunk
            work: Optional[str] = None
            author: Optional[str] = None
            if chunks.objects:
                first: Dict[str, Any] = chunks.objects[0].properties
                work_obj: Any = first.get("work", {})
                work = work_obj.get("title") if isinstance(work_obj, dict) else None
                author = work_obj.get("author") if isinstance(work_obj, dict) else None

            return DocumentStats(
                success=True,
                sourceId=doc_name,
                chunks_count=chunks_count,
                work=work,
                author=author,
            )

    except Exception as e:
        logger.error(f"Erreur stats document: {e}")
        return DocumentStats(success=False, error=str(e))
