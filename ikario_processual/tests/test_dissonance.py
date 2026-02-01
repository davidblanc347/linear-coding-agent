#!/usr/bin/env python3
"""
Tests pour le module de dissonance - Phase 2.

Exécuter: pytest ikario_processual/tests/test_dissonance.py -v
"""

import numpy as np
import pytest
from datetime import datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ikario_processual.state_tensor import StateTensor, DIMENSION_NAMES, EMBEDDING_DIM
from ikario_processual.dissonance import (
    DissonanceConfig,
    DissonanceResult,
    compute_dissonance,
    compute_dissonance_enhanced,
    compute_self_dissonance,
    cosine_similarity,
    Impact,
    create_impact_from_dissonance,
)


def create_random_tensor() -> StateTensor:
    """Crée un tenseur avec des vecteurs aléatoires normalisés."""
    tensor = StateTensor(
        state_id=0,
        timestamp=datetime.now().isoformat(),
    )
    for dim_name in DIMENSION_NAMES:
        v = np.random.randn(EMBEDDING_DIM)
        v = v / np.linalg.norm(v)
        setattr(tensor, dim_name, v)
    return tensor


def create_zero_tensor() -> StateTensor:
    """Crée un tenseur avec des vecteurs zéro."""
    return StateTensor(
        state_id=0,
        timestamp=datetime.now().isoformat(),
    )


class TestCosineSimiliarity:
    """Tests pour la fonction cosine_similarity."""

    def test_identical_vectors(self):
        """Vecteurs identiques → similarité = 1."""
        v = np.random.randn(EMBEDDING_DIM)
        v = v / np.linalg.norm(v)
        assert np.isclose(cosine_similarity(v, v), 1.0)

    def test_opposite_vectors(self):
        """Vecteurs opposés → similarité = -1."""
        v = np.random.randn(EMBEDDING_DIM)
        v = v / np.linalg.norm(v)
        assert np.isclose(cosine_similarity(v, -v), -1.0)

    def test_orthogonal_vectors(self):
        """Vecteurs orthogonaux → similarité ≈ 0."""
        v1 = np.zeros(EMBEDDING_DIM)
        v1[0] = 1.0
        v2 = np.zeros(EMBEDDING_DIM)
        v2[1] = 1.0
        assert np.isclose(cosine_similarity(v1, v2), 0.0)

    def test_zero_vector(self):
        """Vecteur zéro → similarité = 0."""
        v1 = np.random.randn(EMBEDDING_DIM)
        v2 = np.zeros(EMBEDDING_DIM)
        assert cosine_similarity(v1, v2) == 0.0


class TestDissonanceConfig:
    """Tests pour DissonanceConfig."""

    def test_default_weights_sum(self):
        """Les poids par défaut doivent sommer à ~1.0."""
        config = DissonanceConfig()
        weights = config.get_dimension_weights()
        total = sum(weights.values())
        assert np.isclose(total, 1.0), f"Total des poids: {total}"

    def test_all_dimensions_have_weight(self):
        """Chaque dimension doit avoir un poids."""
        config = DissonanceConfig()
        weights = config.get_dimension_weights()
        for dim in DIMENSION_NAMES:
            assert dim in weights
            assert weights[dim] >= 0


class TestComputeDissonance:
    """Tests pour compute_dissonance (version basique)."""

    def test_self_dissonance_is_zero(self):
        """E(X_t, X_t) ≈ 0."""
        X_t = create_random_tensor()

        # Utiliser une dimension comme input (simuler entrée identique)
        e_input = X_t.firstness.copy()

        result = compute_dissonance(e_input, X_t)

        # La dissonance avec firstness devrait être ~0
        assert result.dissonances_by_dimension['firstness'] < 0.01

    def test_orthogonal_input_high_dissonance(self):
        """Entrée orthogonale → haute dissonance."""
        X_t = create_random_tensor()

        # Créer un vecteur orthogonal (difficile en haute dimension, mais différent)
        e_input = np.random.randn(EMBEDDING_DIM)
        e_input = e_input / np.linalg.norm(e_input)

        result = compute_dissonance(e_input, X_t)

        # La dissonance totale devrait être significative
        assert result.total > 0.1

    def test_result_structure(self):
        """Vérifier la structure du résultat."""
        X_t = create_random_tensor()
        e_input = np.random.randn(EMBEDDING_DIM)
        e_input = e_input / np.linalg.norm(e_input)

        result = compute_dissonance(e_input, X_t)

        assert isinstance(result, DissonanceResult)
        assert hasattr(result, 'total')
        assert hasattr(result, 'is_choc')
        assert hasattr(result, 'dissonances_by_dimension')
        assert len(result.dissonances_by_dimension) == 8

    def test_is_choc_flag(self):
        """Le flag is_choc dépend du seuil."""
        X_t = create_random_tensor()
        e_input = np.random.randn(EMBEDDING_DIM)
        e_input = e_input / np.linalg.norm(e_input)

        # Seuil bas → plus de chocs
        config_low = DissonanceConfig(choc_threshold=0.1)
        result_low = compute_dissonance(e_input, X_t, config_low)

        # Seuil haut → moins de chocs
        config_high = DissonanceConfig(choc_threshold=0.9)
        result_high = compute_dissonance(e_input, X_t, config_high)

        # Avec seuil bas, plus probable d'avoir un choc
        assert result_low.is_choc or result_high.is_choc is False


class TestComputeDissonanceEnhanced:
    """Tests pour compute_dissonance_enhanced avec hard negatives."""

    def test_no_rag_results(self):
        """Sans résultats RAG → novelty_penalty = 1.0."""
        X_t = create_random_tensor()
        e_input = np.random.randn(EMBEDDING_DIM)
        e_input = e_input / np.linalg.norm(e_input)

        result = compute_dissonance_enhanced(e_input, X_t, rag_results=[])

        assert result.novelty_penalty == 1.0
        assert result.rag_results_count == 0

    def test_with_similar_rag_results(self):
        """Avec résultats RAG similaires → faible novelty."""
        X_t = create_random_tensor()
        e_input = np.random.randn(EMBEDDING_DIM)
        e_input = e_input / np.linalg.norm(e_input)

        # Créer des résultats RAG très similaires (copie avec très peu de bruit)
        rag_results = [
            {'vector': e_input.copy(), 'content': 'identical'},
            {'vector': e_input + np.random.randn(EMBEDDING_DIM) * 0.01, 'content': 'similar'},
        ]
        # Normaliser les vecteurs RAG
        for r in rag_results:
            r['vector'] = r['vector'] / np.linalg.norm(r['vector'])

        result = compute_dissonance_enhanced(e_input, X_t, rag_results)

        # Le premier vecteur est identique donc max_sim ~= 1.0
        assert result.max_similarity_to_corpus > 0.9
        assert result.novelty_penalty == 0.0  # Pas de pénalité si > 0.3

    def test_hard_negatives_detection(self):
        """Détection des hard negatives (similarité < seuil)."""
        X_t = create_random_tensor()
        e_input = np.random.randn(EMBEDDING_DIM)
        e_input = e_input / np.linalg.norm(e_input)

        # Créer un vecteur opposé (hard negative)
        opposite = -e_input

        rag_results = [
            {'vector': opposite, 'content': 'contradiction', 'source': 'test'},
            {'vector': e_input, 'content': 'similar', 'source': 'test'},
        ]

        result = compute_dissonance_enhanced(e_input, X_t, rag_results)

        # Au moins un hard negative devrait être détecté
        assert len(result.hard_negatives) >= 1
        assert result.contradiction_score > 0

    def test_total_dissonance_combines_all(self):
        """La dissonance totale combine base + contradiction + novelty."""
        X_t = create_random_tensor()
        e_input = np.random.randn(EMBEDDING_DIM)
        e_input = e_input / np.linalg.norm(e_input)

        config = DissonanceConfig(
            contradiction_weight=0.2,
            novelty_weight=0.1
        )

        result = compute_dissonance_enhanced(e_input, X_t, [], config)

        expected_total = (
            result.base_dissonance +
            config.contradiction_weight * result.contradiction_score +
            config.novelty_weight * result.novelty_penalty
        )

        assert np.isclose(result.total, expected_total)


class TestSelfDissonance:
    """Tests pour compute_self_dissonance."""

    def test_coherent_tensor(self):
        """Tenseur cohérent → faible dissonance interne."""
        # Créer un tenseur où toutes les dimensions sont identiques
        base_vector = np.random.randn(EMBEDDING_DIM)
        base_vector = base_vector / np.linalg.norm(base_vector)

        tensor = StateTensor(
            state_id=0,
            timestamp=datetime.now().isoformat(),
        )
        for dim_name in DIMENSION_NAMES:
            # Utiliser le même vecteur (parfaitement cohérent)
            setattr(tensor, dim_name, base_vector.copy())

        dissonance = compute_self_dissonance(tensor)

        # Devrait être zéro car toutes les dimensions sont identiques
        assert dissonance < 0.01

    def test_incoherent_tensor(self):
        """Tenseur incohérent → haute dissonance interne."""
        tensor = create_random_tensor()  # Dimensions aléatoires = incohérent

        dissonance = compute_self_dissonance(tensor)

        # Devrait être plus élevé
        assert dissonance > 0.3


class TestImpact:
    """Tests pour la création d'Impact."""

    def test_create_impact_from_dissonance(self):
        """Créer un Impact à partir d'un résultat de dissonance."""
        X_t = create_random_tensor()
        e_input = np.random.randn(EMBEDDING_DIM)
        e_input = e_input / np.linalg.norm(e_input)

        dissonance_result = compute_dissonance(e_input, X_t)

        impact = create_impact_from_dissonance(
            dissonance=dissonance_result,
            trigger_type='user',
            trigger_content='Test message',
            trigger_vector=e_input,
            state_id=0,
            impact_id=1,
        )

        assert impact.impact_id == 1
        assert impact.trigger_type == 'user'
        assert impact.dissonance_total == dissonance_result.total
        assert impact.resolved is False

    def test_impact_to_dict(self):
        """Impact.to_dict() retourne un dictionnaire valide."""
        impact = Impact(
            impact_id=1,
            timestamp=datetime.now().isoformat(),
            state_id_at_impact=0,
            trigger_type='user',
            trigger_content='Test',
            dissonance_total=0.5,
        )

        d = impact.to_dict()

        assert 'impact_id' in d
        assert 'timestamp' in d
        assert d['timestamp'].endswith('Z')
        assert d['resolved'] is False


class TestDissonanceMonotonicity:
    """Tests de monotonie de la dissonance."""

    def test_more_different_more_dissonance(self):
        """Plus différent = plus de dissonance."""
        X_t = create_random_tensor()

        # Entrée identique à une dimension
        identical = X_t.firstness.copy()
        result_identical = compute_dissonance(identical, X_t)

        # Entrée légèrement différente
        slightly_different = X_t.firstness + np.random.randn(EMBEDDING_DIM) * 0.1
        slightly_different = slightly_different / np.linalg.norm(slightly_different)
        result_slight = compute_dissonance(slightly_different, X_t)

        # Entrée très différente
        very_different = np.random.randn(EMBEDDING_DIM)
        very_different = very_different / np.linalg.norm(very_different)
        result_very = compute_dissonance(very_different, X_t)

        # Vérifier la monotonie sur la dimension firstness
        assert result_identical.dissonances_by_dimension['firstness'] < \
               result_slight.dissonances_by_dimension['firstness']


class TestDissonanceResultSerialization:
    """Tests de sérialisation."""

    def test_to_dict(self):
        """DissonanceResult.to_dict() fonctionne."""
        X_t = create_random_tensor()
        e_input = np.random.randn(EMBEDDING_DIM)
        e_input = e_input / np.linalg.norm(e_input)

        result = compute_dissonance(e_input, X_t)
        d = result.to_dict()

        assert 'total' in d
        assert 'is_choc' in d
        assert 'dissonances_by_dimension' in d

    def test_to_json(self):
        """DissonanceResult.to_json() produit du JSON valide."""
        import json

        X_t = create_random_tensor()
        e_input = np.random.randn(EMBEDDING_DIM)
        e_input = e_input / np.linalg.norm(e_input)

        result = compute_dissonance(e_input, X_t)
        json_str = result.to_json()

        # Doit être parseable
        parsed = json.loads(json_str)
        assert parsed['total'] == result.total


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
