"""TOC extraction via Markdown indentation analysis.

This module provides a **cost-free** TOC extraction strategy that works on
already-generated Markdown text. Unlike the OCR annotation approach, this
method doesn't require additional API calls.

Strategy:
    1. Search for "Table des matières" heading in the first N lines
    2. Parse lines matching pattern: "Title.....Page" or "Title  Page"
    3. Detect hierarchy from leading whitespace (indentation)
    4. Build nested TOC structure using stack-based algorithm

When to Use:
    - When OCR has already been performed (markdown available)
    - When cost optimization is critical (no additional API calls)
    - For documents with clear indentation in the TOC

Limitations:
    - Requires French "Table des matières" header (can be extended)
    - Indentation detection may be less accurate than visual/bbox analysis
    - Only works if OCR preserved whitespace accurately

Indentation Levels:
    - 0-2 spaces: Level 1 (main chapters/parts)
    - 3-6 spaces: Level 2 (sections)
    - 7+ spaces: Level 3 (subsections)

Output Structure:
    {
        "success": bool,
        "toc": [...],               # Hierarchical TOC
        "toc_flat": [...],          # Flat entries with levels
        "cost_ocr_annotated": 0.0,  # No additional cost
        "method": "markdown_indentation"
    }

Example:
    >>> from utils.toc_extractor_markdown import extract_toc_from_markdown
    >>>
    >>> markdown = '''
    ... # Table des matières
    ... Introduction.............................5
    ... Première partie..........................10
    ...    Chapitre 1............................15
    ...    Chapitre 2............................25
    ... Deuxième partie..........................50
    ... '''
    >>> result = extract_toc_from_markdown(markdown)
    >>> if result["success"]:
    ...     print(f"Found {len(result['toc_flat'])} entries")
    Found 5 entries

Functions:
    - extract_toc_from_markdown(): Main extraction from markdown text
    - build_hierarchy(): Converts flat entries to nested structure

See Also:
    - utils.toc_extractor: Main entry point (routes to visual by default)
    - utils.toc_extractor_visual: More accurate X-position based extraction
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, TypedDict, Union
from pathlib import Path

logger = logging.getLogger(__name__)


# Type definitions for internal data structures
class MarkdownTOCEntryRaw(TypedDict):
    """Raw TOC entry extracted from markdown with indentation info."""
    title: str
    page_number: int
    level: int
    leading_spaces: int


class MarkdownTOCNode(TypedDict):
    """Hierarchical TOC node with children."""
    title: str
    page: int
    level: int
    type: str
    children: List[MarkdownTOCNode]


class MarkdownTOCFlatEntry(TypedDict):
    """Flat TOC entry with parent information."""
    title: str
    page_number: int
    level: int
    entry_type: str
    parent_title: Optional[str]


class MarkdownTOCResultSuccess(TypedDict):
    """Successful TOC extraction result."""
    success: bool  # Always True
    metadata: Dict[str, Any]
    toc: List[MarkdownTOCNode]
    toc_flat: List[MarkdownTOCFlatEntry]
    cost_ocr_annotated: float
    method: str


class MarkdownTOCResultError(TypedDict):
    """Failed TOC extraction result."""
    success: bool  # Always False
    error: str


# Union type for function return
MarkdownTOCResult = Union[MarkdownTOCResultSuccess, MarkdownTOCResultError]


def extract_toc_from_markdown(
    markdown_text: str,
    max_lines: int = 200,
) -> MarkdownTOCResult:
    """Extract table of contents by analyzing raw markdown text.

    Detects hierarchy by counting leading spaces (indentation) at the
    beginning of each line. This is a cost-free alternative to OCR
    annotation-based extraction.

    Args:
        markdown_text: Complete markdown text of the document.
        max_lines: Maximum number of lines to analyze (searches TOC at start).

    Returns:
        Dictionary with hierarchical TOC structure. On success, includes:
            - success: True
            - metadata: Empty dict (for consistency with other extractors)
            - toc: Hierarchical nested TOC structure
            - toc_flat: Flat list of entries with levels
            - cost_ocr_annotated: 0.0 (no additional cost)
            - method: "markdown_indentation"
        On failure, includes:
            - success: False
            - error: Error message string

    Example:
        >>> markdown = '''
        ... # Table des matières
        ... Introduction.....5
        ... Part One........10
        ...   Chapter 1.....15
        ... '''
        >>> result = extract_toc_from_markdown(markdown)
        >>> if result["success"]:
        ...     print(len(result["toc_flat"]))
        3
    """
    logger.info("Extraction TOC depuis markdown (analyse indentation)")

    lines: List[str] = markdown_text.split('\n')[:max_lines]

    # Find "Table des matières" section
    toc_start: Optional[int] = None
    for i, line in enumerate(lines):
        if re.search(r'table\s+des\s+mati[èe]res', line, re.IGNORECASE):
            toc_start = i + 1
            logger.info(f"TOC trouvée à la ligne {i}")
            break

    if toc_start is None:
        logger.warning("Aucune table des matières trouvée dans le markdown")
        return MarkdownTOCResultError(
            success=False,
            error="Table des matières introuvable"
        )

    # Extract TOC entries
    entries: List[MarkdownTOCEntryRaw] = []
    toc_pattern: re.Pattern[str] = re.compile(r'^(\s*)(.+?)\s*\.+\s*(\d+)\s*$')

    for line in lines[toc_start:toc_start + 100]:  # Max 100 lines of TOC
        line_stripped: str = line.strip()
        if not line_stripped or line_stripped.startswith('#') or line_stripped.startswith('---'):
            continue

        # Search for pattern "Title.....Page"
        # Must analyze line BEFORE strip() to count leading spaces
        original_line: str = lines[lines.index(line) if line in lines else 0]
        leading_spaces: int = len(original_line) - len(original_line.lstrip())

        # Alternative pattern: search for title + number at end
        match: Optional[re.Match[str]] = re.match(r'^(.+?)\s*\.{2,}\s*(\d+)\s*$', line_stripped)
        if not match:
            # Try without dotted leaders
            match = re.match(r'^(.+?)\s+(\d+)\s*$', line_stripped)

        if match:
            title: str = match.group(1).strip()
            page: int = int(match.group(2))

            # Ignore lines too short or that don't look like titles
            if len(title) < 3 or title.isdigit():
                continue

            # Determine level based on indentation
            # 0-2 spaces = level 1
            # 3-6 spaces = level 2
            # 7+ spaces = level 3
            level: int
            if leading_spaces <= 2:
                level = 1
            elif leading_spaces <= 6:
                level = 2
            else:
                level = 3

            entries.append(MarkdownTOCEntryRaw(
                title=title,
                page_number=page,
                level=level,
                leading_spaces=leading_spaces,
            ))

            logger.debug(f"  '{title}' → {leading_spaces} espaces → level {level} (page {page})")

    if not entries:
        logger.warning("Aucune entrée TOC extraite")
        return MarkdownTOCResultError(
            success=False,
            error="Aucune entrée TOC trouvée"
        )

    logger.info(f"✅ {len(entries)} entrées extraites depuis markdown")

    # Build hierarchy
    toc: List[MarkdownTOCNode] = build_hierarchy(entries)

    return MarkdownTOCResultSuccess(
        success=True,
        metadata={},
        toc=toc,
        toc_flat=[
            MarkdownTOCFlatEntry(
                title=e["title"],
                page_number=e["page_number"],
                level=e["level"],
                entry_type="section",
                parent_title=None,
            )
            for e in entries
        ],
        cost_ocr_annotated=0.0,  # No additional cost, uses existing OCR
        method="markdown_indentation",
    )


def build_hierarchy(entries: List[MarkdownTOCEntryRaw]) -> List[MarkdownTOCNode]:
    """Build hierarchical structure from flat entries based on levels.

    Uses a stack-based algorithm to construct nested TOC structure where
    entries with higher indentation become children of the previous
    less-indented entry.

    Args:
        entries: List of raw TOC entries with title, page, and level.

    Returns:
        Nested list of TOC nodes where each node contains children.

    Example:
        >>> entries = [
        ...     {"title": "Part 1", "page_number": 1, "level": 1, "leading_spaces": 0},
        ...     {"title": "Chapter 1", "page_number": 5, "level": 2, "leading_spaces": 4},
        ... ]
        >>> hierarchy = build_hierarchy(entries)
        >>> len(hierarchy[0]["children"])
        1
    """
    toc: List[MarkdownTOCNode] = []
    stack: List[MarkdownTOCNode] = []

    for entry in entries:
        node: MarkdownTOCNode = MarkdownTOCNode(
            title=entry["title"],
            page=entry["page_number"],
            level=entry["level"],
            type="section",
            children=[],
        )

        # Pop from stack until we find a parent at lower level
        while stack and stack[-1]["level"] >= node["level"]:
            stack.pop()

        if stack:
            # Add as child to top of stack
            stack[-1]["children"].append(node)
        else:
            # Add as root-level entry
            toc.append(node)

        stack.append(node)

    return toc
