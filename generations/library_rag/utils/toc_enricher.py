"""TOC Enrichment Module for Chunk Metadata Enhancement.

This module provides functions to enrich chunk metadata with hierarchical
information from the table of contents (TOC). It matches chunks to their
corresponding TOC entries and extracts:
- Full hierarchical paths (e.g., "Peirce: CP 1.628 > 628. It is...")
- Chapter titles
- Canonical academic references (e.g., "CP 1.628", "Ménon 80a")

The enrichment happens before Weaviate ingestion to ensure chunks have
complete metadata for rigorous academic citation.

Usage:
    >>> from utils.toc_enricher import enrich_chunks_with_toc
    >>> enriched_chunks = enrich_chunks_with_toc(chunks, toc, hierarchy)

See Also:
    - utils.types: FlatTOCEntryEnriched type definition
    - utils.weaviate_ingest: Integration point for enrichment
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from .types import FlatTOCEntryEnriched

logger = logging.getLogger(__name__)


def flatten_toc_with_paths(
    toc: List[Dict[str, Any]],
    hierarchy: Dict[str, Any],
) -> List[FlatTOCEntryEnriched]:
    """Flatten hierarchical or flat TOC and build full paths with metadata.

    Handles both hierarchical TOCs (with 'children' keys) and flat TOCs
    (where parent-child relationships are inferred from 'level' field).

    Traverses the TOC structure and creates enriched flat entries with:
    - Full hierarchical path (e.g., "Peirce: CP 1.628 > 628. It is...")
    - Canonical reference extraction (e.g., "CP 1.628")
    - Chapter title tracking (first level 1 ancestor)
    - Parent title list for context

    Args:
        toc: TOC structure with 'title' and 'level' fields, optionally 'children'
        hierarchy: Document hierarchy (currently unused, reserved for future)

    Returns:
        List of enriched flat TOC entries with full metadata.

    Example:
        >>> toc = [
        ...     {"title": "Peirce: CP 1.628", "level": 1},
        ...     {"title": "628. It is the instincts...", "level": 2}
        ... ]
        >>> flat = flatten_toc_with_paths(toc, {})
        >>> flat[1]["full_path"]
        'Peirce: CP 1.628 > 628. It is the instincts...'
        >>> flat[1]["canonical_ref"]
        'CP 1.628'
    """
    flat_toc: List[FlatTOCEntryEnriched] = []

    # Check if TOC is hierarchical (has children) or flat (level-based)
    is_hierarchical = any("children" in entry for entry in toc if entry)

    if is_hierarchical:
        # Original recursive approach for hierarchical TOCs
        def traverse(
            entries: List[Dict[str, Any]],
            parent_titles: List[str],
            current_chapter: str,
            current_canonical: Optional[str],
        ) -> None:
            """Recursively traverse TOC entries and build flat list."""
            for entry in entries:
                title = entry.get("title", "")
                level = entry.get("level", 0)
                children = entry.get("children", [])

                # Build full path from parents + current title
                full_path_parts = parent_titles + [title]
                full_path = " > ".join(full_path_parts)

                # Extract canonical reference if present in title
                canonical_ref = current_canonical
                cp_match = re.search(r'CP\s+(\d+\.\d+)', title)
                stephanus_match = re.search(r'(\w+\s+\d+[a-z])', title)

                if cp_match:
                    canonical_ref = f"CP {cp_match.group(1)}"
                elif stephanus_match:
                    canonical_ref = stephanus_match.group(1)

                # Update chapter title when entering level 1
                chapter_title = current_chapter
                if level == 1:
                    chapter_title = title

                # Create enriched entry
                enriched_entry: FlatTOCEntryEnriched = {
                    "title": title,
                    "level": level,
                    "full_path": full_path,
                    "chapter_title": chapter_title,
                    "canonical_ref": canonical_ref,
                    "parent_titles": parent_titles.copy(),
                    "index_in_flat_list": len(flat_toc),
                }
                flat_toc.append(enriched_entry)

                # Recursively process children
                if children:
                    traverse(
                        children,
                        parent_titles + [title],
                        chapter_title,
                        canonical_ref,
                    )

        traverse(toc, [], "", None)
    else:
        # New iterative approach for flat TOCs (infer hierarchy from levels)
        parent_stack: List[Dict[str, Any]] = []  # Stack of (level, title, canonical_ref)
        current_chapter = ""
        current_canonical: Optional[str] = None

        for entry in toc:
            title = entry.get("title", "")
            level = entry.get("level", 1)

            # Pop parents that are at same or deeper level
            while parent_stack and parent_stack[-1]["level"] >= level:
                parent_stack.pop()

            # Build parent titles list
            parent_titles = [p["title"] for p in parent_stack]

            # Build full path
            full_path_parts = parent_titles + [title]
            full_path = " > ".join(full_path_parts)

            # Extract canonical reference if present in title
            cp_match = re.search(r'CP\s+(\d+\.\d+)', title)
            stephanus_match = re.search(r'(\w+\s+\d+[a-z])', title)

            if cp_match:
                current_canonical = f"CP {cp_match.group(1)}"
            elif stephanus_match:
                current_canonical = stephanus_match.group(1)
            elif level == 1:
                # Reset canonical ref at level 1 if none found
                current_canonical = None

            # Inherit canonical ref from parent if not found
            if not current_canonical and parent_stack:
                current_canonical = parent_stack[-1].get("canonical_ref")

            # Update chapter title when at level 1
            if level == 1:
                current_chapter = title

            # Create enriched entry
            enriched_entry: FlatTOCEntryEnriched = {
                "title": title,
                "level": level,
                "full_path": full_path,
                "chapter_title": current_chapter,
                "canonical_ref": current_canonical,
                "parent_titles": parent_titles.copy(),
                "index_in_flat_list": len(flat_toc),
            }
            flat_toc.append(enriched_entry)

            # Add current entry to parent stack for next iteration
            parent_stack.append({
                "level": level,
                "title": title,
                "canonical_ref": current_canonical,
            })

    return flat_toc


def extract_paragraph_number(section_text: str) -> Optional[str]:
    """Extract paragraph number from section text.

    Handles various academic paragraph numbering formats:
    - "628. Text..." → "628"
    - "§42 Text..." → "42"
    - "80a. Text..." → "80a" (Stephanus pagination)
    - "CP 5.628. Text..." → "628"

    Args:
        section_text: Section title or path text

    Returns:
        Extracted paragraph number or None if not found.

    Example:
        >>> extract_paragraph_number("628. It is the instincts...")
        '628'
        >>> extract_paragraph_number("§42 On the nature of...")
        '42'
        >>> extract_paragraph_number("80a. SOCRATE: Sais-tu...")
        '80a'
    """
    if not section_text:
        return None

    # Pattern 1: Standard paragraph number at start "628. Text"
    match = re.match(r'^(\d+[a-z]?)\.\s', section_text)
    if match:
        return match.group(1)

    # Pattern 2: Section symbol "§42 Text"
    match = re.match(r'^§\s*(\d+[a-z]?)\s', section_text)
    if match:
        return match.group(1)

    # Pattern 3: CP reference "CP 5.628. Text" → extract paragraph only
    match = re.match(r'^CP\s+\d+\.(\d+)\.\s', section_text)
    if match:
        return match.group(1)

    return None


def find_matching_toc_entry(
    chunk: Dict[str, Any],
    flat_toc: List[FlatTOCEntryEnriched],
) -> Optional[FlatTOCEntryEnriched]:
    """Find matching TOC entry for a chunk using multi-strategy matching.

    Matching strategies (in priority order):
    1. **Exact text match**: chunk.section == toc.title
    2. **Paragraph number match**: Extract paragraph number from both and compare
    3. **Proximity match**: Use order_index to find nearest TOC entry

    Args:
        chunk: Chunk dict with 'section', 'sectionPath', 'order_index' fields
        flat_toc: Flattened TOC with enriched metadata

    Returns:
        Best matching TOC entry or None if no match found.

    Example:
        >>> chunk = {"section": "628. It is the instincts...", "order_index": 42}
        >>> toc_entry = find_matching_toc_entry(chunk, flat_toc)
        >>> toc_entry["canonical_ref"]
        'CP 1.628'
    """
    if not flat_toc:
        return None

    chunk_section = chunk.get("section", chunk.get("sectionPath", ""))
    if not chunk_section:
        return None

    # Strategy 1: Exact title match
    for entry in flat_toc:
        if entry["title"] == chunk_section:
            return entry

    # Strategy 2: Paragraph number match
    chunk_para = extract_paragraph_number(chunk_section)
    if chunk_para:
        # Look for matching paragraph in level 2 entries (actual content)
        for i, entry in enumerate(flat_toc):
            if entry["level"] == 2:
                entry_para = extract_paragraph_number(entry["title"])
                if entry_para == chunk_para:
                    # Additional text similarity check to disambiguate
                    # Get first significant word from chunk section
                    chunk_words = [w for w in chunk_section.split() if len(w) > 3]
                    entry_words = [w for w in entry["title"].split() if len(w) > 3]

                    if chunk_words and entry_words:
                        # Check if first significant words match
                        if chunk_words[0].lower() in entry["title"].lower():
                            return entry
                    else:
                        # No text to compare, return paragraph match
                        return entry

    # Strategy 3: Proximity match using order_index
    chunk_order = chunk.get("order_index")
    if chunk_order is not None and flat_toc:
        # Find TOC entry with closest index_in_flat_list to chunk order
        # This is a fallback heuristic assuming TOC and chunks follow similar order
        closest_entry = min(
            flat_toc,
            key=lambda e: abs(e["index_in_flat_list"] - chunk_order),
        )
        return closest_entry

    return None


def enrich_chunks_with_toc(
    chunks: List[Dict[str, Any]],
    toc: List[Dict[str, Any]],
    hierarchy: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Enrich chunks with hierarchical metadata from TOC.

    Main orchestration function that:
    1. Checks if TOC is available (guard clause)
    2. Flattens TOC once for efficiency
    3. Matches each chunk to its TOC entry
    4. Updates chunk metadata: sectionPath, chapterTitle, canonical_reference

    Args:
        chunks: List of chunk dicts from pdf_pipeline
        toc: Hierarchical TOC structure (may be empty)
        hierarchy: Document hierarchy dict (may be empty)

    Returns:
        List of chunks with enriched metadata (same objects, modified in place).
        If TOC is empty, returns chunks unchanged (no regression).

    Example:
        >>> chunks = [{"text": "...", "section": "628. It is..."}]
        >>> toc = [
        ...     {"title": "Peirce: CP 1.628", "level": 1, "children": [
        ...         {"title": "628. It is...", "level": 2, "children": []}
        ...     ]}
        ... ]
        >>> enriched = enrich_chunks_with_toc(chunks, toc, {})
        >>> enriched[0]["sectionPath"]
        'Peirce: CP 1.628 > 628. It is the instincts...'
        >>> enriched[0]["chapterTitle"]
        'Peirce: CP 1.628'
        >>> enriched[0]["canonical_reference"]
        'CP 1.628'
    """
    # Guard: If no TOC, return chunks unchanged (graceful fallback)
    if not toc:
        logger.info("No TOC available, skipping chunk enrichment")
        return chunks

    logger.info(f"Enriching {len(chunks)} chunks with TOC metadata...")

    # Flatten TOC once for efficient matching
    try:
        flat_toc = flatten_toc_with_paths(toc, hierarchy)
        logger.info(f"Flattened TOC: {len(flat_toc)} entries")
    except Exception as e:
        logger.error(f"Failed to flatten TOC: {e}")
        return chunks  # Fallback on error

    # Match each chunk to TOC entry and enrich
    enriched_count = 0
    for chunk in chunks:
        matching_entry = find_matching_toc_entry(chunk, flat_toc)

        if matching_entry:
            # Update sectionPath with full hierarchical path
            chunk["sectionPath"] = matching_entry["full_path"]

            # Update chapterTitle
            chunk["chapterTitle"] = matching_entry["chapter_title"]

            # Add canonicalReference if available
            if matching_entry["canonical_ref"]:
                chunk["canonicalReference"] = matching_entry["canonical_ref"]

            enriched_count += 1

    if chunks:
        logger.info(
            f"Enriched {enriched_count}/{len(chunks)} chunks "
            f"({100 * enriched_count / len(chunks):.1f}%)"
        )
    else:
        logger.info("No chunks to enrich")

    return chunks
