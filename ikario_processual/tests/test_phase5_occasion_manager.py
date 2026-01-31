#!/usr/bin/env python3
"""Tests pour Phase 5 - OccasionManager."""

import tempfile

import pytest

from ..occasion_manager import OccasionManager, get_state_profile


class TestGetStateProfile:
    """Tests de la fonction get_state_profile."""

    @pytest.mark.skip(reason="Nécessite Weaviate avec S(0) et directions")
    def test_get_profile_s0(self):
        """Récupérer le profil de S(0)."""
        profile = get_state_profile(0)

        assert isinstance(profile, dict)
        # Devrait avoir des catégories
        assert len(profile) > 0

        # Les valeurs doivent être dans [-1, 1]
        for category, components in profile.items():
            for name, value in components.items():
                assert -1 <= value <= 1, f"{name} = {value} hors limites"


class TestOccasionManager:
    """Tests de l'OccasionManager."""

    @pytest.fixture
    def manager(self):
        """Créer un manager avec répertoire temporaire."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield OccasionManager(log_dir=tmpdir, embedding_model=None)

    def test_manager_initialization(self, manager):
        """Test d'initialisation du manager."""
        assert manager.current_occasion_id >= 0
        assert manager.logger is not None
        assert manager.transformer is not None

    def test_prehend_structure(self, manager):
        """Test de la structure de préhension."""
        trigger = {
            "type": "user",
            "content": "Test question",
            "metadata": {}
        }

        prehension = manager._prehend(trigger)

        assert "previous_state_id" in prehension
        assert "thoughts" in prehension
        assert "documents" in prehension
        assert isinstance(prehension["thoughts"], list)
        assert isinstance(prehension["documents"], list)

    def test_concresce_simulation(self, manager):
        """Test de la concrescence (simulation)."""
        trigger = {
            "type": "user",
            "content": "Test question sur Whitehead",
            "metadata": {}
        }

        prehension = {
            "previous_state_id": 0,
            "previous_state_vector": None,
            "thoughts": [{"content": "Pensée 1"}],
            "documents": []
        }

        concrescence = manager._concresce(trigger, prehension)

        assert "response" in concrescence
        assert "new_thoughts" in concrescence
        assert "tools_used" in concrescence
        assert "[Simulation]" in concrescence["response"]

    @pytest.mark.skip(reason="Nécessite Weaviate avec S(0)")
    def test_run_occasion_full(self, manager):
        """Test d'un cycle complet d'occasion."""
        trigger = {
            "type": "user",
            "content": "Qu'est-ce que le processus selon Whitehead ?",
            "metadata": {}
        }

        result = manager.run_occasion(trigger)

        assert "occasion_id" in result
        assert "response" in result
        assert "new_state_id" in result
        assert "profile" in result
        assert "processing_time_ms" in result
        assert result["processing_time_ms"] > 0

    @pytest.mark.skip(reason="Nécessite Weaviate avec S(0)")
    def test_state_evolution_after_occasion(self, manager):
        """Vérifier que l'état évolue après une occasion."""
        initial_state_id = manager.transformer.get_current_state_id()

        trigger = {
            "type": "user",
            "content": "Je suis très curieux à propos de la philosophie",
            "metadata": {}
        }

        result = manager.run_occasion(trigger)

        assert result["new_state_id"] == initial_state_id + 1

    @pytest.mark.skip(reason="Nécessite Weaviate")
    def test_occasion_logged(self, manager):
        """Vérifier que l'occasion est loggée."""
        trigger = {
            "type": "user",
            "content": "Test logging",
            "metadata": {}
        }

        result = manager.run_occasion(trigger)

        logged = manager.logger.get_occasion(result["occasion_id"])
        assert logged is not None
        assert logged.trigger_content == "Test logging"


class TestOccasionManagerTriggerTypes:
    """Tests des différents types de triggers."""

    @pytest.fixture
    def manager(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield OccasionManager(log_dir=tmpdir, embedding_model=None)

    def test_user_trigger(self, manager):
        """Test trigger utilisateur."""
        trigger = {
            "type": "user",
            "content": "Question utilisateur",
            "metadata": {}
        }

        prehension = manager._prehend(trigger)
        concrescence = manager._concresce(trigger, prehension)

        assert "Question utilisateur" in concrescence["response"]

    def test_timer_trigger(self, manager):
        """Test trigger timer (auto-réflexion)."""
        trigger = {
            "type": "timer",
            "content": "Moment d'auto-réflexion",
            "metadata": {"auto": True}
        }

        prehension = manager._prehend(trigger)
        concrescence = manager._concresce(trigger, prehension)

        assert concrescence["response"] is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
