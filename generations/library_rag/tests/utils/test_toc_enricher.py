"""Unit tests for TOC enrichment module.

Tests the enrichment of chunk metadata with hierarchical information
from the table of contents (TOC).
"""

from typing import Any, Dict, List

import pytest

from utils.toc_enricher import (
    enrich_chunks_with_toc,
    extract_paragraph_number,
    find_matching_toc_entry,
    flatten_toc_with_paths,
)
from utils.types import FlatTOCEntryEnriched


class TestFlattenTocWithPaths:
    """Tests for flatten_toc_with_paths function."""

    def test_flatten_simple_toc(self) -> None:
        """Test flattening a simple two-level TOC."""
        toc: List[Dict[str, Any]] = [
            {
                "title": "Chapter 1",
                "level": 1,
                "children": [
                    {"title": "Section 1.1", "level": 2, "children": []},
                    {"title": "Section 1.2", "level": 2, "children": []},
                ],
            },
        ]

        flat_toc = flatten_toc_with_paths(toc, {})

        assert len(flat_toc) == 3
        assert flat_toc[0]["title"] == "Chapter 1"
        assert flat_toc[0]["level"] == 1
        assert flat_toc[0]["full_path"] == "Chapter 1"
        assert flat_toc[1]["title"] == "Section 1.1"
        assert flat_toc[1]["full_path"] == "Chapter 1 > Section 1.1"
        assert flat_toc[1]["chapter_title"] == "Chapter 1"

    def test_flatten_peirce_toc_with_cp_references(self) -> None:
        """Test flattening Peirce TOC with CP references."""
        toc: List[Dict[str, Any]] = [
            {
                "title": "Peirce: CP 1.628",
                "level": 1,
                "children": [
                    {
                        "title": "628. It is the instincts...",
                        "level": 2,
                        "children": [],
                    },
                ],
            },
        ]

        flat_toc = flatten_toc_with_paths(toc, {})

        assert len(flat_toc) == 2
        # Level 1 entry should extract CP reference
        assert flat_toc[0]["canonical_ref"] == "CP 1.628"
        # Level 2 entry should inherit CP reference
        assert flat_toc[1]["canonical_ref"] == "CP 1.628"
        assert flat_toc[1]["full_path"] == "Peirce: CP 1.628 > 628. It is the instincts..."
        assert flat_toc[1]["chapter_title"] == "Peirce: CP 1.628"

    def test_flatten_empty_toc(self) -> None:
        """Test flattening an empty TOC."""
        flat_toc = flatten_toc_with_paths([], {})
        assert flat_toc == []

    def test_flatten_nested_hierarchy(self) -> None:
        """Test flattening a deeply nested hierarchy."""
        toc: List[Dict[str, Any]] = [
            {
                "title": "Part I",
                "level": 1,
                "children": [
                    {
                        "title": "Chapter 1",
                        "level": 2,
                        "children": [
                            {
                                "title": "Section 1.1",
                                "level": 3,
                                "children": [],
                            },
                        ],
                    },
                ],
            },
        ]

        flat_toc = flatten_toc_with_paths(toc, {})

        assert len(flat_toc) == 3
        assert flat_toc[2]["full_path"] == "Part I > Chapter 1 > Section 1.1"
        assert flat_toc[2]["parent_titles"] == ["Part I", "Chapter 1"]
        assert flat_toc[2]["chapter_title"] == "Part I"

    def test_flatten_stephanus_pagination(self) -> None:
        """Test flattening TOC with Stephanus pagination (e.g., Plato)."""
        toc: List[Dict[str, Any]] = [
            {
                "title": "Ménon 80a",
                "level": 1,
                "children": [
                    {
                        "title": "80a. MÉNON : Socrate...",
                        "level": 2,
                        "children": [],
                    },
                ],
            },
        ]

        flat_toc = flatten_toc_with_paths(toc, {})

        assert flat_toc[0]["canonical_ref"] == "Ménon 80a"
        assert flat_toc[1]["canonical_ref"] == "Ménon 80a"


class TestExtractParagraphNumber:
    """Tests for extract_paragraph_number function."""

    def test_extract_standard_paragraph(self) -> None:
        """Test extracting standard paragraph number."""
        assert extract_paragraph_number("628. It is the instincts...") == "628"
        assert extract_paragraph_number("42. On the nature of...") == "42"

    def test_extract_stephanus_paragraph(self) -> None:
        """Test extracting Stephanus-style paragraph (with letter)."""
        assert extract_paragraph_number("80a. SOCRATE: Sais-tu...") == "80a"
        assert extract_paragraph_number("215c. Text here") == "215c"

    def test_extract_section_symbol(self) -> None:
        """Test extracting paragraph with section symbol."""
        assert extract_paragraph_number("§42 On the nature of...") == "42"
        assert extract_paragraph_number("§ 628 Text") == "628"

    def test_extract_cp_reference(self) -> None:
        """Test extracting paragraph from CP reference."""
        assert extract_paragraph_number("CP 5.628. Text") == "628"
        assert extract_paragraph_number("CP 1.42. My philosophy") == "42"

    def test_extract_no_paragraph(self) -> None:
        """Test extraction when no paragraph number present."""
        assert extract_paragraph_number("Introduction") is None
        assert extract_paragraph_number("") is None
        assert extract_paragraph_number("Chapter One") is None


class TestFindMatchingTocEntry:
    """Tests for find_matching_toc_entry function."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.flat_toc: List[FlatTOCEntryEnriched] = [
            {
                "title": "Peirce: CP 1.628",
                "level": 1,
                "full_path": "Peirce: CP 1.628",
                "chapter_title": "Peirce: CP 1.628",
                "canonical_ref": "CP 1.628",
                "parent_titles": [],
                "index_in_flat_list": 0,
            },
            {
                "title": "628. It is the instincts...",
                "level": 2,
                "full_path": "Peirce: CP 1.628 > 628. It is the instincts...",
                "chapter_title": "Peirce: CP 1.628",
                "canonical_ref": "CP 1.628",
                "parent_titles": ["Peirce: CP 1.628"],
                "index_in_flat_list": 1,
            },
            {
                "title": "Peirce: CP 1.42",
                "level": 1,
                "full_path": "Peirce: CP 1.42",
                "chapter_title": "Peirce: CP 1.42",
                "canonical_ref": "CP 1.42",
                "parent_titles": [],
                "index_in_flat_list": 2,
            },
            {
                "title": "42. My philosophy resuscitates Hegel",
                "level": 2,
                "full_path": "Peirce: CP 1.42 > 42. My philosophy resuscitates Hegel",
                "chapter_title": "Peirce: CP 1.42",
                "canonical_ref": "CP 1.42",
                "parent_titles": ["Peirce: CP 1.42"],
                "index_in_flat_list": 3,
            },
        ]

    def test_exact_title_match(self) -> None:
        """Test exact title matching."""
        chunk: Dict[str, Any] = {
            "section": "628. It is the instincts...",
            "order_index": 0,
        }

        entry = find_matching_toc_entry(chunk, self.flat_toc)

        assert entry is not None
        assert entry["title"] == "628. It is the instincts..."
        assert entry["canonical_ref"] == "CP 1.628"

    def test_paragraph_number_match(self) -> None:
        """Test paragraph number matching with text similarity."""
        chunk: Dict[str, Any] = {
            "section": "42. My philosophy resuscitates Hegel",
            "order_index": 1,
        }

        entry = find_matching_toc_entry(chunk, self.flat_toc)

        assert entry is not None
        assert entry["canonical_ref"] == "CP 1.42"

    def test_no_match_empty_toc(self) -> None:
        """Test behavior with empty TOC."""
        chunk: Dict[str, Any] = {"section": "Some section", "order_index": 0}

        entry = find_matching_toc_entry(chunk, [])

        assert entry is None

    def test_no_match_empty_section(self) -> None:
        """Test behavior with chunk having no section."""
        chunk: Dict[str, Any] = {"text": "Some text", "order_index": 0}

        entry = find_matching_toc_entry(chunk, self.flat_toc)

        # Without section field, function returns None (doesn't guess)
        # This is correct behavior - we don't want to match without text
        assert entry is None

    def test_proximity_match_fallback(self) -> None:
        """Test proximity matching when no text match found."""
        chunk: Dict[str, Any] = {
            "section": "Unknown section",
            "order_index": 1,
        }

        entry = find_matching_toc_entry(chunk, self.flat_toc)

        # Should return entry with closest index_in_flat_list to order_index=1
        assert entry is not None
        assert entry["index_in_flat_list"] == 1


class TestEnrichChunksWithToc:
    """Tests for enrich_chunks_with_toc function."""

    def test_enrich_chunks_no_toc(self) -> None:
        """Test graceful fallback when TOC is absent."""
        chunks: List[Dict[str, Any]] = [
            {"text": "test", "section": "Intro"},
        ]

        enriched = enrich_chunks_with_toc(chunks, [], {})

        assert enriched == chunks  # Unchanged

    def test_enrich_chunks_with_match(self) -> None:
        """Test enrichment with successful TOC matching."""
        chunks: List[Dict[str, Any]] = [
            {"text": "test", "section": "628. It is the instincts..."},
        ]

        toc: List[Dict[str, Any]] = [
            {
                "title": "Peirce: CP 1.628",
                "level": 1,
                "children": [
                    {
                        "title": "628. It is the instincts...",
                        "level": 2,
                        "children": [],
                    },
                ],
            },
        ]

        enriched = enrich_chunks_with_toc(chunks, toc, {})

        assert len(enriched) == 1
        assert "Peirce: CP 1.628" in enriched[0]["sectionPath"]
        assert enriched[0]["chapterTitle"] == "Peirce: CP 1.628"
        assert enriched[0]["canonical_reference"] == "CP 1.628"

    def test_enrich_chunks_partial_match(self) -> None:
        """Test enrichment when only some chunks match."""
        chunks: List[Dict[str, Any]] = [
            {"text": "test1", "section": "628. It is the instincts...", "order_index": 0},
            {"text": "test2", "section": "Unknown section", "order_index": 1},
        ]

        toc: List[Dict[str, Any]] = [
            {
                "title": "Peirce: CP 1.628",
                "level": 1,
                "children": [
                    {
                        "title": "628. It is the instincts...",
                        "level": 2,
                        "children": [],
                    },
                ],
            },
        ]

        enriched = enrich_chunks_with_toc(chunks, toc, {})

        # First chunk should be enriched
        assert "Peirce: CP 1.628" in enriched[0]["sectionPath"]
        assert enriched[0]["canonical_reference"] == "CP 1.628"

        # Second chunk doesn't match, so uses proximity fallback
        # Proximity matching will assign it to the closest TOC entry
        assert "sectionPath" in enriched[1]  # Should get proximity match

    def test_enrich_chunks_preserves_original_fields(self) -> None:
        """Test that enrichment preserves other chunk fields."""
        chunks: List[Dict[str, Any]] = [
            {
                "text": "test",
                "section": "628. It is the instincts...",
                "order_index": 42,
                "keywords": ["test"],
            },
        ]

        toc: List[Dict[str, Any]] = [
            {
                "title": "Peirce: CP 1.628",
                "level": 1,
                "children": [
                    {
                        "title": "628. It is the instincts...",
                        "level": 2,
                        "children": [],
                    },
                ],
            },
        ]

        enriched = enrich_chunks_with_toc(chunks, toc, {})

        # Original fields should be preserved
        assert enriched[0]["text"] == "test"
        assert enriched[0]["order_index"] == 42
        assert enriched[0]["keywords"] == ["test"]
        # New fields should be added
        assert "canonical_reference" in enriched[0]

    def test_enrich_chunks_empty_chunks_list(self) -> None:
        """Test behavior with empty chunks list."""
        toc: List[Dict[str, Any]] = [
            {"title": "Chapter 1", "level": 1, "children": []},
        ]

        enriched = enrich_chunks_with_toc([], toc, {})

        assert enriched == []


# Integration test combining multiple functions
class TestTocEnricherIntegration:
    """Integration tests for the complete enrichment pipeline."""

    def test_full_peirce_enrichment_pipeline(self) -> None:
        """Test complete enrichment pipeline with Peirce data."""
        # Realistic Peirce TOC structure
        toc: List[Dict[str, Any]] = [
            {
                "title": "Peirce: CP 6.628",
                "level": 1,
                "children": [
                    {
                        "title": "628. I think we need to reflect...",
                        "level": 2,
                        "children": [],
                    },
                    {
                        "title": "629. The next point is...",
                        "level": 2,
                        "children": [],
                    },
                ],
            },
        ]

        # Realistic chunks from pdf_pipeline
        chunks: List[Dict[str, Any]] = [
            {
                "text": "I think we need to reflect on the nature of signs...",
                "section": "628. I think we need to reflect...",
                "order_index": 0,
            },
            {
                "text": "The next point is about interpretation...",
                "section": "629. The next point is...",
                "order_index": 1,
            },
        ]

        # Run enrichment
        enriched = enrich_chunks_with_toc(chunks, toc, {})

        # Verify results
        assert len(enriched) == 2

        # First chunk
        assert enriched[0]["sectionPath"] == "Peirce: CP 6.628 > 628. I think we need to reflect..."
        assert enriched[0]["chapterTitle"] == "Peirce: CP 6.628"
        assert enriched[0]["canonical_reference"] == "CP 6.628"

        # Second chunk
        assert enriched[1]["sectionPath"] == "Peirce: CP 6.628 > 629. The next point is..."
        assert enriched[1]["chapterTitle"] == "Peirce: CP 6.628"
        assert enriched[1]["canonical_reference"] == "CP 6.628"
