"""Visual TOC extraction using bounding box X-coordinate analysis.

This module provides the **most accurate** TOC extraction strategy for
philosophical texts by analyzing the horizontal position (X-coordinate)
of each TOC entry. This approach is more reliable than text indentation
analysis because it directly measures visual layout.

How It Works:
    1. OCR with annotations extracts text + bounding box positions
    2. Pydantic schema (TocEntryBbox) captures title, page, and x_position
    3. X-coordinates are clustered to identify distinct indentation levels
    4. Hierarchy is built based on relative X-positions

X-Position Interpretation:
    The x_position is normalized between 0.0 (left edge) and 1.0 (right edge):

    - x ≈ 0.05-0.12: Level 1 (no indentation, main parts/chapters)
    - x ≈ 0.13-0.22: Level 2 (small indentation, sections)
    - x ≈ 0.23-0.35: Level 3 (double indentation, subsections)

    Positions within 0.03 tolerance are grouped into the same level.

Advantages over Markdown Analysis:
    - Works regardless of OCR whitespace accuracy
    - More reliable for complex hierarchies
    - Handles both printed and handwritten indentation

Cost:
    - Uses OCR with annotations: ~0.003€/page
    - Only processes first N pages (default: 8)

Pydantic Schemas:
    - TocEntryBbox: Single TOC entry with text, page_number, x_position
    - DocumentTocBbox: Container for list of entries

Output Structure:
    {
        "success": bool,
        "metadata": {...},
        "toc": [...],               # Hierarchical TOC
        "toc_flat": [...],          # Flat entries with levels
        "cost_ocr_annotated": float,
        "method": "visual_x_position"
    }

Example:
    >>> from pathlib import Path
    >>> from utils.toc_extractor_visual import extract_toc_with_visual_analysis
    >>>
    >>> result = extract_toc_with_visual_analysis(
    ...     pdf_path=Path("input/philosophy_book.pdf"),
    ...     max_toc_pages=8
    ... )
    >>> if result["success"]:
    ...     for entry in result["toc"]:
    ...         indent = "  " * (entry["level"] - 1)
    ...         print(f"{indent}{entry['title']} (p.{entry['page']})")

Algorithm Details:
    1. Collect all x_position values from OCR response
    2. Sort and cluster positions (tolerance: 0.03)
    3. Compute cluster centroids as level thresholds
    4. Assign level to each entry based on nearest centroid
    5. Build hierarchy using stack-based approach

Functions:
    - extract_toc_with_visual_analysis(): Main extraction function
    - build_hierarchy_from_bbox(): Converts entries with X-positions to hierarchy
    - flatten_toc(): Flattens hierarchical TOC for storage

See Also:
    - utils.toc_extractor: Main entry point (routes here by default)
    - utils.toc_extractor_markdown: Alternative cost-free extraction
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TypedDict, Union

from pydantic import BaseModel, Field

from .mistral_client import create_client
from .ocr_processor import run_ocr_with_annotations

logger: logging.Logger = logging.getLogger(__name__)


class TocEntryBbox(BaseModel):
    """TOC entry with bounding box for visual detection.

    Attributes:
        text: Complete entry text as it appears in the table of contents.
            Example: 'Presentation' or 'What is virtue?' or 'Meno or on virtue'.
            DO NOT include leader dots or page number in this field.
        page_number: Actual page number as printed in the book (the visible number
            on the right in the TOC). Example: if the line says 'Presentation.....3',
            extract the number 3. This is the BOOK page number, not the PDF index.
        x_position: Horizontal position (X coordinate) of the text start, normalized
            between 0 and 1. This is the CRUCIAL COORDINATE for detecting indentation:
            - x ≈ 0.05-0.12 = left-aligned title, NOT indented (hierarchical level 1)
            - x ≈ 0.13-0.22 = title with SMALL indentation (hierarchical level 2)
            - x ≈ 0.23-0.35 = title with DOUBLE indentation (hierarchical level 3)
            Measure precisely where the first character of the title begins.
    """
    text: str = Field(..., description="""Texte COMPLET de l'entrée tel qu'il apparaît dans la table des matières. 
    Exemple: 'Présentation' ou 'Qu'est-ce que la vertu ?' ou 'Ménon ou de la vertu'.
    NE PAS inclure les points de suite ni le numéro de page dans ce champ.""")
    page_number: int = Field(..., description="""Numéro de page réel tel qu'imprimé dans le livre (le numéro visible à droite dans la TOC).
    Exemple: si la ligne dit 'Présentation.....3', extraire le nombre 3.
    C'est le numéro de page du LIVRE, pas l'index PDF.""")
    x_position: float = Field(..., description="""Position horizontale (coordonnée X) du début du texte, normalisée entre 0 et 1.
    C'est LA COORDONNÉE CRUCIALE pour détecter l'indentation:
    - x ≈ 0.05-0.12 = titre aligné à gauche, NON indenté (niveau hiérarchique 1)
    - x ≈ 0.13-0.22 = titre avec PETITE indentation (niveau hiérarchique 2)
    - x ≈ 0.23-0.35 = titre avec DOUBLE indentation (niveau hiérarchique 3)
    Mesurer précisément où commence le premier caractère du titre.""")


class DocumentTocBbox(BaseModel):
    """Schema for extracting all TOC entries with their positions.

    Attributes:
        entries: Complete list of ALL entries found in the table of contents.
            For EACH line in the TOC, extract:
            1. The title text (without leader dots)
            2. The page number (the number on the right)
            3. The exact horizontal X position of the title start (to detect indentation)

            Include ALL entries, even those that appear to be at the same visual level.
    """

    entries: List[TocEntryBbox] = Field(
        ...,
        description="""Complete list of ALL entries found in the table of contents.
    For EACH line in the TOC, extract:
    1. The title text (without leader dots)
    2. The page number (the number on the right)
    3. The exact horizontal X position of the title start (to detect indentation)

    Include ALL entries, even those that appear to be at the same visual level.""",
    )


# TypedDict classes for structured return types
class VisualTOCMetadata(TypedDict):
    """Metadata extracted from the document.

    Attributes:
        title: Document title.
        author: Document author.
        languages: List of languages present in the document.
        summary: Brief document summary.
    """

    title: str
    author: str
    languages: List[str]
    summary: str


class VisualTOCNode(TypedDict):
    """Hierarchical TOC node.

    Attributes:
        title: Entry title text.
        page: Page number in the book.
        level: Hierarchical level (1 = top level, 2 = subsection, etc.).
        type: Entry type (e.g., "section", "chapter").
        children: List of child nodes.
    """

    title: str
    page: int
    level: int
    type: str
    children: List[VisualTOCNode]


class VisualTOCFlatEntry(TypedDict):
    """Flattened TOC entry for storage.

    Attributes:
        title: Entry title text.
        page_number: Page number in the book.
        level: Hierarchical level.
        entry_type: Entry type (e.g., "section", "chapter").
        parent_title: Title of the parent entry, if any.
    """

    title: str
    page_number: int
    level: int
    entry_type: str
    parent_title: Optional[str]


class VisualTOCResultSuccess(TypedDict):
    """Successful TOC extraction result.

    Attributes:
        success: Always True for success case.
        metadata: Document metadata.
        toc: Hierarchical TOC structure.
        toc_flat: Flattened TOC entries.
        cost_ocr_annotated: OCR processing cost in euros.
        method: Extraction method identifier.
    """

    success: bool
    metadata: VisualTOCMetadata
    toc: List[VisualTOCNode]
    toc_flat: List[VisualTOCFlatEntry]
    cost_ocr_annotated: float
    method: str


class VisualTOCResultError(TypedDict):
    """Failed TOC extraction result.

    Attributes:
        success: Always False for error case.
        error: Error message describing the failure.
    """

    success: bool
    error: str


# Union type for the function return
VisualTOCResult = Union[VisualTOCResultSuccess, VisualTOCResultError]


class VisualTOCEntryInternal(TypedDict):
    """Internal representation of TOC entry during processing.

    Attributes:
        text: Entry title text.
        page_number: Page number in the book.
        x_position: Normalized X position (0.0 to 1.0).
        x_start: Same as x_position (for processing).
        page: Same as page_number (for processing).
        level: Computed hierarchical level.
    """

    text: str
    page_number: int
    x_position: float
    x_start: float
    page: int
    level: int


def extract_toc_with_visual_analysis(
    pdf_path: Path,
    api_key: Optional[str] = None,
    max_toc_pages: int = 8,
) -> VisualTOCResult:
    """Extract TOC by visually analyzing bounding boxes.

    Detects hierarchy from horizontal alignment (X coordinate). This method
    uses OCR with annotations to extract the precise X-coordinate of each
    TOC entry, then clusters these positions to identify indentation levels.

    Args:
        pdf_path: Path to the PDF file.
        api_key: Mistral API key (optional, uses environment variable if not provided).
        max_toc_pages: Number of pages to analyze (default: 8).

    Returns:
        Dictionary containing either:
            - Success: metadata, hierarchical TOC, flat TOC, cost, method
            - Error: success=False and error message

    Raises:
        Does not raise exceptions; errors are returned in the result dictionary.

    Example:
        >>> from pathlib import Path
        >>> result = extract_toc_with_visual_analysis(Path("book.pdf"))
        >>> if result["success"]:
        ...     print(f"Extracted {len(result['toc'])} top-level entries")
        ... else:
        ...     print(f"Error: {result['error']}")
    """
    try:
        client = create_client(api_key)
        pdf_bytes: bytes = pdf_path.read_bytes()
    except Exception as e:
        logger.error(f"Initialization error: {e}")
        return {"success": False, "error": str(e)}

    logger.info(f"Visual TOC extraction on {max_toc_pages} pages")

    # Call OCR with document_annotation_format for global structure
    try:
        response = run_ocr_with_annotations(
            client=client,
            file_bytes=pdf_bytes,
            filename=pdf_path.name,
            include_images=False,
            document_annotation_format=DocumentTocBbox,
            pages=list(range(max_toc_pages)),
        )
    except Exception as e:
        logger.error(f"OCR with annotations error: {e}")
        return {"success": False, "error": f"OCR failed: {str(e)}"}

    # Extract annotations
    doc_annotation: Any = getattr(response, "document_annotation", None)

    if not doc_annotation:
        return {"success": False, "error": "No annotation returned"}

    # Parse entries
    try:
        if isinstance(doc_annotation, str):
            toc_data: Any = json.loads(doc_annotation)
        else:
            toc_data = doc_annotation

        entries_data: List[Dict[str, Any]] = (
            toc_data.get("entries", []) if isinstance(toc_data, dict) else toc_data
        )

        # Build hierarchy from X coordinates
        toc_entries: List[VisualTOCNode] = build_hierarchy_from_bbox(entries_data)

        logger.info(f"TOC extracted visually: {len(toc_entries)} entries")

        # Basic metadata (no enriched metadata in visual mode)
        metadata: VisualTOCMetadata = {
            "title": pdf_path.stem,
            "author": "Unknown author",
            "languages": [],
            "summary": "",
        }

        result: VisualTOCResultSuccess = {
            "success": True,
            "metadata": metadata,
            "toc": toc_entries,
            "toc_flat": flatten_toc(toc_entries),
            "cost_ocr_annotated": max_toc_pages * 0.003,
            "method": "visual_x_position",
        }
        return result
    except Exception as e:
        logger.error(f"Bbox parsing error: {e}")
        return {"success": False, "error": f"Parsing failed: {str(e)}"}


def build_hierarchy_from_bbox(entries: List[Dict[str, Any]]) -> List[VisualTOCNode]:
    """Build TOC hierarchy from X positions (indentation).

    Detects the hierarchical level by analyzing the horizontal X coordinate.
    Clusters nearby X positions to identify distinct indentation levels, then
    builds a tree structure using a stack-based approach.

    Args:
        entries: List of entries with x_position field. Each entry should have:
            - text: Entry title
            - page_number: Page number
            - x_position: Normalized X coordinate (0.0 to 1.0)

    Returns:
        Hierarchical TOC structure as a list of nodes. Each node contains:
            - title: Entry title
            - page: Page number
            - level: Hierarchical level (1, 2, 3, ...)
            - type: Entry type (always "section")
            - children: List of child nodes

    Example:
        >>> entries = [
        ...     {"text": "Chapter 1", "page_number": 1, "x_position": 0.1},
        ...     {"text": "Section 1.1", "page_number": 2, "x_position": 0.2},
        ... ]
        >>> hierarchy = build_hierarchy_from_bbox(entries)
        >>> hierarchy[0]["children"][0]["title"]
        'Section 1.1'
    """
    if not entries:
        return []

    # Extract X positions and normalize entry data
    entry_list: List[VisualTOCEntryInternal] = []
    for entry in entries:
        x_start: float = entry.get("x_position", 0.1)
        page_num: int = entry.get("page_number", 0)
        entry["x_start"] = x_start
        entry["page"] = page_num
        entry_list.append(entry)  # type: ignore[arg-type]

    # Find unique indentation thresholds
    x_positions: List[float] = sorted(set(e["x_start"] for e in entry_list))

    if not x_positions:
        logger.warning("No X position detected")
        return []

    # Group nearby positions (tolerance 0.03 to normalize small variations)
    x_levels: List[float] = []
    current_group: List[float] = [x_positions[0]]

    for x in x_positions[1:]:
        if x - current_group[-1] < 0.03:
            current_group.append(x)
        else:
            x_levels.append(sum(current_group) / len(current_group))
            current_group = [x]

    if current_group:
        x_levels.append(sum(current_group) / len(current_group))

    logger.info(
        f"Indentation levels detected (X positions): {[f'{x:.3f}' for x in x_levels]}"
    )

    # Assign levels based on X position
    for entry_item in entry_list:
        x_val: float = entry_item["x_start"]
        # Find the closest level
        level: int = min(range(len(x_levels)), key=lambda i: abs(x_levels[i] - x_val)) + 1
        entry_item["level"] = level
        logger.debug(f"  '{entry_item.get('text', '')}' -> X={x_val:.3f} -> level {level}")

    # Build hierarchy
    toc: List[VisualTOCNode] = []
    stack: List[VisualTOCNode] = []

    for entry_item in entry_list:
        node: VisualTOCNode = {
            "title": entry_item.get("text", "").strip(),
            "page": entry_item["page"],
            "level": entry_item["level"],
            "type": "section",
            "children": [],
        }

        # Pop from stack while current level is less than or equal to stack top
        while stack and stack[-1]["level"] >= node["level"]:
            stack.pop()

        if stack:
            stack[-1]["children"].append(node)
        else:
            toc.append(node)

        stack.append(node)

    return toc


def flatten_toc(toc: List[VisualTOCNode]) -> List[VisualTOCFlatEntry]:
    """Flatten a hierarchical TOC.

    Converts a nested TOC structure into a flat list of entries, preserving
    parent-child relationships through the parent_title field.

    Args:
        toc: Hierarchical TOC structure (list of VisualTOCNode).

    Returns:
        Flat list of TOC entries with parent references.

    Example:
        >>> toc = [{
        ...     "title": "Chapter 1",
        ...     "page": 1,
        ...     "level": 1,
        ...     "type": "section",
        ...     "children": [{
        ...         "title": "Section 1.1",
        ...         "page": 2,
        ...         "level": 2,
        ...         "type": "section",
        ...         "children": []
        ...     }]
        ... }]
        >>> flat = flatten_toc(toc)
        >>> len(flat)
        2
        >>> flat[1]["parent_title"]
        'Chapter 1'
    """
    flat: List[VisualTOCFlatEntry] = []

    def recurse(items: List[VisualTOCNode], parent_title: Optional[str] = None) -> None:
        """Recursively flatten TOC nodes.

        Args:
            items: List of TOC nodes to process.
            parent_title: Title of the parent node (None for top level).
        """
        for item in items:
            flat_entry: VisualTOCFlatEntry = {
                "title": item["title"],
                "page_number": item["page"],
                "level": item["level"],
                "entry_type": item["type"],
                "parent_title": parent_title,
            }
            flat.append(flat_entry)
            if item.get("children"):
                recurse(item["children"], item["title"])

    recurse(toc)
    return flat

