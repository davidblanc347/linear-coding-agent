"""Word document processing pipeline for RAG ingestion.

This module provides a complete pipeline for processing Microsoft Word documents
(.docx) through the RAG system. It extracts content, builds structured markdown,
applies LLM processing, and ingests chunks into Weaviate.

The pipeline reuses existing LLM modules (metadata extraction, classification,
chunking, cleaning, validation) from the PDF pipeline, only replacing the initial
extraction step with Word-specific processing.

Example:
    Process a Word document with default settings:

        from pathlib import Path
        from utils.word_pipeline import process_word

        result = process_word(
            Path("document.docx"),
            use_llm=True,
            llm_provider="ollama",
            ingest_to_weaviate=True,
        )

        print(f"Success: {result['success']}")
        print(f"Chunks created: {result['chunks_count']}")

    Process without Weaviate ingestion:

        result = process_word(
            Path("document.docx"),
            use_llm=True,
            ingest_to_weaviate=False,
        )

Pipeline Steps:
    1. Word Extraction (word_processor.py)
    2. Markdown Construction
    3. TOC Extraction (word_toc_extractor.py)
    4. Metadata Extraction (llm_metadata.py) - REUSED
    5. Section Classification (llm_classifier.py) - REUSED
    6. Semantic Chunking (llm_chunker.py) - REUSED
    7. Chunk Cleaning (llm_cleaner.py) - REUSED
    8. Chunk Validation (llm_validator.py) - REUSED
    9. Weaviate Ingestion (weaviate_ingest.py) - REUSED

See Also:
    - utils.word_processor: Word content extraction
    - utils.word_toc_extractor: TOC construction from headings
    - utils.pdf_pipeline: Similar pipeline for PDF documents
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
import json

from utils.types import (
    Metadata,
    TOCEntry,
    ChunkData,
    PipelineResult,
    LLMProvider,
    ProgressCallback,
)
from utils.word_processor import (
    extract_word_content,
    extract_word_metadata,
    build_markdown_from_word,
    extract_word_images,
)
from utils.word_toc_extractor import build_toc_from_headings, flatten_toc

# Note: LLM modules imported dynamically when use_llm=True to avoid import errors


def _default_progress_callback(step: str, status: str, detail: str = "") -> None:
    """Default progress callback that prints to console.

    Args:
        step: Current pipeline step name.
        status: Step status (running, completed, error).
        detail: Optional detail message.
    """
    status_symbol = {
        "running": ">>>",
        "completed": "[OK]",
        "error": "[ERROR]",
    }.get(status, "[INFO]")

    print(f"{status_symbol} {step}: {detail}" if detail else f"{status_symbol} {step}")


def process_word(
    word_path: Path,
    *,
    use_llm: bool = True,
    llm_provider: LLMProvider = "ollama",
    use_semantic_chunking: bool = True,
    ingest_to_weaviate: bool = True,
    skip_metadata_lines: int = 5,
    extract_images: bool = True,
    progress_callback: Optional[ProgressCallback] = None,
) -> PipelineResult:
    """Process a Word document through the complete RAG pipeline.

    Extracts content from a .docx file, processes it with LLM modules,
    and optionally ingests the chunks into Weaviate. Reuses all LLM
    processing steps from the PDF pipeline (metadata, classification,
    chunking, cleaning, validation).

    Args:
        word_path: Path to the .docx file to process.
        use_llm: Enable LLM processing steps (metadata, chunking, validation).
            If False, uses simple text splitting. Default: True.
        llm_provider: LLM provider to use ("ollama" for local, "mistral" for API).
            Default: "ollama".
        use_semantic_chunking: Use LLM-based semantic chunking instead of simple
            text splitting. Requires use_llm=True. Default: True.
        ingest_to_weaviate: Ingest processed chunks into Weaviate database.
            Default: True.
        skip_metadata_lines: Number of initial paragraphs to skip when building
            markdown (metadata header lines like TITRE, AUTEUR). Default: 5.
        extract_images: Extract and save inline images from the document.
            Default: True.
        progress_callback: Optional callback for progress updates.
            Signature: (step: str, status: str, detail: str) -> None.

    Returns:
        PipelineResult dictionary with keys:
        - success (bool): Whether processing succeeded
        - document_name (str): Name of processed document
        - output_dir (Path): Directory containing outputs
        - chunks_count (int): Number of chunks created
        - cost_ocr (float): OCR cost (always 0 for Word)
        - cost_llm (float): LLM processing cost
        - cost_total (float): Total cost
        - error (str): Error message if success=False

    Raises:
        FileNotFoundError: If word_path does not exist.
        ValueError: If file is not a .docx document.

    Example:
        >>> result = process_word(
        ...     Path("darwin.docx"),
        ...     use_llm=True,
        ...     llm_provider="ollama",
        ...     ingest_to_weaviate=True,
        ... )
        >>> print(f"Created {result['chunks_count']} chunks")
        >>> print(f"Total cost: ${result['cost_total']:.4f}")

    Note:
        No OCR cost for Word documents (cost_ocr always 0).
        LLM costs depend on provider and document length.
    """
    # Use default progress callback if none provided
    callback = progress_callback or _default_progress_callback

    try:
        # Validate input
        if not word_path.exists():
            raise FileNotFoundError(f"Word document not found: {word_path}")

        if not word_path.suffix.lower() == ".docx":
            raise ValueError(f"File must be .docx format: {word_path}")

        doc_name = word_path.stem
        output_dir = Path("output") / doc_name
        output_dir.mkdir(parents=True, exist_ok=True)

        # ================================================================
        # STEP 1: Extract Word Content
        # ================================================================
        callback("Word Extraction", "running", "Extracting document content...")

        content = extract_word_content(word_path)

        callback(
            "Word Extraction",
            "completed",
            f"Extracted {content['total_paragraphs']} paragraphs, "
            f"{len(content['headings'])} headings",
        )

        # ================================================================
        # STEP 2: Build Markdown
        # ================================================================
        callback("Markdown Construction", "running", "Building markdown...")

        markdown_text = build_markdown_from_word(
            content["paragraphs"],
            skip_metadata_lines=skip_metadata_lines,
        )

        # Save markdown
        markdown_path = output_dir / f"{doc_name}.md"
        with open(markdown_path, "w", encoding="utf-8") as f:
            f.write(markdown_text)

        callback(
            "Markdown Construction",
            "completed",
            f"Saved to {markdown_path.name} ({len(markdown_text)} chars)",
        )

        # ================================================================
        # STEP 3: Build TOC
        # ================================================================
        callback("TOC Extraction", "running", "Building table of contents...")

        toc_hierarchical = build_toc_from_headings(content["headings"])
        toc_flat = flatten_toc(toc_hierarchical)

        callback(
            "TOC Extraction",
            "completed",
            f"Built TOC with {len(toc_flat)} entries",
        )

        # ================================================================
        # STEP 4: Extract Images (if requested)
        # ================================================================
        image_paths: List[Path] = []
        if extract_images and content["has_images"]:
            callback("Image Extraction", "running", "Extracting images...")

            from docx import Document
            doc = Document(word_path)
            image_paths = extract_word_images(
                doc,
                output_dir / "images",
                doc_name,
            )

            callback(
                "Image Extraction",
                "completed",
                f"Extracted {len(image_paths)} images",
            )

        # ================================================================
        # STEP 5: LLM Metadata Extraction (REUSED)
        # ================================================================
        metadata: Metadata
        cost_llm = 0.0

        if use_llm:
            from utils.llm_metadata import extract_metadata

            callback("Metadata Extraction", "running", "Extracting metadata with LLM...")

            try:
                metadata_llm = extract_metadata(
                    markdown_text,
                    provider=llm_provider,
                )

                # Fallback to Word properties if LLM returns None
                if metadata_llm is None:
                    callback(
                        "Metadata Extraction",
                        "completed",
                        "LLM extraction failed, using Word properties",
                    )
                    raw_meta = content["metadata_raw"]
                    metadata = Metadata(
                        title=raw_meta.get("title", doc_name),
                        author=raw_meta.get("author", "Unknown"),
                        year=raw_meta.get("created").year if raw_meta.get("created") else None,
                        language=raw_meta.get("language", "unknown"),
                    )
                else:
                    metadata = metadata_llm
                    callback(
                        "Metadata Extraction",
                        "completed",
                        f"Title: {metadata.get('title', '')[:50]}..., Author: {metadata.get('author', '')}",
                    )
            except Exception as e:
                callback(
                    "Metadata Extraction",
                    "completed",
                    f"LLM error ({str(e)}), using Word properties",
                )
                raw_meta = content["metadata_raw"]
                metadata = Metadata(
                    title=raw_meta.get("title", doc_name),
                    author=raw_meta.get("author", "Unknown"),
                    year=raw_meta.get("created").year if raw_meta.get("created") else None,
                    language=raw_meta.get("language", "unknown"),
                )
        else:
            # Use metadata from Word properties
            raw_meta = content["metadata_raw"]
            metadata = Metadata(
                title=raw_meta.get("title", doc_name),
                author=raw_meta.get("author", "Unknown"),
                year=raw_meta.get("created").year if raw_meta.get("created") else None,
                language=raw_meta.get("language", "unknown"),
            )

            callback(
                "Metadata Extraction",
                "completed",
                "Using Word document properties",
            )

        # ================================================================
        # STEP 6: Section Classification (REUSED)
        # ================================================================
        if use_llm:
            from utils.llm_classifier import classify_sections

            callback("Section Classification", "running", "Classifying sections...")

            # Note: classify_sections expects a list of section dicts, not raw TOC
            sections_to_classify = [
                {
                    "section_path": entry["sectionPath"],
                    "title": entry["title"],
                    "content": "",  # Content matched later
                }
                for entry in toc_flat
            ]

            classified_sections = classify_sections(
                sections_to_classify,
                document_title=metadata.get("title", ""),
                provider=llm_provider,
            )

            main_sections = [
                s for s in classified_sections
                if s.get("type") == "main_content"
            ]

            callback(
                "Section Classification",
                "completed",
                f"{len(main_sections)}/{len(classified_sections)} main content sections",
            )
        else:
            # All sections are main content by default
            classified_sections = [
                {
                    "section_path": entry["sectionPath"],
                    "type": "main_content",
                    "should_index": True,
                    "classification_reason": "No LLM classification",
                }
                for entry in toc_flat
            ]

            callback(
                "Section Classification",
                "completed",
                "Skipped (use_llm=False)",
            )

        # ================================================================
        # STEP 7: Semantic Chunking (REUSED)
        # ================================================================
        if use_llm and use_semantic_chunking:
            from utils.llm_chunker import chunk_section_with_llm

            callback("Semantic Chunking", "running", "Chunking with LLM...")

            # Chunk each section
            all_chunks: List[ChunkData] = []
            for entry in toc_flat:
                # TODO: Extract section content from markdown based on sectionPath
                # For now, using simple approach
                section_chunks = chunk_section_with_llm(
                    markdown_text,
                    entry["title"],
                    metadata.get("title", ""),
                    metadata.get("author", ""),
                    provider=llm_provider,
                )
                all_chunks.extend(section_chunks)

            chunks = all_chunks

            callback(
                "Semantic Chunking",
                "completed",
                f"Created {len(chunks)} semantic chunks",
            )
        else:
            # Simple text splitting (fallback)
            callback("Text Splitting", "running", "Simple text splitting...")

            # Simple chunking by paragraphs (basic fallback)
            chunks_simple = []
            for i, para in enumerate(content["paragraphs"][skip_metadata_lines:]):
                if para["text"] and not para["is_heading"]:
                    chunk_dict: ChunkData = {
                        "text": para["text"],
                        "keywords": [],
                        "sectionPath": "1",  # Default section
                        "chapterTitle": "Main Content",
                        "unitType": "paragraph",
                        "orderIndex": i,
                        "work": {
                            "title": metadata["title"],
                            "author": metadata["author"],
                        },
                        "document": {
                            "sourceId": doc_name,
                            "edition": content["metadata_raw"].get("edition", ""),
                        },
                    }
                    chunks_simple.append(chunk_dict)

            chunks = chunks_simple

            callback(
                "Text Splitting",
                "completed",
                f"Created {len(chunks)} simple chunks",
            )

        # ================================================================
        # STEP 8: Chunk Cleaning (REUSED)
        # ================================================================
        if use_llm:
            from utils.llm_cleaner import clean_chunk, is_chunk_valid

            callback("Chunk Cleaning", "running", "Cleaning chunks...")

            # Clean each chunk
            cleaned_chunks = []
            for chunk in chunks:
                # Extract text from chunk dict
                text: str = chunk.get("text", "")

                # Clean the text
                cleaned_text = clean_chunk(text, use_llm=False)

                # Validate chunk
                if is_chunk_valid(cleaned_text, min_chars=30, min_words=8):
                    # Update chunk with cleaned text
                    chunk["text"] = cleaned_text
                    cleaned_chunks.append(chunk)

            chunks = cleaned_chunks

            callback(
                "Chunk Cleaning",
                "completed",
                f"{len(chunks)} chunks after cleaning",
            )

        # ================================================================
        # STEP 9: Chunk Validation (REUSED)
        # ================================================================
        if use_llm:
            from utils.llm_validator import enrich_chunks_with_concepts

            callback("Chunk Validation", "running", "Enriching chunks with concepts...")

            # Enrich chunks with keywords/concepts
            enriched_chunks = enrich_chunks_with_concepts(
                chunks,
                provider=llm_provider,
            )

            chunks = enriched_chunks

            callback(
                "Chunk Validation",
                "completed",
                f"Validated {len(chunks)} chunks",
            )

        # ================================================================
        # STEP 10: Save Chunks JSON
        # ================================================================
        callback("Save Results", "running", "Saving chunks to JSON...")

        chunks_output = {
            "metadata": metadata,
            "toc": toc_flat,
            "classified_sections": classified_sections,
            "chunks": chunks,
            "cost_ocr": 0.0,  # No OCR for Word documents
            "cost_llm": cost_llm,
            "cost_total": cost_llm,
            "paragraphs": content["total_paragraphs"],
            "chunks_count": len(chunks),
        }

        chunks_path = output_dir / f"{doc_name}_chunks.json"
        with open(chunks_path, "w", encoding="utf-8") as f:
            json.dump(chunks_output, f, indent=2, ensure_ascii=False, default=str)

        callback(
            "Save Results",
            "completed",
            f"Saved to {chunks_path.name}",
        )

        # ================================================================
        # STEP 11: Weaviate Ingestion (REUSED)
        # ================================================================
        if ingest_to_weaviate:
            from utils.weaviate_ingest import ingest_document

            callback("Weaviate Ingestion", "running", "Ingesting into Weaviate...")

            ingestion_result = ingest_document(
                metadata=metadata,
                chunks=chunks,
                toc=toc_flat,
                document_source_id=doc_name,
            )

            # Save ingestion results
            weaviate_path = output_dir / f"{doc_name}_weaviate.json"
            with open(weaviate_path, "w", encoding="utf-8") as f:
                json.dump(ingestion_result, f, indent=2, ensure_ascii=False, default=str)

            callback(
                "Weaviate Ingestion",
                "completed",
                f"Ingested {ingestion_result.get('chunks_ingested', 0)} chunks",
            )

        # ================================================================
        # Return Success Result
        # ================================================================
        return PipelineResult(
            success=True,
            document_name=doc_name,
            output_dir=output_dir,
            chunks_count=len(chunks),
            cost_ocr=0.0,
            cost_llm=cost_llm,
            cost_total=cost_llm,
            error="",
        )

    except Exception as e:
        error_msg = f"Pipeline failed: {str(e)}"
        callback("Pipeline Error", "error", error_msg)

        return PipelineResult(
            success=False,
            document_name=word_path.stem,
            output_dir=Path("output") / word_path.stem,
            chunks_count=0,
            cost_ocr=0.0,
            cost_llm=0.0,
            cost_total=0.0,
            error=error_msg,
        )
