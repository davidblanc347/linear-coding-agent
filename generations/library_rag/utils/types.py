"""Library RAG - Central Type Definitions.

This module contains all TypedDict, Protocol, NewType, and Literal definitions
used across the Library RAG codebase. It provides strict type safety for:

- OCR processing (Mistral API responses)
- Document metadata extraction
- Table of contents (TOC) structures
- Section classification
- Semantic chunking
- Pipeline orchestration results
- Weaviate ingestion objects

Usage:
    >>> from utils.types import (
    ...     Metadata, TOCEntry, ChunkData, PipelineResult,
    ...     LLMProvider, ProgressCallback, SectionType,
    ... )
    >>>
    >>> def process_document(
    ...     metadata: Metadata,
    ...     callback: ProgressCallback | None = None,
    ... ) -> PipelineResult:
    ...     ...

See Also:
    - pdf_pipeline: Main orchestration using these types
    - weaviate_ingest: Database operations using these types
    - llm_*: LLM modules using provider and response types
"""

from __future__ import annotations

from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Literal,
    NewType,
    Optional,
    Protocol,
    TypedDict,
    Union,
)


# =============================================================================
# NewType Definitions for Semantic Type Safety
# =============================================================================

#: Unique identifier for a document (typically filename without extension)
DocumentName = NewType("DocumentName", str)

#: Unique identifier for a chunk (UUID or composite key)
ChunkId = NewType("ChunkId", str)

#: Hierarchical path representing section location (e.g., "Chapter 1 > Section 2")
SectionPath = NewType("SectionPath", str)

#: Weaviate collection UUID
WeaviateUUID = NewType("WeaviateUUID", str)


# =============================================================================
# Literal Types for String Constants
# =============================================================================

#: LLM provider options
LLMProvider = Literal["ollama", "mistral"]

#: Section types for document classification
SectionType = Literal[
    "front_matter",   # Title page, copyright, credits
    "toc_display",    # Table of contents display (not indexed)
    "preface",        # Preface, foreword, acknowledgments
    "abstract",       # Abstract, summary
    "introduction",   # Document introduction
    "chapter",        # Main chapter content
    "conclusion",     # Document conclusion
    "appendix",       # Appendices
    "bibliography",   # Bibliography, references
    "index",          # Index pages
    "notes",          # End notes
    "ignore",         # Skip (ads, blank pages, technical metadata)
]

#: Chunk unit types for semantic chunking
UnitType = Literal[
    "argument",       # Argumentative unit
    "definition",     # Definition or explanation
    "example",        # Example or illustration
    "transition",     # Transitional passage
    "citation",       # Quote or citation
    "thesis",         # Main thesis statement
    "objection",      # Counter-argument
    "response",       # Response to objection
    "exposition",     # Expository content
    "analysis",       # Analytical content
]

#: Pipeline step status
PipelineStepStatus = Literal["pending", "running", "success", "error", "skipped"]


# =============================================================================
# Protocol Types for Callbacks and Interfaces
# =============================================================================

class ProgressCallback(Protocol):
    """Protocol for pipeline progress callbacks.

    Called during PDF processing to report step progress.

    Args:
        step_id: Identifier for the current step (e.g., "ocr", "metadata")
        status: Current status ("running", "success", "error")
        detail: Optional detail message or error description

    Example:
        >>> def my_callback(step_id: str, status: str, detail: str | None) -> None:
        ...     print(f"[{step_id}] {status}: {detail or ''}")
    """

    def __call__(
        self,
        step_id: str,
        status: str,
        detail: Optional[str] = None,
    ) -> None:
        """Report progress for a pipeline step."""
        ...


class ImageWriter(Protocol):
    """Protocol for image writing callbacks.

    Called during markdown building to save extracted images.

    Args:
        image_data: Raw image bytes (PNG, JPEG, etc.)
        image_name: Suggested filename for the image

    Returns:
        Path or URL to the saved image for markdown reference.

    Example:
        >>> def save_image(image_data: bytes, image_name: str) -> str:
        ...     path = Path("output/images") / image_name
        ...     path.write_bytes(image_data)
        ...     return f"images/{image_name}"
    """

    def __call__(self, image_data: bytes, image_name: str) -> str:
        """Save image and return path/URL for markdown reference."""
        ...


# =============================================================================
# TypedDict Definitions - Metadata
# =============================================================================

class Metadata(TypedDict, total=False):
    """Bibliographic metadata extracted from a document.

    All fields are optional (total=False) as LLM extraction may fail
    to identify some metadata.

    Attributes:
        title: Document title (with subtitle if present)
        author: Primary author name
        collection: Collection or series name
        publisher: Publisher name
        year: Publication year (as string for flexibility)
        doi: Digital Object Identifier
        isbn: ISBN number
        language: ISO 639-1 language code (e.g., "fr", "en")
        genre: Document type (e.g., "philosophie", "essai")
        confidence: Confidence scores for each field (0.0-1.0)
    """

    title: str
    author: str
    collection: Optional[str]
    publisher: Optional[str]
    year: Optional[str]
    doi: Optional[str]
    isbn: Optional[str]
    language: str
    genre: Optional[str]
    confidence: Dict[str, float]


class MetadataConfidence(TypedDict, total=False):
    """Confidence scores for metadata fields (0.0 to 1.0)."""

    title: float
    author: float
    collection: float
    publisher: float
    year: float


# =============================================================================
# TypedDict Definitions - Table of Contents
# =============================================================================

class TOCEntry(TypedDict):
    """Single entry in the table of contents.

    Represents a hierarchical section with optional children.

    Attributes:
        title: Section title
        level: Hierarchy level (1 = chapter, 2 = section, 3 = subsection)
        page: Optional page number (if available from OCR)
        children: Nested TOC entries (empty list if leaf node)
    """

    title: str
    level: int
    page: Optional[int]
    children: List["TOCEntry"]


class FlatTOCEntry(TypedDict):
    """Flattened TOC entry with full path.

    Attributes:
        title: Section title
        level: Hierarchy level
        path: Full path (e.g., "Chapter 1 > Section 2 > Subsection A")
    """

    title: str
    level: int
    path: str


class FlatTOCEntryEnriched(TypedDict):
    """Enriched flattened TOC entry with hierarchical metadata for chunk matching.

    Used by toc_enricher to match chunks to their hierarchical context in the TOC.
    Extends FlatTOCEntry with additional metadata for citation extraction.

    Attributes:
        title: Section title (original TOC entry title)
        level: Hierarchy level (1=chapter, 2=section, etc.)
        full_path: Complete hierarchical path (e.g., "Peirce: CP 1.628 > 628. It is...")
        chapter_title: Title of parent chapter (level 1 ancestor)
        canonical_ref: Academic citation reference (e.g., "CP 1.628", "Ménon 80a")
        parent_titles: List of all parent titles from root to this entry
        index_in_flat_list: Position in flattened TOC list (for proximity matching)
    """

    title: str
    level: int
    full_path: str
    chapter_title: str
    canonical_ref: Optional[str]
    parent_titles: List[str]
    index_in_flat_list: int


class TOCResult(TypedDict):
    """Complete TOC extraction result.

    Attributes:
        toc: Hierarchical TOC structure
        flat_toc: Flattened TOC for easy iteration
    """

    toc: List[TOCEntry]
    flat_toc: List[FlatTOCEntry]


# =============================================================================
# TypedDict Definitions - Section Classification
# =============================================================================

class ClassifiedSection(TypedDict):
    """Section with classification metadata.

    Attributes:
        title: Section title
        level: Hierarchy level
        type: Section type classification
        should_index: Whether to include in vector index
        chapter_number: Chapter number (if applicable)
        content_preview: First N characters for context
    """

    title: str
    level: int
    type: SectionType
    should_index: bool
    chapter_number: Optional[int]
    content_preview: Optional[str]


class SectionInput(TypedDict):
    """Input structure for section classification.

    Attributes:
        title: Section title
        level: Hierarchy level
        content_preview: First N characters of content
    """

    title: str
    level: int
    content_preview: str


# =============================================================================
# TypedDict Definitions - Chunking
# =============================================================================

class ChunkData(TypedDict, total=False):
    """Semantic chunk extracted from a document.

    Represents an argumentative or conceptual unit for vector indexing.

    Attributes:
        text: Chunk text content (will be vectorized)
        summary: Brief summary of the chunk
        concepts: Key concepts mentioned
        keywords: Search keywords (will be vectorized)
        type: Unit type (argument, definition, etc.)
        paragraph_number: Original paragraph number if available
        section_path: Full hierarchical path
        chapter_title: Parent chapter title
        subsection_title: Parent subsection title (if any)
        order_index: Position in document order
        language: ISO 639-1 language code
        unit_type: Semantic unit type
    """

    text: str
    summary: Optional[str]
    concepts: List[str]
    keywords: List[str]
    type: Optional[UnitType]
    paragraph_number: Optional[int]
    section_path: str
    chapter_title: Optional[str]
    subsection_title: Optional[str]
    order_index: int
    language: str
    unit_type: Optional[str]


class SemanticChunk(TypedDict, total=False):
    """Semantic chunk from LLM-based chunking with pipeline metadata.

    Produced by llm_chunker.chunk_content_semantically(). Contains
    the chunk content and semantic metadata, plus fields added by
    the pipeline for tracking and ingestion.

    Attributes:
        text: Chunk text content.
        summary: Brief summary of the chunk.
        concepts: Key concepts extracted.
        type: Semantic unit type (argument, definition, etc.).
        section_level: Hierarchy level of source section.
        paragraph_number: Original paragraph number if detected.
        subsection_title: Parent subsection title if applicable.
        error: Error message if fallback chunking was used.
        chunk_id: Unique identifier assigned by pipeline.
        section: Section title (alias for section_path).
        chapter_title: Parent chapter title.
        section_path: Full hierarchical path.
        order_index: Position in document order.
        language: ISO 639-1 language code.
        keywords: Search keywords for vectorization.
    """

    text: str
    summary: str
    concepts: List[str]
    type: str
    section_level: int
    paragraph_number: int
    subsection_title: str
    error: str
    # Fields added by pdf_pipeline during processing
    chunk_id: str
    section: str
    chapter_title: str
    section_path: str
    order_index: int
    language: str
    keywords: List[str]


class ChunkingResult(TypedDict):
    """Result from semantic chunking operation.

    Attributes:
        chunks: List of extracted chunks
        total_chunks: Total number of chunks created
        avg_chunk_size: Average chunk size in characters
    """

    chunks: List[ChunkData]
    total_chunks: int
    avg_chunk_size: float


# =============================================================================
# TypedDict Definitions - Validation
# =============================================================================

class ValidationResult(TypedDict, total=False):
    """Document validation result from LLM.

    Attributes:
        valid: Whether document passed validation
        errors: List of validation errors
        warnings: List of validation warnings
        corrections: Suggested corrections
        concepts: Extracted key concepts
        score: Overall quality score (0.0-1.0)
    """

    valid: bool
    errors: List[str]
    warnings: List[str]
    corrections: Dict[str, str]
    concepts: List[str]
    score: float


# =============================================================================
# TypedDict Definitions - Pipeline Results
# =============================================================================

class PipelineFiles(TypedDict, total=False):
    """Paths to files generated by the pipeline.

    Attributes:
        markdown: Path to generated markdown file
        chunks_json: Path to chunks JSON file
        weaviate_json: Path to Weaviate export
        images_dir: Path to extracted images directory
    """

    markdown: Path
    chunks_json: Path
    weaviate_json: Path
    images_dir: Path


class PipelineCosts(TypedDict):
    """Cost breakdown for pipeline execution.

    Attributes:
        ocr: OCR processing cost in euros
        llm: LLM API cost in euros (0 if using Ollama)
        total: Total cost
    """

    ocr: float
    llm: float
    total: float


class PipelineResult(TypedDict, total=False):
    """Complete result from PDF processing pipeline.

    Returned by process_pdf_v2 and related functions.

    Attributes:
        success: Whether processing completed without errors
        document_name: Identifier for the processed document
        pages: Number of pages in the PDF
        chunks_count: Number of chunks generated
        cost_ocr: OCR cost in euros
        cost_llm: LLM cost in euros
        cost_total: Total processing cost
        metadata: Extracted bibliographic metadata
        toc: Hierarchical table of contents
        classified_sections: Sections with type classification
        chunks: List of generated chunks
        files: Paths to generated files
        errors: List of errors encountered
        warnings: List of warnings
        processing_time_seconds: Total processing time
    """

    success: bool
    document_name: str
    pages: int
    chunks_count: int
    cost_ocr: float
    cost_llm: float
    cost_total: float
    metadata: Metadata
    toc: List[TOCEntry]
    classified_sections: List[ClassifiedSection]
    chunks: List[ChunkData]
    files: PipelineFiles
    errors: List[str]
    warnings: List[str]
    processing_time_seconds: float


class PipelineOptions(TypedDict, total=False):
    """Options for pipeline execution.

    Attributes:
        use_llm: Enable LLM-based processing
        llm_provider: LLM provider to use
        llm_model: Specific model name
        llm_temperature: Model temperature
        skip_ocr: Reuse existing markdown
        use_ocr_annotations: Use OCR with annotations (3x cost)
        use_semantic_chunking: Enable LLM-based chunking
        ingest_to_weaviate: Insert into Weaviate after processing
        clean_chunks: Apply chunk cleaning
        extract_concepts: Extract concepts from chunks
        validate_output: Run final validation
        embed_images: Embed images as base64
        max_toc_pages: Max pages for TOC extraction
    """

    use_llm: bool
    llm_provider: LLMProvider
    llm_model: Optional[str]
    llm_temperature: float
    skip_ocr: bool
    use_ocr_annotations: bool
    use_semantic_chunking: bool
    ingest_to_weaviate: bool
    clean_chunks: bool
    extract_concepts: bool
    validate_output: bool
    embed_images: bool
    max_toc_pages: int


# =============================================================================
# TypedDict Definitions - Weaviate Objects
# =============================================================================

class WorkReference(TypedDict):
    """Nested Work reference for Weaviate objects.

    Attributes:
        title: Work title
        author: Work author
    """

    title: str
    author: str


class DocumentReference(TypedDict, total=False):
    """Nested Document reference for Weaviate objects.

    Attributes:
        sourceId: Document identifier
        edition: Edition information
    """

    sourceId: str
    edition: Optional[str]


class WeaviateChunk(TypedDict, total=False):
    """Chunk object structure for Weaviate ingestion.

    Attributes:
        text: Chunk text (vectorized)
        keywords: Keywords (vectorized)
        sectionPath: Hierarchical section path
        chapterTitle: Parent chapter title
        unitType: Semantic unit type
        orderIndex: Position in document
        language: ISO 639-1 language code
        work: Nested work reference
        document: Nested document reference
    """

    text: str
    keywords: List[str]
    sectionPath: str
    chapterTitle: Optional[str]
    unitType: Optional[str]
    orderIndex: int
    language: str
    work: WorkReference
    document: DocumentReference


class WeaviateDocument(TypedDict, total=False):
    """Document object structure for Weaviate.

    Attributes:
        sourceId: Document identifier
        title: Document title
        author: Document author
        toc: JSON-encoded TOC
        hierarchy: JSON-encoded hierarchy
        pages: Page count
        chunksCount: Number of chunks
        language: ISO 639-1 language code
        createdAt: ISO 8601 timestamp
    """

    sourceId: str
    title: str
    author: str
    toc: str  # JSON string
    hierarchy: str  # JSON string
    pages: int
    chunksCount: int
    language: str
    createdAt: str


# =============================================================================
# TypedDict Definitions - Hierarchy
# =============================================================================

class HierarchyNode(TypedDict):
    """Node in the document hierarchy tree.

    Represents a section in the document hierarchy with its content
    and child sections. Used by hierarchy_parser.build_hierarchy().

    Attributes:
        title: Section title (None for root/preamble nodes).
        level: Hierarchy level (0=root, 1=chapter, 2=section, etc.).
        content: Section text content.
        children: Nested child sections.
    """

    title: Optional[str]
    level: int
    content: str
    children: List["HierarchyNode"]


class DocumentHierarchy(TypedDict):
    """Complete document hierarchy structure.

    Returned by hierarchy_parser.build_hierarchy(). Contains the
    document's preamble (content before first heading) and all
    sections in a hierarchical tree structure.

    Attributes:
        preamble: Content before first section heading.
        sections: Top-level sections as a list of HierarchyNode.
    """

    preamble: str
    sections: List[HierarchyNode]


class HierarchyPath(TypedDict):
    """Hierarchical path for a chunk in document structure.

    Represents the path from root to a specific section in the
    document hierarchy. Used by flatten_hierarchy() to preserve
    context for semantic search.

    Attributes:
        part: Part title (level 1 heading).
        chapter: Chapter title (level 2 heading).
        section: Section title (level 3 heading).
        subsection: Subsection title (level 4+ heading).
    """

    part: Optional[str]
    chapter: Optional[str]
    section: Optional[str]
    subsection: Optional[str]


class FlatChunk(TypedDict):
    """Flattened chunk with hierarchical context.

    Produced by hierarchy_parser.flatten_hierarchy(). Contains
    the chunk text along with its position in the document
    hierarchy for context-aware RAG retrieval.

    Attributes:
        chunk_id: Unique chunk identifier (e.g., "chunk_00001").
        text: Chunk text content.
        hierarchy: Hierarchical path to this chunk.
        type: Chunk type (e.g., "preamble", "main_content").
        level: Heading level (0=preamble, 1-6=heading levels).
        title: Section title (None for preamble).
    """

    chunk_id: str
    text: str
    hierarchy: HierarchyPath
    type: str
    level: int
    title: Optional[str]


# =============================================================================
# TypedDict Definitions - OCR
# =============================================================================

class OCRPageDimensions(TypedDict):
    """Page dimensions from OCR."""

    width: int
    height: int
    dpi: int


class OCRPage(TypedDict, total=False):
    """Single page from OCR response.

    Attributes:
        index: Page index (0-based)
        markdown: Markdown content
        images: List of extracted images
        dimensions: Page dimensions
    """

    index: int
    markdown: str
    images: List[Dict[str, Any]]
    dimensions: Optional[OCRPageDimensions]


class OCRResponse(TypedDict, total=False):
    """Complete OCR response structure.

    Attributes:
        pages: List of processed pages
        model: Model used for OCR
        usage: Token usage statistics
    """

    pages: List[OCRPage]
    model: str
    usage: Dict[str, int]


# =============================================================================
# Type Aliases for Common Patterns
# =============================================================================

#: Generic JSON-compatible dictionary
JSONDict = Dict[str, Any]

#: Progress callback function signature
ProgressCallbackType = Callable[[str, str, Optional[str]], None]

#: Optional progress callback
OptionalProgressCallback = Optional[ProgressCallbackType]


# =============================================================================
# TypedDict Definitions - Legacy/Helper Functions
# =============================================================================

class SimpleTOCEntry(TypedDict):
    """Simple TOC entry used in legacy extraction.

    Attributes:
        title: Section title
        level: Hierarchy level (1-3)
    """

    title: str
    level: int


class LegacyMetadata(TypedDict, total=False):
    """Metadata structure from legacy extraction.

    Used by extract_document_metadata_legacy function.

    Attributes:
        title: Document title
        author: Document author
        work: Work name (defaults to doc_name)
        chunks_count: Number of chunks
        toc: Simple TOC entries
    """

    title: Optional[str]
    author: Optional[str]
    work: str
    chunks_count: int
    toc: List[SimpleTOCEntry]


class FlatSection(TypedDict, total=False):
    """Flattened section structure with parent context.

    Used by flatten_all_sections helper function.

    Attributes:
        title: Section title
        content: Section content text
        level: Hierarchy level
        chapter_title: Parent chapter title
        parent_title: Immediate parent title
    """

    title: str
    content: str
    level: int
    chapter_title: Optional[str]
    parent_title: Optional[str]


class LLMCostStats(TypedDict):
    """LLM cost statistics from API calls (Mistral or Ollama).

    Returned by llm_structurer.get_llm_cost(). Tracks cumulative
    cost and token usage across all LLM API calls in a session.

    Attributes:
        total_cost: Total cost in euros (0 for Ollama).
        total_input_tokens: Total input tokens used.
        total_output_tokens: Total output tokens used.
        calls_count: Number of API calls made.
    """

    total_cost: float
    total_input_tokens: int
    total_output_tokens: int
    calls_count: int


class WeaviateIngestResult(TypedDict, total=False):
    """Result from Weaviate document ingestion operation.

    Returned by weaviate_ingest.ingest_document(). Contains
    complete ingestion status including inserted objects.

    Attributes:
        success: Whether ingestion succeeded.
        count: Number of chunks successfully inserted.
        message: Optional informational message.
        error: Error message if ingestion failed.
        inserted: List of inserted chunk summaries (first 10).
        work: Title of the ingested work.
        author: Author of the ingested work.
        work_uuid: UUID of created Work object (if any).
        all_objects: Complete list of all inserted ChunkObjects.

    Note:
        The inserted and all_objects fields use Any to accommodate
        the module-specific TypedDicts defined in weaviate_ingest.py.
    """

    success: bool
    count: int
    message: str
    error: str
    inserted: List[Any]  # List[InsertedChunkSummary] from weaviate_ingest
    work: str
    author: str
    work_uuid: Optional[str]
    all_objects: List[Any]  # List[ChunkObject] from weaviate_ingest


# Type alias for backward compatibility
IngestResult = WeaviateIngestResult


class V1PipelineResult(TypedDict, total=False):
    """Result from V1 (legacy) pipeline.

    Attributes:
        success: Whether processing succeeded
        document_name: Document identifier
        output_dir: Output directory path
        files: Generated file paths
        pages: Page count
        cost: OCR cost in euros
        metadata: Extracted metadata
        chunks_count: Number of chunks
        weaviate_ingest: Weaviate ingestion result
        error: Error message if failed
        pipeline_version: Always "1.0"
    """

    success: bool
    document_name: str
    output_dir: str
    files: Dict[str, Any]
    pages: int
    cost: float
    metadata: LegacyMetadata
    chunks_count: int
    weaviate_ingest: Optional[WeaviateIngestResult]
    error: str
    pipeline_version: str


# =============================================================================
# TypedDict Definitions - Pipeline V2 Step Results
# =============================================================================

class TOCExtractionResult(TypedDict, total=False):
    """Result from TOC extraction (LLM or annotations).

    Attributes:
        toc: Hierarchical TOC structure
        flat_toc: Flattened TOC entries
        success: Whether extraction succeeded
        cost_ocr_annotated: Additional cost if annotations used
        error: Error message if failed
        metadata: Additional metadata from annotations
    """

    toc: List[Dict[str, Any]]
    flat_toc: List[Dict[str, Any]]
    success: bool
    cost_ocr_annotated: float
    error: Optional[str]
    metadata: Dict[str, Any]


class ParsedDocument(TypedDict, total=False):
    """Parsed document structure used for validation.

    Attributes:
        metadata: Document metadata
        toc: Table of contents
        chunks: Document chunks
    """

    metadata: Dict[str, Any]
    toc: List[Dict[str, Any]]
    chunks: List[Dict[str, Any]]


class ChunksDataExport(TypedDict, total=False):
    """Complete chunks data export structure (saved to JSON).

    Attributes:
        document: Document name
        pages: Number of pages
        metadata: Extracted metadata
        toc: Hierarchical TOC
        flat_toc: Flattened TOC
        hierarchy: Document hierarchy
        classified_sections: Classified sections
        chunks: Final chunks
        validation: Validation results
        pipeline_version: Pipeline version string
    """

    document: str
    pages: int
    metadata: Dict[str, Any]
    toc: List[Dict[str, Any]]
    flat_toc: List[Dict[str, Any]]
    hierarchy: DocumentHierarchy
    classified_sections: List[Dict[str, Any]]
    chunks: List[Dict[str, Any]]
    validation: Optional[ValidationResult]
    pipeline_version: str


class V2PipelineFiles(TypedDict, total=False):
    """File paths generated by V2 pipeline.

    Attributes:
        markdown: Path to markdown file
        chunks: Path to chunks JSON
        ocr: Path to OCR JSON
        weaviate: Path to Weaviate export
        images: List of image paths
        images_dir: Path to images directory
    """

    markdown: str
    chunks: str
    ocr: str
    weaviate: str
    images: List[str]
    images_dir: str


class V2PipelineResult(TypedDict, total=False):
    """Complete result from V2 pipeline (process_pdf_v2).

    Attributes:
        success: Whether processing succeeded
        document_name: Document identifier
        output_dir: Output directory path
        files: Generated file paths
        pages: Number of pages
        cost_ocr: OCR cost in euros
        cost_llm: LLM API cost in euros
        cost_total: Total cost
        llm_stats: Detailed LLM statistics
        metadata: Extracted metadata
        toc: Table of contents
        chunks_count: Number of chunks
        validation: Validation result
        weaviate_ingest: Weaviate ingestion result
        pipeline_version: Always "2.0"
        error: Error message if failed
    """

    success: bool
    document_name: str
    output_dir: str
    files: V2PipelineFiles
    pages: int
    cost_ocr: float
    cost_llm: float
    cost_total: float
    llm_stats: Optional[LLMCostStats]
    metadata: Dict[str, Any]
    toc: List[Dict[str, Any]]
    chunks_count: int
    validation: Optional[ValidationResult]
    weaviate_ingest: Optional[WeaviateIngestResult]
    pipeline_version: str
    error: str


# =============================================================================
# TypedDict Definitions - Flask Application Types
# =============================================================================


class CollectionStats(TypedDict, total=False):
    """Statistics about Weaviate collections for Flask display.

    Attributes:
        passages: Total number of passages/chunks
        authors: Number of unique authors
        works: Number of unique works
        languages: Number of unique languages
        author_list: List of all author names
        work_list: List of all work titles
        language_list: List of all language codes
    """

    passages: int
    authors: int
    works: int
    languages: int
    author_list: List[str]
    work_list: List[str]
    language_list: List[str]


class PassageResult(TypedDict, total=False):
    """Single passage/chunk result with metadata.

    Attributes:
        uuid: Weaviate object UUID
        text: Passage text content
        author: Author name
        work: Work title
        section_path: Hierarchical section path
        language: Language code
        distance: Semantic distance (for search results)
        similarity: Similarity percentage (for search results)
    """

    uuid: str
    text: str
    author: Optional[str]
    work: Optional[str]
    section_path: Optional[str]
    language: Optional[str]
    distance: Optional[float]
    similarity: Optional[float]


class ProcessingOptions(TypedDict):
    """Options for PDF processing job.

    Attributes:
        skip_ocr: Skip OCR and reuse existing markdown
        use_llm: Enable LLM-based processing
        llm_provider: LLM provider (ollama or mistral)
        llm_model: Specific model name
        ingest_weaviate: Insert into Weaviate after processing
        use_ocr_annotations: Use OCR with annotations (3x cost)
        max_toc_pages: Maximum pages for TOC extraction
    """

    skip_ocr: bool
    use_llm: bool
    llm_provider: str
    llm_model: str
    ingest_weaviate: bool
    use_ocr_annotations: bool
    max_toc_pages: int


class ProcessingJob(TypedDict):
    """Processing job state for tracking background PDF processing.

    Attributes:
        status: Job status (processing, complete, error)
        queue: Queue for SSE events
        result: Processing result when complete
        filename: Original filename
    """

    status: str
    queue: Any  # queue.Queue - can't be typed more specifically
    result: Optional[Dict[str, Any]]
    filename: str


class SSEEvent(TypedDict, total=False):
    """Server-Sent Event structure for progress updates.

    Attributes:
        type: Event type (step, complete, error, keepalive)
        step: Current step identifier
        status: Step status
        detail: Additional detail message
        message: Error message (for error events)
        redirect: Redirect URL (for complete events)
    """

    type: str
    step: Optional[str]
    status: Optional[str]
    detail: Optional[str]
    message: Optional[str]
    redirect: Optional[str]


class DocumentInfo(TypedDict, total=False):
    """Document information for list display.

    Attributes:
        name: Document identifier
        path: Full path to document directory
        has_markdown: Whether markdown file exists
        has_chunks: Whether chunks JSON exists
        has_structured: Whether structured JSON exists
        has_images: Whether images directory has content
        image_count: Number of images
        metadata: Document metadata
        pages: Page count
        chunks_count: Number of chunks
        title: Document title
        author: Document author
        toc: Table of contents
    """

    name: str
    path: str
    has_markdown: bool
    has_chunks: bool
    has_structured: bool
    has_images: bool
    image_count: int
    metadata: Dict[str, Any]
    pages: int
    chunks_count: int
    title: Optional[str]
    author: Optional[str]
    toc: List[Dict[str, Any]]


class DocumentViewResult(TypedDict, total=False):
    """Complete document view data for template rendering.

    Attributes:
        document_name: Document identifier
        output_dir: Output directory path
        files: File paths dictionary
        metadata: Document metadata
        weaviate_ingest: Weaviate ingestion result
        pages: Page count
        chunks_count: Number of chunks
        chunks: List of chunks
        toc: Hierarchical TOC
        flat_toc: Flattened TOC
        cost: Processing cost
    """

    document_name: str
    output_dir: str
    files: Dict[str, Any]
    metadata: Dict[str, Any]
    weaviate_ingest: Optional[Dict[str, Any]]
    pages: int
    chunks_count: int
    chunks: List[Dict[str, Any]]
    toc: List[Dict[str, Any]]
    flat_toc: List[Dict[str, Any]]
    cost: float


class DeleteDocumentResult(TypedDict, total=False):
    """Result from document deletion operation.

    Attributes:
        success: Whether deletion succeeded
        deleted_passages: Number of passages deleted from Weaviate
        deleted_sections: Number of sections deleted
        deleted_document: Whether document record was deleted
        error: Error message if failed
    """

    success: bool
    deleted_passages: int
    deleted_sections: int
    deleted_document: bool
    error: Optional[str]


class BatchFileInfo(TypedDict, total=False):
    """Information about a single file in a batch upload.

    Attributes:
        filename: Original filename
        job_id: Processing job ID (assigned when processing starts)
        status: Current status (pending, processing, complete, error)
        error: Error message if processing failed
        size_bytes: File size in bytes
    """

    filename: str
    job_id: Optional[str]
    status: str  # Literal["pending", "processing", "complete", "error"]
    error: Optional[str]
    size_bytes: int


class BatchJob(TypedDict, total=False):
    """Batch processing job tracking multiple file uploads.

    Attributes:
        job_ids: List of individual processing job IDs
        files: List of file information dictionaries
        total_files: Total number of files in batch
        completed_files: Number of files successfully processed
        failed_files: Number of files that failed processing
        status: Overall batch status (processing, complete, partial)
        current_job_id: Currently processing job ID (None if between files)
        options: Processing options applied to all files
        created_at: Timestamp when batch was created
    """

    job_ids: List[str]
    files: List[BatchFileInfo]
    total_files: int
    completed_files: int
    failed_files: int
    status: str  # Literal["processing", "complete", "partial"]
    current_job_id: Optional[str]
    options: ProcessingOptions
    created_at: float
