#!/usr/bin/env python3
"""
Tests pour la Phase 2: Directions de Projection.

Usage:
    pytest tests/test_phase2_directions.py -v
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
    get_state_vector,
    WEAVIATE_URL,
)
from projection_directions import (
    get_existing_classes,
    get_direction,
    get_all_directions,
    get_state_profile,
    project_state_on_direction,
    DIRECTIONS_CONFIG,
)


def weaviate_is_available() -> bool:
    """Verifie si Weaviate est accessible."""
    return check_weaviate_ready()


# Skip tous les tests si Weaviate n'est pas disponible
pytestmark = pytest.mark.skipif(
    not weaviate_is_available(),
    reason=f"Weaviate non disponible sur {WEAVIATE_URL}"
)


class TestProjectionDirectionCollection:
    """Tests de la collection ProjectionDirection."""

    def test_collection_exists(self):
        """La collection ProjectionDirection doit exister."""
        classes = get_existing_classes()
        assert "ProjectionDirection" in classes

    def test_all_directions_created(self):
        """Toutes les directions configurees doivent exister."""
        directions = get_all_directions()
        direction_names = [d["name"] for d in directions]

        for name in DIRECTIONS_CONFIG.keys():
            assert name in direction_names, f"Direction manquante: {name}"

    def test_directions_count(self):
        """Le nombre de directions doit correspondre a la config."""
        directions = get_all_directions()
        assert len(directions) == len(DIRECTIONS_CONFIG)


class TestDirectionVectors:
    """Tests des vecteurs de direction."""

    def test_curiosity_direction_exists(self):
        """La direction 'curiosity' doit exister."""
        direction = get_direction("curiosity")
        assert direction is not None
        assert direction["name"] == "curiosity"
        assert direction["category"] == "epistemic"

    def test_direction_has_vector(self):
        """Chaque direction doit avoir un vecteur."""
        direction = get_direction("curiosity")
        assert direction is not None

        vector = direction.get("_additional", {}).get("vector")
        assert vector is not None
        assert len(vector) > 0

    def test_direction_vector_is_1024_dim(self):
        """Les vecteurs de direction doivent etre 1024-dim."""
        direction = get_direction("curiosity")
        assert direction is not None

        vector = direction.get("_additional", {}).get("vector")
        assert len(vector) == 1024

    def test_direction_vector_is_normalized(self):
        """Les vecteurs de direction doivent etre normalises."""
        direction = get_direction("curiosity")
        assert direction is not None

        vector = np.array(direction.get("_additional", {}).get("vector"))
        norm = np.linalg.norm(vector)

        assert abs(norm - 1.0) < 0.01, f"Norme: {norm}"

    def test_all_categories_present(self):
        """Toutes les categories doivent etre representees."""
        directions = get_all_directions()
        categories = set(d["category"] for d in directions)

        expected_categories = {"epistemic", "affective", "relational", "vital", "philosophical"}
        assert categories == expected_categories


class TestProjection:
    """Tests des fonctions de projection."""

    def test_projection_in_range(self):
        """Les projections doivent etre entre -1 et 1."""
        s0 = get_state_vector(0)
        assert s0 is not None

        state_vec = np.array(s0.get("_additional", {}).get("vector"))
        profile = get_state_profile(state_vec)

        for category, components in profile.items():
            for name, value in components.items():
                assert -1 <= value <= 1, f"{name} = {value} hors limites [-1, 1]"

    def test_get_state_profile_structure(self):
        """Le profil doit avoir la bonne structure."""
        s0 = get_state_vector(0)
        assert s0 is not None

        state_vec = np.array(s0.get("_additional", {}).get("vector"))
        profile = get_state_profile(state_vec)

        # Verifier que c'est un dict de dicts
        assert isinstance(profile, dict)
        for category, components in profile.items():
            assert isinstance(components, dict)
            for name, value in components.items():
                assert isinstance(value, float)

    def test_projection_orthogonal_vectors(self):
        """Test de projection avec des vecteurs orthogonaux."""
        # Deux vecteurs orthogonaux ont une projection de 0
        v1 = np.zeros(1024)
        v1[0] = 1.0

        v2 = np.zeros(1024)
        v2[1] = 1.0

        projection = project_state_on_direction(v1, v2)
        assert abs(projection) < 0.001

    def test_projection_parallel_vectors(self):
        """Test de projection avec des vecteurs paralleles."""
        v = np.random.randn(1024)
        v = v / np.linalg.norm(v)

        projection = project_state_on_direction(v, v)
        assert abs(projection - 1.0) < 0.001

    def test_projection_antiparallel_vectors(self):
        """Test de projection avec des vecteurs antiparalleles."""
        v = np.random.randn(1024)
        v = v / np.linalg.norm(v)

        projection = project_state_on_direction(v, -v)
        assert abs(projection + 1.0) < 0.001


class TestS0Profile:
    """Tests du profil de S(0)."""

    def test_s0_has_profile(self):
        """S(0) doit avoir un profil calculable."""
        s0 = get_state_vector(0)
        assert s0 is not None

        state_vec = np.array(s0.get("_additional", {}).get("vector"))
        profile = get_state_profile(state_vec)

        assert len(profile) > 0

    def test_s0_profile_has_all_categories(self):
        """Le profil de S(0) doit avoir toutes les categories."""
        s0 = get_state_vector(0)
        assert s0 is not None

        state_vec = np.array(s0.get("_additional", {}).get("vector"))
        profile = get_state_profile(state_vec)

        expected = {"epistemic", "affective", "relational", "vital", "philosophical"}
        assert set(profile.keys()) == expected

    def test_s0_has_curiosity_component(self):
        """S(0) doit avoir une composante curiosity."""
        s0 = get_state_vector(0)
        assert s0 is not None

        state_vec = np.array(s0.get("_additional", {}).get("vector"))
        profile = get_state_profile(state_vec)

        assert "curiosity" in profile.get("epistemic", {})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
