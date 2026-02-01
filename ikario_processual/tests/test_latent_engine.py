#!/usr/bin/env python3
"""
Tests pour le LatentEngine - Phase 4.

Le cycle sémiotique :
1. FIRSTNESS  : Vectoriser, extraire saillances
2. SECONDNESS : Calculer dissonance, créer Impacts
3. THIRDNESS  : Appliquer fixation, mettre à jour état
4. SÉMIOSE    : Créer Thoughts, décider verbalisation

Exécuter: pytest ikario_processual/tests/test_latent_engine.py -v
"""

import numpy as np
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ikario_processual.state_tensor import StateTensor, DIMENSION_NAMES, EMBEDDING_DIM
from ikario_processual.dissonance import DissonanceResult, DissonanceConfig
from ikario_processual.fixation import FixationResult, FixationConfig
from ikario_processual.latent_engine import (
    Thought,
    CycleResult,
    CycleLogger,
    LatentEngine,
)


def create_random_tensor(state_id: int = 0) -> StateTensor:
    """Crée un tenseur avec des vecteurs aléatoires normalisés."""
    tensor = StateTensor(
        state_id=state_id,
        timestamp=datetime.now().isoformat(),
    )
    for dim_name in DIMENSION_NAMES:
        v = np.random.randn(EMBEDDING_DIM)
        v = v / np.linalg.norm(v)
        setattr(tensor, dim_name, v)
    return tensor


class TestThought:
    """Tests pour la classe Thought."""

    def test_create_thought(self):
        """Créer une Thought."""
        thought = Thought(
            thought_id=1,
            timestamp=datetime.now().isoformat(),
            state_id=5,
            content="Test thought content",
            thought_type="reflection",
            trigger_type="user",
            trigger_summary="Hello",
            delta_magnitude=0.0005,
            dissonance_total=0.3,
            dimensions_affected=['science', 'authority'],
        )

        assert thought.thought_id == 1
        assert thought.thought_type == "reflection"

    def test_thought_to_dict(self):
        """to_dict() fonctionne."""
        thought = Thought(
            thought_id=1,
            timestamp=datetime.now().isoformat(),
            state_id=5,
            content="Test",
            thought_type="insight",
            trigger_type="user",
            trigger_summary="Hello",
            delta_magnitude=0.001,
            dissonance_total=0.5,
            dimensions_affected=[],
        )

        d = thought.to_dict()
        assert 'thought_id' in d
        assert 'content' in d
        assert d['timestamp'].endswith('Z')


class TestCycleLogger:
    """Tests pour CycleLogger."""

    def test_log_cycle(self):
        """Logger enregistre les cycles."""
        logger = CycleLogger()

        # Créer un mock CycleResult
        mock_result = MagicMock(spec=CycleResult)
        mock_result.to_dict.return_value = {
            'dissonance_total': 0.5,
            'impacts_count': 1,
            'thoughts_count': 0,
            'processing_time_ms': 50,
        }

        logger.log_cycle(mock_result)

        assert logger.total_cycles == 1
        assert len(logger.history) == 1

    def test_get_stats_empty(self):
        """Stats avec aucun cycle."""
        logger = CycleLogger()
        stats = logger.get_stats()

        assert stats['total_cycles'] == 0

    def test_get_stats_with_cycles(self):
        """Stats avec plusieurs cycles."""
        logger = CycleLogger()

        for i in range(5):
            mock_result = MagicMock(spec=CycleResult)
            mock_result.to_dict.return_value = {
                'dissonance_total': 0.3 + i * 0.1,
                'impacts_count': 1 if i % 2 == 0 else 0,
                'thoughts_count': 1,
                'processing_time_ms': 40 + i * 10,
            }
            logger.log_cycle(mock_result)

        stats = logger.get_stats()

        assert stats['total_cycles'] == 5
        assert stats['recent_cycles'] == 5
        assert stats['avg_dissonance'] > 0
        assert stats['total_impacts'] == 3  # i=0,2,4

    def test_max_history_limit(self):
        """Limite de l'historique respectée."""
        logger = CycleLogger(max_history=10)

        for i in range(20):
            mock_result = MagicMock(spec=CycleResult)
            mock_result.to_dict.return_value = {
                'dissonance_total': 0.5,
                'impacts_count': 0,
                'thoughts_count': 0,
                'processing_time_ms': 50,
            }
            logger.log_cycle(mock_result)

        assert logger.total_cycles == 20
        assert len(logger.history) == 10


class TestCycleResult:
    """Tests pour CycleResult."""

    def test_to_dict(self):
        """to_dict() retourne les bonnes clés."""
        tensor = create_random_tensor(state_id=1)

        dissonance = DissonanceResult(
            total=0.5,
            base_dissonance=0.4,
            contradiction_score=0.1,
            novelty_penalty=0.0,
            is_choc=True,
            dissonances_by_dimension={},
            hard_negatives=[],
            max_similarity_to_corpus=0.7,
            rag_results_count=3,
        )

        fixation = FixationResult(
            delta=np.zeros(EMBEDDING_DIM),
            magnitude=0.001,
            was_clamped=True,
            contributions={'tenacity': 0, 'authority': 0, 'apriori': 0, 'science': 0.001},
        )

        result = CycleResult(
            new_state=tensor,
            previous_state_id=0,
            dissonance=dissonance,
            fixation=fixation,
            impacts=[],
            thoughts=[],
            should_verbalize=True,
            verbalization_reason="conversation_mode",
            processing_time_ms=100,
            cycle_number=1,
        )

        d = result.to_dict()

        assert d['cycle_number'] == 1
        assert d['new_state_id'] == 1
        assert d['is_choc'] is True
        assert d['should_verbalize'] is True


class TestLatentEngineUnit:
    """Tests unitaires pour LatentEngine (sans Weaviate)."""

    def test_vectorize_input(self):
        """_vectorize_input normalise le vecteur."""
        # Mock du model
        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.randn(EMBEDDING_DIM)

        # Mock du client
        mock_client = MagicMock()

        engine = LatentEngine(
            weaviate_client=mock_client,
            embedding_model=mock_model
        )

        result = engine._vectorize_input("Test content")

        assert result.shape == (EMBEDDING_DIM,)
        assert np.isclose(np.linalg.norm(result), 1.0)

    def test_extract_saillances(self):
        """_extract_saillances retourne les bonnes dimensions."""
        mock_model = MagicMock()
        mock_client = MagicMock()

        engine = LatentEngine(
            weaviate_client=mock_client,
            embedding_model=mock_model
        )

        X_t = create_random_tensor()
        e_input = np.random.randn(EMBEDDING_DIM)
        e_input = e_input / np.linalg.norm(e_input)

        saillances = engine._extract_saillances(e_input, X_t)

        assert len(saillances) == 8
        for dim in DIMENSION_NAMES:
            assert dim in saillances
            assert -1.0 <= saillances[dim] <= 1.0

    def test_should_verbalize_user_mode(self):
        """Mode user → toujours verbaliser."""
        mock_model = MagicMock()
        mock_client = MagicMock()

        engine = LatentEngine(
            weaviate_client=mock_client,
            embedding_model=mock_model
        )

        trigger = {'type': 'user', 'content': 'Hello'}

        dissonance = MagicMock()
        dissonance.total = 0.2
        dissonance.hard_negatives = []

        fixation = MagicMock()
        X_new = create_random_tensor()

        should, reason = engine._should_verbalize(trigger, dissonance, fixation, X_new)

        assert should is True
        assert reason == "conversation_mode"

    def test_should_verbalize_high_dissonance(self):
        """Haute dissonance en mode autonome → verbaliser."""
        mock_model = MagicMock()
        mock_client = MagicMock()

        engine = LatentEngine(
            weaviate_client=mock_client,
            embedding_model=mock_model
        )

        trigger = {'type': 'corpus', 'content': 'Article'}

        dissonance = MagicMock()
        dissonance.total = 0.7  # > 0.6
        dissonance.hard_negatives = []

        fixation = MagicMock()
        X_new = create_random_tensor()

        should, reason = engine._should_verbalize(trigger, dissonance, fixation, X_new)

        assert should is True
        assert reason == "high_dissonance_discovery"

    def test_should_verbalize_silent(self):
        """Faible dissonance en mode autonome → silencieux."""
        mock_model = MagicMock()
        mock_client = MagicMock()

        engine = LatentEngine(
            weaviate_client=mock_client,
            embedding_model=mock_model
        )

        trigger = {'type': 'timer', 'content': 'Tick'}

        dissonance = MagicMock()
        dissonance.total = 0.2
        dissonance.hard_negatives = []

        fixation = MagicMock()
        X_new = create_random_tensor()

        should, reason = engine._should_verbalize(trigger, dissonance, fixation, X_new)

        assert should is False
        assert reason == "silent_processing"

    def test_generate_thought_content_insight(self):
        """Génération de contenu pour insight."""
        mock_model = MagicMock()
        mock_client = MagicMock()

        engine = LatentEngine(
            weaviate_client=mock_client,
            embedding_model=mock_model
        )

        dissonance = MagicMock()
        dissonance.total = 0.6
        dissonance.hard_negatives = [{'content': 'test'}]

        fixation = MagicMock()
        fixation.magnitude = 0.001

        content = engine._generate_thought_content(
            trigger_type='user',
            trigger_content='Test trigger',
            dissonance=dissonance,
            fixation_result=fixation,
            thought_type='insight'
        )

        assert 'Choc détecté' in content
        assert '0.600' in content


class TestLatentEngineGetStats:
    """Tests pour get_stats()."""

    def test_get_stats_initial(self):
        """Stats initiales."""
        mock_model = MagicMock()
        mock_client = MagicMock()

        engine = LatentEngine(
            weaviate_client=mock_client,
            embedding_model=mock_model
        )

        stats = engine.get_stats()

        assert stats['total_cycles'] == 0
        assert stats['impacts_created'] == 0
        assert stats['thoughts_created'] == 0


# Note: Les tests d'intégration avec Weaviate réel sont dans un fichier séparé
# car ils nécessitent une connexion active.


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
