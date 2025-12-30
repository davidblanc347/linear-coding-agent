"""
Unit tests for MCP retrieval tools.

Tests all 7 retrieval tool handlers with mocked Weaviate dependencies:
- search_chunks: Semantic search on text chunks
- search_summaries: Search in chapter/section summaries
- get_document: Retrieve document by ID
- list_documents: List all documents with filtering
- get_chunks_by_document: Get chunks by document ID
- filter_by_author: Filter works by author
- delete_document: Delete a document and all its chunks/summaries

Uses asyncio for async test support and mocks all Weaviate connections.
"""

import asyncio
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from mcp_tools.retrieval_tools import (
    delete_document_handler,
    filter_by_author_handler,
    get_chunks_by_document_handler,
    get_document_handler,
    get_nested_dict,
    get_weaviate_client,
    list_documents_handler,
    safe_int,
    safe_json_parse,
    safe_list,
    safe_str,
    search_chunks_handler,
    search_summaries_handler,
)
from mcp_tools.schemas import (
    ChunkResult,
    DeleteDocumentInput,
    DeleteDocumentOutput,
    DocumentInfo,
    DocumentSummary,
    FilterByAuthorInput,
    FilterByAuthorOutput,
    GetChunksByDocumentInput,
    GetChunksByDocumentOutput,
    GetDocumentInput,
    GetDocumentOutput,
    ListDocumentsInput,
    ListDocumentsOutput,
    SearchChunksInput,
    SearchChunksOutput,
    SearchSummariesInput,
    SearchSummariesOutput,
    SummaryResult,
)
from mcp_tools.exceptions import WeaviateConnectionError


# =============================================================================
# Mock Filter Helper
# =============================================================================


def create_mock_filter() -> MagicMock:
    """Create a mock filter that supports chained operations.

    Returns:
        MagicMock that supports .by_property(), .equal(), .like(),
        .greater_or_equal(), .less_or_equal(), and & operations.
    """
    mock_filter = MagicMock()
    # Make by_property return the same mock for chaining
    mock_filter.by_property.return_value = mock_filter
    mock_filter.equal.return_value = mock_filter
    mock_filter.like.return_value = mock_filter
    mock_filter.greater_or_equal.return_value = mock_filter
    mock_filter.less_or_equal.return_value = mock_filter
    # Support & operator for combining filters
    mock_filter.__and__ = MagicMock(return_value=mock_filter)
    return mock_filter


# =============================================================================
# Test Helper Functions
# =============================================================================


class TestSafeStr:
    """Tests for the safe_str helper function."""

    def test_string_value(self) -> None:
        """Test that string values pass through."""
        assert safe_str("test") == "test"

    def test_none_value(self) -> None:
        """Test that None returns default."""
        assert safe_str(None) == ""
        assert safe_str(None, "default") == "default"

    def test_integer_value(self) -> None:
        """Test that integers are converted to strings."""
        assert safe_str(42) == "42"

    def test_empty_string(self) -> None:
        """Test that empty strings pass through."""
        assert safe_str("") == ""


class TestSafeInt:
    """Tests for the safe_int helper function."""

    def test_integer_value(self) -> None:
        """Test that integer values pass through."""
        assert safe_int(42) == 42

    def test_none_value(self) -> None:
        """Test that None returns default."""
        assert safe_int(None) == 0
        assert safe_int(None, 10) == 10

    def test_string_number(self) -> None:
        """Test that string numbers are converted."""
        assert safe_int("42") == 42

    def test_invalid_string(self) -> None:
        """Test that invalid strings return default."""
        assert safe_int("not a number") == 0
        assert safe_int("not a number", 5) == 5

    def test_float_value(self) -> None:
        """Test that floats are truncated to int."""
        assert safe_int(3.14) == 3


class TestGetNestedDict:
    """Tests for the get_nested_dict helper function."""

    def test_valid_nested_dict(self) -> None:
        """Test extraction of nested dict."""
        props = {"work": {"title": "Test", "author": "Author"}}
        result = get_nested_dict(props, "work")
        assert result == {"title": "Test", "author": "Author"}

    def test_missing_key(self) -> None:
        """Test missing key returns empty dict."""
        props = {"other": "value"}
        result = get_nested_dict(props, "work")
        assert result == {}

    def test_non_dict_value(self) -> None:
        """Test non-dict value returns empty dict."""
        props = {"work": "not a dict"}
        result = get_nested_dict(props, "work")
        assert result == {}


class TestSafeList:
    """Tests for the safe_list helper function."""

    def test_valid_list(self) -> None:
        """Test that list values pass through as strings."""
        assert safe_list(["a", "b", "c"]) == ["a", "b", "c"]

    def test_none_value(self) -> None:
        """Test that None returns empty list."""
        assert safe_list(None) == []

    def test_mixed_list(self) -> None:
        """Test that mixed types are converted to strings."""
        assert safe_list([1, "two", 3.0]) == ["1", "two", "3.0"]


class TestSafeJsonParse:
    """Tests for the safe_json_parse helper function."""

    def test_valid_json_string(self) -> None:
        """Test parsing valid JSON string."""
        result = safe_json_parse('{"key": "value"}')
        assert result == {"key": "value"}

    def test_none_value(self) -> None:
        """Test that None returns None."""
        assert safe_json_parse(None) is None

    def test_dict_passthrough(self) -> None:
        """Test that dict passes through."""
        result = safe_json_parse({"key": "value"})
        assert result == {"key": "value"}

    def test_invalid_json(self) -> None:
        """Test that invalid JSON returns None."""
        assert safe_json_parse("not valid json") is None

    def test_json_array(self) -> None:
        """Test that JSON array returns None (we expect dict)."""
        assert safe_json_parse("[1, 2, 3]") is None


# =============================================================================
# Fixtures for Weaviate Mocking
# =============================================================================


@pytest.fixture
def mock_chunk_object() -> MagicMock:
    """Create a mock Weaviate chunk object."""
    obj = MagicMock()
    obj.properties = {
        "text": "This is a test chunk about justice and virtue.",
        "sectionPath": "Chapter 1 > Section 1",
        "chapterTitle": "Introduction",
        "orderIndex": 1,
        "language": "en",
        "work": {"title": "Test Work", "author": "Test Author"},
        "document": {"sourceId": "test-document"},
    }
    obj.metadata = MagicMock()
    obj.metadata.distance = 0.15  # ~85% similarity
    return obj


@pytest.fixture
def mock_summary_object() -> MagicMock:
    """Create a mock Weaviate summary object."""
    obj = MagicMock()
    obj.properties = {
        "text": "Summary of the chapter discussing virtue.",
        "title": "Chapter 1 Summary",
        "sectionPath": "Chapter 1",
        "level": 1,
        "concepts": ["virtue", "justice", "ethics"],
        "document": {"sourceId": "test-document"},
    }
    obj.metadata = MagicMock()
    obj.metadata.distance = 0.20  # ~80% similarity
    return obj


@pytest.fixture
def mock_document_object() -> MagicMock:
    """Create a mock Weaviate document object."""
    obj = MagicMock()
    obj.properties = {
        "sourceId": "platon-menon",
        "edition": "GF Flammarion",
        "pages": 80,
        "language": "fr",
        "chunksCount": 150,
        "toc": '{"chapters": [{"title": "Introduction"}]}',
        "hierarchy": '{"levels": 3}',
        "work": {"title": "Ménon", "author": "Platon"},
    }
    return obj


@pytest.fixture
def mock_work_object() -> MagicMock:
    """Create a mock Weaviate work object."""
    obj = MagicMock()
    obj.properties = {
        "title": "Ménon",
        "author": "Platon",
        "year": -380,
        "language": "grc",
        "genre": "dialogue",
    }
    return obj


# =============================================================================
# Test search_chunks Tool
# =============================================================================


class TestSearchChunksHandler:
    """Tests for the search_chunks_handler function."""

    def test_basic_search(self, mock_chunk_object: MagicMock) -> None:
        """Test basic semantic search without filters."""

        async def run_test() -> None:
            with patch("mcp_tools.retrieval_tools.get_weaviate_client") as mock_ctx:
                # Setup mock
                mock_client = MagicMock()
                mock_collection = MagicMock()
                mock_result = MagicMock()
                mock_result.objects = [mock_chunk_object]

                mock_collection.query.near_text.return_value = mock_result
                mock_client.collections.get.return_value = mock_collection
                mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_client)
                mock_ctx.return_value.__exit__ = MagicMock(return_value=None)

                input_data = SearchChunksInput(query="justice and virtue", limit=10)
                result = await search_chunks_handler(input_data)

                assert isinstance(result, SearchChunksOutput)
                assert result.query == "justice and virtue"
                assert result.total_count == 1
                assert len(result.results) == 1
                assert result.results[0].text == "This is a test chunk about justice and virtue."
                assert result.results[0].similarity == 0.85  # 1 - 0.15

        asyncio.run(run_test())

    def test_search_with_author_filter(self, mock_chunk_object: MagicMock) -> None:
        """Test search with author filter."""

        async def run_test() -> None:
            with patch("mcp_tools.retrieval_tools.get_weaviate_client") as mock_ctx:
                with patch("mcp_tools.retrieval_tools.Filter") as mock_filter_class:
                    # Setup filter mock
                    mock_filter_class.by_property.return_value = create_mock_filter()

                    mock_client = MagicMock()
                    mock_collection = MagicMock()
                    mock_result = MagicMock()
                    mock_result.objects = [mock_chunk_object]

                    mock_collection.query.near_text.return_value = mock_result
                    mock_client.collections.get.return_value = mock_collection
                    mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_client)
                    mock_ctx.return_value.__exit__ = MagicMock(return_value=None)

                    input_data = SearchChunksInput(
                        query="virtue",
                        limit=5,
                        author_filter="Platon",
                    )
                    result = await search_chunks_handler(input_data)

                    assert result.total_count == 1
                    mock_collection.query.near_text.assert_called_once()

        asyncio.run(run_test())

    def test_search_with_min_similarity_filter(self, mock_chunk_object: MagicMock) -> None:
        """Test that min_similarity filters out low-scoring results."""

        async def run_test() -> None:
            with patch("mcp_tools.retrieval_tools.get_weaviate_client") as mock_ctx:
                mock_client = MagicMock()
                mock_collection = MagicMock()
                mock_result = MagicMock()

                # Set distance to give 0.7 similarity (below 0.8 threshold)
                mock_chunk_object.metadata.distance = 0.30
                mock_result.objects = [mock_chunk_object]

                mock_collection.query.near_text.return_value = mock_result
                mock_client.collections.get.return_value = mock_collection
                mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_client)
                mock_ctx.return_value.__exit__ = MagicMock(return_value=None)

                input_data = SearchChunksInput(
                    query="virtue",
                    min_similarity=0.8,
                )
                result = await search_chunks_handler(input_data)

                # Result should be filtered out due to low similarity
                assert result.total_count == 0

        asyncio.run(run_test())

    def test_search_empty_results(self) -> None:
        """Test handling of empty search results."""

        async def run_test() -> None:
            with patch("mcp_tools.retrieval_tools.get_weaviate_client") as mock_ctx:
                mock_client = MagicMock()
                mock_collection = MagicMock()
                mock_result = MagicMock()
                mock_result.objects = []

                mock_collection.query.near_text.return_value = mock_result
                mock_client.collections.get.return_value = mock_collection
                mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_client)
                mock_ctx.return_value.__exit__ = MagicMock(return_value=None)

                input_data = SearchChunksInput(query="nonexistent topic")
                result = await search_chunks_handler(input_data)

                assert result.total_count == 0
                assert result.results == []

        asyncio.run(run_test())

    def test_search_weaviate_connection_error(self) -> None:
        """Test error handling when Weaviate connection fails."""

        async def run_test() -> None:
            with patch("mcp_tools.retrieval_tools.get_weaviate_client") as mock_ctx:
                mock_ctx.return_value.__enter__ = MagicMock(
                    side_effect=WeaviateConnectionError("Connection failed")
                )
                mock_ctx.return_value.__exit__ = MagicMock(return_value=None)

                input_data = SearchChunksInput(query="test")
                with pytest.raises(WeaviateConnectionError):
                    await search_chunks_handler(input_data)

        asyncio.run(run_test())


# =============================================================================
# Test search_summaries Tool
# =============================================================================


class TestSearchSummariesHandler:
    """Tests for the search_summaries_handler function."""

    def test_basic_summary_search(self, mock_summary_object: MagicMock) -> None:
        """Test basic summary search without level filters."""

        async def run_test() -> None:
            with patch("mcp_tools.retrieval_tools.get_weaviate_client") as mock_ctx:
                mock_client = MagicMock()
                mock_collection = MagicMock()
                mock_result = MagicMock()
                mock_result.objects = [mock_summary_object]

                mock_collection.query.near_text.return_value = mock_result
                mock_client.collections.get.return_value = mock_collection
                mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_client)
                mock_ctx.return_value.__exit__ = MagicMock(return_value=None)

                input_data = SearchSummariesInput(query="virtue and ethics", limit=5)
                result = await search_summaries_handler(input_data)

                assert isinstance(result, SearchSummariesOutput)
                assert result.query == "virtue and ethics"
                assert result.total_count == 1
                assert result.results[0].text == "Summary of the chapter discussing virtue."
                assert result.results[0].level == 1

        asyncio.run(run_test())

    def test_summary_search_with_level_filters(
        self, mock_summary_object: MagicMock
    ) -> None:
        """Test summary search with min/max level filters."""

        async def run_test() -> None:
            with patch("mcp_tools.retrieval_tools.get_weaviate_client") as mock_ctx:
                mock_client = MagicMock()
                mock_collection = MagicMock()
                mock_result = MagicMock()
                mock_result.objects = [mock_summary_object]

                mock_collection.query.near_text.return_value = mock_result
                mock_client.collections.get.return_value = mock_collection
                mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_client)
                mock_ctx.return_value.__exit__ = MagicMock(return_value=None)

                input_data = SearchSummariesInput(
                    query="virtue",
                    min_level=1,
                    max_level=2,
                )
                result = await search_summaries_handler(input_data)

                assert result.total_count == 1
                mock_collection.query.near_text.assert_called_once()

        asyncio.run(run_test())

    def test_summary_search_empty_results(self) -> None:
        """Test handling of empty summary search results."""

        async def run_test() -> None:
            with patch("mcp_tools.retrieval_tools.get_weaviate_client") as mock_ctx:
                mock_client = MagicMock()
                mock_collection = MagicMock()
                mock_result = MagicMock()
                mock_result.objects = []

                mock_collection.query.near_text.return_value = mock_result
                mock_client.collections.get.return_value = mock_collection
                mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_client)
                mock_ctx.return_value.__exit__ = MagicMock(return_value=None)

                input_data = SearchSummariesInput(query="nonexistent")
                result = await search_summaries_handler(input_data)

                assert result.total_count == 0
                assert result.results == []

        asyncio.run(run_test())


# =============================================================================
# Test get_document Tool
# =============================================================================


class TestGetDocumentHandler:
    """Tests for the get_document_handler function."""

    def test_get_document_found(self, mock_document_object: MagicMock) -> None:
        """Test retrieving an existing document."""

        async def run_test() -> None:
            with patch("mcp_tools.retrieval_tools.get_weaviate_client") as mock_ctx:
                mock_client = MagicMock()
                mock_collection = MagicMock()
                mock_result = MagicMock()
                mock_result.objects = [mock_document_object]

                mock_collection.query.fetch_objects.return_value = mock_result
                mock_client.collections.get.return_value = mock_collection
                mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_client)
                mock_ctx.return_value.__exit__ = MagicMock(return_value=None)

                input_data = GetDocumentInput(source_id="platon-menon")
                result = await get_document_handler(input_data)

                assert isinstance(result, GetDocumentOutput)
                assert result.found is True
                assert result.document is not None
                assert result.document.source_id == "platon-menon"
                assert result.document.work_title == "Ménon"
                assert result.document.work_author == "Platon"
                assert result.chunks_total == 150

        asyncio.run(run_test())

    def test_get_document_not_found(self) -> None:
        """Test retrieving a non-existent document."""

        async def run_test() -> None:
            with patch("mcp_tools.retrieval_tools.get_weaviate_client") as mock_ctx:
                mock_client = MagicMock()
                mock_collection = MagicMock()
                mock_result = MagicMock()
                mock_result.objects = []

                mock_collection.query.fetch_objects.return_value = mock_result
                mock_client.collections.get.return_value = mock_collection
                mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_client)
                mock_ctx.return_value.__exit__ = MagicMock(return_value=None)

                input_data = GetDocumentInput(source_id="nonexistent-document")
                result = await get_document_handler(input_data)

                assert result.found is False
                assert result.document is None
                assert "not found" in result.error.lower()

        asyncio.run(run_test())

    def test_get_document_with_chunks(
        self, mock_document_object: MagicMock, mock_chunk_object: MagicMock
    ) -> None:
        """Test retrieving document with chunks included."""

        async def run_test() -> None:
            with patch("mcp_tools.retrieval_tools.get_weaviate_client") as mock_ctx:
                with patch("mcp_tools.retrieval_tools.Filter") as mock_filter_class:
                    # Setup filter mock
                    mock_filter_class.by_property.return_value = create_mock_filter()

                    mock_client = MagicMock()

                    # Mock Document collection
                    mock_doc_collection = MagicMock()
                    mock_doc_result = MagicMock()
                    mock_doc_result.objects = [mock_document_object]
                    mock_doc_collection.query.fetch_objects.return_value = mock_doc_result

                    # Mock Chunk collection
                    mock_chunk_collection = MagicMock()
                    mock_chunk_result = MagicMock()
                    mock_chunk_result.objects = [mock_chunk_object]
                    mock_chunk_collection.query.fetch_objects.return_value = mock_chunk_result

                    def get_collection(name: str) -> MagicMock:
                        if name == "Document":
                            return mock_doc_collection
                        elif name == "Chunk":
                            return mock_chunk_collection
                        return MagicMock()

                    mock_client.collections.get.side_effect = get_collection
                    mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_client)
                    mock_ctx.return_value.__exit__ = MagicMock(return_value=None)

                    input_data = GetDocumentInput(
                        source_id="platon-menon",
                        include_chunks=True,
                        chunk_limit=50,
                    )
                    result = await get_document_handler(input_data)

                    assert result.found is True
                    assert len(result.chunks) == 1
                    assert result.chunks[0].text == "This is a test chunk about justice and virtue."

        asyncio.run(run_test())


# =============================================================================
# Test list_documents Tool
# =============================================================================


class TestListDocumentsHandler:
    """Tests for the list_documents_handler function."""

    def test_list_documents_basic(self, mock_document_object: MagicMock) -> None:
        """Test basic document listing."""

        async def run_test() -> None:
            with patch("mcp_tools.retrieval_tools.get_weaviate_client") as mock_ctx:
                mock_client = MagicMock()
                mock_collection = MagicMock()
                mock_result = MagicMock()
                mock_result.objects = [mock_document_object]

                mock_collection.query.fetch_objects.return_value = mock_result
                mock_client.collections.get.return_value = mock_collection
                mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_client)
                mock_ctx.return_value.__exit__ = MagicMock(return_value=None)

                input_data = ListDocumentsInput()
                result = await list_documents_handler(input_data)

                assert isinstance(result, ListDocumentsOutput)
                assert result.total_count == 1
                assert len(result.documents) == 1
                assert result.documents[0].source_id == "platon-menon"

        asyncio.run(run_test())

    def test_list_documents_with_filters(
        self, mock_document_object: MagicMock
    ) -> None:
        """Test document listing with filters."""

        async def run_test() -> None:
            with patch("mcp_tools.retrieval_tools.get_weaviate_client") as mock_ctx:
                with patch("mcp_tools.retrieval_tools.Filter") as mock_filter_class:
                    # Setup filter mock
                    mock_filter_class.by_property.return_value = create_mock_filter()

                    mock_client = MagicMock()
                    mock_collection = MagicMock()
                    mock_result = MagicMock()
                    mock_result.objects = [mock_document_object]

                    mock_collection.query.fetch_objects.return_value = mock_result
                    mock_client.collections.get.return_value = mock_collection
                    mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_client)
                    mock_ctx.return_value.__exit__ = MagicMock(return_value=None)

                    input_data = ListDocumentsInput(
                        author_filter="Platon",
                        language_filter="fr",
                        limit=10,
                    )
                    result = await list_documents_handler(input_data)

                    assert result.limit == 10
                    assert result.offset == 0
                    mock_collection.query.fetch_objects.assert_called()

        asyncio.run(run_test())

    def test_list_documents_pagination(
        self, mock_document_object: MagicMock
    ) -> None:
        """Test document listing with pagination."""

        async def run_test() -> None:
            with patch("mcp_tools.retrieval_tools.get_weaviate_client") as mock_ctx:
                mock_client = MagicMock()
                mock_collection = MagicMock()
                mock_result = MagicMock()
                # Simulate multiple documents
                mock_result.objects = [mock_document_object, mock_document_object]

                mock_collection.query.fetch_objects.return_value = mock_result
                mock_client.collections.get.return_value = mock_collection
                mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_client)
                mock_ctx.return_value.__exit__ = MagicMock(return_value=None)

                input_data = ListDocumentsInput(limit=1, offset=1)
                result = await list_documents_handler(input_data)

                # Should return 1 document (offset skips first)
                assert result.limit == 1
                assert result.offset == 1
                assert len(result.documents) == 1

        asyncio.run(run_test())

    def test_list_documents_empty(self) -> None:
        """Test listing when no documents exist."""

        async def run_test() -> None:
            with patch("mcp_tools.retrieval_tools.get_weaviate_client") as mock_ctx:
                mock_client = MagicMock()
                mock_collection = MagicMock()
                mock_result = MagicMock()
                mock_result.objects = []

                mock_collection.query.fetch_objects.return_value = mock_result
                mock_client.collections.get.return_value = mock_collection
                mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_client)
                mock_ctx.return_value.__exit__ = MagicMock(return_value=None)

                input_data = ListDocumentsInput()
                result = await list_documents_handler(input_data)

                assert result.total_count == 0
                assert result.documents == []

        asyncio.run(run_test())


# =============================================================================
# Test get_chunks_by_document Tool
# =============================================================================


class TestGetChunksByDocumentHandler:
    """Tests for the get_chunks_by_document_handler function."""

    def test_get_chunks_by_document_basic(
        self, mock_chunk_object: MagicMock
    ) -> None:
        """Test basic chunk retrieval by document."""

        async def run_test() -> None:
            with patch("mcp_tools.retrieval_tools.get_weaviate_client") as mock_ctx:
                with patch("mcp_tools.retrieval_tools.Filter") as mock_filter_class:
                    # Setup filter mock
                    mock_filter_class.by_property.return_value = create_mock_filter()

                    mock_client = MagicMock()
                    mock_collection = MagicMock()
                    mock_result = MagicMock()
                    mock_result.objects = [mock_chunk_object]

                    mock_collection.query.fetch_objects.return_value = mock_result
                    mock_client.collections.get.return_value = mock_collection
                    mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_client)
                    mock_ctx.return_value.__exit__ = MagicMock(return_value=None)

                    input_data = GetChunksByDocumentInput(source_id="test-document")
                    result = await get_chunks_by_document_handler(input_data)

                    assert isinstance(result, GetChunksByDocumentOutput)
                    assert result.document_source_id == "test-document"
                    assert result.total_count == 1
                    assert len(result.chunks) == 1

        asyncio.run(run_test())

    def test_get_chunks_ordering(self) -> None:
        """Test that chunks are ordered by order_index."""

        async def run_test() -> None:
            with patch("mcp_tools.retrieval_tools.get_weaviate_client") as mock_ctx:
                with patch("mcp_tools.retrieval_tools.Filter") as mock_filter_class:
                    # Setup filter mock
                    mock_filter_class.by_property.return_value = create_mock_filter()

                    mock_client = MagicMock()
                    mock_collection = MagicMock()
                    mock_result = MagicMock()

                    # Create chunks with different order indices
                    chunk1 = MagicMock()
                    chunk1.properties = {
                        "text": "Second chunk",
                        "sectionPath": "",
                        "chapterTitle": None,
                        "orderIndex": 2,
                        "work": {"title": "Test", "author": "Author"},
                    }

                    chunk2 = MagicMock()
                    chunk2.properties = {
                        "text": "First chunk",
                        "sectionPath": "",
                        "chapterTitle": None,
                        "orderIndex": 1,
                        "work": {"title": "Test", "author": "Author"},
                    }

                    mock_result.objects = [chunk1, chunk2]  # Out of order

                    mock_collection.query.fetch_objects.return_value = mock_result
                    mock_client.collections.get.return_value = mock_collection
                    mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_client)
                    mock_ctx.return_value.__exit__ = MagicMock(return_value=None)

                    input_data = GetChunksByDocumentInput(source_id="test-document")
                    result = await get_chunks_by_document_handler(input_data)

                    # Should be sorted by order_index
                    assert result.chunks[0].order_index == 1
                    assert result.chunks[0].text == "First chunk"
                    assert result.chunks[1].order_index == 2
                    assert result.chunks[1].text == "Second chunk"

        asyncio.run(run_test())

    def test_get_chunks_with_section_filter(
        self, mock_chunk_object: MagicMock
    ) -> None:
        """Test chunk retrieval with section filter."""

        async def run_test() -> None:
            with patch("mcp_tools.retrieval_tools.get_weaviate_client") as mock_ctx:
                with patch("mcp_tools.retrieval_tools.Filter") as mock_filter_class:
                    # Setup filter mock
                    mock_filter_class.by_property.return_value = create_mock_filter()

                    mock_client = MagicMock()
                    mock_collection = MagicMock()
                    mock_result = MagicMock()
                    mock_result.objects = [mock_chunk_object]

                    mock_collection.query.fetch_objects.return_value = mock_result
                    mock_client.collections.get.return_value = mock_collection
                    mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_client)
                    mock_ctx.return_value.__exit__ = MagicMock(return_value=None)

                    input_data = GetChunksByDocumentInput(
                        source_id="test-document",
                        section_filter="Chapter 1",
                    )
                    result = await get_chunks_by_document_handler(input_data)

                    assert result.total_count == 1
                    mock_collection.query.fetch_objects.assert_called()

        asyncio.run(run_test())

    def test_get_chunks_pagination(self, mock_chunk_object: MagicMock) -> None:
        """Test chunk retrieval with pagination."""

        async def run_test() -> None:
            with patch("mcp_tools.retrieval_tools.get_weaviate_client") as mock_ctx:
                with patch("mcp_tools.retrieval_tools.Filter") as mock_filter_class:
                    # Setup filter mock
                    mock_filter_class.by_property.return_value = create_mock_filter()

                    mock_client = MagicMock()
                    mock_collection = MagicMock()
                    mock_result = MagicMock()
                    # Simulate 3 chunks
                    mock_result.objects = [
                        mock_chunk_object,
                        mock_chunk_object,
                        mock_chunk_object,
                    ]

                    mock_collection.query.fetch_objects.return_value = mock_result
                    mock_client.collections.get.return_value = mock_collection
                    mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_client)
                    mock_ctx.return_value.__exit__ = MagicMock(return_value=None)

                    input_data = GetChunksByDocumentInput(
                        source_id="test-document",
                        limit=2,
                        offset=1,
                    )
                    result = await get_chunks_by_document_handler(input_data)

                    assert result.limit == 2
                    assert result.offset == 1
                    # With offset=1, should skip first and take next 2
                    assert len(result.chunks) == 2

        asyncio.run(run_test())


# =============================================================================
# Test filter_by_author Tool
# =============================================================================


class TestFilterByAuthorHandler:
    """Tests for the filter_by_author_handler function."""

    def test_filter_by_author_basic(
        self, mock_work_object: MagicMock, mock_document_object: MagicMock
    ) -> None:
        """Test basic author filtering."""

        async def run_test() -> None:
            with patch("mcp_tools.retrieval_tools.get_weaviate_client") as mock_ctx:
                with patch("mcp_tools.retrieval_tools.Filter") as mock_filter_class:
                    # Setup filter mock
                    mock_filter_class.by_property.return_value = create_mock_filter()

                    mock_client = MagicMock()

                    # Mock Work collection
                    mock_work_collection = MagicMock()
                    mock_work_result = MagicMock()
                    mock_work_result.objects = [mock_work_object]
                    mock_work_collection.query.fetch_objects.return_value = mock_work_result

                    # Mock Document collection
                    mock_doc_collection = MagicMock()
                    mock_doc_result = MagicMock()
                    mock_doc_result.objects = [mock_document_object]
                    mock_doc_collection.query.fetch_objects.return_value = mock_doc_result

                    # Mock Chunk collection (for chunk counts)
                    mock_chunk_collection = MagicMock()
                    mock_chunk_result = MagicMock()
                    mock_chunk_result.objects = []
                    mock_chunk_collection.query.fetch_objects.return_value = mock_chunk_result

                    def get_collection(name: str) -> MagicMock:
                        if name == "Work":
                            return mock_work_collection
                        elif name == "Document":
                            return mock_doc_collection
                        elif name == "Chunk":
                            return mock_chunk_collection
                        return MagicMock()

                    mock_client.collections.get.side_effect = get_collection
                    mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_client)
                    mock_ctx.return_value.__exit__ = MagicMock(return_value=None)

                    input_data = FilterByAuthorInput(author="Platon")
                    result = await filter_by_author_handler(input_data)

                    assert isinstance(result, FilterByAuthorOutput)
                    assert result.author == "Platon"
                    assert result.total_works == 1
                    assert result.total_documents == 1
                    assert result.works[0].work.title == "Ménon"

        asyncio.run(run_test())

    def test_filter_by_author_no_works(self) -> None:
        """Test author filtering when author has no works."""

        async def run_test() -> None:
            with patch("mcp_tools.retrieval_tools.get_weaviate_client") as mock_ctx:
                with patch("mcp_tools.retrieval_tools.Filter") as mock_filter_class:
                    # Setup filter mock
                    mock_filter_class.by_property.return_value = create_mock_filter()

                    mock_client = MagicMock()
                    mock_work_collection = MagicMock()
                    mock_work_result = MagicMock()
                    mock_work_result.objects = []
                    mock_work_collection.query.fetch_objects.return_value = mock_work_result

                    # Need to mock Document and Chunk too as they're retrieved in the function
                    mock_doc_collection = MagicMock()
                    mock_chunk_collection = MagicMock()

                    def get_collection(name: str) -> MagicMock:
                        if name == "Work":
                            return mock_work_collection
                        elif name == "Document":
                            return mock_doc_collection
                        elif name == "Chunk":
                            return mock_chunk_collection
                        return MagicMock()

                    mock_client.collections.get.side_effect = get_collection
                    mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_client)
                    mock_ctx.return_value.__exit__ = MagicMock(return_value=None)

                    input_data = FilterByAuthorInput(author="Unknown Author")
                    result = await filter_by_author_handler(input_data)

                    assert result.total_works == 0
                    assert result.total_documents == 0
                    assert result.works == []

        asyncio.run(run_test())

    def test_filter_by_author_chunk_counts(
        self, mock_work_object: MagicMock, mock_document_object: MagicMock
    ) -> None:
        """Test that chunk counts are aggregated correctly."""

        async def run_test() -> None:
            with patch("mcp_tools.retrieval_tools.get_weaviate_client") as mock_ctx:
                with patch("mcp_tools.retrieval_tools.Filter") as mock_filter_class:
                    # Setup filter mock
                    mock_filter_class.by_property.return_value = create_mock_filter()

                    mock_client = MagicMock()

                    # Mock Work collection
                    mock_work_collection = MagicMock()
                    mock_work_result = MagicMock()
                    mock_work_result.objects = [mock_work_object]
                    mock_work_collection.query.fetch_objects.return_value = mock_work_result

                    # Mock Document collection with chunksCount
                    mock_doc_collection = MagicMock()
                    mock_doc_result = MagicMock()
                    mock_document_object.properties["chunksCount"] = 150
                    mock_doc_result.objects = [mock_document_object]
                    mock_doc_collection.query.fetch_objects.return_value = mock_doc_result

                    # Mock Chunk collection
                    mock_chunk_collection = MagicMock()
                    mock_chunk_result = MagicMock()
                    mock_chunk_result.objects = []
                    mock_chunk_collection.query.fetch_objects.return_value = mock_chunk_result

                    def get_collection(name: str) -> MagicMock:
                        if name == "Work":
                            return mock_work_collection
                        elif name == "Document":
                            return mock_doc_collection
                        elif name == "Chunk":
                            return mock_chunk_collection
                        return MagicMock()

                    mock_client.collections.get.side_effect = get_collection
                    mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_client)
                    mock_ctx.return_value.__exit__ = MagicMock(return_value=None)

                    input_data = FilterByAuthorInput(
                        author="Platon", include_chunk_counts=True
                    )
                    result = await filter_by_author_handler(input_data)

                    assert result.total_chunks == 150

        asyncio.run(run_test())


# =============================================================================
# Test delete_document Tool
# =============================================================================


class TestDeleteDocumentHandler:
    """Tests for the delete_document_handler function."""

    def test_delete_document_without_confirmation(self) -> None:
        """Test that deletion fails without confirmation."""

        async def run_test() -> None:
            input_data = DeleteDocumentInput(
                source_id="test-document",
                confirm=False,
            )
            result = await delete_document_handler(input_data)

            assert isinstance(result, DeleteDocumentOutput)
            assert result.success is False
            assert "confirmation required" in result.error.lower()
            assert result.chunks_deleted == 0
            assert result.summaries_deleted == 0

        asyncio.run(run_test())

    def test_delete_document_with_confirmation(self) -> None:
        """Test successful document deletion with confirmation."""

        async def run_test() -> None:
            with patch("mcp_tools.retrieval_tools.get_weaviate_client") as mock_ctx:
                with patch("mcp_tools.retrieval_tools.Filter") as mock_filter_class:
                    # Setup filter mock
                    mock_filter_class.by_property.return_value = create_mock_filter()

                    mock_client = MagicMock()

                    # Mock Chunk collection
                    mock_chunk_collection = MagicMock()
                    mock_chunk_delete = MagicMock()
                    mock_chunk_delete.successful = 10
                    mock_chunk_collection.data.delete_many.return_value = mock_chunk_delete

                    # Mock Summary collection
                    mock_summary_collection = MagicMock()
                    mock_summary_delete = MagicMock()
                    mock_summary_delete.successful = 3
                    mock_summary_collection.data.delete_many.return_value = mock_summary_delete

                    # Mock Document collection
                    mock_doc_collection = MagicMock()
                    mock_doc_delete = MagicMock()
                    mock_doc_delete.successful = 1
                    mock_doc_collection.data.delete_many.return_value = mock_doc_delete

                    def get_collection(name: str) -> MagicMock:
                        if name == "Chunk":
                            return mock_chunk_collection
                        elif name == "Summary":
                            return mock_summary_collection
                        elif name == "Document":
                            return mock_doc_collection
                        return MagicMock()

                    mock_client.collections.get.side_effect = get_collection
                    mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_client)
                    mock_ctx.return_value.__exit__ = MagicMock(return_value=None)

                    input_data = DeleteDocumentInput(
                        source_id="test-document",
                        confirm=True,
                    )
                    result = await delete_document_handler(input_data)

                    assert result.success is True
                    assert result.source_id == "test-document"
                    assert result.chunks_deleted == 10
                    assert result.summaries_deleted == 3
                    assert result.error is None

        asyncio.run(run_test())

    def test_delete_document_weaviate_error(self) -> None:
        """Test error handling when Weaviate connection fails during deletion."""

        async def run_test() -> None:
            with patch("mcp_tools.retrieval_tools.get_weaviate_client") as mock_ctx:
                mock_ctx.return_value.__enter__ = MagicMock(
                    side_effect=WeaviateConnectionError("Connection failed")
                )
                mock_ctx.return_value.__exit__ = MagicMock(return_value=None)

                input_data = DeleteDocumentInput(
                    source_id="test-document",
                    confirm=True,
                )
                with pytest.raises(WeaviateConnectionError):
                    await delete_document_handler(input_data)

        asyncio.run(run_test())

    def test_delete_document_partial_failure(self) -> None:
        """Test that partial failures are handled gracefully."""

        async def run_test() -> None:
            with patch("mcp_tools.retrieval_tools.get_weaviate_client") as mock_ctx:
                with patch("mcp_tools.retrieval_tools.Filter") as mock_filter_class:
                    # Setup filter mock
                    mock_filter_class.by_property.return_value = create_mock_filter()

                    mock_client = MagicMock()

                    # Mock Chunk collection - success
                    mock_chunk_collection = MagicMock()
                    mock_chunk_delete = MagicMock()
                    mock_chunk_delete.successful = 5
                    mock_chunk_collection.data.delete_many.return_value = mock_chunk_delete

                    # Mock Summary collection - raises exception
                    mock_summary_collection = MagicMock()
                    mock_summary_collection.data.delete_many.side_effect = Exception(
                        "Summary delete failed"
                    )

                    # Mock Document collection - success
                    mock_doc_collection = MagicMock()
                    mock_doc_delete = MagicMock()
                    mock_doc_delete.successful = 1
                    mock_doc_collection.data.delete_many.return_value = mock_doc_delete

                    def get_collection(name: str) -> MagicMock:
                        if name == "Chunk":
                            return mock_chunk_collection
                        elif name == "Summary":
                            return mock_summary_collection
                        elif name == "Document":
                            return mock_doc_collection
                        return MagicMock()

                    mock_client.collections.get.side_effect = get_collection
                    mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_client)
                    mock_ctx.return_value.__exit__ = MagicMock(return_value=None)

                    input_data = DeleteDocumentInput(
                        source_id="test-document",
                        confirm=True,
                    )
                    result = await delete_document_handler(input_data)

                    # Should still succeed, partial failure is handled
                    assert result.success is True
                    assert result.chunks_deleted == 5
                    assert result.summaries_deleted == 0  # Failed

        asyncio.run(run_test())


# =============================================================================
# Test Output Schema Validation
# =============================================================================


class TestOutputSchemaValidation:
    """Tests for output schema compliance across all retrieval tools."""

    def test_search_chunks_output_schema(
        self, mock_chunk_object: MagicMock
    ) -> None:
        """Test that SearchChunksOutput conforms to schema."""

        async def run_test() -> None:
            with patch("mcp_tools.retrieval_tools.get_weaviate_client") as mock_ctx:
                mock_client = MagicMock()
                mock_collection = MagicMock()
                mock_result = MagicMock()
                mock_result.objects = [mock_chunk_object]

                mock_collection.query.near_text.return_value = mock_result
                mock_client.collections.get.return_value = mock_collection
                mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_client)
                mock_ctx.return_value.__exit__ = MagicMock(return_value=None)

                input_data = SearchChunksInput(query="test")
                result = await search_chunks_handler(input_data)

                assert isinstance(result, SearchChunksOutput)
                assert hasattr(result, "results")
                assert hasattr(result, "total_count")
                assert hasattr(result, "query")
                assert all(isinstance(r, ChunkResult) for r in result.results)

        asyncio.run(run_test())

    def test_search_summaries_output_schema(
        self, mock_summary_object: MagicMock
    ) -> None:
        """Test that SearchSummariesOutput conforms to schema."""

        async def run_test() -> None:
            with patch("mcp_tools.retrieval_tools.get_weaviate_client") as mock_ctx:
                mock_client = MagicMock()
                mock_collection = MagicMock()
                mock_result = MagicMock()
                mock_result.objects = [mock_summary_object]

                mock_collection.query.near_text.return_value = mock_result
                mock_client.collections.get.return_value = mock_collection
                mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_client)
                mock_ctx.return_value.__exit__ = MagicMock(return_value=None)

                input_data = SearchSummariesInput(query="test")
                result = await search_summaries_handler(input_data)

                assert isinstance(result, SearchSummariesOutput)
                assert hasattr(result, "results")
                assert hasattr(result, "total_count")
                assert hasattr(result, "query")
                assert all(isinstance(r, SummaryResult) for r in result.results)

        asyncio.run(run_test())

    def test_get_document_output_schema(
        self, mock_document_object: MagicMock
    ) -> None:
        """Test that GetDocumentOutput conforms to schema."""

        async def run_test() -> None:
            with patch("mcp_tools.retrieval_tools.get_weaviate_client") as mock_ctx:
                mock_client = MagicMock()
                mock_collection = MagicMock()
                mock_result = MagicMock()
                mock_result.objects = [mock_document_object]

                mock_collection.query.fetch_objects.return_value = mock_result
                mock_client.collections.get.return_value = mock_collection
                mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_client)
                mock_ctx.return_value.__exit__ = MagicMock(return_value=None)

                input_data = GetDocumentInput(source_id="test")
                result = await get_document_handler(input_data)

                assert isinstance(result, GetDocumentOutput)
                assert hasattr(result, "document")
                assert hasattr(result, "chunks")
                assert hasattr(result, "chunks_total")
                assert hasattr(result, "found")
                if result.document:
                    assert isinstance(result.document, DocumentInfo)

        asyncio.run(run_test())

    def test_list_documents_output_schema(
        self, mock_document_object: MagicMock
    ) -> None:
        """Test that ListDocumentsOutput conforms to schema."""

        async def run_test() -> None:
            with patch("mcp_tools.retrieval_tools.get_weaviate_client") as mock_ctx:
                mock_client = MagicMock()
                mock_collection = MagicMock()
                mock_result = MagicMock()
                mock_result.objects = [mock_document_object]

                mock_collection.query.fetch_objects.return_value = mock_result
                mock_client.collections.get.return_value = mock_collection
                mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_client)
                mock_ctx.return_value.__exit__ = MagicMock(return_value=None)

                input_data = ListDocumentsInput()
                result = await list_documents_handler(input_data)

                assert isinstance(result, ListDocumentsOutput)
                assert hasattr(result, "documents")
                assert hasattr(result, "total_count")
                assert hasattr(result, "limit")
                assert hasattr(result, "offset")
                assert all(isinstance(d, DocumentSummary) for d in result.documents)

        asyncio.run(run_test())

    def test_delete_document_output_schema(self) -> None:
        """Test that DeleteDocumentOutput conforms to schema."""

        async def run_test() -> None:
            input_data = DeleteDocumentInput(source_id="test", confirm=False)
            result = await delete_document_handler(input_data)

            assert isinstance(result, DeleteDocumentOutput)
            assert hasattr(result, "success")
            assert hasattr(result, "source_id")
            assert hasattr(result, "chunks_deleted")
            assert hasattr(result, "summaries_deleted")
            assert hasattr(result, "error")

        asyncio.run(run_test())
