"""Utils - Pipeline de parsing PDF avec OCR Mistral et structuration LLM.

Version 2.0 : Pipeline intelligent avec extraction LLM des métadonnées,
TOC, classification des sections, chunking sémantique et validation.
"""

from .mistral_client import create_client, get_api_key, estimate_ocr_cost
from .pdf_uploader import upload_pdf
from .ocr_processor import run_ocr, serialize_ocr_response
from .markdown_builder import build_markdown
from .image_extractor import extract_images, create_image_writer
from .hierarchy_parser import build_hierarchy
from .llm_structurer import structure_with_llm, LLMStructureError

# Nouveaux modules LLM v2
from .llm_metadata import extract_metadata
from .llm_toc import extract_toc
from .llm_classifier import classify_sections, filter_indexable_sections
from .llm_cleaner import clean_chunk, clean_page_markers, is_chunk_valid
from .llm_chunker import chunk_section_with_llm, simple_chunk_by_paragraphs, extract_concepts_from_chunk, extract_paragraph_number
from .llm_validator import validate_document, apply_corrections, enrich_chunks_with_concepts

# Pipeline
from .pdf_pipeline import process_pdf, process_pdf_v2, process_pdf_bytes
from .weaviate_ingest import ingest_document, delete_document_chunks

__all__ = [
    # Client Mistral
    "create_client",
    "get_api_key", 
    "estimate_ocr_cost",
    # Upload
    "upload_pdf",
    # OCR
    "run_ocr",
    "serialize_ocr_response",
    # Markdown
    "build_markdown",
    # Images
    "extract_images",
    "create_image_writer",
    # Hiérarchie
    "build_hierarchy",
    # LLM Legacy
    "structure_with_llm",
    "LLMStructureError",
    # LLM v2 - Métadonnées
    "extract_metadata",
    # LLM v2 - TOC
    "extract_toc",
    # LLM v2 - Classification
    "classify_sections",
    "filter_indexable_sections",
    # LLM v2 - Nettoyage
    "clean_chunk",
    "clean_page_markers",
    "is_chunk_valid",
    # LLM v2 - Chunking
    "chunk_section_with_llm",
    "simple_chunk_by_paragraphs",
    "extract_concepts_from_chunk",
    "extract_paragraph_number",
    # LLM v2 - Validation
    "validate_document",
    "apply_corrections",
    "enrich_chunks_with_concepts",
    # Pipeline
    "process_pdf",
    "process_pdf_v2",
    "process_pdf_bytes",
    # Weaviate
    "ingest_document",
    "delete_document_chunks",
]
