#!/usr/bin/env python3
"""
Tests pour le module de métriques - Phase 8.

Exécuter: pytest ikario_processual/tests/test_metrics.py -v
"""

import numpy as np
import pytest
from datetime import datetime, timedelta

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ikario_processual.state_tensor import StateTensor, DIMENSION_NAMES, EMBEDDING_DIM
from ikario_processual.daemon import TriggerType
from ikario_processual.metrics import (
    MetricPeriod,
    StateEvolutionMetrics,
    CycleMetrics,
    VerbalizationMetrics,
    ImpactMetrics,
    AlertMetrics,
    DailyReport,
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


class TestMetricPeriod:
    """Tests pour MetricPeriod."""

    def test_all_periods_exist(self):
        """Toutes les périodes existent."""
        assert MetricPeriod.HOURLY.value == "hourly"
        assert MetricPeriod.DAILY.value == "daily"
        assert MetricPeriod.WEEKLY.value == "weekly"
        assert MetricPeriod.MONTHLY.value == "monthly"


class TestStateEvolutionMetrics:
    """Tests pour StateEvolutionMetrics."""

    def test_default_values(self):
        """Valeurs par défaut."""
        metrics = StateEvolutionMetrics()

        assert metrics.total_drift_from_s0 == 0.0
        assert metrics.drift_from_ref == 0.0
        assert metrics.dimensions_most_changed == []
        assert metrics.average_delta_magnitude == 0.0


class TestCycleMetrics:
    """Tests pour CycleMetrics."""

    def test_default_values(self):
        """Valeurs par défaut."""
        metrics = CycleMetrics()

        assert metrics.total == 0
        assert metrics.conversation == 0
        assert metrics.autonomous == 0
        assert metrics.by_trigger_type == {}


class TestVerbalizationMetrics:
    """Tests pour VerbalizationMetrics."""

    def test_default_values(self):
        """Valeurs par défaut."""
        metrics = VerbalizationMetrics()

        assert metrics.total == 0
        assert metrics.from_conversation == 0
        assert metrics.from_autonomous == 0
        assert metrics.average_length == 0.0
        assert metrics.reasoning_detected_count == 0


class TestImpactMetrics:
    """Tests pour ImpactMetrics."""

    def test_default_values(self):
        """Valeurs par défaut."""
        metrics = ImpactMetrics()

        assert metrics.created == 0
        assert metrics.resolved == 0
        assert metrics.pending == 0


class TestAlertMetrics:
    """Tests pour AlertMetrics."""

    def test_default_values(self):
        """Valeurs par défaut."""
        metrics = AlertMetrics()

        assert metrics.total == 0
        assert metrics.ok == 0
        assert metrics.warning == 0
        assert metrics.critical == 0
        assert metrics.last_alert_time is None


class TestDailyReport:
    """Tests pour DailyReport."""

    def test_create_report(self):
        """Créer un rapport."""
        report = DailyReport(
            date="2024-01-15",
            cycles=CycleMetrics(total=100, conversation=30, autonomous=70),
            verbalizations=VerbalizationMetrics(total=35),
            state_evolution=StateEvolutionMetrics(total_drift_from_s0=0.05),
            impacts=ImpactMetrics(created=10, resolved=8),
            alerts=AlertMetrics(total=5, ok=3, warning=2),
            thoughts_created=50,
            uptime_hours=24.0,
        )

        assert report.date == "2024-01-15"
        assert report.cycles.total == 100
        assert report.verbalizations.total == 35
        assert report.thoughts_created == 50

    def test_to_dict(self):
        """Conversion en dictionnaire."""
        report = DailyReport(
            date="2024-01-15",
            cycles=CycleMetrics(total=100),
            verbalizations=VerbalizationMetrics(total=35),
            state_evolution=StateEvolutionMetrics(),
            impacts=ImpactMetrics(),
            alerts=AlertMetrics(),
        )

        d = report.to_dict()

        assert 'date' in d
        assert 'cycles' in d
        assert 'verbalizations' in d
        assert d['cycles']['total'] == 100
        assert d['verbalizations']['total'] == 35

    def test_format_summary(self):
        """Formatage du résumé textuel."""
        report = DailyReport(
            date="2024-01-15",
            cycles=CycleMetrics(total=100, conversation=30, autonomous=70),
            verbalizations=VerbalizationMetrics(total=35, average_length=150.0),
            state_evolution=StateEvolutionMetrics(
                total_drift_from_s0=0.05,
                dimensions_most_changed=[('valeurs', 0.02), ('firstness', 0.01)]
            ),
            impacts=ImpactMetrics(created=10, resolved=8),
            alerts=AlertMetrics(total=5, ok=3, warning=2),
            thoughts_created=50,
            uptime_hours=24.0,
        )

        summary = report.format_summary()

        assert "RAPPORT IKARIO" in summary
        assert "2024-01-15" in summary
        assert "Total: 100" in summary
        assert "Conversation: 30" in summary
        assert "Autonome: 70" in summary
        assert "valeurs" in summary


class TestProcessMetrics:
    """Tests pour ProcessMetrics."""

    def test_create_metrics(self):
        """Créer un collecteur de métriques."""
        metrics = ProcessMetrics()

        assert metrics.S_0 is None
        assert metrics.x_ref is None
        assert len(metrics._cycle_history) == 0

    def test_create_with_references(self):
        """Créer avec références S_0 et x_ref."""
        S_0 = create_random_tensor(state_id=0, seed=42)
        x_ref = create_random_tensor(state_id=-1, seed=43)

        metrics = ProcessMetrics(S_0=S_0, x_ref=x_ref)

        assert metrics.S_0 is S_0
        assert metrics.x_ref is x_ref

    def test_record_cycle(self):
        """Enregistrer un cycle."""
        metrics = ProcessMetrics()

        metrics.record_cycle(
            trigger_type=TriggerType.USER,
            delta_magnitude=0.01,
        )

        assert len(metrics._cycle_history) == 1
        assert metrics._cycle_history[0]['trigger_type'] == 'user'
        assert metrics._cycle_history[0]['delta_magnitude'] == 0.01

    def test_record_multiple_cycles(self):
        """Enregistrer plusieurs cycles."""
        metrics = ProcessMetrics()

        for i in range(10):
            metrics.record_cycle(
                trigger_type=TriggerType.USER,
                delta_magnitude=0.01 * i,
            )

        assert len(metrics._cycle_history) == 10
        assert len(metrics._delta_history) == 10

    def test_record_verbalization(self):
        """Enregistrer une verbalisation."""
        metrics = ProcessMetrics()

        text = "Ceci est une verbalisation de test."
        metrics.record_verbalization(
            text=text,
            from_autonomous=False,
            reasoning_detected=True,
        )

        assert len(metrics._verbalization_history) == 1
        assert metrics._verbalization_history[0]['length'] == len(text)
        assert metrics._verbalization_history[0]['reasoning_detected'] is True

    def test_record_impact(self):
        """Enregistrer un impact."""
        metrics = ProcessMetrics()

        metrics.record_impact(
            impact_id="impact_001",
            created=True,
            resolved=False,
        )

        assert len(metrics._impact_history) == 1
        assert metrics._impact_history[0]['impact_id'] == "impact_001"

    def test_record_alert(self):
        """Enregistrer une alerte."""
        metrics = ProcessMetrics()

        metrics.record_alert(
            level="warning",
            cumulative_drift=0.015,
        )

        assert len(metrics._alert_history) == 1
        assert metrics._alert_history[0]['level'] == "warning"

    def test_record_thought(self):
        """Enregistrer une thought."""
        metrics = ProcessMetrics()

        metrics.record_thought(
            thought_id="thought_001",
            trigger_content="Question philosophique",
        )

        assert len(metrics._thought_history) == 1
        assert metrics._thought_history[0]['thought_id'] == "thought_001"


class TestDailyReportComputation:
    """Tests pour le calcul du rapport quotidien."""

    def test_compute_empty_report(self):
        """Rapport vide si pas de données."""
        metrics = ProcessMetrics()
        report = metrics.compute_daily_report()

        assert report.cycles.total == 0
        assert report.verbalizations.total == 0
        assert report.alerts.total == 0

    def test_compute_with_cycles(self):
        """Rapport avec cycles."""
        metrics = ProcessMetrics()

        # Ajouter des cycles
        for _ in range(5):
            metrics.record_cycle(TriggerType.USER, 0.01)
        for _ in range(10):
            metrics.record_cycle(TriggerType.VEILLE, 0.005)

        report = metrics.compute_daily_report()

        assert report.cycles.total == 15
        assert report.cycles.conversation == 5
        assert report.cycles.autonomous == 10

    def test_compute_with_state_evolution(self):
        """Rapport avec évolution d'état."""
        S_0 = create_random_tensor(state_id=0, seed=42)
        x_ref = create_random_tensor(state_id=-1, seed=43)
        X_current = create_random_tensor(state_id=100, seed=44)

        metrics = ProcessMetrics(S_0=S_0, x_ref=x_ref)
        report = metrics.compute_daily_report(current_state=X_current)

        assert report.state_evolution.total_drift_from_s0 > 0
        assert report.state_evolution.drift_from_ref > 0
        assert len(report.state_evolution.dimensions_most_changed) == 8

    def test_compute_with_alerts(self):
        """Rapport avec alertes."""
        metrics = ProcessMetrics()

        metrics.record_alert("ok", 0.001)
        metrics.record_alert("ok", 0.002)
        metrics.record_alert("warning", 0.015)
        metrics.record_alert("critical", 0.025)

        report = metrics.compute_daily_report()

        assert report.alerts.total == 4
        assert report.alerts.ok == 2
        assert report.alerts.warning == 1
        assert report.alerts.critical == 1

    def test_compute_average_verbalization_length(self):
        """Calcul de la longueur moyenne des verbalisations."""
        metrics = ProcessMetrics()

        metrics.record_verbalization("Court", from_autonomous=False)
        metrics.record_verbalization("Un texte un peu plus long", from_autonomous=False)
        metrics.record_verbalization("Encore plus long pour le test", from_autonomous=True)

        report = metrics.compute_daily_report()

        assert report.verbalizations.total == 3
        assert report.verbalizations.from_conversation == 2
        assert report.verbalizations.from_autonomous == 1
        assert report.verbalizations.average_length > 0


class TestWeeklySummary:
    """Tests pour le résumé hebdomadaire."""

    def test_compute_weekly_summary(self):
        """Calcul du résumé hebdomadaire."""
        metrics = ProcessMetrics()

        # Ajouter des données
        for _ in range(50):
            metrics.record_cycle(TriggerType.USER, 0.01)

        summary = metrics.compute_weekly_summary()

        assert 'period' in summary
        assert summary['period'] == 'weekly'
        assert 'daily_reports' in summary
        assert len(summary['daily_reports']) == 7
        assert 'summary' in summary
        assert summary['summary']['total_cycles'] == 50


class TestHealthStatus:
    """Tests pour l'état de santé."""

    def test_healthy_status(self):
        """Statut sain."""
        metrics = ProcessMetrics()

        # Quelques cycles normaux
        for _ in range(10):
            metrics.record_cycle(TriggerType.USER, 0.01)

        status = metrics.get_health_status()

        assert status['status'] == 'healthy'
        assert status['total_cycles'] == 10

    def test_warning_status(self):
        """Statut warning."""
        metrics = ProcessMetrics()

        # Plusieurs warnings récents
        for _ in range(5):
            metrics.record_alert("warning", 0.015)

        status = metrics.get_health_status()

        assert status['status'] == 'warning'

    def test_critical_status(self):
        """Statut critical."""
        metrics = ProcessMetrics()

        metrics.record_alert("critical", 0.03)

        status = metrics.get_health_status()

        assert status['status'] == 'critical'

    def test_uptime_tracked(self):
        """Uptime est suivi."""
        metrics = ProcessMetrics()

        status = metrics.get_health_status()

        assert 'uptime_hours' in status
        assert status['uptime_hours'] >= 0


class TestReset:
    """Tests pour la réinitialisation."""

    def test_reset_clears_history(self):
        """Reset efface tous les historiques."""
        metrics = ProcessMetrics()

        # Ajouter des données
        metrics.record_cycle(TriggerType.USER, 0.01)
        metrics.record_verbalization("Test")
        metrics.record_alert("ok", 0.001)

        assert len(metrics._cycle_history) > 0
        assert len(metrics._verbalization_history) > 0

        # Reset
        metrics.reset()

        assert len(metrics._cycle_history) == 0
        assert len(metrics._verbalization_history) == 0
        assert len(metrics._alert_history) == 0


class TestCreateMetricsFactory:
    """Tests pour la factory create_metrics."""

    def test_create_without_args(self):
        """Créer sans arguments."""
        metrics = create_metrics()

        assert metrics is not None
        assert isinstance(metrics, ProcessMetrics)

    def test_create_with_references(self):
        """Créer avec références."""
        S_0 = create_random_tensor(state_id=0, seed=42)
        x_ref = create_random_tensor(state_id=-1, seed=43)

        metrics = create_metrics(S_0=S_0, x_ref=x_ref)

        assert metrics.S_0 is S_0
        assert metrics.x_ref is x_ref


class TestIntegrationWithDaemon:
    """Tests d'intégration avec le daemon."""

    def test_cycle_types_match_daemon(self):
        """Les types de cycles correspondent au daemon."""
        metrics = ProcessMetrics()

        # Tous les types de triggers
        for trigger_type in TriggerType:
            metrics.record_cycle(trigger_type, 0.01)

        assert len(metrics._cycle_history) == len(TriggerType)

        # Vérifier les types
        recorded_types = {c['trigger_type'] for c in metrics._cycle_history}
        expected_types = {t.value for t in TriggerType}
        assert recorded_types == expected_types


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
