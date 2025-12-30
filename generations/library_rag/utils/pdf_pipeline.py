"""PDF Processing Pipeline for Philosophical and Academic Texts.

This module provides a comprehensive 10-step pipeline for processing PDF documents
through OCR, intelligent LLM-based extraction, and vector database ingestion.
It is the main orchestration layer for the Library RAG application.

Pipeline V2 Architecture (10 Steps):
    1. **OCR Processing**: Extract text and images via Mistral OCR API (~0.003 EUR/page)
    2. **Markdown Building**: Convert OCR output to structured Markdown
    3. **Image Extraction**: Save document images to disk (optional base64 embedding)
    4. **Metadata Extraction**: LLM-based extraction of title, author, year, language
    5. **TOC Extraction**: Hierarchical table of contents via LLM or OCR annotations
    6. **Section Classification**: Classify sections (main_content, exposition, etc.)
    7. **Semantic Chunking**: Split content into argumentative units via LLM
    8. **Chunk Cleaning**: Remove OCR artifacts and validate chunk quality
    9. **Validation & Enrichment**: LLM validation + concept extraction
    10. **Weaviate Ingestion**: Vectorize and store chunks for semantic search

LLM Provider Options:
    - **Ollama** (local): Free, slower, good for development/testing
    - **Mistral API** (remote): Fast, paid, recommended for production

Key Parameters:
    - ``skip_ocr``: Reuse existing markdown (avoids OCR cost on re-processing)
    - ``use_llm``: Enable/disable LLM processing steps
    - ``use_semantic_chunking``: Use LLM for intelligent chunking (slower but precise)
    - ``use_ocr_annotations``: Use OCR annotations for TOC (3x cost, more reliable)
    - ``ingest_to_weaviate``: Insert chunks into Weaviate vector database

Example:
    Basic usage with default settings (Ollama local)::

        from pathlib import Path
        from utils.pdf_pipeline import process_pdf

        result = process_pdf(
            Path("input/descartes_meditations.pdf"),
            output_dir=Path("output"),
            use_llm=True,
            llm_provider="ollama",
        )

        if result["success"]:
            print(f"Processed: {result['document_name']}")
            print(f"Chunks: {result['chunks_count']}")
            print(f"Cost: {result.get('cost_total', 0):.4f} EUR")

    Production usage with Mistral API::

        result = process_pdf(
            Path("input/document.pdf"),
            llm_provider="mistral",
            use_semantic_chunking=True,  # Better quality chunks
            use_ocr_annotations=True,     # More reliable TOC
            ingest_to_weaviate=True,
        )

    Re-processing without OCR cost::

        result = process_pdf(
            Path("input/document.pdf"),
            skip_ocr=True,  # Reuse existing markdown
            use_llm=True,
        )

Cost Tracking:
    The pipeline tracks costs for both OCR and LLM operations:

    - OCR costs: ~0.003 EUR/page (standard), ~0.009 EUR/page (with annotations)
    - LLM costs: Variable when using Mistral API, free with Ollama

    Costs are returned in the result dict::

        result["cost_ocr"]   # OCR cost in euros
        result["cost_llm"]   # LLM cost in euros (Mistral API only)
        result["cost_total"] # Total cost

Output Files:
    For each processed document, the pipeline creates::

        output/<doc_name>/
            <doc_name>.md           # Structured markdown
            <doc_name>_ocr.json     # Raw OCR response
            <doc_name>_chunks.json  # Processed chunks + metadata
            <doc_name>_weaviate.json # Weaviate ingestion results
            images/                 # Extracted images (if not embedded)

See Also:
    - :mod:`utils.mistral_client`: OCR API client
    - :mod:`utils.llm_metadata`: Metadata extraction
    - :mod:`utils.llm_toc`: TOC extraction
    - :mod:`utils.llm_classifier`: Section classification
    - :mod:`utils.llm_chunker`: Semantic chunking
    - :mod:`utils.llm_cleaner`: Chunk cleaning
    - :mod:`utils.llm_validator`: Document validation
    - :mod:`utils.weaviate_ingest`: Vector database ingestion
    - :mod:`utils.types`: Type definitions for all data structures

Note:
    This module supports both V1 (legacy) and V2 (current) pipelines.
    V1 is kept for backwards compatibility but V2 is recommended.

Version: 2.0
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, TYPE_CHECKING, Union, cast

# Import Mistral types for type checking only (avoids runtime import issues)
if TYPE_CHECKING:
    from mistralai import Mistral as MistralClient

from .types import (
    ChunkData,
    ChunksDataExport,
    ClassifiedSection,
    DocumentHierarchy,
    FlatChunk,
    FlatSection,
    HierarchyNode,
    LegacyMetadata,
    LLMCostStats,
    LLMProvider,
    Metadata,
    OptionalProgressCallback,
    ParsedDocument,
    PipelineResult,
    SemanticChunk,
    SimpleTOCEntry,
    TOCEntry,
    TOCExtractionResult,
    V1PipelineResult,
    V2PipelineFiles,
    V2PipelineResult,
    ValidationResult,
    WeaviateIngestResult,
)

from .mistral_client import create_client, estimate_ocr_cost
from .ocr_processor import run_ocr, serialize_ocr_response
from .markdown_builder import build_markdown
from .image_extractor import create_image_writer
from .hierarchy_parser import build_hierarchy, flatten_hierarchy
from .llm_structurer import structure_with_llm, LLMStructureError, LLMStructuredResult, reset_llm_cost, get_llm_cost

# Nouveaux modules LLM v2
from .llm_metadata import extract_metadata
from .llm_toc import extract_toc
from .llm_classifier import classify_sections, filter_indexable_sections
from .llm_cleaner import clean_chunk, is_chunk_valid
from .llm_chunker import chunk_section_with_llm, simple_chunk_by_paragraphs
from .llm_validator import validate_document, apply_corrections, enrich_chunks_with_concepts

from .weaviate_ingest import ingest_document


# Logger
logger = logging.getLogger(__name__)


def extract_document_metadata_legacy(
    hierarchy: DocumentHierarchy,
    chunks: List[Dict[str, Any]],
    doc_name: str,
) -> LegacyMetadata:
    """Extrait les métadonnées du document depuis la hiérarchie et les chunks (méthode legacy).

    Args:
        hierarchy: Structure hiérarchique du document (DocumentHierarchy).
        chunks: Liste des chunks aplatis.
        doc_name: Nom du document.

    Returns:
        Dictionnaire de métadonnées au format LegacyMetadata.
    """
    import re

    metadata: LegacyMetadata = {
        "title": None,
        "author": None,
        "work": doc_name,
        "chunks_count": len(chunks),
        "toc": [],
    }

    sections: List[HierarchyNode] = hierarchy.get("sections", [])
    if sections:
        first_section: HierarchyNode = sections[0]
        metadata["title"] = first_section.get("title")

    def _extract_toc_entries(
        sections: List[HierarchyNode],
        level: int = 0,
    ) -> List[SimpleTOCEntry]:
        """Extract simple TOC entries from hierarchy nodes."""
        toc_items: List[SimpleTOCEntry] = []
        for section in sections:
            section_level: int = section.get("level", 1)
            if section_level <= 2:
                toc_items.append({
                    "title": section.get("title") or "Sans titre",
                    "level": section_level,
                })
            children: List[HierarchyNode] = section.get("children", [])
            if children:
                toc_items.extend(_extract_toc_entries(children, level + 1))
        return toc_items

    metadata["toc"] = _extract_toc_entries(sections)

    preamble: str = hierarchy.get("preamble", "")
    author_patterns: List[str] = [
        r"(?:par|by|auteur|author)[:\s]+([A-ZÀ-Ü][a-zà-ü]+(?:\s+[A-ZÀ-Ü][a-zà-ü]+)*)",
        r"([A-ZÀ-Ü][a-zà-ü]+(?:\s+[A-ZÀ-Ü][a-zà-ü]+)*)\s*[-–—]\s*(?:auteur|author)",
    ]

    for pattern in author_patterns:
        match = re.search(pattern, preamble, re.IGNORECASE)
        if match:
            metadata["author"] = match.group(1).strip()
            break

    return metadata


def process_pdf_v2(
    pdf_path: Path,
    output_dir: Path = Path("output"),
    *,
    document_name: Optional[str] = None,
    api_key: Optional[str] = None,
    use_llm: bool = True,
    llm_provider: LLMProvider = "ollama",
    llm_model: Optional[str] = None,
    llm_base_url: Optional[str] = None,
    llm_temperature: float = 0.2,
    embed_images: bool = False,
    ingest_to_weaviate: bool = True,
    clean_chunks: bool = True,
    extract_concepts: bool = True,
    validate_output: bool = True,
    skip_ocr: bool = False,
    use_ocr_annotations: bool = False,
    max_toc_pages: int = 8,
    use_semantic_chunking: bool = False,
    progress_callback: OptionalProgressCallback = None,
) -> V2PipelineResult:
    """Process a PDF document through the intelligent V2 pipeline with LLM extraction.

    This is the main entry point for processing philosophical and academic PDF documents.
    The pipeline performs OCR, LLM-based metadata/TOC extraction, semantic chunking,
    and optional Weaviate ingestion for semantic search.

    The 10 processing steps are:
        1. OCR via Mistral API (unless skip_ocr=True)
        2. Markdown construction from OCR output
        3. Image extraction to disk (or base64 embedding)
        4. Metadata extraction via LLM (title, author, year, language)
        5. TOC extraction via LLM or OCR annotations
        6. Section classification via LLM (main_content, exposition, etc.)
        7. Semantic chunking via LLM (argumentative units)
        8. Chunk cleaning (remove OCR artifacts, validate quality)
        9. Validation and concept enrichment via LLM
        10. Weaviate ingestion (vectorization and storage)

    Args:
        pdf_path: Path to the PDF file to process. Must exist and be readable.
        output_dir: Base output directory. A subdirectory named after the document
            will be created. Defaults to "output".
        document_name: Override the document name (derived from filename if None).
        api_key: Mistral API key for OCR. If None, uses MISTRAL_API_KEY env var.
        use_llm: Enable LLM processing steps (metadata, TOC, classification,
            chunking, validation). Set to False for basic processing only.
        llm_provider: LLM provider to use. "ollama" for local (free, slower) or
            "mistral" for API (fast, paid). Defaults to "ollama".
        llm_model: Specific model name. If None, uses provider default
            (e.g., "qwen2.5:7b" for Ollama, "mistral-small" for Mistral).
        llm_base_url: Base URL for Ollama server. Defaults to "http://localhost:11434".
        llm_temperature: LLM sampling temperature. Lower values (0.1-0.3) produce
            more deterministic output. Defaults to 0.2.
        embed_images: If True, embed images as base64 in markdown. If False,
            save images to disk. Defaults to False.
        ingest_to_weaviate: Insert processed chunks into Weaviate vector database
            for semantic search. Requires Weaviate to be running. Defaults to True.
        clean_chunks: Apply chunk cleaning to remove OCR artifacts and validate
            minimum quality thresholds. Defaults to True.
        extract_concepts: Extract philosophical/academic concepts from chunks
            using LLM. Adds concept keywords for search. Defaults to True.
        validate_output: Run final LLM validation on the processed document.
            Checks metadata accuracy and suggests corrections. Defaults to True.
        skip_ocr: Skip OCR step and reuse existing markdown file from previous run.
            Useful for re-processing without incurring OCR costs. Defaults to False.
        use_ocr_annotations: Use OCR with annotations for more reliable TOC extraction.
            Costs approximately 3x more than standard OCR. Defaults to False.
        max_toc_pages: Maximum number of pages to analyze for TOC extraction.
            Mistral API limits to 8 pages maximum. Defaults to 8.
        use_semantic_chunking: Use LLM-based semantic chunking instead of basic
            paragraph splitting. Slower but produces higher quality argumentative
            units. Defaults to False.
        progress_callback: Optional callback function for progress updates.
            Signature: ``callback(step_id: str, status: str, detail: str | None)``.
            step_id values: ocr, markdown, metadata, toc, classify, chunking,
            cleaning, validation, weaviate.
            status values: active, completed, error, skipped.

    Returns:
        V2PipelineResult dictionary containing:
            - success (bool): Whether processing completed successfully.
            - document_name (str): Name of the processed document.
            - output_dir (str): Path to the output directory.
            - files (dict): Paths to generated files (markdown, chunks, ocr, weaviate).
            - pages (int): Number of pages in the PDF.
            - cost_ocr (float): OCR cost in euros.
            - cost_llm (float): LLM cost in euros (Mistral API only).
            - cost_total (float): Total processing cost.
            - llm_stats (dict | None): Detailed LLM usage statistics.
            - metadata (dict): Extracted document metadata.
            - toc (list): Hierarchical table of contents.
            - chunks_count (int): Number of chunks generated.
            - validation (dict | None): Validation results if enabled.
            - weaviate_ingest (dict | None): Weaviate ingestion results.
            - pipeline_version (str): Always "2.0" for this pipeline.
            - error (str): Error message if success is False.

    Raises:
        FileNotFoundError: If pdf_path does not exist and skip_ocr is False.
        ValueError: If skip_ocr is True but no cached markdown exists.

    Example:
        Basic processing with Ollama::

            from pathlib import Path
            from utils.pdf_pipeline import process_pdf_v2

            result = process_pdf_v2(
                Path("input/plato_republic.pdf"),
                use_llm=True,
                llm_provider="ollama",
            )

            if result["success"]:
                print(f"Processed {result['chunks_count']} chunks")
                print(f"Title: {result['metadata'].get('title')}")

        Production processing with Mistral API::

            result = process_pdf_v2(
                Path("input/kant_critique.pdf"),
                llm_provider="mistral",
                use_semantic_chunking=True,
                use_ocr_annotations=True,
            )
            print(f"Total cost: {result['cost_total']:.4f} EUR")

    Note:
        Cost implications:
            - OCR: ~0.003 EUR/page (standard), ~0.009 EUR/page (with annotations)
            - LLM (Mistral API): Variable based on token usage
            - LLM (Ollama): Free (local processing)

        Use ``skip_ocr=True`` when re-processing to avoid OCR costs.
        The function will reuse the existing markdown file.
    """
    pdf_path = Path(pdf_path).resolve()

    # Detect file type by extension
    file_ext: str = pdf_path.suffix.lower()
    is_markdown_file: bool = file_ext == ".md"
    
    doc_name: str = document_name or pdf_path.stem
    if doc_name.lower().endswith(".pdf"):
        doc_name = doc_name[:-4]
    elif doc_name.lower().endswith(".md"):
        doc_name = doc_name[:-3]

    doc_output_dir: Path = Path(output_dir).resolve() / doc_name
    doc_output_dir.mkdir(parents=True, exist_ok=True)

    # Chemins des fichiers de sortie
    md_path: Path = doc_output_dir / f"{doc_name}.md"
    chunks_path: Path = doc_output_dir / f"{doc_name}_chunks.json"
    ocr_path: Path = doc_output_dir / f"{doc_name}_ocr.json"
    images_dir: Path = doc_output_dir / "images"
    
    logger.info(f"[V2] Traitement de : {pdf_path}")
    logger.info(f"[V2] Sortie dans : {doc_output_dir}")
    
    # Helper pour émettre la progression
    def emit_progress(step: str, status: str, detail: Optional[str] = None) -> None:
        if progress_callback:
            try:
                progress_callback(step, status, detail)
            except Exception:
                pass
    
    try:
        # ═══════════════════════════════════════════════════════════════════
        # ÉTAPE 1-4 : OCR et Markdown (sauf si skip_ocr)
        # ═══════════════════════════════════════════════════════════════════

        nb_pages: int = 0
        cost: float = 0.0  # Coût OCR (0 si skip_ocr)

        # Réinitialiser le compteur de coût LLM pour ce document
        if llm_provider == "mistral":
            reset_llm_cost()

        if is_markdown_file:
            # Mode Markdown natif : charger directement le fichier .md
            emit_progress("ocr", "active", "Chargement Markdown...")
            
            if not pdf_path.is_file():
                emit_progress("ocr", "error", "Fichier Markdown introuvable")
                return {
                    "success": False,
                    "error": f"Fichier Markdown introuvable : {pdf_path}",
                }
            
            logger.info("[1-4/10] 📝 Chargement direct du fichier Markdown (pas d'OCR)")
            markdown_text: str = pdf_path.read_text(encoding="utf-8")
            
            # Copier le contenu vers le répertoire de sortie
            md_path.write_text(markdown_text, encoding="utf-8")
            
            # Estimer le nombre de "pages" à partir des en-têtes H1
            h1_count = markdown_text.count("\n# ") + (1 if markdown_text.startswith("# ") else 0)
            nb_pages = max(h1_count, 1)  # Au moins 1 "page"
            
            emit_progress("ocr", "skipped", f"Markdown (0.00€)")
            emit_progress("markdown", "completed", f"{nb_pages} sections détectées")
            logger.info(f"Fichier Markdown chargé directement ({nb_pages} sections H1 détectées)")
        elif skip_ocr:
            # Mode test : réutiliser le markdown existant
            emit_progress("ocr", "active", "Vérification du cache...")

            if not md_path.exists():
                emit_progress("ocr", "error", "Fichier non trouvé")
                return {
                    "success": False,
                    "error": f"Mode skip_ocr activé mais fichier non trouvé : {md_path}",
                }

            logger.info("[1-4/10] ⚡ Skip OCR - Réutilisation du markdown existant")
            markdown_text = md_path.read_text(encoding="utf-8")
            
            # Essayer de récupérer le nombre de pages depuis l'OCR existant
            if ocr_path.exists():
                try:
                    ocr_data = json.loads(ocr_path.read_text(encoding="utf-8"))
                    nb_pages = len(ocr_data.get("pages", []))
                except Exception:
                    nb_pages = markdown_text.count("<!-- Page")
            else:
                nb_pages = markdown_text.count("<!-- Page")
            
            emit_progress("ocr", "skipped", f"{nb_pages} pages (cache)")
            emit_progress("markdown", "skipped", "Réutilisation")
            logger.info(f"Markdown existant chargé ({nb_pages} pages détectées)")
        else:
            # Mode normal : OCR via Mistral
            if not pdf_path.is_file():
                emit_progress("ocr", "error", "PDF introuvable")
                return {
                    "success": False,
                    "error": f"Fichier PDF introuvable : {pdf_path}",
                }
            
            emit_progress("ocr", "active", "Connexion à Mistral...")
            logger.info("[1/10] Connexion à Mistral...")
            client: Any = create_client(api_key)  # Mistral client

            pdf_bytes: bytes = pdf_path.read_bytes()

            emit_progress("ocr", "active", "OCR en cours...")
            logger.info("[2/10] OCR en cours...")
            # Step 1: OCR processing - returns Mistral OCR response (Pydantic model)
            ocr_response: Any = run_ocr(client, pdf_bytes, pdf_path.name, include_images=True)
            
            nb_pages = len(ocr_response.pages)
            cost = estimate_ocr_cost(nb_pages)
            emit_progress("ocr", "completed", f"{nb_pages} pages ({cost:.4f}€)")
            logger.info(f"OCR terminé : {nb_pages} pages (coût estimé : {cost:.4f}€)")
            
            # Sauvegarder OCR brut
            ocr_json: Dict[str, Any] = serialize_ocr_response(ocr_response)
            ocr_path.write_text(json.dumps(ocr_json, ensure_ascii=False, indent=2), encoding="utf-8")

            # Step 3: Image extraction
            emit_progress("markdown", "active", "Construction du markdown...")
            image_writer: Optional[Callable[[int, int, str], Optional[str]]] = None
            if not embed_images:
                logger.info("[3/10] Extraction des images...")
                images_dir.mkdir(parents=True, exist_ok=True)
                image_writer = create_image_writer(images_dir)

            # Step 4: Markdown building - input: OCR response, output: str
            logger.info("[4/10] Construction du Markdown...")
            markdown_text = build_markdown(ocr_response, embed_images=embed_images, image_writer=image_writer)
            md_path.write_text(markdown_text, encoding="utf-8")
            emit_progress("markdown", "completed", "Document généré")
        
        # Analyse hiérarchique basique (fallback)
        hierarchy: DocumentHierarchy = build_hierarchy(markdown_text)
        basic_chunks: List[FlatChunk] = flatten_hierarchy(hierarchy)

        # ═══════════════════════════════════════════════════════════════════
        # ÉTAPE 5 : Extraction métadonnées via LLM
        # ═══════════════════════════════════════════════════════════════════

        # Step 5: Metadata extraction - input: markdown str, output: Dict[str, Any]
        emit_progress("metadata", "active", "Analyse du document...")
        metadata: Dict[str, Any]
        if use_llm:
            logger.info(f"[5/10] Extraction métadonnées via {llm_provider.upper()}...")
            metadata = extract_metadata(markdown_text, model=llm_model, provider=llm_provider, temperature=llm_temperature)
        else:
            logger.info("[5/10] Extraction métadonnées (mode basique)...")
            metadata = cast(Dict[str, Any], extract_document_metadata_legacy(hierarchy, cast(List[Dict[str, Any]], basic_chunks), doc_name))

        # Compléter les métadonnées
        metadata["work"] = metadata.get("title") or doc_name
        metadata["chunks_count"] = 0  # Sera mis à jour plus tard
        title_str = metadata.get("title") or "Métadonnées extraites"
        emit_progress("metadata", "completed", title_str[:50])

        # ═══════════════════════════════════════════════════════════════════
        # ÉTAPE 6 : Extraction TOC via LLM ou Annotations OCR
        # ═══════════════════════════════════════════════════════════════════

        # Step 6: TOC extraction - input: markdown str, output: List[Dict[str, Any]]
        emit_progress("toc", "active", "Extraction de la structure...")
        toc: List[Dict[str, Any]] = []
        flat_toc: List[Dict[str, Any]] = []

        # Branche 1 : OCR avec annotations (analyse markdown pour détecter indentation)
        toc_result: Dict[str, Any]
        if use_ocr_annotations:
            logger.info(f"[6/10] Extraction TOC via analyse markdown (indentation)...")
            emit_progress("toc", "active", "Analyse indentation TOC...")

            from .toc_extractor_markdown import extract_toc_from_markdown, MarkdownTOCResult

            toc_result_typed: MarkdownTOCResult = extract_toc_from_markdown(
                markdown_text,
                max_lines=300,
            )
            toc_result = cast(Dict[str, Any], toc_result_typed)

            if toc_result.get("success"):
                # Succès : utiliser les annotations
                metadata_annotated: Dict[str, Any] = toc_result["metadata"]
                toc = toc_result["toc"]
                flat_toc = toc_result["toc_flat"]
                cost += toc_result["cost_ocr_annotated"]
                
                # Enrichir les métadonnées existantes
                metadata.update({
                    "title": metadata_annotated.get("title", metadata.get("title")),
                    "author": metadata_annotated.get("author", metadata.get("author")),
                    "languages": metadata_annotated.get("languages", []),
                    "summary": metadata_annotated.get("summary", ""),
                    "collection": metadata_annotated.get("collection"),
                    "publisher": metadata_annotated.get("publisher"),
                    "year": metadata_annotated.get("year"),
                })
                
                emit_progress("toc", "completed", f"{len(flat_toc)} entrées (annotations, +{toc_result['cost_ocr_annotated']:.4f}€)")
                logger.info(f"TOC extraite via annotations : {len(flat_toc)} entrées (coût : +{toc_result['cost_ocr_annotated']:.4f}€)")
            else:
                # Échec : fallback sur extraction LLM classique
                error_msg = toc_result.get("error", "Erreur inconnue")
                logger.warning(f"Échec annotations OCR ({error_msg}), fallback sur LLM...")
                emit_progress("toc", "active", f"Fallback LLM après échec annotations...")
                
                if use_llm:
                    toc_result = extract_toc(markdown_text, document_title=metadata.get("title"), model=llm_model, provider=llm_provider)
                    toc = toc_result.get("toc", [])
                    flat_toc = toc_result.get("flat_toc", [])
                else:
                    toc = metadata.get("toc", [])
                    flat_toc = toc
                
                emit_progress("toc", "completed", f"{len(flat_toc)} entrées (fallback LLM)")
        
        # Branche 2 : Extraction LLM classique (moins fiable mais moins cher)
        elif use_llm:
            logger.info(f"[6/10] Extraction TOC via {llm_provider.upper()}...")
            toc_result = extract_toc(markdown_text, document_title=metadata.get("title"), model=llm_model, provider=llm_provider)
            toc = toc_result.get("toc", [])
            flat_toc = toc_result.get("flat_toc", [])
            emit_progress("toc", "completed", f"{len(flat_toc)} entrées (LLM)")
        
        # Branche 3 : Mode basique (sans LLM ni annotations)
        else:
            logger.info("[6/10] Extraction TOC (mode basique)...")
            toc = metadata.get("toc", [])
            flat_toc = toc
            emit_progress("toc", "completed", f"{len(flat_toc)} entrées (basique)")
        
        metadata["toc"] = toc
        
        # ═══════════════════════════════════════════════════════════════════
        # ÉTAPE 7 : Aplatir la hiérarchie et classifier les sections
        # ═══════════════════════════════════════════════════════════════════
        
        # Aplatir TOUTE la hiérarchie (inclut les sous-sections avec contenu)
        def flatten_all_sections(
            sections: List[HierarchyNode],
            parent_title: Optional[str] = None,
            parent_chapter: Optional[str] = None,
        ) -> List[FlatSection]:
            """Aplatit récursivement toutes les sections avec leur contenu."""
            result: List[FlatSection] = []
            for section in sections:
                title: str = section.get("title") or ""
                content: str = section.get("content") or ""
                level: int = section.get("level", 1)

                # Déterminer le chapitre parent
                chapter_title: Optional[str] = parent_chapter
                if level == 1:
                    chapter_title = title
                elif level == 2 and parent_title:
                    chapter_title = parent_title

                # Ajouter cette section avec son contenu
                flat_section: FlatSection = {
                    "title": title,
                    "content": content,
                    "level": level,
                    "chapter_title": chapter_title,
                    "parent_title": parent_title,
                }
                result.append(flat_section)

                # Récursion sur les enfants
                children: List[HierarchyNode] = section.get("children", [])
                if children:
                    result.extend(flatten_all_sections(children, title, chapter_title))

            return result
        
        # Aplatir toutes les sections
        all_sections: List[FlatSection] = flatten_all_sections(hierarchy.get("sections", []))
        logger.info(f"Sections aplaties: {len(all_sections)} sections trouvées")

        # Préparer pour classification (seulement celles avec contenu significatif)
        sections_for_classification: List[FlatSection] = [
            s for s in all_sections
            if s.get("content") and len(s["content"].strip()) > 30
        ]

        # Step 7: Section classification - input: sections, output: classified sections
        emit_progress("classify", "active", f"Analyse de {len(sections_for_classification)} sections...")
        classified_sections: List[Dict[str, Any]]
        indexable_sections: List[Dict[str, Any]]
        if use_llm and sections_for_classification:
            logger.info(f"[7/10] Classification des sections via {llm_provider.upper()}...")
            classified_sections = classify_sections(
                cast(List[Dict[str, Any]], sections_for_classification),
                document_title=metadata.get("title"),
                model=llm_model,
                provider=llm_provider,
            )
            # Double validation pour détecter les faux positifs (morceaux de TOC)
            from .llm_classifier import validate_classified_sections
            classified_sections = validate_classified_sections(classified_sections)
            indexable_sections = filter_indexable_sections(classified_sections)
        else:
            logger.info("[7/10] Classification (mode basique)...")
            classified_sections = cast(List[Dict[str, Any]], sections_for_classification)
            # Par défaut, tout est indexable sauf les sections vides
            indexable_sections = cast(List[Dict[str, Any]], [s for s in sections_for_classification if s.get("content")])

        emit_progress("classify", "completed", f"{len(indexable_sections)} sections indexables")
        logger.info(f"Sections indexables: {len(indexable_sections)} sections")

        # ═══════════════════════════════════════════════════════════════════
        # ÉTAPE 8 : Chunking sémantique via LLM
        # ═══════════════════════════════════════════════════════════════════

        # Step 8: Chunking - input: sections, output: List[SemanticChunk]
        all_chunks: List[SemanticChunk] = []
        chunk_index: int = 0
        
        emit_progress("chunking", "active", "Découpage sémantique..." if use_semantic_chunking else "Découpage basique...")
        if use_llm and use_semantic_chunking:
            logger.info("[8/10] Chunking sémantique via LLM...")
            
            for section in indexable_sections:
                section_title = section.get("title", "")
                section_content = section.get("content", "")
                section_level = section.get("level", 1)
                chapter_title = section.get("chapter_title", section_title)
                
                # Déterminer le sous-chapitre (niveau 2) si on est niveau 3+
                subsection_title = None
                if section_level >= 2:
                    subsection_title = section.get("parent_title") or section_title
                
                # Seuil plus bas pour inclure plus de contenu
                if not section_content or len(section_content.strip()) < 30:
                    continue
                
                # Chunker la section avec hiérarchie complète
                section_chunks = chunk_section_with_llm(
                    section_content,
                    section_title,
                    chapter_title=chapter_title,
                    subsection_title=subsection_title,
                    section_level=section_level,
                    model=llm_model,
                    provider=llm_provider,
                    temperature=llm_temperature,
                )
                
                # Ajouter les métadonnées à chaque chunk
                for chunk in section_chunks:
                    # Cast to Dict for modification
                    chunk_dict = cast(Dict[str, Any], chunk)
                    chunk_dict["chunk_id"] = f"chunk_{chunk_index:05d}"
                    chunk_dict["section"] = section_title
                    chunk_dict["section_level"] = section_level
                    chunk_dict["chapter_title"] = chapter_title

                    # Ajouter le sous-chapitre si différent
                    if subsection_title and subsection_title != chapter_title:
                        chunk_dict["subsection_title"] = subsection_title

                    chunk_index += 1
                    all_chunks.append(cast(SemanticChunk, chunk_dict))
        else:
            logger.info("[8/10] Chunking (mode basique)...")
            # Utiliser les chunks basiques
            for i, flat_chunk in enumerate(basic_chunks):
                chunk_dict = cast(Dict[str, Any], flat_chunk)
                basic_semantic_chunk: SemanticChunk = cast(SemanticChunk, {
                    "chunk_id": f"chunk_{i:05d}",
                    "text": chunk_dict.get("text", ""),
                    "section": chunk_dict.get("title", f"Section {i}"),
                    "section_level": chunk_dict.get("level", 1),
                    "type": chunk_dict.get("type", "main_content"),
                    "concepts": [],
                })
                all_chunks.append(basic_semantic_chunk)
        
        # ═══════════════════════════════════════════════════════════════════
        # ÉTAPE 9 : Nettoyage des chunks
        # ═══════════════════════════════════════════════════════════════════
        
        emit_progress("chunking", "completed", f"{len(all_chunks)} chunks générés")
        emit_progress("cleaning", "active", "Nettoyage des artefacts...")
        logger.info("[9/10] Nettoyage et filtrage des chunks...")
        
        # Step 9: Cleaning - input: chunks, output: List[SemanticChunk]
        cleaned_chunks: List[SemanticChunk] = []
        for chunk in all_chunks:
            # Nettoyer le texte
            chunk_dict = cast(Dict[str, Any], chunk)
            text: str = chunk_dict.get("text", "")
            if clean_chunks and use_llm:
                text = clean_chunk(text, use_llm=False)  # Nettoyage basique rapide
            else:
                text = clean_chunk(text, use_llm=False)

            # Vérifier validité
            if is_chunk_valid(text, min_chars=30, min_words=8):
                chunk_dict["text"] = text
                cleaned_chunks.append(cast(SemanticChunk, chunk_dict))
        
        emit_progress("cleaning", "completed", f"{len(cleaned_chunks)} chunks valides")
        logger.info(f"Chunks après nettoyage: {len(cleaned_chunks)} (sur {len(all_chunks)})")
        
        # Extraire concepts si demandé
        if extract_concepts and use_llm and cleaned_chunks:
            logger.info(f"Enrichissement avec concepts via {llm_provider.upper()}...")
            enriched = enrich_chunks_with_concepts(cast(List[Dict[str, Any]], cleaned_chunks[:50]), model=llm_model, provider=llm_provider)  # Limiter
            cleaned_chunks = cast(List[SemanticChunk], enriched)
        
        metadata["chunks_count"] = len(cleaned_chunks)
        
        # ═══════════════════════════════════════════════════════════════════
        # ÉTAPE 10 : Validation finale
        # ═══════════════════════════════════════════════════════════════════
        
        # Step 10: Validation - input: parsed doc, output: ValidationResult
        emit_progress("validation", "active", "Vérification de la qualité...")
        validation_result: Optional[ValidationResult] = None
        parsed_doc: Dict[str, Any] = {
            "metadata": metadata,
            "toc": toc,
            "chunks": cleaned_chunks,
        }
        
        if validate_output and use_llm:
            logger.info("[10/10] Validation du document...")
            validation_result = validate_document(parsed_doc, model=llm_model, provider=llm_provider)

            # Appliquer les corrections (ou nettoyer les métadonnées)
            parsed_doc = apply_corrections(parsed_doc, cast(Dict[str, Any], validation_result))
            metadata = parsed_doc.get("metadata", metadata)
            emit_progress("validation", "completed", "Qualité vérifiée")
        else:
            logger.info("[10/10] Validation (ignorée)...")
            # Nettoyer quand même les métadonnées (titre, auteur)
            parsed_doc = apply_corrections(parsed_doc, None)
            metadata = parsed_doc.get("metadata", metadata)
            emit_progress("validation", "skipped", "Non activée")
        
        # ═══════════════════════════════════════════════════════════════════
        # Sauvegarder les résultats
        # ═══════════════════════════════════════════════════════════════════
        
        # Export data structure
        chunks_data: Dict[str, Any] = {
            "document": doc_name,
            "pages": nb_pages,
            "metadata": metadata,
            "toc": toc,
            "flat_toc": flat_toc if use_llm else [],
            "hierarchy": hierarchy,
            "classified_sections": classified_sections if use_llm else [],
            "chunks": cleaned_chunks,
            "validation": validation_result,
            "pipeline_version": "2.0",
        }
        
        chunks_path.write_text(json.dumps(chunks_data, ensure_ascii=False, indent=2), encoding="utf-8")
        
        # ═══════════════════════════════════════════════════════════════════
        # Ingestion Weaviate
        # ═══════════════════════════════════════════════════════════════════
        
        # Weaviate ingestion step
        weaviate_result: Optional[WeaviateIngestResult] = None
        if ingest_to_weaviate:
            emit_progress("weaviate", "active", "Vectorisation et stockage...")
            logger.info("Ingestion dans Weaviate...")
            weaviate_result = ingest_document(
                doc_name=doc_name,
                chunks=cast(List[Dict[str, Any]], cleaned_chunks),
                metadata=metadata,
                language=metadata.get("language", "fr"),
            )
            
            if weaviate_result.get("success"):
                emit_progress("weaviate", "completed", f"{weaviate_result.get('count', 0)} passages insérés")
                logger.info(f"Ingestion terminée: {weaviate_result.get('count', 0)} passages")
                weaviate_path = doc_output_dir / f"{doc_name}_weaviate.json"
                weaviate_path.write_text(json.dumps(weaviate_result, ensure_ascii=False, indent=2), encoding="utf-8")
            else:
                emit_progress("weaviate", "error", weaviate_result.get('error', 'Erreur'))
                logger.warning(f"Erreur ingestion: {weaviate_result.get('error')}")
        else:
            emit_progress("weaviate", "skipped", "Non activée")
        
        # Résultat final - file paths
        files_dict: Dict[str, Any] = {
            "markdown": str(md_path),
            "chunks": str(chunks_path),
            "ocr": str(ocr_path),
        }

        if weaviate_result and weaviate_result.get("success"):
            files_dict["weaviate"] = str(doc_output_dir / f"{doc_name}_weaviate.json")

        if not embed_images and images_dir.exists():
            image_files: List[Path] = list(images_dir.glob("*.png"))
            files_dict["images"] = [str(f) for f in image_files]
            files_dict["images_dir"] = str(images_dir)

        files: V2PipelineFiles = cast(V2PipelineFiles, files_dict)

        # Récupérer le coût LLM si Mistral API utilisée
        llm_cost_stats: Optional[LLMCostStats] = get_llm_cost() if llm_provider == "mistral" else None
        total_cost: float = cost  # Coût OCR
        if llm_cost_stats:
            total_cost += llm_cost_stats["total_cost"]
            logger.info(f"Coût LLM Mistral: {llm_cost_stats['total_cost']:.4f}€ ({llm_cost_stats['calls_count']} appels)")
        
        logger.info(f"[V2] Traitement terminé : {doc_name} - Coût total: {total_cost:.4f}€")
        
        return {
            "success": True,
            "document_name": doc_name,
            "output_dir": str(doc_output_dir),
            "files": files,
            "pages": nb_pages,
            "cost_ocr": cost,
            "cost_llm": llm_cost_stats["total_cost"] if llm_cost_stats else 0.0,
            "cost_total": total_cost,
            "llm_stats": llm_cost_stats,
            "metadata": metadata,
            "toc": toc,
            "chunks_count": len(cleaned_chunks),
            "validation": validation_result,
            "weaviate_ingest": weaviate_result,
            "pipeline_version": "2.0",
        }
        
    except Exception as e:
        logger.error(f"Erreur : {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "document_name": doc_name,
            "output_dir": str(doc_output_dir),
            "error": str(e),
            "pipeline_version": "2.0",
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Fonctions legacy pour compatibilité
# ═══════════════════════════════════════════════════════════════════════════════

# Alias pour la fonction legacy
extract_document_metadata = extract_document_metadata_legacy


def process_pdf(
    pdf_path: Path,
    output_dir: Path = Path("output"),
    *,
    document_name: Optional[str] = None,
    api_key: Optional[str] = None,
    use_llm: bool = True,
    llm_provider: LLMProvider = "ollama",
    llm_model: Optional[str] = None,
    llm_base_url: Optional[str] = None,
    llm_temperature: float = 0.2,
    llm_max_chars: int = 8000,
    llm_timeout: int = 300,
    embed_images: bool = False,
    ingest_to_weaviate: bool = True,
    use_v2_pipeline: bool = True,
    skip_ocr: bool = False,
    use_ocr_annotations: bool = False,
    max_toc_pages: int = 8,
    use_semantic_chunking: bool = False,
    progress_callback: OptionalProgressCallback = None,
) -> Union[V2PipelineResult, V1PipelineResult]:
    """Main entry point for PDF processing pipeline.

    This is the unified API for processing philosophical and academic PDF documents.
    By default, it uses the V2 pipeline with intelligent LLM-based extraction.
    The V1 pipeline is available for backwards compatibility via use_v2_pipeline=False.

    The function automatically selects the appropriate pipeline version and delegates
    to either process_pdf_v2() or _process_pdf_v1() based on the use_v2_pipeline flag.

    Args:
        pdf_path: Path to the PDF file to process. Must exist and be readable.
        output_dir: Base output directory. A subdirectory named after the document
            will be created for all output files. Defaults to "output".
        document_name: Override the document name used for output files. If None,
            the name is derived from the PDF filename (stem).
        api_key: Mistral API key for OCR. If None, reads from MISTRAL_API_KEY
            environment variable.
        use_llm: Enable LLM processing for metadata extraction, TOC extraction,
            section classification, chunking, and validation. Set to False for
            basic processing without LLM intelligence. Defaults to True.
        llm_provider: LLM provider to use for intelligent processing.
            "ollama" uses a local Ollama server (free, slower).
            "mistral" uses the Mistral API (paid, faster).
            Defaults to "ollama".
        llm_model: Specific model name to use. If None, uses provider defaults:
            - Ollama: "qwen2.5:7b"
            - Mistral: "mistral-small"
        llm_base_url: Base URL for Ollama server. Only used when llm_provider="ollama".
            Defaults to "http://localhost:11434".
        llm_temperature: Sampling temperature for LLM calls. Lower values (0.1-0.3)
            produce more deterministic, focused output. Defaults to 0.2.
        llm_max_chars: Maximum characters to send to LLM per call. V1 pipeline only.
            Defaults to 8000.
        llm_timeout: Timeout in seconds for LLM calls. V1 pipeline only.
            Defaults to 300.
        embed_images: If True, embed images as base64 data URIs in the markdown.
            If False, save images as separate files in an images/ subdirectory.
            Defaults to False.
        ingest_to_weaviate: Insert processed chunks into the Weaviate vector database
            for semantic search. Requires Weaviate to be running locally via Docker.
            Defaults to True.
        use_v2_pipeline: Use the V2 pipeline with intelligent processing. Set to False
            to use the legacy V1 pipeline. Defaults to True.
        skip_ocr: Skip OCR and reuse existing markdown from a previous run.
            Useful for re-processing without incurring additional OCR costs.
            The markdown file must exist at output/<doc_name>/<doc_name>.md.
            V2 pipeline only. Defaults to False.
        use_ocr_annotations: Use OCR with annotations for more reliable TOC extraction.
            Annotations provide visual structure hints but cost approximately 3x more
            than standard OCR (~0.009 EUR/page vs ~0.003 EUR/page).
            V2 pipeline only. Defaults to False.
        max_toc_pages: Maximum number of pages to analyze for TOC extraction.
            Mistral API limits annotations to 8 pages maximum.
            V2 pipeline only. Defaults to 8.
        use_semantic_chunking: Use LLM-based semantic chunking to identify
            argumentative units. More accurate but slower than paragraph-based splitting.
            V2 pipeline only. Defaults to False.
        progress_callback: Optional callback function for real-time progress updates.
            Signature: ``callback(step_id: str, status: str, detail: str | None)``.
            step_id values: ocr, markdown, metadata, toc, classify, chunking,
            cleaning, validation, weaviate.
            status values: active, completed, error, skipped.
            V2 pipeline only.

    Returns:
        Dictionary containing processing results. The exact structure depends on
        the pipeline version used:

        V2 Pipeline (use_v2_pipeline=True) returns V2PipelineResult:
            - success (bool): Whether processing completed successfully.
            - document_name (str): Name of the processed document.
            - output_dir (str): Path to the output directory.
            - files (dict): Paths to generated files.
            - pages (int): Number of pages in the PDF.
            - cost_ocr (float): OCR cost in euros.
            - cost_llm (float): LLM cost in euros.
            - cost_total (float): Total processing cost.
            - metadata (dict): Extracted document metadata.
            - toc (list): Hierarchical table of contents.
            - chunks_count (int): Number of chunks generated.
            - validation (dict | None): Validation results.
            - weaviate_ingest (dict | None): Weaviate ingestion results.
            - pipeline_version (str): "2.0"
            - error (str): Error message if success is False.

        V1 Pipeline (use_v2_pipeline=False) returns V1PipelineResult:
            - success (bool): Whether processing completed successfully.
            - document_name (str): Name of the processed document.
            - output_dir (str): Path to the output directory.
            - files (dict): Paths to generated files.
            - pages (int): Number of pages in the PDF.
            - cost (float): OCR cost in euros.
            - metadata (dict): Extracted document metadata.
            - chunks_count (int): Number of chunks generated.
            - weaviate_ingest (dict | None): Weaviate ingestion results.
            - pipeline_version (str): "1.0"
            - error (str): Error message if success is False.

    Raises:
        FileNotFoundError: If pdf_path does not exist (and skip_ocr is False).
        ValueError: If skip_ocr is True but no cached markdown exists.

    Example:
        Basic processing with local Ollama::

            from pathlib import Path
            from utils.pdf_pipeline import process_pdf

            result = process_pdf(
                Path("input/philosophy_book.pdf"),
                use_llm=True,
                llm_provider="ollama",
            )

            if result["success"]:
                print(f"Processed: {result['document_name']}")
                print(f"Chunks: {result['chunks_count']}")

        Production processing with Mistral API::

            result = process_pdf(
                Path("input/kant_critique.pdf"),
                llm_provider="mistral",
                use_semantic_chunking=True,
                use_ocr_annotations=True,
                ingest_to_weaviate=True,
            )

            print(f"OCR cost: {result['cost_ocr']:.4f} EUR")
            print(f"LLM cost: {result['cost_llm']:.4f} EUR")
            print(f"Total: {result['cost_total']:.4f} EUR")

        Re-processing without OCR cost::

            result = process_pdf(
                Path("input/existing_document.pdf"),
                skip_ocr=True,  # Reuse cached markdown
                use_semantic_chunking=True,
            )

        Legacy V1 pipeline::

            result = process_pdf(
                Path("input/document.pdf"),
                use_v2_pipeline=False,  # Use V1 pipeline
            )

    Note:
        **Cost Implications:**

        - OCR: ~0.003 EUR/page (standard), ~0.009 EUR/page (with annotations)
        - LLM (Mistral API): Variable based on token usage
        - LLM (Ollama): Free (local processing)

        Use ``skip_ocr=True`` when re-processing documents to avoid OCR costs.

        **Pipeline Comparison:**

        - V2 (default): Intelligent 10-step pipeline with LLM-based extraction.
          Better metadata, TOC, and semantic chunking. Recommended for production.
        - V1 (legacy): Basic pipeline with simple hierarchy parsing.
          Faster but less accurate. Kept for backwards compatibility.

    See Also:
        - :func:`process_pdf_v2`: Direct access to V2 pipeline.
        - :func:`process_pdf_bytes`: Process PDF from bytes (for Flask uploads).
        - :mod:`utils.types`: Type definitions for result dictionaries.
    """
    if use_v2_pipeline:
        return process_pdf_v2(
            pdf_path,
            output_dir,
            document_name=document_name,
            api_key=api_key,
            use_llm=use_llm,
            llm_provider=llm_provider,
            llm_model=llm_model,
            llm_base_url=llm_base_url,
            llm_temperature=llm_temperature,
            embed_images=embed_images,
            ingest_to_weaviate=ingest_to_weaviate,
            skip_ocr=skip_ocr,
            use_ocr_annotations=use_ocr_annotations,
            max_toc_pages=max_toc_pages,
            use_semantic_chunking=use_semantic_chunking,
            progress_callback=progress_callback,
        )
    else:
        # Pipeline V1 legacy
        return _process_pdf_v1(
            pdf_path,
            output_dir,
            document_name=document_name,
            api_key=api_key,
            use_llm=use_llm,
            llm_model=llm_model,
            llm_base_url=llm_base_url,
            llm_temperature=llm_temperature,
            llm_max_chars=llm_max_chars,
            llm_timeout=llm_timeout,
            embed_images=embed_images,
            ingest_to_weaviate=ingest_to_weaviate,
        )


def _process_pdf_v1(
    pdf_path: Path,
    output_dir: Path = Path("output"),
    *,
    document_name: Optional[str] = None,
    api_key: Optional[str] = None,
    use_llm: bool = True,
    llm_model: Optional[str] = None,
    llm_base_url: Optional[str] = None,
    llm_temperature: float = 0.2,
    llm_max_chars: int = 8000,
    llm_timeout: int = 300,
    embed_images: bool = False,
    ingest_to_weaviate: bool = True,
) -> V1PipelineResult:
    """Pipeline V1 (legacy) - gardé pour compatibilité.

    Args:
        pdf_path: Chemin du fichier PDF.
        output_dir: Dossier de sortie de base.
        document_name: Nom du document (optionnel).
        api_key: Clé API Mistral.
        use_llm: Activer les traitements LLM.
        llm_model: Modèle Ollama/Mistral.
        llm_base_url: URL Ollama.
        llm_temperature: Température LLM.
        llm_max_chars: Nombre maximum de caractères à traiter.
        llm_timeout: Timeout en secondes pour les appels LLM.
        embed_images: Intégrer images en base64.
        ingest_to_weaviate: Insérer dans Weaviate.

    Returns:
        Résultat du pipeline V1 au format V1PipelineResult.
    """
    pdf_path = Path(pdf_path).resolve()

    if not pdf_path.is_file():
        return {"success": False, "error": f"Fichier PDF introuvable : {pdf_path}"}

    # Detect file type by extension
    file_ext: str = pdf_path.suffix.lower()
    is_markdown_file: bool = file_ext == ".md"
    
    doc_name: str = document_name or pdf_path.stem
    if doc_name.lower().endswith(".pdf"):
        doc_name = doc_name[:-4]
    elif doc_name.lower().endswith(".md"):
        doc_name = doc_name[:-3]

    doc_output_dir: Path = Path(output_dir).resolve() / doc_name
    doc_output_dir.mkdir(parents=True, exist_ok=True)

    md_path: Path = doc_output_dir / f"{doc_name}.md"
    chunks_path: Path = doc_output_dir / f"{doc_name}_chunks.json"
    structured_path: Path = doc_output_dir / f"{doc_name}_structured.json"
    ocr_path: Path = doc_output_dir / f"{doc_name}_ocr.json"
    images_dir: Path = doc_output_dir / "images"

    logger.info(f"[V1] Traitement de : {pdf_path}")

    try:
        client = create_client(api_key)
        pdf_bytes: bytes = pdf_path.read_bytes()
        ocr_response = run_ocr(client, pdf_bytes, pdf_path.name, include_images=True)

        nb_pages: int = len(ocr_response.pages)
        cost: float = estimate_ocr_cost(nb_pages)
        
        ocr_json: Dict[str, Any] = serialize_ocr_response(ocr_response)
        ocr_path.write_text(json.dumps(ocr_json, ensure_ascii=False, indent=2), encoding="utf-8")

        if not embed_images:
            images_dir.mkdir(parents=True, exist_ok=True)
            image_writer = create_image_writer(images_dir)
        else:
            image_writer = None

        markdown_text: str = build_markdown(ocr_response, embed_images=embed_images, image_writer=image_writer)
        md_path.write_text(markdown_text, encoding="utf-8")

        hierarchy: DocumentHierarchy = build_hierarchy(markdown_text)
        chunks: List[Dict[str, Any]] = cast(List[Dict[str, Any]], flatten_hierarchy(hierarchy))
        metadata: LegacyMetadata = extract_document_metadata_legacy(hierarchy, chunks, doc_name)

        chunks_data: Dict[str, Any] = {
            "document": doc_name,
            "pages": nb_pages,
            "metadata": metadata,
            "hierarchy": hierarchy,
            "chunks": chunks,
            "pipeline_version": "1.0",
        }
        chunks_path.write_text(json.dumps(chunks_data, ensure_ascii=False, indent=2), encoding="utf-8")

        structured_data_typed: Optional[LLMStructuredResult] = None
        structured_data: Optional[Dict[str, Any]] = None
        if use_llm:
            try:
                structured_data_typed = structure_with_llm(
                    markdown_text, cast(Dict[str, Any], hierarchy),
                    model=llm_model, base_url=llm_base_url,
                    temperature=llm_temperature, max_chars=llm_max_chars, timeout=llm_timeout,
                )
                structured_data = cast(Dict[str, Any], structured_data_typed)
                structured_data["llm_model"] = llm_model or "qwen2.5:7b"
                structured_path.write_text(json.dumps(structured_data, ensure_ascii=False, indent=2), encoding="utf-8")
            except LLMStructureError as e:
                logger.warning(f"Erreur LLM : {e}")
                structured_data = {"error": str(e)}

        weaviate_result: Optional[WeaviateIngestResult] = None
        if ingest_to_weaviate:
            weaviate_result = ingest_document(doc_name=doc_name, chunks=chunks, metadata=cast(Dict[str, Any], metadata), language="fr")
            if weaviate_result.get("success"):
                weaviate_path: Path = doc_output_dir / f"{doc_name}_weaviate.json"
                weaviate_path.write_text(json.dumps(weaviate_result, ensure_ascii=False, indent=2), encoding="utf-8")

        files: Dict[str, Any] = {"markdown": str(md_path), "chunks": str(chunks_path), "ocr": str(ocr_path)}
        if use_llm and structured_data:
            files["structured"] = str(structured_path)
        if weaviate_result and weaviate_result.get("success"):
            files["weaviate"] = str(doc_output_dir / f"{doc_name}_weaviate.json")
        if not embed_images and images_dir.exists():
            files["images"] = [str(f) for f in images_dir.glob("*.png")]
            files["images_dir"] = str(images_dir)
        
        return {
            "success": True,
            "document_name": doc_name,
            "output_dir": str(doc_output_dir),
            "files": files,
            "pages": nb_pages,
            "cost": cost,
            "metadata": metadata,
            "chunks_count": len(chunks),
            "weaviate_ingest": weaviate_result,
            "pipeline_version": "1.0",
        }
        
    except Exception as e:
        logger.error(f"Erreur : {e}")
        return {"success": False, "document_name": doc_name, "output_dir": str(doc_output_dir), "error": str(e)}


def process_pdf_bytes(
    file_bytes: bytes,
    filename: str,
    output_dir: Path = Path("output"),
    progress_callback: OptionalProgressCallback = None,
    llm_provider: LLMProvider = "ollama",
    **kwargs: Any,
) -> Union[V2PipelineResult, V1PipelineResult]:
    """Process a PDF document from raw bytes.

    This function is designed for web application integrations where PDFs are
    received as file uploads (e.g., Flask request.files). It creates a temporary
    file, processes it through the main pipeline, and cleans up afterward.

    The function delegates to process_pdf() internally, supporting all the same
    processing options via **kwargs.

    Args:
        file_bytes: Raw bytes content of the PDF file. Typically obtained from
            a file upload in a web framework (e.g., request.files['pdf'].read()).
        filename: Original filename of the uploaded PDF. Used to derive the
            document name for output files. Should include the .pdf extension.
        output_dir: Base output directory. A subdirectory named after the document
            will be created for all output files. Defaults to "output".
        progress_callback: Optional callback function for real-time progress updates.
            Signature: ``callback(step_id: str, status: str, detail: str | None)``.
            step_id values: ocr, markdown, metadata, toc, classify, chunking,
            cleaning, validation, weaviate.
            status values: active, completed, error, skipped.
            Used for Server-Sent Events (SSE) in web interfaces.
        llm_provider: LLM provider to use for intelligent processing.
            "ollama" uses a local Ollama server (free, slower).
            "mistral" uses the Mistral API (paid, faster).
            Defaults to "ollama".
        **kwargs: Additional keyword arguments passed directly to process_pdf().
            Common options include:
            - use_llm (bool): Enable LLM processing. Defaults to True.
            - use_semantic_chunking (bool): Use LLM-based chunking. Defaults to False.
            - use_ocr_annotations (bool): Use OCR annotations. Defaults to False.
            - ingest_to_weaviate (bool): Insert into Weaviate. Defaults to True.
            - skip_ocr (bool): Reuse cached markdown. Defaults to False.
            See process_pdf() for the complete list of supported options.

    Returns:
        Dictionary containing processing results from process_pdf(). The structure
        depends on whether V2 or V1 pipeline is used (V2 by default).

        V2 Pipeline returns V2PipelineResult:
            - success (bool): Whether processing completed successfully.
            - document_name (str): Name derived from the uploaded filename.
            - output_dir (str): Path to the output directory.
            - files (dict): Paths to generated files.
            - pages (int): Number of pages in the PDF.
            - cost_ocr (float): OCR cost in euros.
            - cost_llm (float): LLM cost in euros.
            - cost_total (float): Total processing cost.
            - metadata (dict): Extracted document metadata.
            - toc (list): Hierarchical table of contents.
            - chunks_count (int): Number of chunks generated.
            - validation (dict | None): Validation results.
            - weaviate_ingest (dict | None): Weaviate ingestion results.
            - pipeline_version (str): "2.0"
            - error (str): Error message if success is False.

    Raises:
        No exceptions are raised directly. Errors are returned in the result
        dictionary with success=False and an error message.

    Example:
        Flask file upload handler::

            from flask import request
            from utils.pdf_pipeline import process_pdf_bytes

            @app.route('/upload', methods=['POST'])
            def upload_pdf():
                pdf_file = request.files['document']
                file_bytes = pdf_file.read()

                result = process_pdf_bytes(
                    file_bytes,
                    pdf_file.filename,
                    llm_provider="ollama",
                    use_semantic_chunking=True,
                )

                if result["success"]:
                    return jsonify({
                        "document": result["document_name"],
                        "chunks": result["chunks_count"],
                    })
                else:
                    return jsonify({"error": result["error"]}), 500

        With SSE progress callback::

            def emit_progress(step_id: str, status: str, detail: str | None) -> None:
                # Send SSE event to client
                sse.publish({"step": step_id, "status": status, "detail": detail})

            result = process_pdf_bytes(
                file_bytes,
                filename,
                progress_callback=emit_progress,
                llm_provider="mistral",
            )

    Note:
        - The function creates a temporary file on disk during processing.
          The temporary file is automatically deleted after processing completes,
          even if an error occurs.
        - For large files, ensure adequate disk space in the system temp directory.
        - The document name is derived from the filename stem (without extension).

    See Also:
        - :func:`process_pdf`: Main processing function called internally.
        - :func:`process_pdf_v2`: Direct access to V2 pipeline.
    """
    import tempfile

    original_name = Path(filename).stem
    file_ext = Path(filename).suffix.lower()  # Get original extension (.pdf or .md)

    # Use appropriate suffix for temp file to ensure correct processing
    with tempfile.NamedTemporaryFile(suffix=file_ext, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = Path(tmp.name)
    
    try:
        result = process_pdf(
            tmp_path,
            output_dir,
            document_name=original_name,
            progress_callback=progress_callback,
            llm_provider=llm_provider,
            **kwargs
        )
        return result
    finally:
        try:
            tmp_path.unlink()
        except Exception:
            pass
