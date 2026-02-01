#!/usr/bin/env python3
"""
Tests pour le module daemon - Phase 7.

Le daemon d'individuation autonome :
1. Mode CONVERSATION : toujours verbalise
2. Mode AUTONOME : pensee silencieuse (~1000 cycles/jour)
3. Amendment #5 : Rumination sur impacts non resolus

Executer: pytest ikario_processual/tests/test_daemon.py -v
"""

import asyncio
import numpy as np
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ikario_processual.state_tensor import StateTensor, DIMENSION_NAMES, EMBEDDING_DIM
from ikario_processual.dissonance import DissonanceResult
from ikario_processual.fixation import FixationResult
from ikario_processual.latent_engine import CycleResult, LatentEngine
from ikario_processual.vigilance import VigilanceSystem, VigilanceAlert
from ikario_processual.state_to_language import StateToLanguage, TranslationResult
from ikario_processual.daemon import (
    TriggerType,
    DaemonMode,
    DaemonConfig,
    DaemonStats,
    Trigger,
    VerbalizationEvent,
    TriggerGenerator,
    IkarioDaemon,
    create_daemon,
)


def create_random_tensor(state_id: int = 0, seed: int = None) -> StateTensor:
    """Cree un tenseur avec des vecteurs aleatoires normalises."""
    if seed is not None:
        np.random.seed(seed)

    tensor = StateTensor(
        state_id=state_id,
        timestamp=datetime.now().isoformat(),
    )
    for dim_name in DIMENSION_NAMES:
        v = np.random.randn(EMBEDDING_DIM)
        v = v / np.linalg.norm(v)
        setattr(tensor, dim_name, v)
    return tensor


def create_mock_cycle_result(
    state_id: int = 1,
    should_verbalize: bool = False,
    verbalization_reason: str = "silent_processing",
    dissonance_total: float = 0.3,
) -> CycleResult:
    """Cree un CycleResult mock."""
    tensor = create_random_tensor(state_id=state_id)

    dissonance = DissonanceResult(
        total=dissonance_total,
        base_dissonance=dissonance_total * 0.8,
        contradiction_score=0.0,
        novelty_penalty=0.0,
        is_choc=dissonance_total > 0.3,
        dissonances_by_dimension={},
        hard_negatives=[],
        max_similarity_to_corpus=0.5,
        rag_results_count=5,
    )

    fixation = FixationResult(
        delta=np.zeros(EMBEDDING_DIM),
        magnitude=0.0005,
        was_clamped=False,
        contributions={'tenacity': 0, 'authority': 0, 'apriori': 0, 'science': 0.0005},
    )

    return CycleResult(
        new_state=tensor,
        previous_state_id=state_id - 1,
        dissonance=dissonance,
        fixation=fixation,
        impacts=[],
        thoughts=[],
        should_verbalize=should_verbalize,
        verbalization_reason=verbalization_reason,
        processing_time_ms=50,
        cycle_number=state_id,
    )


class TestTriggerType:
    """Tests pour TriggerType enum."""

    def test_all_types_exist(self):
        """Tous les types existent."""
        assert TriggerType.USER.value == "user"
        assert TriggerType.VEILLE.value == "veille"
        assert TriggerType.CORPUS.value == "corpus"
        assert TriggerType.RUMINATION.value == "rumination"
        assert TriggerType.RUMINATION_FREE.value == "rumination_free"
        assert TriggerType.TIMER.value == "timer"
        assert TriggerType.EMPTY.value == "empty"


class TestDaemonMode:
    """Tests pour DaemonMode enum."""

    def test_all_modes_exist(self):
        """Tous les modes existent."""
        assert DaemonMode.CONVERSATION.value == "conversation"
        assert DaemonMode.AUTONOMOUS.value == "autonomous"
        assert DaemonMode.PAUSED.value == "paused"


class TestDaemonConfig:
    """Tests pour DaemonConfig."""

    def test_default_config(self):
        """Configuration par defaut."""
        config = DaemonConfig()

        assert config.cycle_interval_seconds == 90.0
        assert config.prob_unresolved_impact == 0.50
        assert config.prob_corpus == 0.30
        assert config.prob_rumination_free == 0.20

    def test_probabilities_sum_to_one(self):
        """Les probabilites somment a 1."""
        config = DaemonConfig()
        total = config.prob_unresolved_impact + config.prob_corpus + config.prob_rumination_free
        assert np.isclose(total, 1.0)

    def test_validate_default(self):
        """La config par defaut est valide."""
        config = DaemonConfig()
        assert config.validate() == True

    def test_validate_invalid_probabilities(self):
        """Config invalide si probabilites != 1."""
        config = DaemonConfig(
            prob_unresolved_impact=0.5,
            prob_corpus=0.5,
            prob_rumination_free=0.5,  # Total = 1.5
        )
        assert config.validate() == False


class TestDaemonStats:
    """Tests pour DaemonStats."""

    def test_initial_stats(self):
        """Stats initiales a zero."""
        stats = DaemonStats()

        assert stats.total_cycles == 0
        assert stats.conversation_cycles == 0
        assert stats.autonomous_cycles == 0
        assert stats.verbalizations == 0

    def test_to_dict(self):
        """to_dict() fonctionne."""
        stats = DaemonStats()
        stats.total_cycles = 10
        stats.verbalizations = 3

        d = stats.to_dict()

        assert d['total_cycles'] == 10
        assert d['verbalizations'] == 3
        assert 'uptime_seconds' in d


class TestTrigger:
    """Tests pour Trigger."""

    def test_create_trigger(self):
        """Creer un trigger."""
        trigger = Trigger(
            type=TriggerType.USER,
            content="Hello Ikario",
            source="user",
            priority=2,
        )

        assert trigger.type == TriggerType.USER
        assert trigger.content == "Hello Ikario"
        assert trigger.priority == 2

    def test_to_dict(self):
        """to_dict() convertit correctement."""
        trigger = Trigger(
            type=TriggerType.CORPUS,
            content="Whitehead on process",
            source="library",
            metadata={'author': 'Whitehead'},
        )

        d = trigger.to_dict()

        assert d['type'] == 'corpus'
        assert d['content'] == "Whitehead on process"
        assert d['metadata']['author'] == 'Whitehead'


class TestVerbalizationEvent:
    """Tests pour VerbalizationEvent."""

    def test_create_event(self):
        """Creer un evenement."""
        event = VerbalizationEvent(
            text="Je suis curieux.",
            reason="conversation_mode",
            trigger_type="user",
            state_id=5,
            dissonance=0.4,
        )

        assert event.text == "Je suis curieux."
        assert event.reason == "conversation_mode"

    def test_to_dict(self):
        """to_dict() fonctionne."""
        event = VerbalizationEvent(
            text="Test",
            reason="test",
            trigger_type="user",
            state_id=1,
            dissonance=0.5,
        )

        d = event.to_dict()

        assert 'text' in d
        assert 'reason' in d
        assert 'timestamp' in d


class TestTriggerGenerator:
    """Tests pour TriggerGenerator."""

    def test_create_generator(self):
        """Creer un generateur."""
        config = DaemonConfig()
        generator = TriggerGenerator(config)

        assert generator.config is config
        assert generator.weaviate is None

    def test_create_user_trigger(self):
        """Creer un trigger utilisateur."""
        config = DaemonConfig()
        generator = TriggerGenerator(config)

        trigger = generator.create_user_trigger("Bonjour")

        assert trigger.type == TriggerType.USER
        assert trigger.content == "Bonjour"
        assert trigger.priority == 2  # Priorite max

    def test_create_veille_trigger(self):
        """Creer un trigger de veille."""
        config = DaemonConfig()
        generator = TriggerGenerator(config)

        trigger = generator.create_veille_trigger(
            title="Decouverte philosophique",
            snippet="Nouvelle interpretation de Whitehead",
            url="https://example.com/news",
        )

        assert trigger.type == TriggerType.VEILLE
        assert "Decouverte philosophique" in trigger.content
        assert trigger.metadata['url'] == "https://example.com/news"

    def test_fallback_trigger_without_weaviate(self):
        """Sans Weaviate, retourne trigger fallback."""
        config = DaemonConfig()
        generator = TriggerGenerator(config)

        async def run_test():
            trigger = await generator.generate_autonomous_trigger()
            # Sans Weaviate, tous les generateurs font fallback
            assert trigger.type in (TriggerType.CORPUS, TriggerType.RUMINATION_FREE, TriggerType.EMPTY)

        asyncio.run(run_test())


class TestTriggerGeneratorAmendment5:
    """Tests pour Amendment #5 : Rumination sur impacts non resolus."""

    def test_probabilities_prioritize_impacts(self):
        """Les probabilites priorisent les impacts (50%)."""
        config = DaemonConfig()

        assert config.prob_unresolved_impact > config.prob_corpus
        assert config.prob_unresolved_impact > config.prob_rumination_free
        assert config.prob_unresolved_impact == 0.50

    def test_old_impact_has_high_priority(self):
        """Impact ancien (>7j) a priorite haute."""
        config = DaemonConfig()
        generator = TriggerGenerator(config)

        # Simuler un impact ancien via metadata
        trigger = Trigger(
            type=TriggerType.RUMINATION,
            content="Tension non resolue",
            metadata={
                'days_unresolved': 10,
                'is_old_tension': True,
            },
            priority=1,
        )

        assert trigger.priority == 1
        assert trigger.metadata['is_old_tension'] is True


class TestIkarioDaemon:
    """Tests pour IkarioDaemon."""

    def create_mock_daemon(self) -> IkarioDaemon:
        """Cree un daemon avec mocks."""
        # Mock LatentEngine
        mock_engine = MagicMock(spec=LatentEngine)
        mock_engine.run_cycle = AsyncMock(return_value=create_mock_cycle_result())
        mock_engine._get_current_state = MagicMock(return_value=create_random_tensor())

        # Mock VigilanceSystem
        mock_vigilance = MagicMock(spec=VigilanceSystem)
        mock_vigilance.check_drift = MagicMock(return_value=VigilanceAlert(level="ok"))

        # Mock StateToLanguage
        mock_translator = MagicMock(spec=StateToLanguage)
        mock_translator.translate = AsyncMock(return_value=TranslationResult(
            text="Je suis curieux.",
            projections={},
            output_type="response",
        ))

        return IkarioDaemon(
            latent_engine=mock_engine,
            vigilance=mock_vigilance,
            translator=mock_translator,
            config=DaemonConfig(cycle_interval_seconds=0.1),  # Rapide pour tests
        )

    def test_create_daemon(self):
        """Creer un daemon."""
        daemon = self.create_mock_daemon()

        assert daemon.running is False
        assert daemon.mode == DaemonMode.PAUSED
        assert daemon.stats.total_cycles == 0

    def test_initial_stats(self):
        """Stats initiales."""
        daemon = self.create_mock_daemon()
        stats = daemon.get_stats()

        assert stats['total_cycles'] == 0
        assert stats['conversation_cycles'] == 0
        assert stats['autonomous_cycles'] == 0

    def test_is_running_property(self):
        """Propriete is_running."""
        daemon = self.create_mock_daemon()

        assert daemon.is_running is False

    def test_current_mode_property(self):
        """Propriete current_mode."""
        daemon = self.create_mock_daemon()

        assert daemon.current_mode == DaemonMode.PAUSED


class TestDaemonStartStop:
    """Tests pour start/stop du daemon."""

    def create_mock_daemon(self) -> IkarioDaemon:
        """Cree un daemon avec mocks."""
        mock_engine = MagicMock(spec=LatentEngine)
        mock_engine.run_cycle = AsyncMock(return_value=create_mock_cycle_result())
        mock_engine._get_current_state = MagicMock(return_value=create_random_tensor())

        mock_vigilance = MagicMock(spec=VigilanceSystem)
        mock_vigilance.check_drift = MagicMock(return_value=VigilanceAlert(level="ok"))

        mock_translator = MagicMock(spec=StateToLanguage)
        mock_translator.translate = AsyncMock(return_value=TranslationResult(
            text="Test",
            projections={},
            output_type="response",
        ))

        return IkarioDaemon(
            latent_engine=mock_engine,
            vigilance=mock_vigilance,
            translator=mock_translator,
            config=DaemonConfig(
                cycle_interval_seconds=0.05,
                vigilance_interval_seconds=0.1,
            ),
        )

    def test_start_stop(self):
        """Demarrer et arreter le daemon."""
        daemon = self.create_mock_daemon()

        async def run_test():
            await daemon.start()
            assert daemon.running is True
            assert daemon.mode == DaemonMode.AUTONOMOUS

            await asyncio.sleep(0.1)

            await daemon.stop()
            assert daemon.running is False
            assert daemon.mode == DaemonMode.PAUSED

        asyncio.run(run_test())

    def test_run_with_duration(self):
        """Executer le daemon avec duree limitee."""
        daemon = self.create_mock_daemon()

        async def run_test():
            await daemon.run(duration_seconds=0.2)
            assert daemon.running is False

        asyncio.run(run_test())


class TestConversationMode:
    """Tests pour le mode conversation."""

    def create_mock_daemon(self) -> IkarioDaemon:
        """Cree un daemon avec mocks."""
        mock_engine = MagicMock(spec=LatentEngine)
        mock_engine.run_cycle = AsyncMock(return_value=create_mock_cycle_result(
            should_verbalize=True,
            verbalization_reason="conversation_mode",
        ))
        mock_engine._get_current_state = MagicMock(return_value=create_random_tensor())

        mock_vigilance = MagicMock(spec=VigilanceSystem)
        mock_vigilance.check_drift = MagicMock(return_value=VigilanceAlert(level="ok"))

        mock_translator = MagicMock(spec=StateToLanguage)
        mock_translator.translate = AsyncMock(return_value=TranslationResult(
            text="Je suis curieux de cette question.",
            projections={'epistemic': {'curiosity': 0.7}},
            output_type="response",
        ))

        return IkarioDaemon(
            latent_engine=mock_engine,
            vigilance=mock_vigilance,
            translator=mock_translator,
        )

    def test_conversation_always_verbalizes(self):
        """Mode conversation verbalise toujours."""
        daemon = self.create_mock_daemon()

        async def run_test():
            event = await daemon.send_message("Qu'est-ce que Whitehead?")

            assert event.text == "Je suis curieux de cette question."
            assert event.reason == "conversation_mode"
            assert daemon.stats.conversation_cycles == 1
            assert daemon.stats.verbalizations == 1

        asyncio.run(run_test())

    def test_translator_called_with_context(self):
        """Le traducteur recoit le contexte."""
        daemon = self.create_mock_daemon()

        async def run_test():
            await daemon.send_message("Test message")

            # Verifier que translate a ete appele
            daemon.translator.translate.assert_called()

            # Verifier les arguments
            call_kwargs = daemon.translator.translate.call_args.kwargs
            assert call_kwargs['output_type'] == 'response'
            assert 'Test message' in call_kwargs['context']

        asyncio.run(run_test())


class TestAutonomousMode:
    """Tests pour le mode autonome."""

    def create_mock_daemon(self, should_verbalize: bool = False) -> IkarioDaemon:
        """Cree un daemon avec mocks."""
        mock_engine = MagicMock(spec=LatentEngine)
        mock_engine.run_cycle = AsyncMock(return_value=create_mock_cycle_result(
            should_verbalize=should_verbalize,
            verbalization_reason="high_dissonance_discovery" if should_verbalize else "silent_processing",
            dissonance_total=0.7 if should_verbalize else 0.2,
        ))
        mock_engine._get_current_state = MagicMock(return_value=create_random_tensor())

        mock_vigilance = MagicMock(spec=VigilanceSystem)
        mock_vigilance.check_drift = MagicMock(return_value=VigilanceAlert(level="ok"))

        mock_translator = MagicMock(spec=StateToLanguage)
        mock_translator.translate = AsyncMock(return_value=TranslationResult(
            text="Decouverte interessante.",
            projections={},
            output_type="autonomous_verbalization",
        ))

        return IkarioDaemon(
            latent_engine=mock_engine,
            vigilance=mock_vigilance,
            translator=mock_translator,
            config=DaemonConfig(
                cycle_interval_seconds=0.05,  # Tres rapide pour tests
                vigilance_interval_seconds=1.0,
            ),
        )

    def test_autonomous_silent_processing(self):
        """Mode autonome traite silencieusement par defaut."""
        daemon = self.create_mock_daemon(should_verbalize=False)

        async def run_test():
            await daemon.start()
            await asyncio.sleep(0.2)  # Quelques cycles
            await daemon.stop()

            # Doit avoir fait des cycles autonomes
            assert daemon.stats.autonomous_cycles > 0
            # Mais pas de verbalisation
            assert daemon.stats.verbalizations == 0
            assert daemon.stats.silent_cycles > 0

        asyncio.run(run_test())

    def test_autonomous_verbalizes_on_discovery(self):
        """Mode autonome verbalise sur decouverte importante."""
        daemon = self.create_mock_daemon(should_verbalize=True)

        async def run_test():
            await daemon.start()
            await asyncio.sleep(0.2)  # Quelques cycles
            await daemon.stop()

            # Doit avoir verbalise
            assert daemon.stats.verbalizations > 0

        asyncio.run(run_test())


class TestVigilanceLoop:
    """Tests pour la boucle de vigilance."""

    def create_mock_daemon(self, alert_level: str = "ok") -> IkarioDaemon:
        """Cree un daemon avec mocks."""
        mock_engine = MagicMock(spec=LatentEngine)
        mock_engine.run_cycle = AsyncMock(return_value=create_mock_cycle_result())
        mock_engine._get_current_state = MagicMock(return_value=create_random_tensor())

        mock_vigilance = MagicMock(spec=VigilanceSystem)
        mock_vigilance.check_drift = MagicMock(return_value=VigilanceAlert(
            level=alert_level,
            message=f"Test alert {alert_level}",
        ))

        mock_translator = MagicMock(spec=StateToLanguage)
        mock_translator.translate = AsyncMock(return_value=TranslationResult(
            text="Test",
            projections={},
            output_type="response",
        ))

        return IkarioDaemon(
            latent_engine=mock_engine,
            vigilance=mock_vigilance,
            translator=mock_translator,
            config=DaemonConfig(
                cycle_interval_seconds=1.0,
                vigilance_interval_seconds=0.05,  # Rapide pour tests
            ),
        )

    def test_vigilance_checks_drift(self):
        """La boucle vigilance verifie la derive."""
        daemon = self.create_mock_daemon()

        async def run_test():
            await daemon.start()
            await asyncio.sleep(0.2)
            await daemon.stop()

            # check_drift doit avoir ete appele
            daemon.vigilance.check_drift.assert_called()

        asyncio.run(run_test())

    def test_vigilance_counts_alerts(self):
        """Les alertes sont comptees."""
        daemon = self.create_mock_daemon(alert_level="warning")

        async def run_test():
            await daemon.start()
            await asyncio.sleep(0.2)
            await daemon.stop()

            assert daemon.stats.vigilance_alerts > 0

        asyncio.run(run_test())


class TestNotificationCallback:
    """Tests pour le callback de notification."""

    def test_callback_called_on_autonomous_verbalization(self):
        """Le callback est appele sur verbalisation autonome."""
        # Mock callback
        callback = AsyncMock()

        mock_engine = MagicMock(spec=LatentEngine)
        mock_engine.run_cycle = AsyncMock(return_value=create_mock_cycle_result(
            should_verbalize=True,
            verbalization_reason="high_dissonance",
        ))
        mock_engine._get_current_state = MagicMock(return_value=create_random_tensor())

        mock_vigilance = MagicMock(spec=VigilanceSystem)
        mock_vigilance.check_drift = MagicMock(return_value=VigilanceAlert(level="ok"))

        mock_translator = MagicMock(spec=StateToLanguage)
        mock_translator.translate = AsyncMock(return_value=TranslationResult(
            text="Notification test",
            projections={},
            output_type="autonomous",
        ))

        daemon = IkarioDaemon(
            latent_engine=mock_engine,
            vigilance=mock_vigilance,
            translator=mock_translator,
            config=DaemonConfig(
                cycle_interval_seconds=0.05,
                vigilance_interval_seconds=1.0,
            ),
            notification_callback=callback,
        )

        async def run_test():
            await daemon.start()
            await asyncio.sleep(0.2)
            await daemon.stop()

            # Le callback doit avoir ete appele
            callback.assert_called()

        asyncio.run(run_test())


class TestVerbalizationHistory:
    """Tests pour l'historique des verbalisations."""

    def create_mock_daemon(self) -> IkarioDaemon:
        """Cree un daemon avec mocks."""
        mock_engine = MagicMock(spec=LatentEngine)
        mock_engine.run_cycle = AsyncMock(return_value=create_mock_cycle_result())
        mock_engine._get_current_state = MagicMock(return_value=create_random_tensor())

        mock_vigilance = MagicMock(spec=VigilanceSystem)
        mock_vigilance.check_drift = MagicMock(return_value=VigilanceAlert(level="ok"))

        mock_translator = MagicMock(spec=StateToLanguage)
        mock_translator.translate = AsyncMock(return_value=TranslationResult(
            text="Test response",
            projections={},
            output_type="response",
        ))

        return IkarioDaemon(
            latent_engine=mock_engine,
            vigilance=mock_vigilance,
            translator=mock_translator,
        )

    def test_history_records_conversations(self):
        """L'historique enregistre les conversations."""
        daemon = self.create_mock_daemon()

        async def run_test():
            await daemon.send_message("Message 1")
            await daemon.send_message("Message 2")

            history = daemon.get_verbalization_history()

            assert len(history) == 2
            assert all('text' in h for h in history)

        asyncio.run(run_test())

    def test_history_limit(self):
        """L'historique respecte la limite."""
        daemon = self.create_mock_daemon()

        async def run_test():
            for i in range(15):
                await daemon.send_message(f"Message {i}")

            history = daemon.get_verbalization_history(limit=5)

            assert len(history) == 5

        asyncio.run(run_test())


class TestCreateDaemonFactory:
    """Tests pour la factory create_daemon."""

    def test_create_daemon_factory(self):
        """create_daemon cree un daemon."""
        mock_engine = MagicMock(spec=LatentEngine)
        mock_vigilance = MagicMock(spec=VigilanceSystem)
        mock_translator = MagicMock(spec=StateToLanguage)

        daemon = create_daemon(
            latent_engine=mock_engine,
            vigilance=mock_vigilance,
            translator=mock_translator,
        )

        assert isinstance(daemon, IkarioDaemon)
        assert daemon.engine is mock_engine
        assert daemon.vigilance is mock_vigilance
        assert daemon.translator is mock_translator

    def test_create_daemon_with_config(self):
        """create_daemon accepte une config."""
        mock_engine = MagicMock(spec=LatentEngine)
        mock_vigilance = MagicMock(spec=VigilanceSystem)
        mock_translator = MagicMock(spec=StateToLanguage)

        config = DaemonConfig(cycle_interval_seconds=60.0)

        daemon = create_daemon(
            latent_engine=mock_engine,
            vigilance=mock_vigilance,
            translator=mock_translator,
            config=config,
        )

        assert daemon.config.cycle_interval_seconds == 60.0


class TestCycleRate:
    """Tests pour le taux de cycles (~1000/jour)."""

    def test_default_cycle_rate(self):
        """Le taux par defaut est ~1000 cycles/jour."""
        config = DaemonConfig()

        # 86400 secondes/jour / 90 secondes/cycle = 960 cycles/jour
        cycles_per_day = 86400 / config.cycle_interval_seconds

        assert 900 < cycles_per_day < 1100  # ~1000 cycles/jour


class TestStatsTracking:
    """Tests pour le suivi des statistiques."""

    def create_mock_daemon(self) -> IkarioDaemon:
        """Cree un daemon avec mocks."""
        mock_engine = MagicMock(spec=LatentEngine)
        mock_engine.run_cycle = AsyncMock(return_value=create_mock_cycle_result())
        mock_engine._get_current_state = MagicMock(return_value=create_random_tensor())

        mock_vigilance = MagicMock(spec=VigilanceSystem)
        mock_vigilance.check_drift = MagicMock(return_value=VigilanceAlert(level="ok"))

        mock_translator = MagicMock(spec=StateToLanguage)
        mock_translator.translate = AsyncMock(return_value=TranslationResult(
            text="Test",
            projections={},
            output_type="response",
        ))

        return IkarioDaemon(
            latent_engine=mock_engine,
            vigilance=mock_vigilance,
            translator=mock_translator,
            config=DaemonConfig(
                cycle_interval_seconds=0.05,
                vigilance_interval_seconds=1.0,
            ),
        )

    def test_total_cycles_tracked(self):
        """Les cycles totaux sont suivis."""
        daemon = self.create_mock_daemon()

        async def run_test():
            # Envoyer quelques messages
            await daemon.send_message("Test 1")
            await daemon.send_message("Test 2")

            stats = daemon.get_stats()

            # Au moins 2 cycles (les conversations)
            assert stats['total_cycles'] >= 2

        asyncio.run(run_test())

    def test_last_cycle_time_updated(self):
        """last_cycle_time est mis a jour."""
        daemon = self.create_mock_daemon()

        async def run_test():
            await daemon.send_message("Test")

            stats = daemon.get_stats()

            assert stats['last_cycle_time'] != ""

        asyncio.run(run_test())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
