#!/usr/bin/env python3
"""Tests pour Phase 4 - Logging des occasions."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from ..occasion_logger import OccasionLogger, OccasionLog


class TestOccasionLog:
    """Tests de la structure OccasionLog."""

    def test_create_occasion_log(self):
        """Créer un OccasionLog basique."""
        log = OccasionLog(
            occasion_id=1,
            timestamp=datetime.now().isoformat(),
            trigger_type="user",
            trigger_content="Test",
            previous_state_id=0,
            prehended_thoughts_count=5,
            prehended_docs_count=2,
            response_summary="Response",
            new_state_id=1,
            alpha_used=0.85,
            beta_used=0.15,
            processing_time_ms=1000
        )

        assert log.occasion_id == 1
        assert log.trigger_type == "user"
        assert log.alpha_used == 0.85

    def test_default_lists(self):
        """Les listes par défaut sont vides."""
        log = OccasionLog(
            occasion_id=1,
            timestamp=datetime.now().isoformat(),
            trigger_type="user",
            trigger_content="Test",
            previous_state_id=0,
            prehended_thoughts_count=0,
            prehended_docs_count=0,
            response_summary="Response",
            new_state_id=1,
            alpha_used=0.85,
            beta_used=0.15
        )

        assert log.new_thoughts == []
        assert log.tools_used == []
        assert log.prehended_thoughts == []


class TestOccasionLogger:
    """Tests du logger d'occasions."""

    @pytest.fixture
    def temp_logger(self):
        """Créer un logger avec répertoire temporaire."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield OccasionLogger(tmpdir)

    def test_log_and_retrieve(self, temp_logger):
        """Logger et relire une occasion."""
        occasion = OccasionLog(
            occasion_id=42,
            timestamp=datetime.now().isoformat(),
            trigger_type="user",
            trigger_content="Question test",
            previous_state_id=5,
            prehended_thoughts_count=3,
            prehended_docs_count=1,
            response_summary="Réponse test",
            new_thoughts=["Nouvelle pensée"],
            tools_used=["search_thoughts"],
            new_state_id=6,
            alpha_used=0.82,
            beta_used=0.18,
            processing_time_ms=2500
        )

        # Logger
        filepath = temp_logger.log(occasion)
        assert filepath.exists()

        # Relire
        loaded = temp_logger.get_occasion(42)
        assert loaded is not None
        assert loaded.occasion_id == 42
        assert loaded.trigger_content == "Question test"
        assert loaded.new_thoughts == ["Nouvelle pensée"]

    def test_get_nonexistent(self, temp_logger):
        """Récupérer une occasion inexistante retourne None."""
        loaded = temp_logger.get_occasion(99999)
        assert loaded is None

    def test_get_recent_occasions(self, temp_logger):
        """Récupérer les occasions récentes."""
        # Créer plusieurs occasions
        for i in range(5):
            occasion = OccasionLog(
                occasion_id=i,
                timestamp=datetime.now().isoformat(),
                trigger_type="user",
                trigger_content=f"Question {i}",
                previous_state_id=max(0, i - 1),
                prehended_thoughts_count=i,
                prehended_docs_count=1,
                response_summary=f"Réponse {i}",
                new_state_id=i,
                alpha_used=0.85,
                beta_used=0.15,
                processing_time_ms=1000 + i * 100
            )
            temp_logger.log(occasion)

        # Récupérer les 3 dernières
        recent = temp_logger.get_recent_occasions(3)
        assert len(recent) == 3

        # Vérifier l'ordre (plus récent d'abord)
        assert recent[0].occasion_id == 4
        assert recent[1].occasion_id == 3
        assert recent[2].occasion_id == 2

    def test_get_last_occasion_id(self, temp_logger):
        """Récupérer l'ID de la dernière occasion."""
        # Vide
        assert temp_logger.get_last_occasion_id() == -1

        # Ajouter une occasion
        occasion = OccasionLog(
            occasion_id=10,
            timestamp=datetime.now().isoformat(),
            trigger_type="user",
            trigger_content="Test",
            previous_state_id=0,
            prehended_thoughts_count=0,
            prehended_docs_count=0,
            response_summary="Response",
            new_state_id=1,
            alpha_used=0.85,
            beta_used=0.15
        )
        temp_logger.log(occasion)

        assert temp_logger.get_last_occasion_id() == 10

    def test_profile_evolution(self, temp_logger):
        """Tracer l'évolution d'une composante."""
        # Créer des occasions avec évolution de curiosité
        for i in range(5):
            occasion = OccasionLog(
                occasion_id=i,
                timestamp=datetime.now().isoformat(),
                trigger_type="user",
                trigger_content=f"Question {i}",
                previous_state_id=max(0, i - 1),
                prehended_thoughts_count=0,
                prehended_docs_count=0,
                response_summary=f"Réponse {i}",
                new_state_id=i,
                alpha_used=0.85,
                beta_used=0.15,
                profile_before={"epistemic": {"curiosity": 0.5 + i * 0.05}},
                profile_after={"epistemic": {"curiosity": 0.5 + (i + 1) * 0.05}}
            )
            temp_logger.log(occasion)

        evolution = temp_logger.get_profile_evolution("curiosity", last_n=5)

        assert len(evolution) == 5
        # Vérifier que la curiosité augmente
        values = [v for _, v in evolution]
        assert values[-1] > values[0]

    def test_statistics(self, temp_logger):
        """Calculer des statistiques."""
        # Créer quelques occasions
        for i in range(3):
            occasion = OccasionLog(
                occasion_id=i,
                timestamp=datetime.now().isoformat(),
                trigger_type="user" if i % 2 == 0 else "timer",
                trigger_content=f"Question {i}",
                previous_state_id=max(0, i - 1),
                prehended_thoughts_count=0,
                prehended_docs_count=0,
                response_summary=f"Réponse {i}",
                new_thoughts=["t1"] if i == 0 else [],
                tools_used=["tool1", "tool2"],
                new_state_id=i,
                alpha_used=0.85,
                beta_used=0.15,
                processing_time_ms=1000 + i * 500
            )
            temp_logger.log(occasion)

        stats = temp_logger.get_statistics()

        assert stats["count"] == 3
        assert "processing_time" in stats
        assert "thoughts_created" in stats
        assert "trigger_distribution" in stats
        assert stats["trigger_distribution"]["user"] == 2
        assert stats["trigger_distribution"]["timer"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
