#!/usr/bin/env python3
"""
Tests d'intégration Phase 8 - Architecture v2.

Tests simplifiés pour valider l'intégration entre les modules.
Ces tests utilisent l'API réelle des modules implémentés.

Exécuter: pytest ikario_processual/tests/test_integration_v2.py -v
"""

import asyncio
import numpy as np
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ikario_processual.state_tensor import StateTensor, DIMENSION_NAMES, EMBEDDING_DIM
from ikario_processual.dissonance import DissonanceResult, Impact, compute_dissonance
from ikario_processual.fixation import FixationResult, compute_delta, apply_delta
from ikario_processual.vigilance import (
    VigilanceSystem,
    VigilanceConfig,
    VigilanceAlert,
    create_vigilance_system,
)
from ikario_processual.state_to_language import (
    StateToLanguage,
    TranslationResult,
    ProjectionDirection,
    REASONING_MARKERS,
)
from ikario_processual.daemon import (
    IkarioDaemon,
    DaemonConfig,
    DaemonMode,
    TriggerType,
    Trigger,
    TriggerGenerator,
    create_daemon,
)
from ikario_processual.metrics import (
    ProcessMetrics,
    create_metrics,
)


def create_random_tensor(state_id: int = 0, seed: int = None) -> StateTensor:
    """Crée un tenseur avec des vecteurs aléatoires normalisés."""
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


def create_mock_embedding_model():
    """Crée un mock du modèle d'embedding."""
    mock = MagicMock()

    def mock_encode(texts):
        np.random.seed(hash(str(texts)) % (2**32))
        embeddings = np.random.randn(len(texts), EMBEDDING_DIM)
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        return embeddings / norms

    mock.encode = mock_encode
    return mock


class TestVigilanceIntegration:
    """Tests d'intégration du système de vigilance."""

    def test_vigilance_with_state_tensor(self):
        """Test: vigilance fonctionne avec StateTensor."""
        x_ref = create_random_tensor(state_id=-1, seed=42)
        vigilance = VigilanceSystem(x_ref=x_ref)

        # État identique = pas de drift
        alert = vigilance.check_drift(x_ref)
        assert alert.level == "ok"

    def test_vigilance_detects_drift(self):
        """Test: vigilance détecte la dérive."""
        x_ref = create_random_tensor(state_id=-1, seed=42)
        config = VigilanceConfig(
            threshold_cumulative=0.0001,
            threshold_per_cycle=0.00001,
        )
        vigilance = VigilanceSystem(x_ref=x_ref, config=config)

        # Premier check
        vigilance.check_drift(x_ref)

        # État différent = dérive
        X_different = create_random_tensor(state_id=1, seed=999)
        alert = vigilance.check_drift(X_different)

        assert alert.level in ("warning", "critical")

    def test_vigilance_identifies_dimensions(self):
        """Test: vigilance identifie les dimensions en dérive."""
        x_ref = create_random_tensor(state_id=-1, seed=42)
        vigilance = VigilanceSystem(x_ref=x_ref)

        # Inverser une dimension
        X_modified = x_ref.copy()
        X_modified.state_id = 1
        X_modified.valeurs = -x_ref.valeurs

        alert = vigilance.check_drift(X_modified)
        assert 'valeurs' in alert.top_drifting_dimensions

    def test_vigilance_cumulative_drift(self):
        """Test: dérive cumulative augmente."""
        x_ref = create_random_tensor(state_id=-1, seed=42)
        vigilance = VigilanceSystem(x_ref=x_ref)

        # Plusieurs checks
        for i in range(5):
            X = create_random_tensor(state_id=i, seed=i + 100)
            vigilance.check_drift(X)

        assert vigilance.cumulative_drift > 0
        assert len(vigilance.history) == 5


class TestStateToLanguageIntegration:
    """Tests d'intégration de StateToLanguage."""

    def test_projection_on_directions(self):
        """Test: projection sur les directions."""
        X = create_random_tensor(state_id=5, seed=42)

        # Créer direction avec la bonne signature
        direction_vec = np.random.randn(EMBEDDING_DIM)
        direction_vec = direction_vec / np.linalg.norm(direction_vec)

        direction = ProjectionDirection(
            name="test_dir",
            category="epistemic",
            pole_positive="positif",
            pole_negative="négatif",
            description="Direction de test",
            vector=direction_vec,
        )

        translator = StateToLanguage(directions=[direction])
        projections = translator.project_state(X)

        # Projection existe pour la catégorie epistemic
        assert 'epistemic' in projections
        assert 'test_dir' in projections['epistemic']

    def test_translator_async_translate(self):
        """Test: traduction async avec mock client."""

        def run_test():
            async def async_test():
                X = create_random_tensor(state_id=5, seed=42)

                mock_client = AsyncMock()
                mock_client.messages.create = AsyncMock(return_value=MagicMock(
                    content=[MagicMock(text="État de curiosité intense.")]
                ))

                translator = StateToLanguage(
                    directions=[],
                    anthropic_client=mock_client,
                )

                result = await translator.translate(X)

                assert result is not None
                assert isinstance(result, TranslationResult)
                assert len(result.text) > 0

            asyncio.run(async_test())

        run_test()

    def test_reasoning_markers_defined(self):
        """Test: marqueurs de raisonnement définis."""
        assert len(REASONING_MARKERS) > 0
        assert any("pense" in m.lower() for m in REASONING_MARKERS)


class TestDissonanceFixationIntegration:
    """Tests d'intégration dissonance + fixation."""

    def test_dissonance_on_tensor(self):
        """Test: compute_dissonance fonctionne."""
        X = create_random_tensor(state_id=0, seed=42)
        mock_model = create_mock_embedding_model()

        e_input = mock_model.encode(["Test input"])[0]

        result = compute_dissonance(
            e_input=e_input,
            X_t=X,
        )

        assert isinstance(result, DissonanceResult)
        assert len(result.dissonances_by_dimension) == 8

    def test_fixation_applies_delta(self):
        """Test: fixation applique le delta."""
        X = create_random_tensor(state_id=0, seed=42)
        X_before = X.to_flat().copy()

        # Créer un delta
        delta = np.random.randn(EMBEDDING_DIM) * 0.01

        # Appliquer sur une dimension
        X_new = apply_delta(
            X_t=X,
            delta=delta,
            target_dim="firstness",
        )

        X_after = X_new.to_flat()

        # L'état a changé
        assert not np.allclose(X_before, X_after)


class TestDaemonComponents:
    """Tests des composants du daemon."""

    def test_trigger_creation(self):
        """Test: création de triggers."""
        trigger = Trigger(
            type=TriggerType.USER,
            content="Test message",
            metadata={"source": "test"},
        )

        assert trigger.type == TriggerType.USER
        assert trigger.content == "Test message"
        assert trigger.metadata["source"] == "test"

    def test_daemon_config_validation(self):
        """Test: validation de config."""
        config = DaemonConfig()

        total = (
            config.prob_unresolved_impact +
            config.prob_corpus +
            config.prob_rumination_free
        )
        assert np.isclose(total, 1.0)
        assert config.validate() == True

    def test_daemon_mode_enum(self):
        """Test: modes du daemon."""
        assert DaemonMode.CONVERSATION.value == "conversation"
        assert DaemonMode.AUTONOMOUS.value == "autonomous"

    def test_trigger_types(self):
        """Test: types de triggers."""
        assert TriggerType.USER.value == "user"
        assert TriggerType.VEILLE.value == "veille"
        assert TriggerType.CORPUS.value == "corpus"
        assert TriggerType.RUMINATION_FREE.value == "rumination_free"


class TestMetricsIntegration:
    """Tests d'intégration des métriques."""

    def test_metrics_with_state_references(self):
        """Test: métriques avec références d'état."""
        S_0 = create_random_tensor(state_id=0, seed=42)
        x_ref = create_random_tensor(state_id=-1, seed=43)

        metrics = create_metrics(S_0=S_0, x_ref=x_ref)

        # Enregistrer des cycles
        for _ in range(10):
            metrics.record_cycle(TriggerType.USER, 0.01)

        report = metrics.compute_daily_report()
        assert report.cycles.total == 10

    def test_metrics_state_evolution(self):
        """Test: métriques d'évolution de l'état."""
        S_0 = create_random_tensor(state_id=0, seed=42)
        x_ref = create_random_tensor(state_id=-1, seed=43)
        X_current = create_random_tensor(state_id=100, seed=44)

        metrics = create_metrics(S_0=S_0, x_ref=x_ref)
        report = metrics.compute_daily_report(current_state=X_current)

        # Drift calculé
        assert report.state_evolution.total_drift_from_s0 > 0
        assert report.state_evolution.drift_from_ref > 0

    def test_metrics_health_status(self):
        """Test: statut de santé."""
        metrics = create_metrics()

        # Sans alertes = healthy
        status = metrics.get_health_status()
        assert status['status'] == 'healthy'

        # Avec alerte critical
        metrics.record_alert("critical", 0.03)
        status = metrics.get_health_status()
        assert status['status'] == 'critical'


class TestAmendmentsCompliance:
    """Tests de conformité aux amendements."""

    def test_amendment_4_reasoning_markers(self):
        """Amendment #4: Marqueurs de raisonnement définis."""
        assert len(REASONING_MARKERS) > 0

    def test_amendment_5_rumination_probability(self):
        """Amendment #5: Probabilité 50% impacts non résolus."""
        config = DaemonConfig()
        assert config.prob_unresolved_impact == 0.5

    def test_amendment_6_memory_efficient(self):
        """Amendment #6: Tenseur efficace en mémoire."""
        tensor = create_random_tensor(state_id=0, seed=42)
        flat = tensor.to_flat()

        # 8 × 1024 = 8192 floats
        assert flat.shape == (8 * EMBEDDING_DIM,)

        # < 64 KB
        assert flat.nbytes <= 64 * 1024

    def test_amendment_15_xref_not_attractor(self):
        """Amendment #15: x_ref est garde-fou, pas attracteur."""
        x_ref = create_random_tensor(state_id=-1, seed=42)
        vigilance = VigilanceSystem(x_ref=x_ref)

        # x_ref a state_id = -1
        assert vigilance.x_ref.state_id == -1

        # Vigilance n'attire pas vers x_ref, elle observe
        X = create_random_tensor(state_id=5, seed=123)
        X_before = X.to_flat().copy()

        vigilance.check_drift(X)

        # L'état n'a pas été modifié
        assert np.allclose(X_before, X.to_flat())


class TestEndToEndSimplified:
    """Tests end-to-end simplifiés."""

    def test_vigilance_with_metrics(self):
        """Test: vigilance intégrée avec métriques."""
        x_ref = create_random_tensor(state_id=-1, seed=42)
        vigilance = VigilanceSystem(x_ref=x_ref)
        metrics = create_metrics(x_ref=x_ref)

        # Simuler évolution
        for i in range(5):
            X = create_random_tensor(state_id=i, seed=i + 100)
            alert = vigilance.check_drift(X)
            metrics.record_alert(alert.level, vigilance.cumulative_drift)

        # Métriques enregistrées
        report = metrics.compute_daily_report()
        assert report.alerts.total == 5

    def test_state_evolution_tracked(self):
        """Test: évolution d'état suivie."""
        S_0 = create_random_tensor(state_id=0, seed=42)
        x_ref = create_random_tensor(state_id=-1, seed=43)

        vigilance = VigilanceSystem(x_ref=x_ref)
        metrics = create_metrics(S_0=S_0, x_ref=x_ref)

        # Simuler 10 cycles
        current_state = S_0
        for i in range(10):
            # Enregistrer cycle
            metrics.record_cycle(TriggerType.USER, 0.01)

            # Créer nouvel état (simulation)
            current_state = create_random_tensor(state_id=i + 1, seed=i + 50)

            # Vérifier vigilance
            alert = vigilance.check_drift(current_state)
            metrics.record_alert(alert.level, vigilance.cumulative_drift)

        # Rapport final
        report = metrics.compute_daily_report(current_state=current_state)

        assert report.cycles.total == 10
        assert report.state_evolution.total_drift_from_s0 > 0
        assert report.state_evolution.drift_from_ref > 0

    def test_full_module_imports(self):
        """Test: tous les modules s'importent correctement."""
        from ikario_processual import (
            # V1
            OccasionLog,
            OccasionLogger,
            OccasionManager,
            # V2
            StateTensor,
            DissonanceResult,
            FixationResult,
            VigilanceSystem,
            StateToLanguage,
            IkarioDaemon,
            ProcessMetrics,
        )

        # Tous les imports fonctionnent
        assert StateTensor is not None
        assert DissonanceResult is not None
        assert VigilanceSystem is not None
        assert StateToLanguage is not None
        assert IkarioDaemon is not None
        assert ProcessMetrics is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
