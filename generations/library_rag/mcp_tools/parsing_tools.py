"""Parsing tools for Library RAG MCP Server.

This module implements the parse_pdf tool with optimal pre-configured parameters
for PDF ingestion into the Library RAG system.

The tool uses fixed optimal parameters:
    - llm_provider: "mistral" (API-based, fast)
    - llm_model: "mistral-medium-latest" (best quality/cost ratio)
    - use_semantic_chunking: True (LLM-based intelligent chunking)
    - use_ocr_annotations: True (3x cost but better TOC extraction)
    - ingest_to_weaviate: True (automatic vectorization and storage)

Example:
    The parse_pdf tool can be invoked via MCP with a simple path::

        {
            "tool": "parse_pdf",
            "arguments": {
                "pdf_path": "/path/to/document.pdf"
            }
        }

    Or with a URL::

        {
            "tool": "parse_pdf",
            "arguments": {
                "pdf_path": "https://example.com/document.pdf"
            }
        }
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, Literal
from urllib.parse import urlparse

import httpx

from mcp_tools.schemas import ParsePdfInput, ParsePdfOutput

# Import pdf_pipeline for PDF processing
from utils.pdf_pipeline import process_pdf, process_pdf_bytes
from utils.types import LLMProvider

# Logger for this module
logger = logging.getLogger(__name__)

# =============================================================================
# Constants - Fixed Optimal Parameters
# =============================================================================

# LLM provider configuration (Mistral API for best results)
FIXED_LLM_PROVIDER: LLMProvider = "mistral"
FIXED_LLM_MODEL = "mistral-medium-latest"

# Processing options (optimal settings for quality)
FIXED_USE_SEMANTIC_CHUNKING = True
FIXED_USE_OCR_ANNOTATIONS = True
FIXED_INGEST_TO_WEAVIATE = True

# Additional processing flags
FIXED_USE_LLM = True
# Note: The following flags are not supported by process_pdf() and should not be used
# FIXED_CLEAN_CHUNKS = True
# FIXED_EXTRACT_CONCEPTS = True
# FIXED_VALIDATE_OUTPUT = True


# =============================================================================
# Helper Functions
# =============================================================================


def is_url(path: str) -> bool:
    """Check if a path is a URL.

    Args:
        path: The path or URL string to check.

    Returns:
        True if the path is a valid HTTP/HTTPS URL, False otherwise.

    Example:
        >>> is_url("https://example.com/doc.pdf")
        True
        >>> is_url("/path/to/doc.pdf")
        False
    """
    try:
        result = urlparse(path)
        return result.scheme in ("http", "https")
    except ValueError:
        return False


async def download_pdf(url: str, timeout: float = 60.0) -> bytes:
    """Download a PDF file from a URL.

    Args:
        url: The URL to download from. Must be HTTP or HTTPS.
        timeout: Maximum time in seconds to wait for download.
            Defaults to 60 seconds.

    Returns:
        Raw bytes content of the downloaded PDF file.

    Raises:
        httpx.HTTPError: If the download fails (network error, HTTP error, etc.).
        ValueError: If the URL is invalid or not accessible.

    Example:
        >>> pdf_bytes = await download_pdf("https://example.com/document.pdf")
        >>> len(pdf_bytes) > 0
        True
    """
    logger.info(f"Downloading PDF from: {url}")

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        if "application/pdf" not in content_type.lower() and not url.lower().endswith(
            ".pdf"
        ):
            logger.warning(
                f"URL may not be a PDF (Content-Type: {content_type}), proceeding anyway"
            )

        logger.info(f"Downloaded {len(response.content)} bytes from {url}")
        return response.content


def extract_filename_from_url(url: str) -> str:
    """Extract a filename from a URL.

    Args:
        url: The URL to extract filename from.

    Returns:
        Extracted filename with .pdf extension. Falls back to "downloaded.pdf"
        if no filename can be extracted.

    Example:
        >>> extract_filename_from_url("https://example.com/documents/kant.pdf")
        "kant.pdf"
        >>> extract_filename_from_url("https://example.com/api/download")
        "downloaded.pdf"
    """
    parsed = urlparse(url)
    path = parsed.path

    if path:
        # Get the last path component
        filename = path.split("/")[-1]
        if filename and "." in filename:
            return filename
        if filename:
            return f"{filename}.pdf"

    return "downloaded.pdf"


# =============================================================================
# Main Tool Implementation
# =============================================================================


async def parse_pdf_handler(input_data: ParsePdfInput) -> ParsePdfOutput:
    """Process a PDF document with optimal pre-configured parameters.

    This is the main handler for the parse_pdf MCP tool. It processes PDFs
    through the Library RAG pipeline with the following fixed optimal settings:

    - LLM: Mistral API (mistral-medium-latest) for fast, high-quality processing
    - OCR: Mistral OCR with annotations (better TOC extraction, 3x cost)
    - Chunking: Semantic LLM-based chunking (argumentative units)
    - Ingestion: Automatic Weaviate vectorization and storage

    The tool accepts either a local file path or a URL. URLs are automatically
    downloaded before processing.

    Args:
        input_data: Validated input containing pdf_path (local path or URL).

    Returns:
        ParsePdfOutput containing processing results including:
        - success: Whether processing completed successfully
        - document_name: Name of the processed document
        - source_id: Unique identifier for retrieval
        - pages: Number of pages processed
        - chunks_count: Number of chunks created
        - cost_ocr: OCR cost in EUR
        - cost_llm: LLM cost in EUR
        - cost_total: Total processing cost
        - output_dir: Directory containing output files
        - metadata: Extracted document metadata
        - error: Error message if processing failed

    Example:
        >>> input_data = ParsePdfInput(pdf_path="/docs/aristotle.pdf")
        >>> result = await parse_pdf_handler(input_data)
        >>> result.success
        True
        >>> result.chunks_count > 0
        True
    """
    pdf_path = input_data.pdf_path
    logger.info(f"parse_pdf called with: {pdf_path}")

    try:
        # Determine if input is a URL or local path
        if is_url(pdf_path):
            # Download PDF from URL
            logger.info(f"Detected URL input, downloading: {pdf_path}")
            pdf_bytes = await download_pdf(pdf_path)
            filename = extract_filename_from_url(pdf_path)

            # Process from bytes
            result = process_pdf_bytes(
                file_bytes=pdf_bytes,
                filename=filename,
                output_dir=Path("output"),
                llm_provider=FIXED_LLM_PROVIDER,
                use_llm=FIXED_USE_LLM,
                llm_model=FIXED_LLM_MODEL,
                use_semantic_chunking=FIXED_USE_SEMANTIC_CHUNKING,
                use_ocr_annotations=FIXED_USE_OCR_ANNOTATIONS,
                ingest_to_weaviate=FIXED_INGEST_TO_WEAVIATE,
            )
        else:
            # Process local file
            local_path = Path(pdf_path)
            if not local_path.exists():
                logger.error(f"PDF file not found: {pdf_path}")
                return ParsePdfOutput(
                    success=False,
                    document_name="",
                    source_id="",
                    pages=0,
                    chunks_count=0,
                    cost_ocr=0.0,
                    cost_llm=0.0,
                    cost_total=0.0,
                    output_dir="",
                    metadata={},
                    error=f"PDF file not found: {pdf_path}",
                )

            logger.info(f"Processing local file: {local_path}")
            result = process_pdf(
                pdf_path=local_path,
                output_dir=Path("output"),
                use_llm=FIXED_USE_LLM,
                llm_provider=FIXED_LLM_PROVIDER,
                llm_model=FIXED_LLM_MODEL,
                use_semantic_chunking=FIXED_USE_SEMANTIC_CHUNKING,
                use_ocr_annotations=FIXED_USE_OCR_ANNOTATIONS,
                ingest_to_weaviate=FIXED_INGEST_TO_WEAVIATE,
            )

        # Convert pipeline result to output schema
        success = result.get("success", False)
        document_name = result.get("document_name", "")
        source_id = result.get("source_id", document_name)

        # Extract costs
        cost_ocr = result.get("cost_ocr", 0.0)
        cost_llm = result.get("cost_llm", 0.0)
        cost_total = result.get("cost_total", cost_ocr + cost_llm)

        # Extract metadata
        metadata_raw = result.get("metadata", {})
        if metadata_raw is None:
            metadata_raw = {}

        # Build output
        output = ParsePdfOutput(
            success=success,
            document_name=document_name,
            source_id=source_id,
            pages=result.get("pages", 0),
            chunks_count=result.get("chunks_count", 0),
            cost_ocr=cost_ocr,
            cost_llm=cost_llm,
            cost_total=cost_total,
            output_dir=str(result.get("output_dir", "")),
            metadata=metadata_raw,
            error=result.get("error"),
        )

        if success:
            logger.info(
                f"Successfully processed {document_name}: "
                f"{output.chunks_count} chunks, {output.cost_total:.4f} EUR"
            )
        else:
            logger.error(f"Failed to process {pdf_path}: {output.error}")

        return output

    except httpx.HTTPError as e:
        logger.error(f"HTTP error downloading PDF: {e}")
        return ParsePdfOutput(
            success=False,
            document_name="",
            source_id="",
            pages=0,
            chunks_count=0,
            cost_ocr=0.0,
            cost_llm=0.0,
            cost_total=0.0,
            output_dir="",
            metadata={},
            error=f"Failed to download PDF: {e}",
        )
    except Exception as e:
        logger.error(f"Error processing PDF: {e}", exc_info=True)
        return ParsePdfOutput(
            success=False,
            document_name="",
            source_id="",
            pages=0,
            chunks_count=0,
            cost_ocr=0.0,
            cost_llm=0.0,
            cost_total=0.0,
            output_dir="",
            metadata={},
            error=f"Processing error: {str(e)}",
        )
