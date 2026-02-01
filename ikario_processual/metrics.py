#!/usr/bin/env python3
"""
Métriques Phase 8 - Suivi de l'évolution d'Ikario.

Ce module fournit des outils de monitoring pour:
- Comptage des cycles (conversation, autonome)
- Suivi des verbalisations
- Évolution de l'état (drift)
- Statistiques sur les impacts et thoughts
- Alertes de vigilance

Architecture v2 : "L'espace latent pense. Le LLM traduit."
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
import numpy as np

from .state_tensor import StateTensor, DIMENSION_NAMES, EMBEDDING_DIM
from .daemon import DaemonStats, TriggerType


class MetricPeriod(Enum):
    """Périodes de métriques."""
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


@dataclass
class StateEvolutionMetrics:
    """Métriques d'évolution de l'état."""
    total_drift_from_s0: float = 0.0
    drift_from_ref: float = 0.0
    dimensions_most_changed: List[Tuple[str, float]] = field(default_factory=list)
    average_delta_magnitude: float = 0.0
    max_delta_magnitude: float = 0.0


@dataclass
class CycleMetrics:
    """Métriques des cycles."""
    total: int = 0
    conversation: int = 0
    autonomous: int = 0
    by_trigger_type: Dict[str, int] = field(default_factory=dict)


@dataclass
class VerbalizationMetrics:
    """Métriques des verbalisations."""
    total: int = 0
    from_conversation: int = 0
    from_autonomous: int = 0
    average_length: float = 0.0
    reasoning_detected_count: int = 0


@dataclass
class ImpactMetrics:
    """Métriques des impacts."""
    created: int = 0
    resolved: int = 0
    pending: int = 0
    average_resolution_time_hours: float = 0.0
    oldest_unresolved_days: float = 0.0


@dataclass
class AlertMetrics:
    """Métriques des alertes de vigilance."""
    total: int = 0
    ok: int = 0
    warning: int = 0
    critical: int = 0
    last_alert_time: Optional[str] = None


@dataclass
class DailyReport:
    """Rapport quotidien complet."""
    date: str
    cycles: CycleMetrics
    verbalizations: VerbalizationMetrics
    state_evolution: StateEvolutionMetrics
    impacts: ImpactMetrics
    alerts: AlertMetrics
    thoughts_created: int = 0
    uptime_hours: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire."""
        return {
            'date': self.date,
            'cycles': {
                'total': self.cycles.total,
                'conversation': self.cycles.conversation,
                'autonomous': self.cycles.autonomous,
                'by_trigger_type': self.cycles.by_trigger_type,
            },
            'verbalizations': {
                'total': self.verbalizations.total,
                'from_conversation': self.verbalizations.from_conversation,
                'from_autonomous': self.verbalizations.from_autonomous,
                'average_length': self.verbalizations.average_length,
                'reasoning_detected_count': self.verbalizations.reasoning_detected_count,
            },
            'state_evolution': {
                'total_drift_from_s0': self.state_evolution.total_drift_from_s0,
                'drift_from_ref': self.state_evolution.drift_from_ref,
                'dimensions_most_changed': self.state_evolution.dimensions_most_changed,
                'average_delta_magnitude': self.state_evolution.average_delta_magnitude,
                'max_delta_magnitude': self.state_evolution.max_delta_magnitude,
            },
            'impacts': {
                'created': self.impacts.created,
                'resolved': self.impacts.resolved,
                'pending': self.impacts.pending,
                'average_resolution_time_hours': self.impacts.average_resolution_time_hours,
                'oldest_unresolved_days': self.impacts.oldest_unresolved_days,
            },
            'alerts': {
                'total': self.alerts.total,
                'ok': self.alerts.ok,
                'warning': self.alerts.warning,
                'critical': self.alerts.critical,
                'last_alert_time': self.alerts.last_alert_time,
            },
            'thoughts_created': self.thoughts_created,
            'uptime_hours': self.uptime_hours,
        }

    def format_summary(self) -> str:
        """Formate un résumé textuel."""
        lines = [
            f"=== RAPPORT IKARIO - {self.date} ===",
            "",
            "CYCLES:",
            f"  Total: {self.cycles.total}",
            f"  Conversation: {self.cycles.conversation}",
            f"  Autonome: {self.cycles.autonomous}",
            "",
            "VERBALISATIONS:",
            f"  Total: {self.verbalizations.total}",
            f"  Longueur moyenne: {self.verbalizations.average_length:.0f} chars",
            f"  Raisonnement détecté: {self.verbalizations.reasoning_detected_count}",
            "",
            "ÉVOLUTION DE L'ÉTAT:",
            f"  Dérive totale depuis S0: {self.state_evolution.total_drift_from_s0:.4f}",
            f"  Dérive depuis x_ref: {self.state_evolution.drift_from_ref:.4f}",
            f"  Dimensions les plus changées:",
        ]

        for dim, change in self.state_evolution.dimensions_most_changed[:3]:
            lines.append(f"    - {dim}: {change:.4f}")

        lines.extend([
            "",
            "IMPACTS:",
            f"  Créés: {self.impacts.created}",
            f"  Résolus: {self.impacts.resolved}",
            f"  En attente: {self.impacts.pending}",
            "",
            "ALERTES:",
            f"  OK: {self.alerts.ok}",
            f"  Warning: {self.alerts.warning}",
            f"  Critical: {self.alerts.critical}",
            "",
            f"Thoughts créées: {self.thoughts_created}",
            f"Uptime: {self.uptime_hours:.1f}h",
            "",
            "=" * 40,
        ])

        return "\n".join(lines)


class ProcessMetrics:
    """
    Métriques pour suivre l'évolution d'Ikario.

    Collecte et agrège les métriques de:
    - Cycles sémiotiques
    - Verbalisations
    - Évolution de l'état
    - Impacts
    - Alertes de vigilance
    """

    def __init__(
        self,
        S_0: Optional[StateTensor] = None,
        x_ref: Optional[StateTensor] = None,
    ):
        """
        Initialise le collecteur de métriques.

        Args:
            S_0: État initial (pour mesurer drift total)
            x_ref: Référence David (pour mesurer drift depuis ref)
        """
        self.S_0 = S_0
        self.x_ref = x_ref
        self.start_time = datetime.now()

        # Historiques
        self._cycle_history: List[Dict] = []
        self._verbalization_history: List[Dict] = []
        self._delta_history: List[float] = []
        self._impact_history: List[Dict] = []
        self._alert_history: List[Dict] = []
        self._thought_history: List[Dict] = []

    def record_cycle(
        self,
        trigger_type: TriggerType,
        delta_magnitude: float,
        timestamp: Optional[datetime] = None,
    ):
        """Enregistre un cycle."""
        self._cycle_history.append({
            'timestamp': (timestamp or datetime.now()).isoformat(),
            'trigger_type': trigger_type.value,
            'delta_magnitude': delta_magnitude,
        })
        self._delta_history.append(delta_magnitude)

    def record_verbalization(
        self,
        text: str,
        from_autonomous: bool = False,
        reasoning_detected: bool = False,
        timestamp: Optional[datetime] = None,
    ):
        """Enregistre une verbalisation."""
        self._verbalization_history.append({
            'timestamp': (timestamp or datetime.now()).isoformat(),
            'length': len(text),
            'from_autonomous': from_autonomous,
            'reasoning_detected': reasoning_detected,
        })

    def record_impact(
        self,
        impact_id: str,
        created: bool = True,
        resolved: bool = False,
        timestamp: Optional[datetime] = None,
    ):
        """Enregistre un impact."""
        self._impact_history.append({
            'timestamp': (timestamp or datetime.now()).isoformat(),
            'impact_id': impact_id,
            'created': created,
            'resolved': resolved,
        })

    def record_alert(
        self,
        level: str,
        cumulative_drift: float,
        timestamp: Optional[datetime] = None,
    ):
        """Enregistre une alerte."""
        self._alert_history.append({
            'timestamp': (timestamp or datetime.now()).isoformat(),
            'level': level,
            'cumulative_drift': cumulative_drift,
        })

    def record_thought(
        self,
        thought_id: str,
        trigger_content: str,
        timestamp: Optional[datetime] = None,
    ):
        """Enregistre une thought."""
        self._thought_history.append({
            'timestamp': (timestamp or datetime.now()).isoformat(),
            'thought_id': thought_id,
            'trigger_content': trigger_content[:100],  # Tronquer
        })

    def _filter_by_date(
        self,
        history: List[Dict],
        target_date: datetime,
    ) -> List[Dict]:
        """Filtre l'historique pour une date donnée."""
        target_str = target_date.strftime("%Y-%m-%d")
        return [
            h for h in history
            if h['timestamp'].startswith(target_str)
        ]

    def _count_cycles_by_type(
        self,
        cycles: List[Dict],
        types: List[str],
    ) -> int:
        """Compte les cycles par type."""
        return sum(
            1 for c in cycles
            if c['trigger_type'] in types
        )

    def _compute_dimension_changes(
        self,
        current_state: StateTensor,
        reference: StateTensor,
    ) -> List[Tuple[str, float]]:
        """Calcule les changements par dimension."""
        changes = []
        for dim_name in DIMENSION_NAMES:
            vec_current = getattr(current_state, dim_name)
            vec_ref = getattr(reference, dim_name)

            # Distance cosine
            cos_sim = np.dot(vec_current, vec_ref)
            distance = 1 - cos_sim

            changes.append((dim_name, distance))

        # Trier par changement décroissant
        changes.sort(key=lambda x: x[1], reverse=True)
        return changes

    def compute_daily_report(
        self,
        current_state: Optional[StateTensor] = None,
        target_date: Optional[datetime] = None,
    ) -> DailyReport:
        """
        Calcule le rapport quotidien.

        Args:
            current_state: État actuel d'Ikario
            target_date: Date cible (défaut: aujourd'hui)

        Returns:
            DailyReport avec toutes les métriques
        """
        target_date = target_date or datetime.now()
        date_str = target_date.strftime("%Y-%m-%d")

        # Filtrer par date
        cycles_today = self._filter_by_date(self._cycle_history, target_date)
        verbs_today = self._filter_by_date(self._verbalization_history, target_date)
        impacts_today = self._filter_by_date(self._impact_history, target_date)
        alerts_today = self._filter_by_date(self._alert_history, target_date)
        thoughts_today = self._filter_by_date(self._thought_history, target_date)

        # Cycles
        cycle_metrics = CycleMetrics(
            total=len(cycles_today),
            conversation=self._count_cycles_by_type(cycles_today, ['user']),
            autonomous=self._count_cycles_by_type(
                cycles_today,
                ['veille', 'corpus', 'rumination_free']
            ),
            by_trigger_type={
                tt.value: self._count_cycles_by_type(cycles_today, [tt.value])
                for tt in TriggerType
            },
        )

        # Verbalisations
        verb_lengths = [v['length'] for v in verbs_today]
        verb_metrics = VerbalizationMetrics(
            total=len(verbs_today),
            from_conversation=sum(1 for v in verbs_today if not v['from_autonomous']),
            from_autonomous=sum(1 for v in verbs_today if v['from_autonomous']),
            average_length=np.mean(verb_lengths) if verb_lengths else 0.0,
            reasoning_detected_count=sum(1 for v in verbs_today if v['reasoning_detected']),
        )

        # Évolution de l'état
        state_metrics = StateEvolutionMetrics()
        if current_state is not None:
            if self.S_0 is not None:
                state_metrics.total_drift_from_s0 = np.linalg.norm(
                    current_state.to_flat() - self.S_0.to_flat()
                )
                state_metrics.dimensions_most_changed = self._compute_dimension_changes(
                    current_state, self.S_0
                )

            if self.x_ref is not None:
                state_metrics.drift_from_ref = np.linalg.norm(
                    current_state.to_flat() - self.x_ref.to_flat()
                )

        if self._delta_history:
            state_metrics.average_delta_magnitude = np.mean(self._delta_history)
            state_metrics.max_delta_magnitude = np.max(self._delta_history)

        # Impacts
        created_today = sum(1 for i in impacts_today if i['created'])
        resolved_today = sum(1 for i in impacts_today if i['resolved'])
        impact_metrics = ImpactMetrics(
            created=created_today,
            resolved=resolved_today,
            pending=created_today - resolved_today,
        )

        # Alertes
        alert_levels = [a['level'] for a in alerts_today]
        alert_metrics = AlertMetrics(
            total=len(alerts_today),
            ok=alert_levels.count('ok'),
            warning=alert_levels.count('warning'),
            critical=alert_levels.count('critical'),
            last_alert_time=alerts_today[-1]['timestamp'] if alerts_today else None,
        )

        # Uptime
        uptime = datetime.now() - self.start_time
        uptime_hours = uptime.total_seconds() / 3600

        return DailyReport(
            date=date_str,
            cycles=cycle_metrics,
            verbalizations=verb_metrics,
            state_evolution=state_metrics,
            impacts=impact_metrics,
            alerts=alert_metrics,
            thoughts_created=len(thoughts_today),
            uptime_hours=uptime_hours,
        )

    def compute_weekly_summary(
        self,
        current_state: Optional[StateTensor] = None,
    ) -> Dict[str, Any]:
        """Calcule un résumé hebdomadaire."""
        reports = []
        today = datetime.now()

        for i in range(7):
            target_date = today - timedelta(days=i)
            report = self.compute_daily_report(current_state, target_date)
            reports.append(report.to_dict())

        # Agrégations
        total_cycles = sum(r['cycles']['total'] for r in reports)
        total_verbs = sum(r['verbalizations']['total'] for r in reports)
        total_alerts = sum(r['alerts']['total'] for r in reports)

        return {
            'period': 'weekly',
            'start_date': (today - timedelta(days=6)).strftime("%Y-%m-%d"),
            'end_date': today.strftime("%Y-%m-%d"),
            'daily_reports': reports,
            'summary': {
                'total_cycles': total_cycles,
                'average_cycles_per_day': total_cycles / 7,
                'total_verbalizations': total_verbs,
                'total_alerts': total_alerts,
            },
        }

    def get_health_status(self) -> Dict[str, Any]:
        """
        Retourne l'état de santé du système.

        Returns:
            Dictionnaire avec indicateurs de santé
        """
        # Alertes récentes (dernière heure)
        one_hour_ago = datetime.now() - timedelta(hours=1)
        recent_alerts = [
            a for a in self._alert_history
            if datetime.fromisoformat(a['timestamp']) > one_hour_ago
        ]

        critical_count = sum(1 for a in recent_alerts if a['level'] == 'critical')
        warning_count = sum(1 for a in recent_alerts if a['level'] == 'warning')

        # Déterminer statut global
        if critical_count > 0:
            status = "critical"
        elif warning_count > 2:
            status = "warning"
        else:
            status = "healthy"

        # Cycles récents
        recent_cycles = [
            c for c in self._cycle_history
            if datetime.fromisoformat(c['timestamp']) > one_hour_ago
        ]

        return {
            'status': status,
            'uptime_hours': (datetime.now() - self.start_time).total_seconds() / 3600,
            'recent_alerts': {
                'critical': critical_count,
                'warning': warning_count,
            },
            'cycles_last_hour': len(recent_cycles),
            'total_cycles': len(self._cycle_history),
            'last_activity': (
                self._cycle_history[-1]['timestamp']
                if self._cycle_history else None
            ),
        }

    def reset(self):
        """Réinitialise tous les historiques."""
        self._cycle_history.clear()
        self._verbalization_history.clear()
        self._delta_history.clear()
        self._impact_history.clear()
        self._alert_history.clear()
        self._thought_history.clear()
        self.start_time = datetime.now()


def create_metrics(
    S_0: Optional[StateTensor] = None,
    x_ref: Optional[StateTensor] = None,
) -> ProcessMetrics:
    """
    Factory pour créer un collecteur de métriques.

    Args:
        S_0: État initial
        x_ref: Référence David

    Returns:
        Instance de ProcessMetrics
    """
    return ProcessMetrics(S_0=S_0, x_ref=x_ref)
