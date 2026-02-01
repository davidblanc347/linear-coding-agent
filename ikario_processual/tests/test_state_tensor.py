#!/usr/bin/env python3
"""
Tests pour StateTensor - Tenseur d'état 8×1024.

Exécuter: pytest ikario_processual/tests/test_state_tensor.py -v
"""

import numpy as np
import pytest
from datetime import datetime

# Import du module à tester
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ikario_processual.state_tensor import (
    StateTensor,
    TensorDimension,
    DIMENSION_NAMES,
    EMBEDDING_DIM,
)


class TestStateTensorBasic:
    """Tests de base pour StateTensor."""

    def test_create_empty_tensor(self):
        """Test création d'un tenseur vide."""
        tensor = StateTensor(
            state_id=0,
            timestamp=datetime.now().isoformat(),
        )

        assert tensor.state_id == 0
        assert tensor.firstness.shape == (EMBEDDING_DIM,)
        assert tensor.valeurs.shape == (EMBEDDING_DIM,)
        assert np.all(tensor.firstness == 0)

    def test_create_with_values(self):
        """Test création avec valeurs."""
        firstness = np.random.randn(EMBEDDING_DIM)
        firstness = firstness / np.linalg.norm(firstness)

        tensor = StateTensor(
            state_id=1,
            timestamp=datetime.now().isoformat(),
            firstness=firstness,
        )

        assert np.allclose(tensor.firstness, firstness)
        assert np.isclose(np.linalg.norm(tensor.firstness), 1.0)

    def test_to_matrix(self):
        """Test conversion en matrice."""
        tensor = StateTensor(
            state_id=0,
            timestamp=datetime.now().isoformat(),
        )

        matrix = tensor.to_matrix()
        assert matrix.shape == (8, EMBEDDING_DIM)

    def test_to_flat(self):
        """Test aplatissement."""
        tensor = StateTensor(
            state_id=0,
            timestamp=datetime.now().isoformat(),
        )

        flat = tensor.to_flat()
        assert flat.shape == (8 * EMBEDDING_DIM,)
        assert flat.shape == (8192,)

    def test_dimension_names(self):
        """Test que toutes les dimensions sont présentes."""
        expected = [
            "firstness", "secondness", "thirdness", "dispositions",
            "orientations", "engagements", "pertinences", "valeurs"
        ]
        assert DIMENSION_NAMES == expected
        assert len(DIMENSION_NAMES) == 8


class TestStateTensorOperations:
    """Tests des opérations sur StateTensor."""

    def test_copy(self):
        """Test copie profonde."""
        original = StateTensor(
            state_id=1,
            timestamp=datetime.now().isoformat(),
            firstness=np.random.randn(EMBEDDING_DIM),
        )

        copied = original.copy()

        # Modifier l'original ne doit pas affecter la copie
        original.firstness[0] = 999.0
        assert copied.firstness[0] != 999.0

    def test_set_dimension(self):
        """Test modification d'une dimension."""
        tensor = StateTensor(
            state_id=0,
            timestamp=datetime.now().isoformat(),
        )

        new_vec = np.random.randn(EMBEDDING_DIM)
        tensor.set_dimension(TensorDimension.VALEURS, new_vec)

        # Doit être normalisé
        assert np.isclose(np.linalg.norm(tensor.valeurs), 1.0)

    def test_get_dimension(self):
        """Test récupération d'une dimension."""
        tensor = StateTensor(
            state_id=0,
            timestamp=datetime.now().isoformat(),
        )

        vec = tensor.get_dimension(TensorDimension.FIRSTNESS)
        assert vec.shape == (EMBEDDING_DIM,)

    def test_to_dict(self):
        """Test conversion en dictionnaire."""
        tensor = StateTensor(
            state_id=5,
            timestamp="2026-02-01T12:00:00",
            trigger_type="user",
            trigger_content="Hello",
        )

        d = tensor.to_dict()
        assert d["state_id"] == 5
        assert d["trigger_type"] == "user"
        assert "firstness" not in d  # Vecteurs pas dans properties

    def test_get_vectors_dict(self):
        """Test récupération des vecteurs pour Weaviate."""
        tensor = StateTensor(
            state_id=0,
            timestamp=datetime.now().isoformat(),
        )

        vectors = tensor.get_vectors_dict()
        assert len(vectors) == 8
        assert "firstness" in vectors
        assert "valeurs" in vectors
        assert len(vectors["firstness"]) == EMBEDDING_DIM


class TestStateTensorAggregation:
    """Tests des opérations d'agrégation."""

    def test_weighted_mean_two_tensors(self):
        """Test moyenne pondérée de 2 tenseurs."""
        t1 = StateTensor(
            state_id=1,
            timestamp=datetime.now().isoformat(),
        )
        t2 = StateTensor(
            state_id=2,
            timestamp=datetime.now().isoformat(),
        )

        # Initialiser avec des vecteurs aléatoires normalisés
        for dim_name in DIMENSION_NAMES:
            v1 = np.random.randn(EMBEDDING_DIM)
            v1 = v1 / np.linalg.norm(v1)
            setattr(t1, dim_name, v1)

            v2 = np.random.randn(EMBEDDING_DIM)
            v2 = v2 / np.linalg.norm(v2)
            setattr(t2, dim_name, v2)

        # Moyenne 50/50
        result = StateTensor.weighted_mean([t1, t2], [0.5, 0.5])

        # Résultat doit être normalisé
        for dim_name in DIMENSION_NAMES:
            vec = getattr(result, dim_name)
            assert np.isclose(np.linalg.norm(vec), 1.0, atol=1e-5)

    def test_blend(self):
        """Test blend 70/30."""
        t1 = StateTensor(state_id=1, timestamp=datetime.now().isoformat())
        t2 = StateTensor(state_id=2, timestamp=datetime.now().isoformat())

        # Initialiser
        for dim_name in DIMENSION_NAMES:
            v1 = np.random.randn(EMBEDDING_DIM)
            v1 = v1 / np.linalg.norm(v1)
            setattr(t1, dim_name, v1)

            v2 = np.random.randn(EMBEDDING_DIM)
            v2 = v2 / np.linalg.norm(v2)
            setattr(t2, dim_name, v2)

        result = StateTensor.blend(t1, t2, alpha=0.7)

        assert result is not None
        assert result.state_id == -1  # Non défini

    def test_from_matrix(self):
        """Test création depuis matrice."""
        matrix = np.random.randn(8, EMBEDDING_DIM)

        tensor = StateTensor.from_matrix(
            matrix=matrix,
            state_id=10,
            timestamp="2026-02-01T12:00:00"
        )

        assert tensor.state_id == 10
        assert np.allclose(tensor.firstness, matrix[0])
        assert np.allclose(tensor.valeurs, matrix[7])

    def test_from_matrix_wrong_shape(self):
        """Test erreur si matrice mauvaise forme."""
        matrix = np.random.randn(4, EMBEDDING_DIM)  # 4 au lieu de 8

        with pytest.raises(ValueError):
            StateTensor.from_matrix(matrix, state_id=0, timestamp="")


class TestStateTensorDistance:
    """Tests de calcul de distance entre tenseurs."""

    def test_distance_to_self_is_zero(self):
        """Distance à soi-même = 0."""
        tensor = StateTensor(state_id=0, timestamp=datetime.now().isoformat())

        for dim_name in DIMENSION_NAMES:
            v = np.random.randn(EMBEDDING_DIM)
            v = v / np.linalg.norm(v)
            setattr(tensor, dim_name, v)

        flat = tensor.to_flat()
        distance = np.linalg.norm(flat - flat)
        assert distance == 0.0

    def test_normalized_distance(self):
        """Test distance normalisée entre 2 tenseurs."""
        t1 = StateTensor(state_id=1, timestamp=datetime.now().isoformat())
        t2 = StateTensor(state_id=2, timestamp=datetime.now().isoformat())

        for dim_name in DIMENSION_NAMES:
            v1 = np.random.randn(EMBEDDING_DIM)
            v1 = v1 / np.linalg.norm(v1)
            setattr(t1, dim_name, v1)

            v2 = np.random.randn(EMBEDDING_DIM)
            v2 = v2 / np.linalg.norm(v2)
            setattr(t2, dim_name, v2)

        diff = t1.to_flat() - t2.to_flat()
        distance = np.linalg.norm(diff) / np.linalg.norm(t2.to_flat())

        # Distance normalisée doit être > 0 et finie
        assert distance > 0
        assert np.isfinite(distance)


class TestStateTensorSerialization:
    """Tests de sérialisation."""

    def test_from_dict_roundtrip(self):
        """Test aller-retour dict."""
        original = StateTensor(
            state_id=42,
            timestamp="2026-02-01T12:00:00",
            previous_state_id=41,
            trigger_type="user",
            trigger_content="Test message",
            embedding_model="BAAI/bge-m3",
        )

        # Simuler les vecteurs
        vectors = {}
        for dim_name in DIMENSION_NAMES:
            v = np.random.randn(EMBEDDING_DIM)
            v = v / np.linalg.norm(v)
            setattr(original, dim_name, v)
            vectors[dim_name] = v.tolist()

        # Convertir et recréer
        props = original.to_dict()
        reconstructed = StateTensor.from_dict(props, vectors)

        assert reconstructed.state_id == 42
        assert reconstructed.trigger_type == "user"
        assert np.allclose(reconstructed.firstness, original.firstness)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
