"""
Unit tests for MCP Pydantic schemas.

Tests schema validation, field constraints, and JSON schema generation.
"""

import pytest
from pydantic import ValidationError

from mcp_tools.schemas import (
    ParsePdfInput,
    ParsePdfOutput,
    SearchChunksInput,
    SearchChunksOutput,
    SearchSummariesInput,
    GetDocumentInput,
    ListDocumentsInput,
    GetChunksByDocumentInput,
    FilterByAuthorInput,
    DeleteDocumentInput,
    ChunkResult,
    DocumentInfo,
)


class TestParsePdfInput:
    """Test ParsePdfInput schema validation."""

    def test_valid_path(self) -> None:
        """Test valid PDF path is accepted."""
        input_data = ParsePdfInput(pdf_path="/path/to/document.pdf")
        assert input_data.pdf_path == "/path/to/document.pdf"

    def test_valid_url(self) -> None:
        """Test valid URL is accepted."""
        input_data = ParsePdfInput(pdf_path="https://example.com/doc.pdf")
        assert input_data.pdf_path == "https://example.com/doc.pdf"

    def test_empty_path_rejected(self) -> None:
        """Test empty path raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            ParsePdfInput(pdf_path="")
        assert "string_too_short" in str(exc_info.value).lower()


class TestParsePdfOutput:
    """Test ParsePdfOutput schema."""

    def test_full_output(self) -> None:
        """Test creating complete output."""
        output = ParsePdfOutput(
            success=True,
            document_name="test-doc",
            source_id="test-doc-v1",
            pages=10,
            chunks_count=25,
            cost_ocr=0.03,
            cost_llm=0.01,
            cost_total=0.04,
            output_dir="/output/test-doc",
            metadata={"title": "Test", "author": "Unknown"},
        )
        assert output.success is True
        assert output.cost_total == 0.04
        assert output.metadata["title"] == "Test"

    def test_output_with_error(self) -> None:
        """Test output with error field set."""
        output = ParsePdfOutput(
            success=False,
            document_name="failed-doc",
            source_id="",
            pages=0,
            chunks_count=0,
            cost_ocr=0.0,
            cost_llm=0.0,
            cost_total=0.0,
            output_dir="",
            error="PDF processing failed: corrupted file",
        )
        assert output.success is False
        assert "corrupted" in output.error  # type: ignore


class TestSearchChunksInput:
    """Test SearchChunksInput schema validation."""

    def test_minimal_input(self) -> None:
        """Test minimal valid input."""
        input_data = SearchChunksInput(query="test query")
        assert input_data.query == "test query"
        assert input_data.limit == 10  # default
        assert input_data.min_similarity == 0.0  # default

    def test_full_input(self) -> None:
        """Test input with all fields."""
        input_data = SearchChunksInput(
            query="What is justice?",
            limit=20,
            min_similarity=0.5,
            author_filter="Platon",
            work_filter="Republic",
            language_filter="fr",
        )
        assert input_data.limit == 20
        assert input_data.author_filter == "Platon"

    def test_empty_query_rejected(self) -> None:
        """Test empty query raises error."""
        with pytest.raises(ValidationError):
            SearchChunksInput(query="")

    def test_query_too_long_rejected(self) -> None:
        """Test query over 1000 chars is rejected."""
        with pytest.raises(ValidationError):
            SearchChunksInput(query="a" * 1001)

    def test_limit_bounds(self) -> None:
        """Test limit validation bounds."""
        with pytest.raises(ValidationError):
            SearchChunksInput(query="test", limit=0)
        with pytest.raises(ValidationError):
            SearchChunksInput(query="test", limit=101)

    def test_similarity_bounds(self) -> None:
        """Test similarity validation bounds."""
        with pytest.raises(ValidationError):
            SearchChunksInput(query="test", min_similarity=-0.1)
        with pytest.raises(ValidationError):
            SearchChunksInput(query="test", min_similarity=1.1)


class TestSearchSummariesInput:
    """Test SearchSummariesInput schema validation."""

    def test_level_filters(self) -> None:
        """Test min/max level filters."""
        input_data = SearchSummariesInput(
            query="test",
            min_level=1,
            max_level=3,
        )
        assert input_data.min_level == 1
        assert input_data.max_level == 3

    def test_level_bounds(self) -> None:
        """Test level validation bounds."""
        with pytest.raises(ValidationError):
            SearchSummariesInput(query="test", min_level=0)
        with pytest.raises(ValidationError):
            SearchSummariesInput(query="test", max_level=6)


class TestGetDocumentInput:
    """Test GetDocumentInput schema validation."""

    def test_defaults(self) -> None:
        """Test default values."""
        input_data = GetDocumentInput(source_id="doc-123")
        assert input_data.include_chunks is False
        assert input_data.chunk_limit == 50

    def test_with_chunks(self) -> None:
        """Test requesting chunks."""
        input_data = GetDocumentInput(
            source_id="doc-123",
            include_chunks=True,
            chunk_limit=100,
        )
        assert input_data.include_chunks is True
        assert input_data.chunk_limit == 100


class TestDeleteDocumentInput:
    """Test DeleteDocumentInput schema validation."""

    def test_requires_confirmation(self) -> None:
        """Test confirm defaults to False."""
        input_data = DeleteDocumentInput(source_id="doc-to-delete")
        assert input_data.confirm is False

    def test_with_confirmation(self) -> None:
        """Test explicit confirmation."""
        input_data = DeleteDocumentInput(
            source_id="doc-to-delete",
            confirm=True,
        )
        assert input_data.confirm is True


class TestChunkResult:
    """Test ChunkResult model."""

    def test_full_chunk(self) -> None:
        """Test creating full chunk result."""
        chunk = ChunkResult(
            text="This is the chunk content.",
            similarity=0.85,
            section_path="Chapter 1 > Section 1",
            chapter_title="Introduction",
            work_title="The Republic",
            work_author="Platon",
            order_index=5,
        )
        assert chunk.similarity == 0.85
        assert chunk.order_index == 5


class TestDocumentInfo:
    """Test DocumentInfo model."""

    def test_with_optional_fields(self) -> None:
        """Test DocumentInfo with all fields."""
        doc = DocumentInfo(
            source_id="platon-republic",
            work_title="The Republic",
            work_author="Platon",
            edition="GF Flammarion",
            pages=500,
            language="fr",
            toc={"chapters": ["I", "II", "III"]},
            hierarchy={"level": 1},
        )
        assert doc.toc is not None
        assert doc.hierarchy is not None


class TestJsonSchemaGeneration:
    """Test JSON schema generation from Pydantic models."""

    def test_schemas_have_descriptions(self) -> None:
        """Test all fields have descriptions for JSON schema."""
        schema = SearchChunksInput.model_json_schema()

        # Check field descriptions exist
        properties = schema["properties"]
        assert "description" in properties["query"]
        assert "description" in properties["limit"]
        assert "description" in properties["min_similarity"]

    def test_schema_includes_constraints(self) -> None:
        """Test validation constraints are in JSON schema."""
        schema = SearchChunksInput.model_json_schema()
        props = schema["properties"]

        # Check minLength constraint
        assert props["query"].get("minLength") == 1
        assert props["query"].get("maxLength") == 1000

        # Check numeric constraints
        assert props["limit"].get("minimum") == 1
        assert props["limit"].get("maximum") == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
