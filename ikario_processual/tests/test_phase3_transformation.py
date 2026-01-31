#!/usr/bin/env python3
"""Tests pour Phase 3 - Transformation d'état."""

import numpy as np
import pytest

from ..state_transformation import (
    transform_state,
    compute_adaptive_params,
    StateTransformer
)


class TestTransformState:
    """Tests de la fonction de transformation."""

    def test_transform_preserves_norm(self):
        """Le vecteur transformé doit rester normalisé."""
        s_prev = np.random.randn(1024)
        s_prev = s_prev / np.linalg.norm(s_prev)

        occasion = np.random.randn(1024)
        occasion = occasion / np.linalg.norm(occasion)

        s_new = transform_state(s_prev, occasion)

        assert abs(np.linalg.norm(s_new) - 1.0) < 0.001

    def test_high_alpha_preserves_identity(self):
        """Alpha élevé = peu de changement."""
        s_prev = np.random.randn(1024)
        s_prev = s_prev / np.linalg.norm(s_prev)

        occasion = np.random.randn(1024)
        occasion = occasion / np.linalg.norm(occasion)

        s_new = transform_state(s_prev, occasion, alpha=0.99, beta=0.01)

        similarity = np.dot(s_prev, s_new)
        assert similarity > 0.98, f"Trop de changement: similarity={similarity}"

    def test_low_alpha_allows_change(self):
        """Alpha bas = plus de changement."""
        s_prev = np.random.randn(1024)
        s_prev = s_prev / np.linalg.norm(s_prev)

        # Occasion très différente
        occasion = -s_prev + 0.1 * np.random.randn(1024)
        occasion = occasion / np.linalg.norm(occasion)

        s_new = transform_state(s_prev, occasion, alpha=0.5, beta=0.5)

        similarity = np.dot(s_prev, s_new)
        assert similarity < 0.9, f"Pas assez de changement: similarity={similarity}"

    def test_identical_occasion_increases_identity(self):
        """Si l'occasion est identique à l'état, l'identité est renforcée."""
        s_prev = np.random.randn(1024)
        s_prev = s_prev / np.linalg.norm(s_prev)

        s_new = transform_state(s_prev, s_prev.copy(), alpha=0.85, beta=0.15)

        # Doit rester très similaire
        similarity = np.dot(s_prev, s_new)
        assert similarity > 0.99


class TestAdaptiveParams:
    """Tests des paramètres adaptatifs."""

    def test_default_params(self):
        """Paramètres par défaut."""
        alpha, beta = compute_adaptive_params({})
        assert abs(alpha + beta - 1.0) < 0.001
        assert 0.8 < alpha < 0.9
        assert 0.1 < beta < 0.2

    def test_more_thoughts_increases_beta(self):
        """Plus de pensées = plus de beta."""
        alpha1, beta1 = compute_adaptive_params({'thoughts_created': 0})
        alpha2, beta2 = compute_adaptive_params({'thoughts_created': 5})

        assert beta2 > beta1
        assert alpha2 < alpha1

    def test_timer_reduces_intensity(self):
        """Timer = moins d'intensité."""
        alpha_user, beta_user = compute_adaptive_params({
            'trigger_type': 'user',
            'thoughts_created': 3
        })
        alpha_timer, beta_timer = compute_adaptive_params({
            'trigger_type': 'timer',
            'thoughts_created': 3
        })

        assert beta_timer < beta_user
        assert alpha_timer > alpha_user

    def test_params_sum_to_one(self):
        """Alpha + beta = 1 toujours."""
        test_cases = [
            {'thoughts_created': 0},
            {'thoughts_created': 10},
            {'trigger_type': 'timer'},
            {'trigger_type': 'user', 'trigger_content': 'x' * 300},
        ]

        for case in test_cases:
            alpha, beta = compute_adaptive_params(case)
            assert abs(alpha + beta - 1.0) < 0.001, f"Cas: {case}"


class TestStateTransformer:
    """Tests du StateTransformer (nécessite Weaviate)."""

    @pytest.fixture
    def transformer(self):
        """Créer un transformer sans modèle (tests unitaires)."""
        return StateTransformer(embedding_model=None)

    def test_get_current_state_id(self, transformer):
        """Test de récupération de l'ID courant."""
        # Ce test nécessite Weaviate
        state_id = transformer.get_current_state_id()
        assert isinstance(state_id, int)
        # -1 si pas d'état, sinon >= 0
        assert state_id >= -1

    @pytest.mark.skip(reason="Nécessite Weaviate avec S(0)")
    def test_get_state_vector(self, transformer):
        """Test de récupération du vecteur d'état."""
        vector = transformer.get_state_vector(0)
        if vector is not None:
            assert len(vector) == 1024
            assert abs(np.linalg.norm(vector) - 1.0) < 0.01


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
