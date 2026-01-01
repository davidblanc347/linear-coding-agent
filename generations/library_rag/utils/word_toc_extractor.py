"""Extract hierarchical table of contents from Word document headings.

This module builds a structured TOC from Word heading styles (Heading 1-9),
generating section paths compatible with the existing RAG pipeline and Weaviate
schema (e.g., "1.2.3" for chapter 1, section 2, subsection 3).

Example:
    Build TOC from Word headings:

        from pathlib import Path
        from utils.word_processor import extract_word_content
        from utils.word_toc_extractor import build_toc_from_headings

        content = extract_word_content(Path("doc.docx"))
        toc = build_toc_from_headings(content["headings"])

        for entry in toc:
            print(f"{entry['sectionPath']}: {entry['title']}")

    Output:
        1: Introduction
        1.1: Background
        1.2: Methodology
        2: Results
        2.1: Analysis

Note:
    Compatible with existing TOCEntry TypedDict from utils.types
"""

from typing import List, Dict, Any, Optional
from utils.types import TOCEntry


def _generate_section_path(
    level: int,
    counters: List[int],
) -> str:
    """Generate section path string from level counters.

    Args:
        level: Current heading level (1-9).
        counters: List of counters for each level [c1, c2, c3, ...].

    Returns:
        Section path string (e.g., "1.2.3").

    Example:
        >>> _generate_section_path(3, [1, 2, 3, 0, 0])
        '1.2.3'
        >>> _generate_section_path(1, [2, 0, 0])
        '2'
    """
    # Take counters up to current level
    path_parts = [str(c) for c in counters[:level] if c > 0]
    return ".".join(path_parts) if path_parts else "1"


def build_toc_from_headings(
    headings: List[Dict[str, Any]],
    max_level: int = 9,
) -> List[TOCEntry]:
    """Build hierarchical table of contents from Word headings.

    Processes a list of heading paragraphs (with level attribute) and constructs
    a hierarchical TOC structure with section paths (1, 1.1, 1.2, 2, 2.1, etc.).
    Handles nested headings and missing intermediate levels gracefully.

    Args:
        headings: List of heading dicts from word_processor.extract_word_content().
            Each dict must have:
            - text (str): Heading text
            - level (int): Heading level (1-9)
            - index (int): Paragraph index in document
        max_level: Maximum heading level to process (default: 9).

    Returns:
        List of TOCEntry dicts with hierarchical structure:
        - title (str): Heading text
        - level (int): Heading level (1-9)
        - sectionPath (str): Section path (e.g., "1.2.3")
        - pageRange (str): Empty string (not applicable for Word)
        - children (List[TOCEntry]): Nested sub-headings

    Example:
        >>> headings = [
        ...     {"text": "Chapter 1", "level": 1, "index": 0},
        ...     {"text": "Section 1.1", "level": 2, "index": 1},
        ...     {"text": "Section 1.2", "level": 2, "index": 2},
        ...     {"text": "Chapter 2", "level": 1, "index": 3},
        ... ]
        >>> toc = build_toc_from_headings(headings)
        >>> print(toc[0]["title"])
        'Chapter 1'
        >>> print(toc[0]["sectionPath"])
        '1'
        >>> print(toc[0]["children"][0]["sectionPath"])
        '1.1'

    Note:
        - Empty headings are skipped
        - Handles missing intermediate levels (e.g., H1 → H3 without H2)
        - Section paths are 1-indexed (start from 1, not 0)
    """
    if not headings:
        return []

    toc: List[TOCEntry] = []
    counters = [0] * max_level  # Track counters for each level [h1, h2, h3, ...]
    parent_stack: List[TOCEntry] = []  # Stack to track parent headings

    for heading in headings:
        text = heading.get("text", "").strip()
        level = heading.get("level")

        # Skip empty headings or invalid levels
        if not text or level is None or level < 1 or level > max_level:
            continue

        level_idx = level - 1  # Convert to 0-indexed

        # Increment counter for this level
        counters[level_idx] += 1

        # Reset all deeper level counters
        for i in range(level_idx + 1, max_level):
            counters[i] = 0

        # Generate section path
        section_path = _generate_section_path(level, counters)

        # Create TOC entry
        entry: TOCEntry = {
            "title": text,
            "level": level,
            "sectionPath": section_path,
            "pageRange": "",  # Not applicable for Word documents
            "children": [],
        }

        # Determine parent and add to appropriate location
        if level == 1:
            # Top-level heading - add to root
            toc.append(entry)
            parent_stack = [entry]  # Reset parent stack
        else:
            # Find appropriate parent in stack
            # Pop stack until we find a parent at level < current level
            while parent_stack and parent_stack[-1]["level"] >= level:
                parent_stack.pop()

            if parent_stack:
                # Add to parent's children
                parent_stack[-1]["children"].append(entry)
            else:
                # No valid parent found (missing intermediate levels)
                # Add to root as a fallback
                toc.append(entry)

            # Add current entry to parent stack
            parent_stack.append(entry)

    return toc


def flatten_toc(toc: List[TOCEntry]) -> List[TOCEntry]:
    """Flatten hierarchical TOC into a flat list.

    Converts nested TOC structure to a flat list while preserving section paths
    and hierarchy information. Useful for iteration and database ingestion.

    Args:
        toc: Hierarchical TOC from build_toc_from_headings().

    Returns:
        Flat list of all TOC entries (depth-first traversal).

    Example:
        >>> toc = build_toc_from_headings(headings)
        >>> flat = flatten_toc(toc)
        >>> for entry in flat:
        ...     indent = "  " * (entry["level"] - 1)
        ...     print(f"{indent}{entry['sectionPath']}: {entry['title']}")
    """
    flat: List[TOCEntry] = []

    def _traverse(entries: List[TOCEntry]) -> None:
        for entry in entries:
            # Add current entry (create a copy to avoid mutation)
            flat_entry: TOCEntry = {
                "title": entry["title"],
                "level": entry["level"],
                "sectionPath": entry["sectionPath"],
                "pageRange": entry["pageRange"],
                "children": [],  # Don't include children in flat list
            }
            flat.append(flat_entry)

            # Recursively traverse children
            if entry["children"]:
                _traverse(entry["children"])

    _traverse(toc)
    return flat


def print_toc_tree(
    toc: List[TOCEntry],
    indent: str = "",
) -> None:
    """Print TOC tree structure to console (debug helper).

    Args:
        toc: Hierarchical TOC from build_toc_from_headings().
        indent: Indentation string for nested levels (internal use).

    Example:
        >>> toc = build_toc_from_headings(headings)
        >>> print_toc_tree(toc)
        1: Introduction
          1.1: Background
          1.2: Methodology
        2: Results
          2.1: Analysis
    """
    for entry in toc:
        print(f"{indent}{entry['sectionPath']}: {entry['title']}")
        if entry["children"]:
            print_toc_tree(entry["children"], indent + "  ")


def _roman_to_int(roman: str) -> int:
    """Convert Roman numeral to integer.

    Args:
        roman: Roman numeral string (I, II, III, IV, V, VI, VII, etc.).

    Returns:
        Integer value.

    Example:
        >>> _roman_to_int("I")
        1
        >>> _roman_to_int("IV")
        4
        >>> _roman_to_int("VII")
        7
    """
    roman_values = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
    result = 0
    prev_value = 0

    for char in reversed(roman.upper()):
        value = roman_values.get(char, 0)
        if value < prev_value:
            result -= value
        else:
            result += value
        prev_value = value

    return result


def extract_toc_from_chapter_summaries(paragraphs: List[Dict[str, Any]]) -> List[TOCEntry]:
    """Extract TOC from chapter summary paragraphs (CHAPTER I, CHAPTER II, etc.).

    Many Word documents have a "RESUME DES CHAPITRES" or "TABLE OF CONTENTS" section
    with paragraphs like:
        CHAPTER I.
        VARIATION UNDER DOMESTICATION.
        Description...

    This function extracts those into a proper TOC structure.

    Args:
        paragraphs: List of paragraph dicts from word_processor.extract_word_content().
            Each dict must have:
            - text (str): Paragraph text
            - is_heading (bool): Whether it's a heading
            - index (int): Paragraph index

    Returns:
        List of TOCEntry dicts with hierarchical structure.

    Example:
        >>> paragraphs = [...]
        >>> toc = extract_toc_from_chapter_summaries(paragraphs)
        >>> print(toc[0]["title"])
        'VARIATION UNDER DOMESTICATION'
        >>> print(toc[0]["sectionPath"])
        '1'
    """
    import re

    toc: List[TOCEntry] = []
    toc_started = False

    for para in paragraphs:
        text = para.get("text", "").strip()

        # Detect TOC start (multiple possible markers)
        if any(marker in text.upper() for marker in [
            'RESUME DES CHAPITRES',
            'TABLE OF CONTENTS',
            'CONTENTS',
            'CHAPITRES',
        ]):
            toc_started = True
            continue

        # Extract chapters
        if toc_started and text.startswith('CHAPTER'):
            # Split by newlines to get chapter number and title
            lines = [line.strip() for line in text.split('\n') if line.strip()]

            if len(lines) >= 2:
                chapter_line = lines[0]
                title_line = lines[1]

                # Extract chapter number (roman or arabic)
                match = re.match(r'CHAPTER\s+([IVXLCDM]+|\d+)', chapter_line, re.IGNORECASE)
                if match:
                    chapter_num_str = match.group(1)

                    # Convert to integer
                    if chapter_num_str.isdigit():
                        chapter_num = int(chapter_num_str)
                    else:
                        chapter_num = _roman_to_int(chapter_num_str)

                    # Remove trailing dots
                    title_clean = title_line.rstrip('.')

                    entry: TOCEntry = {
                        "title": title_clean,
                        "level": 1,  # All chapters are top-level
                        "sectionPath": str(chapter_num),
                        "pageRange": "",
                        "children": [],
                    }

                    toc.append(entry)

    return toc
