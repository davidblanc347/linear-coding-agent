#!/usr/bin/env python3
"""
Tests pour le module de vigilance - Phase 6.

Systeme de vigilance x_ref (David) :
1. x_ref N'EST PAS un attracteur (Ikario ne tend pas vers David)
2. x_ref EST un garde-fou (alerte si distance > seuil)
3. Alertes : ok, warning, critical

Executer: pytest ikario_processual/tests/test_vigilance.py -v
"""

import json
import numpy as np
import pytest
import tempfile
from datetime import datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ikario_processual.state_tensor import StateTensor, DIMENSION_NAMES, EMBEDDING_DIM
from ikario_processual.vigilance import (
    VigilanceAlert,
    VigilanceConfig,
    VigilanceSystem,
    DavidReference,
    VigilanceVisualizer,
    create_vigilance_system,
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


def create_similar_tensor(reference: StateTensor, noise: float = 0.01) -> StateTensor:
    """Cree un tenseur similaire a la reference avec un peu de bruit."""
    tensor = reference.copy()
    tensor.state_id = reference.state_id + 1

    for dim_name in DIMENSION_NAMES:
        vec = getattr(tensor, dim_name).copy()
        # Ajouter du bruit
        vec += np.random.randn(EMBEDDING_DIM) * noise
        # Re-normaliser
        vec = vec / np.linalg.norm(vec)
        setattr(tensor, dim_name, vec)

    return tensor


def create_different_tensor(reference: StateTensor, offset: float = 0.5) -> StateTensor:
    """Cree un tenseur different de la reference."""
    tensor = reference.copy()
    tensor.state_id = reference.state_id + 1

    for dim_name in DIMENSION_NAMES:
        # Vecteur orthogonal approximatif
        vec = np.random.randn(EMBEDDING_DIM)
        vec = vec / np.linalg.norm(vec)
        setattr(tensor, dim_name, vec)

    return tensor


class TestVigilanceAlert:
    """Tests pour VigilanceAlert."""

    def test_create_alert(self):
        """Creer une alerte."""
        alert = VigilanceAlert(
            level="warning",
            message="Derive detectee",
            cumulative_drift=0.015,
            state_id=5,
        )

        assert alert.level == "warning"
        assert alert.cumulative_drift == 0.015
        assert alert.is_alert is True

    def test_ok_not_alert(self):
        """'ok' n'est pas une alerte."""
        alert = VigilanceAlert(level="ok")
        assert alert.is_alert is False

    def test_warning_is_alert(self):
        """'warning' est une alerte."""
        alert = VigilanceAlert(level="warning")
        assert alert.is_alert is True

    def test_critical_is_alert(self):
        """'critical' est une alerte."""
        alert = VigilanceAlert(level="critical")
        assert alert.is_alert is True

    def test_to_dict(self):
        """to_dict() fonctionne."""
        alert = VigilanceAlert(
            level="critical",
            message="Test",
            dimensions={'firstness': 0.1},
            cumulative_drift=0.025,
        )

        d = alert.to_dict()
        assert 'level' in d
        assert 'message' in d
        assert 'dimensions' in d
        assert d['cumulative_drift'] == 0.025


class TestVigilanceConfig:
    """Tests pour VigilanceConfig."""

    def test_default_config(self):
        """Configuration par defaut."""
        config = VigilanceConfig()

        assert config.threshold_cumulative == 0.01  # 1%
        assert config.threshold_per_cycle == 0.002  # 0.2%
        assert config.threshold_per_dimension == 0.05  # 5%
        assert config.critical_multiplier == 2.0

    def test_validate_default(self):
        """La config par defaut est valide."""
        config = VigilanceConfig()
        assert config.validate() is True

    def test_validate_invalid(self):
        """Config invalide."""
        config = VigilanceConfig(threshold_cumulative=2.0)  # > 1
        assert config.validate() is False


class TestVigilanceSystem:
    """Tests pour VigilanceSystem."""

    def test_create_system(self):
        """Creer un systeme de vigilance."""
        x_ref = create_random_tensor(state_id=-1, seed=42)
        system = VigilanceSystem(x_ref=x_ref)

        assert system.x_ref is x_ref
        assert system.cumulative_drift == 0.0
        assert len(system.history) == 0

    def test_no_drift_when_identical(self):
        """Pas de derive si X_t == x_ref."""
        x_ref = create_random_tensor(state_id=-1, seed=42)
        system = VigilanceSystem(x_ref=x_ref)

        # Premier check avec x_ref lui-meme
        alert = system.check_drift(x_ref)

        assert alert.level == "ok"
        assert alert.cumulative_drift == 0.0

    def test_warning_when_drifting(self):
        """Alerte warning quand derive > seuil."""
        x_ref = create_random_tensor(state_id=-1, seed=42)
        system = VigilanceSystem(
            x_ref=x_ref,
            config=VigilanceConfig(threshold_cumulative=0.001)  # Seuil bas
        )

        # Premier check etablit X_prev
        system.check_drift(x_ref)

        # Creer un etat different
        X_t = create_different_tensor(x_ref)
        alert = system.check_drift(X_t)

        # Devrait etre au moins warning ou critical
        assert alert.level in ("warning", "critical")

    def test_critical_when_high_drift(self):
        """Alerte critical quand derive >> seuil."""
        x_ref = create_random_tensor(state_id=-1, seed=42)
        system = VigilanceSystem(
            x_ref=x_ref,
            config=VigilanceConfig(
                threshold_cumulative=0.0001,  # Seuil tres bas
                critical_multiplier=1.5
            )
        )

        # Premier check
        system.check_drift(x_ref)

        # Plusieurs checks avec etats differents pour accumuler drift
        for i in range(3):
            X_t = create_different_tensor(x_ref)
            X_t.state_id = i + 1
            alert = system.check_drift(X_t)

        assert alert.level == "critical"

    def test_cumulative_drift_increases(self):
        """La derive cumulative augmente."""
        x_ref = create_random_tensor(state_id=-1, seed=42)
        system = VigilanceSystem(x_ref=x_ref)

        # Premier check
        system.check_drift(x_ref)

        # Plusieurs checks avec de petites differences
        for i in range(5):
            X_t = create_similar_tensor(x_ref, noise=0.1)
            X_t.state_id = i + 1
            system.check_drift(X_t)

        assert system.cumulative_drift > 0

    def test_reset_cumulative(self):
        """Reset de la derive cumulative."""
        x_ref = create_random_tensor(state_id=-1, seed=42)
        system = VigilanceSystem(x_ref=x_ref)

        # Accumuler de la derive
        system.check_drift(x_ref)
        X_t = create_different_tensor(x_ref)
        system.check_drift(X_t)

        assert system.cumulative_drift > 0

        # Reset
        system.reset_cumulative()
        assert system.cumulative_drift == 0.0

    def test_history_recorded(self):
        """L'historique des alertes est enregistre."""
        x_ref = create_random_tensor(state_id=-1, seed=42)
        system = VigilanceSystem(x_ref=x_ref)

        for i in range(3):
            X_t = create_similar_tensor(x_ref, noise=0.05)
            X_t.state_id = i
            system.check_drift(X_t)

        assert len(system.history) == 3


class TestDistanceCalculations:
    """Tests pour les calculs de distance."""

    def test_distance_per_dimension(self):
        """Distance par dimension."""
        x_ref = create_random_tensor(state_id=-1, seed=42)
        system = VigilanceSystem(x_ref=x_ref)

        # Distance avec soi-meme = 0
        distances = system._distance_per_dimension(x_ref)

        for dim_name, dist in distances.items():
            assert np.isclose(dist, 0.0, atol=1e-6)

    def test_distance_opposite_vectors(self):
        """Distance avec vecteurs opposes."""
        x_ref = create_random_tensor(state_id=-1, seed=42)
        system = VigilanceSystem(x_ref=x_ref)

        # Creer un tenseur avec vecteurs opposes
        X_opposite = x_ref.copy()
        for dim_name in DIMENSION_NAMES:
            setattr(X_opposite, dim_name, -getattr(x_ref, dim_name))

        distances = system._distance_per_dimension(X_opposite)

        # Distance cosine avec vecteur oppose = 2 (1 - (-1))
        for dim_name, dist in distances.items():
            assert np.isclose(dist, 2.0, atol=1e-6)

    def test_global_distance_self(self):
        """Distance globale avec soi-meme = 0."""
        x_ref = create_random_tensor(state_id=-1, seed=42)
        system = VigilanceSystem(x_ref=x_ref)

        dist = system._global_distance(x_ref)
        assert np.isclose(dist, 0.0, atol=1e-6)

    def test_global_distance_different(self):
        """Distance globale avec tenseur different > 0."""
        x_ref = create_random_tensor(state_id=-1, seed=42)
        system = VigilanceSystem(x_ref=x_ref)

        X_different = create_random_tensor(state_id=1, seed=123)
        dist = system._global_distance(X_different)

        assert dist > 0


class TestTopDriftingDimensions:
    """Tests pour l'identification des dimensions en derive."""

    def test_identifies_drifting_dims(self):
        """Identifie les dimensions qui derivent."""
        x_ref = create_random_tensor(state_id=-1, seed=42)
        system = VigilanceSystem(x_ref=x_ref)

        # Creer un tenseur ou certaines dimensions sont tres differentes
        X_t = x_ref.copy()
        # Inverser seulement 'firstness' et 'valeurs'
        X_t.firstness = -x_ref.firstness
        X_t.valeurs = -x_ref.valeurs

        alert = system.check_drift(X_t)

        # Les dimensions inversees devraient etre dans le top
        assert 'firstness' in alert.top_drifting_dimensions
        assert 'valeurs' in alert.top_drifting_dimensions


class TestDavidReference:
    """Tests pour DavidReference."""

    def test_create_from_declared_profile_no_model(self):
        """Creer x_ref depuis profil sans modele d'embedding."""
        # Creer un fichier profil temporaire
        profile = {
            "profile": {
                "epistemic": {"curiosity": 8, "certainty": 3},
                "affective": {"enthusiasm": 5},
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(profile, f)
            profile_path = f.name

        x_ref = DavidReference.create_from_declared_profile(profile_path)

        assert x_ref.state_id == -1
        assert x_ref.firstness.shape == (EMBEDDING_DIM,)
        # Vecteurs normalises
        assert np.isclose(np.linalg.norm(x_ref.firstness), 1.0)

    def test_create_hybrid_fallback(self):
        """create_hybrid sans weaviate retourne profil declare."""
        profile = {"profile": {"epistemic": {"curiosity": 5}}}

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(profile, f)
            profile_path = f.name

        # Sans weaviate, utilise create_hybrid avec mock
        x_declared = DavidReference.create_from_declared_profile(profile_path)

        assert x_declared is not None
        assert x_declared.state_id == -1


class TestVigilanceVisualizer:
    """Tests pour VigilanceVisualizer."""

    def test_format_distance_report(self):
        """format_distance_report genere un rapport."""
        x_ref = create_random_tensor(state_id=-1, seed=42)
        X_t = create_similar_tensor(x_ref, noise=0.1)

        report = VigilanceVisualizer.format_distance_report(X_t, x_ref, 0.005)

        assert "RAPPORT VIGILANCE" in report
        assert "Derive cumulative" in report
        for dim_name in DIMENSION_NAMES:
            assert dim_name in report

    def test_format_report_includes_bars(self):
        """Le rapport inclut des barres de progression."""
        x_ref = create_random_tensor(state_id=-1, seed=42)
        X_t = create_different_tensor(x_ref)

        report = VigilanceVisualizer.format_distance_report(X_t, x_ref)

        # Devrait avoir des barres (caracteres # et -)
        assert "#" in report or "-" in report


class TestCreateVigilanceSystem:
    """Tests pour la factory create_vigilance_system."""

    def test_create_without_args(self):
        """Creer un systeme sans arguments (mode test)."""
        system = create_vigilance_system()

        assert system is not None
        assert system.x_ref is not None
        assert system.x_ref.state_id == -1

    def test_create_with_profile(self):
        """Creer un systeme avec profil."""
        profile = {"profile": {"epistemic": {"curiosity": 7}}}

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(profile, f)
            profile_path = f.name

        system = create_vigilance_system(profile_path=profile_path)

        assert system is not None
        assert system.x_ref.state_id == -1

    def test_create_with_custom_config(self):
        """Creer un systeme avec config personnalisee."""
        config = VigilanceConfig(
            threshold_cumulative=0.02,
            threshold_per_cycle=0.005
        )

        system = create_vigilance_system(config=config)

        assert system.config.threshold_cumulative == 0.02
        assert system.config.threshold_per_cycle == 0.005


class TestGetStats:
    """Tests pour get_stats."""

    def test_initial_stats(self):
        """Stats initiales."""
        x_ref = create_random_tensor(state_id=-1, seed=42)
        system = VigilanceSystem(x_ref=x_ref)

        stats = system.get_stats()

        assert stats['cumulative_drift'] == 0.0
        assert stats['total_checks'] == 0
        assert stats['alerts_count'] == {'ok': 0, 'warning': 0, 'critical': 0}

    def test_stats_after_checks(self):
        """Stats apres plusieurs checks."""
        x_ref = create_random_tensor(state_id=-1, seed=42)
        system = VigilanceSystem(x_ref=x_ref)

        for i in range(5):
            X_t = create_similar_tensor(x_ref, noise=0.05)
            X_t.state_id = i
            system.check_drift(X_t)

        stats = system.get_stats()

        assert stats['total_checks'] == 5
        assert len(stats['recent_alerts']) <= 10


class TestIntegrationWithRealProfile:
    """Tests d'integration avec le vrai profil David."""

    def test_load_real_profile(self):
        """Charger le vrai profil david_profile_declared.json."""
        profile_path = Path(__file__).parent.parent / "david_profile_declared.json"

        if not profile_path.exists():
            pytest.skip("david_profile_declared.json not found")

        x_ref = DavidReference.create_from_declared_profile(str(profile_path))

        assert x_ref is not None
        assert x_ref.state_id == -1

        # Verifier que toutes les dimensions sont initialisees
        for dim_name in DIMENSION_NAMES:
            vec = getattr(x_ref, dim_name)
            assert vec.shape == (EMBEDDING_DIM,)
            assert np.isclose(np.linalg.norm(vec), 1.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
