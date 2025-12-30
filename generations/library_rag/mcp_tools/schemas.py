"""
Pydantic schemas for MCP tool inputs and outputs.

All schemas use strict validation and include field descriptions
for automatic JSON schema generation in MCP tool definitions.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# =============================================================================
# Parsing Tool Schemas
# =============================================================================


class ParsePdfInput(BaseModel):
    """Input schema for parse_pdf tool."""

    pdf_path: str = Field(
        ...,
        description="Path to the PDF file to process, or URL to download",
        min_length=1,
    )


class ParsePdfOutput(BaseModel):
    """Output schema for parse_pdf tool."""

    success: bool = Field(..., description="Whether processing succeeded")
    document_name: str = Field(..., description="Name of the processed document")
    source_id: str = Field(..., description="Unique identifier for the document")
    pages: int = Field(..., description="Number of pages processed")
    chunks_count: int = Field(..., description="Number of chunks created")
    cost_ocr: float = Field(..., description="OCR processing cost in EUR")
    cost_llm: float = Field(..., description="LLM processing cost in EUR")
    cost_total: float = Field(..., description="Total processing cost in EUR")
    output_dir: str = Field(..., description="Directory containing output files")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Extracted metadata (title, author, language, year)",
    )
    error: Optional[str] = Field(None, description="Error message if failed")


# =============================================================================
# Retrieval Tool Schemas
# =============================================================================


class ChunkResult(BaseModel):
    """A single chunk result from search."""

    text: str = Field(..., description="Chunk text content")
    similarity: float = Field(..., description="Similarity score (0-1)")
    source_id: str = Field(..., description="Source document ID (e.g., 'peirce_collected_papers')")
    canonical_reference: Optional[str] = Field(None, description="Academic citation reference (e.g., 'CP 5.628', 'Ménon 80a')")
    section_path: str = Field(..., description="Hierarchical section path")
    chapter_title: Optional[str] = Field(None, description="Chapter title if available")
    work_title: str = Field(..., description="Title of the work")
    work_author: str = Field(..., description="Author of the work")
    order_index: int = Field(..., description="Position in document")


class SearchChunksInput(BaseModel):
    """Input schema for search_chunks tool."""

    query: str = Field(
        ...,
        description="Semantic search query",
        min_length=1,
        max_length=1000,
    )
    limit: int = Field(
        default=10,
        description="Maximum number of results to return",
        ge=1,
        le=500,
    )
    min_similarity: float = Field(
        default=0.0,
        description="Minimum similarity threshold (0-1)",
        ge=0.0,
        le=1.0,
    )
    author_filter: Optional[str] = Field(
        None,
        description="Filter by author name",
    )
    work_filter: Optional[str] = Field(
        None,
        description="Filter by work title",
    )
    language_filter: Optional[str] = Field(
        None,
        description="Filter by language code (e.g., 'fr', 'en')",
    )


class SearchChunksOutput(BaseModel):
    """Output schema for search_chunks tool."""

    results: List[ChunkResult] = Field(
        default_factory=list,
        description="List of matching chunks",
    )
    total_count: int = Field(..., description="Total number of results")
    query: str = Field(..., description="Original query")


class SummaryResult(BaseModel):
    """A single summary result from search."""

    text: str = Field(..., description="Summary text")
    similarity: float = Field(..., description="Similarity score (0-1)")
    title: str = Field(..., description="Section title")
    section_path: str = Field(..., description="Hierarchical section path")
    level: int = Field(..., description="Hierarchy level (1=chapter, 2=section, etc.)")
    concepts: List[str] = Field(default_factory=list, description="Key concepts")
    document_source_id: str = Field(..., description="Source document ID")


class SearchSummariesInput(BaseModel):
    """Input schema for search_summaries tool."""

    query: str = Field(
        ...,
        description="Semantic search query",
        min_length=1,
        max_length=1000,
    )
    limit: int = Field(
        default=10,
        description="Maximum number of results to return",
        ge=1,
        le=100,
    )
    min_level: Optional[int] = Field(
        None,
        description="Minimum hierarchy level (1=chapter)",
        ge=1,
        le=5,
    )
    max_level: Optional[int] = Field(
        None,
        description="Maximum hierarchy level",
        ge=1,
        le=5,
    )


class SearchSummariesOutput(BaseModel):
    """Output schema for search_summaries tool."""

    results: List[SummaryResult] = Field(
        default_factory=list,
        description="List of matching summaries",
    )
    total_count: int = Field(..., description="Total number of results")
    query: str = Field(..., description="Original query")


class GetDocumentInput(BaseModel):
    """Input schema for get_document tool."""

    source_id: str = Field(
        ...,
        description="Document source ID (e.g., 'platon-menon')",
        min_length=1,
    )
    include_chunks: bool = Field(
        default=False,
        description="Include document chunks in response",
    )
    chunk_limit: int = Field(
        default=50,
        description="Maximum chunks to return if include_chunks=True",
        ge=1,
        le=500,
    )


class DocumentInfo(BaseModel):
    """Document information."""

    source_id: str = Field(..., description="Unique document identifier")
    work_title: str = Field(..., description="Title of the work")
    work_author: str = Field(..., description="Author of the work")
    edition: Optional[str] = Field(None, description="Edition information")
    pages: int = Field(..., description="Number of pages")
    language: str = Field(..., description="Document language")
    toc: Optional[Dict[str, Any]] = Field(None, description="Table of contents")
    hierarchy: Optional[Dict[str, Any]] = Field(None, description="Document hierarchy")


class GetDocumentOutput(BaseModel):
    """Output schema for get_document tool."""

    document: Optional[DocumentInfo] = Field(None, description="Document information")
    chunks: List[ChunkResult] = Field(
        default_factory=list,
        description="Document chunks (if requested)",
    )
    chunks_total: int = Field(
        default=0,
        description="Total number of chunks in document",
    )
    found: bool = Field(..., description="Whether document was found")
    error: Optional[str] = Field(None, description="Error message if not found")


class ListDocumentsInput(BaseModel):
    """Input schema for list_documents tool."""

    author_filter: Optional[str] = Field(None, description="Filter by author name")
    work_filter: Optional[str] = Field(None, description="Filter by work title")
    language_filter: Optional[str] = Field(None, description="Filter by language code")
    limit: int = Field(
        default=50,
        description="Maximum number of results",
        ge=1,
        le=250,
    )
    offset: int = Field(
        default=0,
        description="Offset for pagination",
        ge=0,
    )


class DocumentSummary(BaseModel):
    """Summary of a document for listing."""

    source_id: str = Field(..., description="Unique document identifier")
    work_title: str = Field(..., description="Title of the work")
    work_author: str = Field(..., description="Author of the work")
    pages: int = Field(..., description="Number of pages")
    chunks_count: int = Field(..., description="Number of chunks")
    language: str = Field(..., description="Document language")


class ListDocumentsOutput(BaseModel):
    """Output schema for list_documents tool."""

    documents: List[DocumentSummary] = Field(
        default_factory=list,
        description="List of documents",
    )
    total_count: int = Field(..., description="Total number of documents")
    limit: int = Field(..., description="Applied limit")
    offset: int = Field(..., description="Applied offset")


class GetChunksByDocumentInput(BaseModel):
    """Input schema for get_chunks_by_document tool."""

    source_id: str = Field(
        ...,
        description="Document source ID",
        min_length=1,
    )
    limit: int = Field(
        default=50,
        description="Maximum number of chunks to return",
        ge=1,
        le=500,
    )
    offset: int = Field(
        default=0,
        description="Offset for pagination",
        ge=0,
    )
    section_filter: Optional[str] = Field(
        None,
        description="Filter by section path prefix",
    )


class GetChunksByDocumentOutput(BaseModel):
    """Output schema for get_chunks_by_document tool."""

    chunks: List[ChunkResult] = Field(
        default_factory=list,
        description="Ordered list of chunks",
    )
    total_count: int = Field(..., description="Total chunks in document")
    document_source_id: str = Field(..., description="Document source ID")
    limit: int = Field(..., description="Applied limit")
    offset: int = Field(..., description="Applied offset")


class WorkInfo(BaseModel):
    """Information about a work."""

    title: str = Field(..., description="Work title")
    author: str = Field(..., description="Author name")
    year: Optional[int] = Field(None, description="Publication year")
    language: str = Field(..., description="Language code")
    genre: Optional[str] = Field(None, description="Genre classification")


class AuthorWorkResult(BaseModel):
    """Work with its documents for author filtering."""

    work: WorkInfo = Field(..., description="Work information")
    documents: List[DocumentSummary] = Field(
        default_factory=list,
        description="Documents for this work",
    )
    total_chunks: int = Field(..., description="Total chunks across all documents")


class FilterByAuthorInput(BaseModel):
    """Input schema for filter_by_author tool."""

    author: str = Field(
        ...,
        description="Author name to search for",
        min_length=1,
    )
    include_chunk_counts: bool = Field(
        default=True,
        description="Include chunk counts in results",
    )


class FilterByAuthorOutput(BaseModel):
    """Output schema for filter_by_author tool."""

    author: str = Field(..., description="Searched author name")
    works: List[AuthorWorkResult] = Field(
        default_factory=list,
        description="Works by this author",
    )
    total_works: int = Field(..., description="Total number of works")
    total_documents: int = Field(..., description="Total number of documents")
    total_chunks: int = Field(..., description="Total number of chunks")


class DeleteDocumentInput(BaseModel):
    """Input schema for delete_document tool."""

    source_id: str = Field(
        ...,
        description="Document source ID to delete",
        min_length=1,
    )
    confirm: bool = Field(
        default=False,
        description="Must be True to confirm deletion",
    )


class DeleteDocumentOutput(BaseModel):
    """Output schema for delete_document tool."""

    success: bool = Field(..., description="Whether deletion succeeded")
    source_id: str = Field(..., description="Deleted document source ID")
    chunks_deleted: int = Field(..., description="Number of chunks deleted")
    summaries_deleted: int = Field(..., description="Number of summaries deleted")
    error: Optional[str] = Field(None, description="Error message if failed")
