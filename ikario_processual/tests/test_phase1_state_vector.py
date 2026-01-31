#!/usr/bin/env python3
"""
Tests pour la Phase 1: StateVector et S(0).

Usage:
    pytest tests/test_phase1_state_vector.py -v
"""

import os
import sys
from pathlib import Path

import pytest
import requests
import numpy as np

# Ajouter le parent au path
sys.path.insert(0, str(Path(__file__).parent.parent))

from state_vector import (
    check_weaviate_ready,
    get_existing_classes,
    filter_thoughts,
    filter_assistant_messages,
    get_state_vector,
    get_current_state_id,
    WEAVIATE_URL,
)


def weaviate_is_available() -> bool:
    """Verifie si Weaviate est accessible."""
    return check_weaviate_ready()


# Skip tous les tests si Weaviate n'est pas disponible
pytestmark = pytest.mark.skipif(
    not weaviate_is_available(),
    reason=f"Weaviate non disponible sur {WEAVIATE_URL}"
)


class TestStateVectorCollection:
    """Tests de la collection StateVector."""

    def test_state_vector_collection_exists(self):
        """La collection StateVector doit exister."""
        classes = get_existing_classes()
        assert "StateVector" in classes, \
            f"StateVector non trouve. Classes: {classes}"

    def test_state_vector_schema_correct(self):
        """Le schema StateVector doit avoir les bonnes proprietes."""
        response = requests.get(f"{WEAVIATE_URL}/v1/schema")
        schema = response.json()

        state_vector_class = None
        for c in schema.get("classes", []):
            if c["class"] == "StateVector":
                state_vector_class = c
                break

        assert state_vector_class is not None

        # Verifier les proprietes requises
        prop_names = [p["name"] for p in state_vector_class.get("properties", [])]
        required = ["state_id", "timestamp", "trigger_type", "occasion_summary"]

        for req in required:
            assert req in prop_names, f"Propriete manquante: {req}"


class TestInitialState:
    """Tests de l'etat initial S(0)."""

    def test_s0_exists(self):
        """S(0) doit exister."""
        s0 = get_state_vector(0)
        assert s0 is not None, "S(0) non trouve"
        assert s0.get("state_id") == 0

    def test_s0_has_vector(self):
        """S(0) doit avoir un vecteur."""
        s0 = get_state_vector(0)
        assert s0 is not None

        vector = s0.get("_additional", {}).get("vector")
        assert vector is not None, "S(0) n'a pas de vecteur"

    def test_s0_vector_is_1024_dim(self):
        """Le vecteur de S(0) doit etre 1024-dim (BGE-M3)."""
        s0 = get_state_vector(0)
        assert s0 is not None

        vector = s0.get("_additional", {}).get("vector")
        assert vector is not None
        assert len(vector) == 1024, f"Dimension: {len(vector)} (attendu: 1024)"

    def test_s0_vector_is_normalized(self):
        """Le vecteur de S(0) doit etre normalise."""
        s0 = get_state_vector(0)
        assert s0 is not None

        vector = np.array(s0.get("_additional", {}).get("vector", []))
        norm = np.linalg.norm(vector)

        assert abs(norm - 1.0) < 0.01, f"Norme: {norm} (attendu: ~1.0)"

    def test_s0_has_source_counts(self):
        """S(0) doit avoir les compteurs de sources."""
        s0 = get_state_vector(0)
        assert s0 is not None

        thoughts_count = s0.get("source_thoughts_count")
        messages_count = s0.get("source_messages_count")

        assert thoughts_count is not None, "source_thoughts_count manquant"
        assert messages_count is not None, "source_messages_count manquant"
        assert thoughts_count > 0 or messages_count > 0, \
            "S(0) doit etre construit a partir de donnees"

    def test_s0_trigger_type_is_initialization(self):
        """Le trigger_type de S(0) doit etre 'initialization'."""
        s0 = get_state_vector(0)
        assert s0 is not None

        trigger_type = s0.get("trigger_type")
        assert trigger_type == "initialization"


class TestFiltering:
    """Tests des fonctions de filtrage."""

    def test_filter_thoughts_excludes_test(self):
        """Les pensees de test doivent etre exclues."""
        thoughts = [
            {"properties": {"content": "Ceci est une vraie pensee philosophique", "thought_type": "reflection"}},
            {"properties": {"content": "test test test", "thought_type": "test"}},
            {"properties": {"content": "debug: checking values", "thought_type": "debug"}},
            {"properties": {"content": "Une autre pensee valide sur Whitehead", "thought_type": "reflection"}},
        ]

        filtered = filter_thoughts(thoughts)

        assert len(filtered) == 2
        for t in filtered:
            assert "test" not in t["properties"]["content"].lower()

    def test_filter_thoughts_excludes_short(self):
        """Les pensees trop courtes doivent etre exclues."""
        thoughts = [
            {"properties": {"content": "OK", "thought_type": "reflection"}},
            {"properties": {"content": "Une pensee suffisamment longue pour etre valide", "thought_type": "reflection"}},
        ]

        filtered = filter_thoughts(thoughts)

        assert len(filtered) == 1
        assert len(filtered[0]["properties"]["content"]) >= 20

    def test_filter_messages_keeps_only_assistant(self):
        """Seuls les messages assistant doivent etre gardes."""
        messages = [
            {"properties": {"role": "user", "content": "Question de l'utilisateur"}},
            {"properties": {"role": "assistant", "content": "Reponse d'Ikario avec suffisamment de contenu pour etre valide"}},
            {"properties": {"role": "system", "content": "Message systeme"}},
        ]

        filtered = filter_assistant_messages(messages)

        assert len(filtered) == 1
        assert filtered[0]["properties"]["role"] == "assistant"

    def test_filter_messages_excludes_short(self):
        """Les messages trop courts doivent etre exclus."""
        messages = [
            {"properties": {"role": "assistant", "content": "OK"}},
            {"properties": {"role": "assistant", "content": "Une reponse complete avec suffisamment de contenu pour representer une vraie interaction"}},
        ]

        filtered = filter_assistant_messages(messages)

        assert len(filtered) == 1
        assert len(filtered[0]["properties"]["content"]) >= 50


class TestStateVectorOperations:
    """Tests des operations sur StateVector."""

    def test_get_current_state_id(self):
        """get_current_state_id doit retourner au moins 0."""
        current_id = get_current_state_id()
        assert current_id >= 0, "Aucun etat trouve"

    def test_get_state_vector_returns_none_for_invalid_id(self):
        """get_state_vector doit retourner None pour un ID invalide."""
        state = get_state_vector(99999)
        assert state is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
