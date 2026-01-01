#!/usr/bin/env python3
"""Tests unitaires pour la validation stricte des métadonnées et nested objects.

Ce module teste les fonctions de validation ajoutées dans weaviate_ingest.py
pour prévenir les erreurs silencieuses causées par des métadonnées invalides.

Run:
    pytest tests/test_validation_stricte.py -v
"""

import pytest
from typing import Any, Dict

from utils.weaviate_ingest import (
    validate_document_metadata,
    validate_chunk_nested_objects,
)


# =============================================================================
# Tests pour validate_document_metadata()
# =============================================================================


def test_validate_document_metadata_valid() -> None:
    """Test validation avec métadonnées valides."""
    # Should not raise
    validate_document_metadata(
        doc_name="platon_republique",
        metadata={"title": "La République", "author": "Platon"},
        language="fr",
    )


def test_validate_document_metadata_valid_with_work_key() -> None:
    """Test validation avec key 'work' au lieu de 'title'."""
    # Should not raise
    validate_document_metadata(
        doc_name="test_doc",
        metadata={"work": "Test Work", "author": "Test Author"},
        language="en",
    )


def test_validate_document_metadata_empty_doc_name() -> None:
    """Test que doc_name vide lève ValueError."""
    with pytest.raises(ValueError, match="Invalid doc_name: empty"):
        validate_document_metadata(
            doc_name="",
            metadata={"title": "Title", "author": "Author"},
            language="fr",
        )


def test_validate_document_metadata_whitespace_doc_name() -> None:
    """Test que doc_name whitespace-only lève ValueError."""
    with pytest.raises(ValueError, match="Invalid doc_name: empty"):
        validate_document_metadata(
            doc_name="   ",
            metadata={"title": "Title", "author": "Author"},
            language="fr",
        )


def test_validate_document_metadata_missing_title() -> None:
    """Test que title manquant lève ValueError."""
    with pytest.raises(ValueError, match="'title' is missing or empty"):
        validate_document_metadata(
            doc_name="test_doc",
            metadata={"author": "Author"},
            language="fr",
        )


def test_validate_document_metadata_empty_title() -> None:
    """Test que title vide lève ValueError."""
    with pytest.raises(ValueError, match="'title' is missing or empty"):
        validate_document_metadata(
            doc_name="test_doc",
            metadata={"title": "", "author": "Author"},
            language="fr",
        )


def test_validate_document_metadata_whitespace_title() -> None:
    """Test que title whitespace-only lève ValueError."""
    with pytest.raises(ValueError, match="'title' is missing or empty"):
        validate_document_metadata(
            doc_name="test_doc",
            metadata={"title": "   ", "author": "Author"},
            language="fr",
        )


def test_validate_document_metadata_missing_author() -> None:
    """Test que author manquant lève ValueError."""
    with pytest.raises(ValueError, match="'author' is missing or empty"):
        validate_document_metadata(
            doc_name="test_doc",
            metadata={"title": "Title"},
            language="fr",
        )


def test_validate_document_metadata_empty_author() -> None:
    """Test que author vide lève ValueError."""
    with pytest.raises(ValueError, match="'author' is missing or empty"):
        validate_document_metadata(
            doc_name="test_doc",
            metadata={"title": "Title", "author": ""},
            language="fr",
        )


def test_validate_document_metadata_none_author() -> None:
    """Test que author=None lève ValueError."""
    with pytest.raises(ValueError, match="'author' is missing or empty"):
        validate_document_metadata(
            doc_name="test_doc",
            metadata={"title": "Title", "author": None},
            language="fr",
        )


def test_validate_document_metadata_empty_language() -> None:
    """Test que language vide lève ValueError."""
    with pytest.raises(ValueError, match="Invalid language.*empty"):
        validate_document_metadata(
            doc_name="test_doc",
            metadata={"title": "Title", "author": "Author"},
            language="",
        )


def test_validate_document_metadata_optional_edition() -> None:
    """Test que edition est optionnel (peut être vide)."""
    # Should not raise - edition is optional
    validate_document_metadata(
        doc_name="test_doc",
        metadata={"title": "Title", "author": "Author", "edition": ""},
        language="fr",
    )


# =============================================================================
# Tests pour validate_chunk_nested_objects()
# =============================================================================


def test_validate_chunk_nested_objects_valid() -> None:
    """Test validation avec chunk valide."""
    chunk = {
        "text": "Some text",
        "work": {"title": "La République", "author": "Platon"},
        "document": {"sourceId": "platon_republique", "edition": "GF"},
    }
    # Should not raise
    validate_chunk_nested_objects(chunk, 0, "platon_republique")


def test_validate_chunk_nested_objects_empty_edition_ok() -> None:
    """Test que edition vide est accepté (optionnel)."""
    chunk = {
        "text": "Some text",
        "work": {"title": "Title", "author": "Author"},
        "document": {"sourceId": "doc_id", "edition": ""},
    }
    # Should not raise
    validate_chunk_nested_objects(chunk, 0, "doc_id")


def test_validate_chunk_nested_objects_work_not_dict() -> None:
    """Test que work non-dict lève ValueError."""
    chunk = {
        "text": "Some text",
        "work": "not a dict",
        "document": {"sourceId": "doc_id", "edition": ""},
    }
    with pytest.raises(ValueError, match="work is not a dict"):
        validate_chunk_nested_objects(chunk, 5, "doc_id")


def test_validate_chunk_nested_objects_empty_work_title() -> None:
    """Test que work.title vide lève ValueError."""
    chunk = {
        "text": "Some text",
        "work": {"title": "", "author": "Author"},
        "document": {"sourceId": "doc_id", "edition": ""},
    }
    with pytest.raises(ValueError, match="work.title is empty"):
        validate_chunk_nested_objects(chunk, 10, "doc_id")


def test_validate_chunk_nested_objects_none_work_title() -> None:
    """Test que work.title=None lève ValueError."""
    chunk = {
        "text": "Some text",
        "work": {"title": None, "author": "Author"},
        "document": {"sourceId": "doc_id", "edition": ""},
    }
    with pytest.raises(ValueError, match="work.title is empty"):
        validate_chunk_nested_objects(chunk, 3, "doc_id")


def test_validate_chunk_nested_objects_whitespace_work_title() -> None:
    """Test que work.title whitespace-only lève ValueError."""
    chunk = {
        "text": "Some text",
        "work": {"title": "   ", "author": "Author"},
        "document": {"sourceId": "doc_id", "edition": ""},
    }
    with pytest.raises(ValueError, match="work.title is empty"):
        validate_chunk_nested_objects(chunk, 7, "doc_id")


def test_validate_chunk_nested_objects_empty_work_author() -> None:
    """Test que work.author vide lève ValueError."""
    chunk = {
        "text": "Some text",
        "work": {"title": "Title", "author": ""},
        "document": {"sourceId": "doc_id", "edition": ""},
    }
    with pytest.raises(ValueError, match="work.author is empty"):
        validate_chunk_nested_objects(chunk, 2, "doc_id")


def test_validate_chunk_nested_objects_document_not_dict() -> None:
    """Test que document non-dict lève ValueError."""
    chunk = {
        "text": "Some text",
        "work": {"title": "Title", "author": "Author"},
        "document": ["not", "a", "dict"],
    }
    with pytest.raises(ValueError, match="document is not a dict"):
        validate_chunk_nested_objects(chunk, 15, "doc_id")


def test_validate_chunk_nested_objects_empty_source_id() -> None:
    """Test que document.sourceId vide lève ValueError."""
    chunk = {
        "text": "Some text",
        "work": {"title": "Title", "author": "Author"},
        "document": {"sourceId": "", "edition": "Ed"},
    }
    with pytest.raises(ValueError, match="document.sourceId is empty"):
        validate_chunk_nested_objects(chunk, 20, "doc_id")


def test_validate_chunk_nested_objects_none_source_id() -> None:
    """Test que document.sourceId=None lève ValueError."""
    chunk = {
        "text": "Some text",
        "work": {"title": "Title", "author": "Author"},
        "document": {"sourceId": None, "edition": "Ed"},
    }
    with pytest.raises(ValueError, match="document.sourceId is empty"):
        validate_chunk_nested_objects(chunk, 25, "doc_id")


def test_validate_chunk_nested_objects_error_message_includes_index() -> None:
    """Test que le message d'erreur inclut l'index du chunk."""
    chunk = {
        "text": "Some text",
        "work": {"title": "", "author": "Author"},
        "document": {"sourceId": "doc_id", "edition": ""},
    }
    with pytest.raises(ValueError, match="Chunk 42"):
        validate_chunk_nested_objects(chunk, 42, "my_doc")


def test_validate_chunk_nested_objects_error_message_includes_doc_name() -> None:
    """Test que le message d'erreur inclut doc_name."""
    chunk = {
        "text": "Some text",
        "work": {"title": "", "author": "Author"},
        "document": {"sourceId": "doc_id", "edition": ""},
    }
    with pytest.raises(ValueError, match="'my_special_doc'"):
        validate_chunk_nested_objects(chunk, 5, "my_special_doc")


# =============================================================================
# Tests d'intégration (scénarios réels)
# =============================================================================


def test_integration_scenario_peirce_collected_papers() -> None:
    """Test avec métadonnées réelles de Peirce Collected Papers."""
    # Métadonnées valides
    validate_document_metadata(
        doc_name="peirce_collected_papers_fixed",
        metadata={
            "title": "Collected Papers of Charles Sanders Peirce",
            "author": "Charles Sanders PEIRCE",
        },
        language="en",
    )

    # Chunk valide
    chunk = {
        "text": "Logic is the science of the necessary laws of thought...",
        "work": {
            "title": "Collected Papers of Charles Sanders Peirce",
            "author": "Charles Sanders PEIRCE",
        },
        "document": {
            "sourceId": "peirce_collected_papers_fixed",
            "edition": "Harvard University Press",
        },
    }
    validate_chunk_nested_objects(chunk, 0, "peirce_collected_papers_fixed")


def test_integration_scenario_platon_menon() -> None:
    """Test avec métadonnées réelles de Platon - Ménon."""
    validate_document_metadata(
        doc_name="Platon_-_Menon_trad._Cousin",
        metadata={
            "title": "Ménon",
            "author": "Platon",
            "edition": "trad. Cousin",
        },
        language="gr",
    )

    chunk = {
        "text": "Peux-tu me dire, Socrate...",
        "work": {"title": "Ménon", "author": "Platon"},
        "document": {
            "sourceId": "Platon_-_Menon_trad._Cousin",
            "edition": "trad. Cousin",
        },
    }
    validate_chunk_nested_objects(chunk, 0, "Platon_-_Menon_trad._Cousin")


def test_integration_scenario_malformed_metadata_caught() -> None:
    """Test que métadonnées malformées sont détectées avant ingestion."""
    # Scénario réel : metadata dict sans author
    with pytest.raises(ValueError, match="'author' is missing"):
        validate_document_metadata(
            doc_name="broken_doc",
            metadata={"title": "Some Title"},  # Manque author !
            language="fr",
        )


def test_integration_scenario_none_values_caught() -> None:
    """Test que valeurs None sont détectées (bug fréquent)."""
    # Scénario réel : LLM extraction rate et retourne None
    with pytest.raises(ValueError, match="'author' is missing"):
        validate_document_metadata(
            doc_name="llm_failed_extraction",
            metadata={"title": "Title", "author": None},  # LLM a échoué
            language="fr",
        )
