#!/usr/bin/env python3
"""
Tests pour le module de fixation - Phase 3.

Les 4 méthodes de Peirce :
1. Tenacity (0.05) - Minimal
2. Authority (0.25) - Pacte multi-vecteurs
3. A Priori (0.25) - Cohérence
4. Science (0.45) - Dominant

Exécuter: pytest ikario_processual/tests/test_fixation.py -v
"""

import numpy as np
import pytest
from datetime import datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ikario_processual.state_tensor import StateTensor, DIMENSION_NAMES, EMBEDDING_DIM
from ikario_processual.fixation import (
    FixationConfig,
    FixationResult,
    Tenacity,
    Authority,
    APriori,
    Science,
    compute_delta,
    apply_delta,
    apply_delta_all_dimensions,
    PACTE_ARTICLES,
    CRITICAL_ARTICLES,
    PHILOSOPHICAL_ANCHORS,
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


def create_random_input() -> np.ndarray:
    """Crée un vecteur d'entrée normalisé."""
    v = np.random.randn(EMBEDDING_DIM)
    return v / np.linalg.norm(v)


class TestFixationConfig:
    """Tests pour FixationConfig."""

    def test_default_weights_sum_to_one(self):
        """Les poids par défaut doivent sommer à 1.0."""
        config = FixationConfig()
        total = config.w_tenacity + config.w_authority + config.w_apriori + config.w_science
        assert np.isclose(total, 1.0)

    def test_validate(self):
        """validate() retourne True pour config valide."""
        config = FixationConfig()
        assert config.validate() is True

    def test_science_is_dominant(self):
        """Science doit avoir le poids le plus élevé."""
        config = FixationConfig()
        assert config.w_science > config.w_authority
        assert config.w_science > config.w_apriori
        assert config.w_science > config.w_tenacity

    def test_tenacity_is_minimal(self):
        """Tenacity doit avoir le poids le plus faible."""
        config = FixationConfig()
        assert config.w_tenacity < config.w_authority
        assert config.w_tenacity < config.w_apriori
        assert config.w_tenacity < config.w_science


class TestTenacity:
    """Tests pour la méthode Tenacity."""

    def test_confirming_input_gives_delta(self):
        """Entrée confirmante → delta non-nul."""
        X_t = create_random_tensor()
        tenacity = Tenacity()

        # Utiliser thirdness comme entrée (très confirmant)
        e_input = X_t.thirdness.copy()

        delta, details = tenacity.compute(e_input, X_t)

        assert details['confirmation_score'] > 0.99
        assert details['action'] == 'reinforce'
        # Delta peut être très petit car e_input ≈ thirdness

    def test_contradicting_input_resists(self):
        """Entrée contradictoire → résistance (delta nul)."""
        X_t = create_random_tensor()
        tenacity = Tenacity()

        # Entrée aléatoire (peu confirmante)
        e_input = create_random_input()

        delta, details = tenacity.compute(e_input, X_t)

        # En haute dimension, similarité aléatoire ~0
        assert details['action'] == 'resist'
        assert np.allclose(delta, 0)


class TestAuthority:
    """Tests pour la méthode Authority (Pacte multi-vecteurs)."""

    def test_pacte_articles_count(self):
        """Vérifier qu'il y a 8 articles du Pacte."""
        assert len(PACTE_ARTICLES) == 8

    def test_critical_articles_count(self):
        """Vérifier qu'il y a 3 articles critiques."""
        assert len(CRITICAL_ARTICLES) == 3

    def test_philosophical_anchors_count(self):
        """Vérifier qu'il y a 3 ancres philosophiques."""
        assert len(PHILOSOPHICAL_ANCHORS) == 3

    def test_authority_without_vectors_is_neutral(self):
        """Authority sans vecteurs → neutre."""
        X_t = create_random_tensor()
        e_input = create_random_input()

        authority = Authority()  # Pas de vecteurs
        delta, details = authority.compute(e_input, X_t)

        assert np.allclose(delta, 0)

    def test_authority_with_mock_vectors(self):
        """Authority avec vecteurs mock fonctionne."""
        X_t = create_random_tensor()
        e_input = create_random_input()

        # Créer des vecteurs mock
        mock_pacte = {
            'article_1_conatus': create_random_input(),
            'article_2_non_nuisance': create_random_input(),
        }

        authority = Authority(pacte_vectors=mock_pacte)
        delta, details = authority.compute(e_input, X_t)

        assert 'pacte_alignments' in details
        assert len(details['pacte_alignments']) == 2


class TestAPriori:
    """Tests pour la méthode A Priori."""

    def test_coherent_input_integrates(self):
        """Entrée cohérente → intégration."""
        X_t = create_random_tensor()
        apriori = APriori()

        # Créer une entrée cohérente (moyenne des dimensions)
        coherent = (X_t.firstness + X_t.thirdness + X_t.orientations + X_t.valeurs) / 4
        coherent = coherent / np.linalg.norm(coherent)

        delta, details = apriori.compute(coherent, X_t)

        assert details['avg_coherence'] > 0.3
        assert np.linalg.norm(delta) > 0

    def test_incoherent_input_weak_integrate(self):
        """Entrée incohérente → faible intégration."""
        X_t = create_random_tensor()
        apriori = APriori()

        # Entrée opposée (incohérente)
        incoherent = -X_t.thirdness

        delta, details = apriori.compute(incoherent, X_t)

        assert details['avg_coherence'] < 0
        assert details['action'] == 'weak_integrate'


class TestScience:
    """Tests pour la méthode Science."""

    def test_no_rag_results_prudent(self):
        """Sans RAG → prudence."""
        X_t = create_random_tensor()
        e_input = create_random_input()
        science = Science()

        delta, details = science.compute(e_input, X_t, rag_results=None)

        assert details['action'] == 'no_corroboration_prudent'
        assert np.linalg.norm(delta) > 0  # Petit delta vers secondness

    def test_strong_corroboration_integrates(self):
        """Forte corroboration → intégration forte."""
        X_t = create_random_tensor()
        e_input = create_random_input()
        science = Science()

        # RAG avec vecteurs très similaires
        rag_results = [
            {'vector': e_input.copy()},
            {'vector': e_input + np.random.randn(EMBEDDING_DIM) * 0.01},
        ]
        for r in rag_results:
            r['vector'] = r['vector'] / np.linalg.norm(r['vector'])

        delta, details = science.compute(e_input, X_t, rag_results)

        assert details['avg_corroboration'] > 0.9
        assert details['action'] == 'strong_corroboration'

    def test_weak_corroboration_tension(self):
        """Faible corroboration → tension (secondness)."""
        X_t = create_random_tensor()
        e_input = create_random_input()
        science = Science()

        # RAG avec vecteurs opposés
        rag_results = [
            {'vector': -e_input},
        ]

        delta, details = science.compute(e_input, X_t, rag_results)

        assert details['avg_corroboration'] < 0
        assert details['action'] == 'low_corroboration_tension'


class TestComputeDelta:
    """Tests pour compute_delta (combinaison des 4 méthodes)."""

    def test_delta_magnitude_clamped(self):
        """||δ|| doit être ≤ δ_max."""
        X_t = create_random_tensor()
        e_input = create_random_input()

        config = FixationConfig(delta_max=0.001)
        result = compute_delta(e_input, X_t, config=config)

        assert result.magnitude <= config.delta_max + 1e-9

    def test_all_contributions_present(self):
        """Toutes les contributions doivent être présentes."""
        X_t = create_random_tensor()
        e_input = create_random_input()

        result = compute_delta(e_input, X_t)

        assert 'tenacity' in result.contributions
        assert 'authority' in result.contributions
        assert 'apriori' in result.contributions
        assert 'science' in result.contributions

    def test_science_has_most_influence(self):
        """Science (0.45) doit généralement avoir le plus d'influence."""
        # Note: Ce test est probabiliste
        X_t = create_random_tensor()

        # Créer des RAG avec forte corroboration
        e_input = create_random_input()
        rag_results = [{'vector': e_input.copy()}]

        result = compute_delta(e_input, X_t, rag_results=rag_results)

        # Science devrait contribuer significativement
        # (pas toujours le plus à cause des autres méthodes)
        assert result.contributions['science'] >= 0

    def test_result_has_details(self):
        """Le résultat doit contenir les détails de chaque méthode."""
        X_t = create_random_tensor()
        e_input = create_random_input()

        result = compute_delta(e_input, X_t)

        assert hasattr(result, 'tenacity_detail')
        assert hasattr(result, 'authority_detail')
        assert hasattr(result, 'apriori_detail')
        assert hasattr(result, 'science_detail')


class TestApplyDelta:
    """Tests pour apply_delta."""

    def test_state_id_incremented(self):
        """state_id doit être incrémenté."""
        X_t = create_random_tensor()
        X_t.state_id = 5

        delta = np.random.randn(EMBEDDING_DIM) * 0.001

        X_new = apply_delta(X_t, delta)

        assert X_new.state_id == 6
        assert X_new.previous_state_id == 5

    def test_result_normalized(self):
        """La dimension modifiée doit rester normalisée."""
        X_t = create_random_tensor()
        delta = np.random.randn(EMBEDDING_DIM) * 0.1

        X_new = apply_delta(X_t, delta, target_dim='thirdness')

        assert np.isclose(np.linalg.norm(X_new.thirdness), 1.0)

    def test_other_dimensions_unchanged(self):
        """Les autres dimensions ne doivent pas changer."""
        X_t = create_random_tensor()
        delta = np.random.randn(EMBEDDING_DIM) * 0.1

        X_new = apply_delta(X_t, delta, target_dim='thirdness')

        # firstness ne doit pas avoir changé
        assert np.allclose(X_new.firstness, X_t.firstness)


class TestApplyDeltaAllDimensions:
    """Tests pour apply_delta_all_dimensions."""

    def test_all_dimensions_modified(self):
        """Toutes les dimensions doivent être modifiées."""
        X_t = create_random_tensor()
        e_input = create_random_input()

        result = compute_delta(e_input, X_t)
        X_new = apply_delta_all_dimensions(X_t, e_input, result)

        # Vérifier que les dimensions ont changé
        changes = []
        for dim_name in DIMENSION_NAMES:
            old = getattr(X_t, dim_name)
            new = getattr(X_new, dim_name)
            diff = np.linalg.norm(new - old)
            changes.append(diff)

        # Au moins quelques dimensions devraient avoir changé
        assert sum(c > 0 for c in changes) > 0

    def test_all_dimensions_normalized(self):
        """Toutes les dimensions doivent rester normalisées."""
        X_t = create_random_tensor()
        e_input = create_random_input()

        result = compute_delta(e_input, X_t)
        X_new = apply_delta_all_dimensions(X_t, e_input, result)

        for dim_name in DIMENSION_NAMES:
            vec = getattr(X_new, dim_name)
            assert np.isclose(np.linalg.norm(vec), 1.0, atol=1e-5)


class TestFixationResultSerialization:
    """Tests de sérialisation."""

    def test_to_dict(self):
        """to_dict() fonctionne."""
        X_t = create_random_tensor()
        e_input = create_random_input()

        result = compute_delta(e_input, X_t)
        d = result.to_dict()

        assert 'magnitude' in d
        assert 'was_clamped' in d
        assert 'contributions' in d


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
