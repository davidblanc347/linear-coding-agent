#!/usr/bin/env python3
"""Unit tests for Works Filter backend routes.

Tests the /api/get-works and /chat/send selected_works parameter functionality.
All Weaviate operations are mocked - no real database calls.

LRP-146: Testing - Tests backend routes
"""

import json
from typing import Any, Dict, Generator, List
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_chunk_objects() -> List[MagicMock]:
    """Create mock Weaviate chunk objects with work metadata.

    Returns:
        List of MagicMock objects simulating Weaviate chunk results.
    """
    # Create test data representing chunks from different works
    test_works = [
        {"title": "Ménon", "author": "Platon"},
        {"title": "Ménon", "author": "Platon"},
        {"title": "Ménon", "author": "Platon"},
        {"title": "La logique de la science", "author": "Charles Sanders Peirce"},
        {"title": "La logique de la science", "author": "Charles Sanders Peirce"},
        {"title": "La pensée-signe", "author": "Claudine Tiercelin"},
    ]

    mock_objects = []
    for work in test_works:
        obj = MagicMock()
        obj.properties = {"work": work}
        mock_objects.append(obj)

    return mock_objects


@pytest.fixture
def mock_weaviate_client_get_works(
    mock_chunk_objects: List[MagicMock],
) -> Generator[MagicMock, None, None]:
    """Provide a mocked Weaviate client for /api/get-works tests.

    Args:
        mock_chunk_objects: List of mock chunk objects.

    Yields:
        MagicMock configured as a Weaviate client with chunks.
    """
    with patch("flask_app.get_weaviate_client") as mock_context:
        mock_client = MagicMock()

        # Mock the chunks collection
        mock_chunks_collection = MagicMock()
        mock_query_result = MagicMock()
        mock_query_result.objects = mock_chunk_objects

        mock_chunks_collection.query.fetch_objects.return_value = mock_query_result
        mock_client.collections.get.return_value = mock_chunks_collection

        # Configure context manager
        mock_context.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_context.return_value.__exit__ = MagicMock(return_value=False)

        yield mock_client


@pytest.fixture
def flask_test_client() -> Generator[Any, None, None]:
    """Create a Flask test client.

    Yields:
        Flask test client for making requests.
    """
    # Import here to avoid circular imports
    from flask_app import app

    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


# =============================================================================
# Tests for /api/get-works route
# =============================================================================


class TestApiGetWorks:
    """Tests for the /api/get-works endpoint."""

    def test_get_works_returns_unique_works(
        self,
        flask_test_client: Any,
        mock_weaviate_client_get_works: MagicMock,
    ) -> None:
        """Test that /api/get-works returns unique works with correct counts."""
        response = flask_test_client.get("/api/get-works")

        assert response.status_code == 200
        data = json.loads(response.data)

        # Should have 3 unique works
        assert len(data) == 3

        # Check that works are present
        titles = [w["title"] for w in data]
        assert "Ménon" in titles
        assert "La logique de la science" in titles
        assert "La pensée-signe" in titles

    def test_get_works_chunks_count_correct(
        self,
        flask_test_client: Any,
        mock_weaviate_client_get_works: MagicMock,
    ) -> None:
        """Test that chunks_count is calculated correctly."""
        response = flask_test_client.get("/api/get-works")

        assert response.status_code == 200
        data = json.loads(response.data)

        # Find Ménon - should have 3 chunks
        menon = next(w for w in data if w["title"] == "Ménon")
        assert menon["chunks_count"] == 3

        # La logique de la science - should have 2 chunks
        logique = next(w for w in data if w["title"] == "La logique de la science")
        assert logique["chunks_count"] == 2

        # La pensée-signe - should have 1 chunk
        pensee = next(w for w in data if w["title"] == "La pensée-signe")
        assert pensee["chunks_count"] == 1

    def test_get_works_sorted_by_author_then_title(
        self,
        flask_test_client: Any,
        mock_weaviate_client_get_works: MagicMock,
    ) -> None:
        """Test that works are sorted by author, then title."""
        response = flask_test_client.get("/api/get-works")

        assert response.status_code == 200
        data = json.loads(response.data)

        # Expected order: Charles Sanders Peirce < Claudine Tiercelin < Platon
        authors = [w["author"] for w in data]
        assert authors == sorted(authors, key=str.lower)

    def test_get_works_includes_author(
        self,
        flask_test_client: Any,
        mock_weaviate_client_get_works: MagicMock,
    ) -> None:
        """Test that each work includes author information."""
        response = flask_test_client.get("/api/get-works")

        assert response.status_code == 200
        data = json.loads(response.data)

        for work in data:
            assert "author" in work
            assert work["author"]  # Not empty

    def test_get_works_weaviate_connection_failure(
        self,
        flask_test_client: Any,
    ) -> None:
        """Test proper error handling when Weaviate connection fails."""
        with patch("flask_app.get_weaviate_client") as mock_context:
            # Simulate connection failure (client is None)
            mock_context.return_value.__enter__ = MagicMock(return_value=None)
            mock_context.return_value.__exit__ = MagicMock(return_value=False)

            response = flask_test_client.get("/api/get-works")

            assert response.status_code == 500
            data = json.loads(response.data)
            assert "error" in data
            assert "Weaviate connection failed" in data["error"]

    def test_get_works_weaviate_query_exception(
        self,
        flask_test_client: Any,
    ) -> None:
        """Test proper error handling when Weaviate query throws exception."""
        with patch("flask_app.get_weaviate_client") as mock_context:
            mock_client = MagicMock()
            mock_client.collections.get.side_effect = Exception("Connection timeout")

            mock_context.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_context.return_value.__exit__ = MagicMock(return_value=False)

            response = flask_test_client.get("/api/get-works")

            assert response.status_code == 500
            data = json.loads(response.data)
            assert "error" in data


class TestApiGetWorksEdgeCases:
    """Edge case tests for /api/get-works."""

    def test_get_works_empty_database(
        self,
        flask_test_client: Any,
    ) -> None:
        """Test behavior when database has no chunks."""
        with patch("flask_app.get_weaviate_client") as mock_context:
            mock_client = MagicMock()
            mock_chunks_collection = MagicMock()
            mock_query_result = MagicMock()
            mock_query_result.objects = []  # Empty

            mock_chunks_collection.query.fetch_objects.return_value = mock_query_result
            mock_client.collections.get.return_value = mock_chunks_collection

            mock_context.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_context.return_value.__exit__ = MagicMock(return_value=False)

            response = flask_test_client.get("/api/get-works")

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data == []

    def test_get_works_missing_title(
        self,
        flask_test_client: Any,
    ) -> None:
        """Test that chunks without titles are ignored."""
        with patch("flask_app.get_weaviate_client") as mock_context:
            mock_client = MagicMock()
            mock_chunks_collection = MagicMock()

            # Create mock with empty title (should be ignored)
            obj1 = MagicMock()
            obj1.properties = {"work": {"title": "", "author": "Unknown"}}
            obj2 = MagicMock()
            obj2.properties = {"work": {"title": "Valid Work", "author": "Author"}}

            mock_query_result = MagicMock()
            mock_query_result.objects = [obj1, obj2]

            mock_chunks_collection.query.fetch_objects.return_value = mock_query_result
            mock_client.collections.get.return_value = mock_chunks_collection

            mock_context.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_context.return_value.__exit__ = MagicMock(return_value=False)

            response = flask_test_client.get("/api/get-works")

            assert response.status_code == 200
            data = json.loads(response.data)
            assert len(data) == 1
            assert data[0]["title"] == "Valid Work"

    def test_get_works_missing_author_defaults_unknown(
        self,
        flask_test_client: Any,
    ) -> None:
        """Test that missing author defaults to 'Unknown'."""
        with patch("flask_app.get_weaviate_client") as mock_context:
            mock_client = MagicMock()
            mock_chunks_collection = MagicMock()

            obj = MagicMock()
            obj.properties = {"work": {"title": "Orphan Work", "author": ""}}

            mock_query_result = MagicMock()
            mock_query_result.objects = [obj]

            mock_chunks_collection.query.fetch_objects.return_value = mock_query_result
            mock_client.collections.get.return_value = mock_chunks_collection

            mock_context.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_context.return_value.__exit__ = MagicMock(return_value=False)

            response = flask_test_client.get("/api/get-works")

            assert response.status_code == 200
            data = json.loads(response.data)
            assert len(data) == 1
            assert data[0]["author"] == "Unknown"


# =============================================================================
# Tests for /chat/send selected_works parameter
# =============================================================================


class TestChatSendSelectedWorks:
    """Tests for selected_works parameter in /chat/send."""

    def test_chat_send_accepts_empty_selected_works(
        self,
        flask_test_client: Any,
    ) -> None:
        """Test that /chat/send accepts empty selected_works (search all)."""
        with patch("flask_app.threading.Thread") as mock_thread:
            mock_thread.return_value.start = MagicMock()

            response = flask_test_client.post(
                "/chat/send",
                data=json.dumps({
                    "question": "Test question",
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "selected_works": []
                }),
                content_type="application/json"
            )

            assert response.status_code == 200
            data = json.loads(response.data)
            assert "session_id" in data
            assert data["status"] == "streaming"

    def test_chat_send_accepts_selected_works_list(
        self,
        flask_test_client: Any,
    ) -> None:
        """Test that /chat/send accepts a list of work titles."""
        with patch("flask_app.threading.Thread") as mock_thread:
            mock_thread.return_value.start = MagicMock()

            response = flask_test_client.post(
                "/chat/send",
                data=json.dumps({
                    "question": "Test question",
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "selected_works": ["Ménon", "La pensée-signe"]
                }),
                content_type="application/json"
            )

            assert response.status_code == 200
            data = json.loads(response.data)
            assert "session_id" in data

    def test_chat_send_rejects_invalid_selected_works_string(
        self,
        flask_test_client: Any,
    ) -> None:
        """Test that /chat/send rejects non-list selected_works."""
        response = flask_test_client.post(
            "/chat/send",
            data=json.dumps({
                "question": "Test question",
                "provider": "openai",
                "model": "gpt-4o-mini",
                "selected_works": "not a list"
            }),
            content_type="application/json"
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert "error" in data
        assert "list" in data["error"].lower()

    def test_chat_send_rejects_invalid_selected_works_dict(
        self,
        flask_test_client: Any,
    ) -> None:
        """Test that /chat/send rejects dict selected_works."""
        response = flask_test_client.post(
            "/chat/send",
            data=json.dumps({
                "question": "Test question",
                "provider": "openai",
                "model": "gpt-4o-mini",
                "selected_works": {"title": "Ménon"}
            }),
            content_type="application/json"
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert "error" in data

    def test_chat_send_rejects_mixed_types_in_list(
        self,
        flask_test_client: Any,
    ) -> None:
        """Test that /chat/send rejects list with non-string elements."""
        response = flask_test_client.post(
            "/chat/send",
            data=json.dumps({
                "question": "Test question",
                "provider": "openai",
                "model": "gpt-4o-mini",
                "selected_works": ["Ménon", 123, None]
            }),
            content_type="application/json"
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert "error" in data
        assert "strings" in data["error"].lower()

    def test_chat_send_passes_selected_works_to_thread(
        self,
        flask_test_client: Any,
    ) -> None:
        """Test that selected_works is passed correctly to background thread."""
        with patch("flask_app.threading.Thread") as mock_thread:
            mock_thread.return_value.start = MagicMock()

            selected = ["Ménon", "La pensée-signe"]
            response = flask_test_client.post(
                "/chat/send",
                data=json.dumps({
                    "question": "Test question",
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "selected_works": selected
                }),
                content_type="application/json"
            )

            assert response.status_code == 200

            # Verify Thread was called with selected_works in args
            call_args = mock_thread.call_args
            thread_args = call_args.kwargs.get("args", call_args[1].get("args", ()))

            # selected_works should be the 7th argument (index 6)
            # args = (session_id, question, provider, model, limit, use_reformulation, selected_works)
            assert len(thread_args) >= 7
            assert thread_args[6] == selected


# =============================================================================
# Tests for rag_search with selected_works filter
# =============================================================================


class TestRagSearchWorksFilter:
    """Tests for rag_search function with selected_works filter."""

    def test_rag_search_without_filter_searches_all(self) -> None:
        """Test that rag_search without selected_works searches all chunks."""
        from flask_app import rag_search

        with patch("flask_app.get_weaviate_client") as mock_context:
            mock_client = MagicMock()
            mock_chunks = MagicMock()

            # Mock near_text result
            mock_result = MagicMock()
            mock_result.objects = []
            mock_chunks.query.near_text.return_value = mock_result

            mock_client.collections.get.return_value = mock_chunks
            mock_context.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_context.return_value.__exit__ = MagicMock(return_value=False)

            # Call without selected_works
            rag_search("test query", limit=5)

            # Verify near_text was called with no filter
            call_kwargs = mock_chunks.query.near_text.call_args.kwargs
            assert call_kwargs.get("filters") is None

    def test_rag_search_with_filter_applies_work_filter(self) -> None:
        """Test that rag_search with selected_works applies contains_any filter."""
        from flask_app import rag_search

        with patch("flask_app.get_weaviate_client") as mock_context:
            mock_client = MagicMock()
            mock_chunks = MagicMock()

            # Mock near_text result
            mock_result = MagicMock()
            mock_result.objects = []
            mock_chunks.query.near_text.return_value = mock_result

            mock_client.collections.get.return_value = mock_chunks
            mock_context.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_context.return_value.__exit__ = MagicMock(return_value=False)

            # Call with selected_works
            rag_search("test query", limit=5, selected_works=["Ménon"])

            # Verify near_text was called with a filter
            call_kwargs = mock_chunks.query.near_text.call_args.kwargs
            assert call_kwargs.get("filters") is not None

    def test_rag_search_empty_list_treated_as_no_filter(self) -> None:
        """Test that empty selected_works list is treated as no filter."""
        from flask_app import rag_search

        with patch("flask_app.get_weaviate_client") as mock_context:
            mock_client = MagicMock()
            mock_chunks = MagicMock()

            mock_result = MagicMock()
            mock_result.objects = []
            mock_chunks.query.near_text.return_value = mock_result

            mock_client.collections.get.return_value = mock_chunks
            mock_context.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_context.return_value.__exit__ = MagicMock(return_value=False)

            # Call with empty list
            rag_search("test query", limit=5, selected_works=[])

            # Verify near_text was called without filter
            call_kwargs = mock_chunks.query.near_text.call_args.kwargs
            assert call_kwargs.get("filters") is None


# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
