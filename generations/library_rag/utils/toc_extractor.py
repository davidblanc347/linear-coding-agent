"""Table of Contents (TOC) extraction using Mistral OCR with annotations.

This module is the **primary entry point** for TOC extraction in the Library RAG
pipeline. It provides intelligent routing between two extraction strategies:

1. **Visual (bbox) Analysis** (default, recommended): Uses bounding box coordinates
   to detect indentation and hierarchy based on horizontal positioning.
2. **Semantic (annotation) Analysis**: Uses Mistral's document_annotation_format
   for structured metadata and TOC extraction.

The visual approach is more reliable for philosophical texts with complex
hierarchies (parts, chapters, sections, subsections).

Extraction Strategies:
    ┌─────────────────────────────────────────────────────────────┐
    │  extract_toc_from_annotations(use_visual_bbox=True)         │
    │         ↓ (default)                                         │
    │  toc_extractor_visual.py → X-coordinate based hierarchy     │
    │                                                             │
    │  extract_toc_from_annotations(use_visual_bbox=False)        │
    │         ↓                                                   │
    │  DocumentMetadata Pydantic schema → Structured extraction   │
    └─────────────────────────────────────────────────────────────┘

Cost Considerations:
    - Annotated OCR: ~0.003€/page (3x standard OCR cost)
    - Only first N pages are processed (default: 8)
    - Total cost: max_toc_pages × 0.003€

Output Structure:
    {
        "success": bool,
        "metadata": {...},           # Document metadata
        "toc": [...],               # Hierarchical TOC (nested children)
        "toc_flat": [...],          # Flat list with levels
        "cost_ocr_annotated": float
    }

Example:
    >>> from pathlib import Path
    >>> from utils.toc_extractor import extract_toc_from_annotations
    >>>
    >>> # Extract TOC using visual analysis (recommended)
    >>> result = extract_toc_from_annotations(
    ...     pdf_path=Path("input/philosophy_book.pdf"),
    ...     max_toc_pages=8,
    ...     use_visual_bbox=True  # default
    ... )
    >>> if result["success"]:
    ...     for entry in result["toc"]:
    ...         print(f"{entry['title']} (p.{entry['page']})")

Functions:
    - extract_toc_from_annotations(): Main entry point with strategy routing
    - build_hierarchical_toc(): Converts flat TOC entries to nested structure
    - map_toc_to_content(): Associates TOC entries with document content

See Also:
    - utils.toc_extractor_visual: Visual/bbox-based extraction (default)
    - utils.toc_extractor_markdown: Markdown indentation-based extraction
    - utils.llm_toc: LLM-based TOC extraction (alternative approach)
"""

import json
import logging
from typing import Any, Dict, List, Optional, Union, cast
from pathlib import Path

from .ocr_schemas import DocumentMetadata, TocEntry
from .ocr_processor import run_ocr_with_annotations
from .mistral_client import create_client

logger: logging.Logger = logging.getLogger(__name__)


# TypedDict for hierarchical TOC nodes
class TOCNode(Dict[str, Any]):
    """Type alias for TOC node structure with title, page, level, type, children."""
    pass


def extract_toc_from_annotations(
    pdf_path: Path,
    api_key: Optional[str] = None,
    max_toc_pages: int = 8,
    use_visual_bbox: bool = True,  # NOUVEAU : Utiliser l'analyse visuelle par défaut
) -> Dict[str, Any]:
    """Extrait la TOC structurée via OCR avec annotations.
    
    Coût : 3€/1000 pages pour les pages annotées (vs 1€/1000 pour OCR basique).
    
    Args:
        pdf_path: Chemin du fichier PDF
        api_key: Clé API Mistral (optionnel, sinon charge depuis .env)
        max_toc_pages: Nombre max de pages à annoter (défaut 8, limite API pour document_annotation)
        use_visual_bbox: Si True, utilise l'analyse visuelle des bounding boxes (plus fiable)
    
    Returns:
        Dict avec :
        - success: bool
        - metadata: dict avec métadonnées enrichies
        - toc: liste hiérarchique [{title, page, level, children}]
        - toc_flat: liste plate [{title, page, level, type, parent_title}]
        - cost_ocr_annotated: float (coût en €)
        - error: str (si échec)
    """
    # Si demandé, utiliser l'approche visuelle (bbox)
    if use_visual_bbox:
        logger.info("Utilisation de l'analyse visuelle (bbox) pour extraction TOC")
        from .toc_extractor_visual import extract_toc_with_visual_analysis
        return cast(Dict[str, Any], extract_toc_with_visual_analysis(pdf_path, api_key, max_toc_pages))
    
    # Sinon, continuer avec l'approche sémantique (document_annotation_format)
    try:
        client = create_client(api_key)
        pdf_bytes = pdf_path.read_bytes()
    except Exception as e:
        logger.error(f"Erreur initialisation client/lecture PDF : {e}")
        return {"success": False, "error": f"Initialisation échouée : {str(e)}"}
    
    # Phase 1 : Annoter les premières pages pour extraire TOC + métadonnées
    logger.info(f"Extraction TOC avec annotations sur {max_toc_pages} premières pages")
    
    try:
        annotated_response = run_ocr_with_annotations(
            client=client,
            file_bytes=pdf_bytes,
            filename=pdf_path.name,
            include_images=False,  # Pas besoin d'images pour la TOC
            document_annotation_format=DocumentMetadata,
            pages=list(range(max_toc_pages)),  # Pages 0 à max_toc_pages-1
        )
    except Exception as e:
        logger.error(f"Erreur appel OCR avec annotations : {e}")
        return {"success": False, "error": f"Appel OCR échoué : {str(e)}"}
    
    # Extraire les annotations du document
    doc_annotation = getattr(annotated_response, "document_annotation", None)
    
    if not doc_annotation:
        return {"success": False, "error": "Aucune annotation retournée par l'API"}
    
    # Convertir en dictionnaire
    try:
        if isinstance(doc_annotation, str):
            metadata_dict = json.loads(doc_annotation)
        else:
            metadata_dict = doc_annotation
    except Exception as e:
        logger.error(f"Erreur parsing annotations : {e}")
        return {"success": False, "error": f"Parsing annotations échoué : {str(e)}"}
    
    # Valider avec Pydantic
    try:
        metadata = DocumentMetadata(**metadata_dict)
        toc_entries = metadata.toc.entries
        
        logger.info(f"TOC extraite : {len(toc_entries)} entrées")
        
        # Construire la TOC hiérarchique
        hierarchical_toc = build_hierarchical_toc(toc_entries)
        
        return {
            "success": True,
            "metadata": metadata.model_dump(),
            "toc": hierarchical_toc,
            "toc_flat": [entry.model_dump() for entry in toc_entries],
            "cost_ocr_annotated": max_toc_pages * 0.003,  # 3€/1000 pages
        }
    except Exception as e:
        logger.error(f"Erreur validation annotations : {e}")
        return {"success": False, "error": f"Validation Pydantic échouée : {str(e)}"}


def build_hierarchical_toc(entries: List[TocEntry]) -> List[Dict[str, Any]]:
    """Construit une TOC hiérarchique à partir des entrées plates avec niveaux.

    Utilise une stack pour gérer la hiérarchie basée sur les niveaux.

    Args:
        entries: Liste d'entrées TocEntry avec level (1=racine, 2=enfant de 1, etc.)

    Returns:
        TOC hiérarchique avec structure [{title, page, level, type, children: [...]}]
    """
    if not entries:
        return []

    toc: List[Dict[str, Any]] = []
    stack: List[Dict[str, Any]] = []  # Stack pour gérer la hiérarchie courante

    for entry in entries:
        node: Dict[str, Any] = {
            "title": entry.title,
            "page": entry.page_number,
            "level": entry.level,
            "type": entry.entry_type.value,
            "children": [],
        }

        # Remonter dans la stack jusqu'au parent approprié
        # Un élément de level N doit être enfant du dernier élément de level < N
        while stack and stack[-1]["level"] >= entry.level:
            stack.pop()

        if stack:
            # Ajouter comme enfant du dernier élément de la stack
            children: List[Dict[str, Any]] = stack[-1]["children"]
            children.append(node)
        else:
            # Ajouter à la racine de la TOC
            toc.append(node)

        # Empiler ce nœud pour les prochaines itérations
        stack.append(node)

    return toc


def map_toc_to_content(
    toc_entries: List[TocEntry],
    all_pages_markdown: str,
) -> Dict[str, str]:
    """Associe les entrées de TOC au contenu réel du document.

    Utilise les vrais numéros de page pour découper le contenu par section.

    Args:
        toc_entries: Entrées de TOC avec numéros de page réels
        all_pages_markdown: Markdown complet du document avec <!-- Page N --> markers

    Returns:
        Mapping {section_title: content_text}
    """
    # Découper le markdown par commentaires de page
    pages: List[str] = all_pages_markdown.split("<!-- Page ")

    content_map: Dict[str, str] = {}

    for i, entry in enumerate(toc_entries):
        start_page: int = entry.page_number

        # Trouver la page de fin (numéro de page de la prochaine entrée ou fin du doc)
        end_page: int
        if i < len(toc_entries) - 1:
            end_page = toc_entries[i + 1].page_number
        else:
            end_page = len(pages)  # Jusqu'à la fin

        # Extraire le contenu entre start_page et end_page
        section_content: List[str] = []
        for page_idx in range(start_page, end_page):
            if page_idx < len(pages):
                # Nettoyer le commentaire de page et extraire le contenu
                page_text: str = pages[page_idx].split("-->", 1)[-1].strip()
                section_content.append(page_text)

        content_map[entry.title] = "\n\n".join(section_content)

    return content_map
