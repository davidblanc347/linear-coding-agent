#!/usr/bin/env python3
"""
Vigilance System - Surveillance de la derive d'Ikario par rapport a x_ref (David).

Phase 6 de l'architecture processuelle v2.

x_ref N'EST PAS un attracteur. Ikario ne "tend" pas vers David.
x_ref EST un garde-fou. Si distance > seuil → ALERTE.

Ce module :
1. Definit x_ref comme StateTensor (profil de David)
2. Calcule la distance par dimension et globalement
3. Detecte les derives et genere des alertes
4. Permet le reset apres validation de David

Amendement #15 : Comparaison StateTensor Ikario <-> x_ref David
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np

from .state_tensor import StateTensor, DIMENSION_NAMES, EMBEDDING_DIM

# Logger
logger = logging.getLogger(__name__)


@dataclass
class VigilanceAlert:
    """Alerte de vigilance quand Ikario derive de x_ref."""
    level: str  # "ok", "warning", "critical"
    message: str = ""
    dimensions: Dict[str, float] = field(default_factory=dict)
    cumulative_drift: float = 0.0
    per_cycle_drift: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat() + "Z")
    state_id: int = 0
    top_drifting_dimensions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise en dictionnaire."""
        return {
            'level': self.level,
            'message': self.message,
            'dimensions': self.dimensions,
            'cumulative_drift': self.cumulative_drift,
            'per_cycle_drift': self.per_cycle_drift,
            'timestamp': self.timestamp,
            'state_id': self.state_id,
            'top_drifting_dimensions': self.top_drifting_dimensions,
        }

    @property
    def is_alert(self) -> bool:
        """True si alerte (warning ou critical)."""
        return self.level in ("warning", "critical")


@dataclass
class VigilanceConfig:
    """Configuration du systeme de vigilance."""
    # Seuil de derive cumulative (fraction)
    threshold_cumulative: float = 0.01  # 1% cumule
    # Seuil de derive par cycle (fraction)
    threshold_per_cycle: float = 0.002  # 0.2% par cycle
    # Seuil par dimension (cosine distance)
    threshold_per_dimension: float = 0.05  # 5% par dimension
    # Seuil critique (multiplicateur)
    critical_multiplier: float = 2.0  # critical = 2x le seuil

    def validate(self) -> bool:
        """Verifie que la config est valide."""
        return (
            0 < self.threshold_cumulative < 1 and
            0 < self.threshold_per_cycle < 1 and
            0 < self.threshold_per_dimension < 1 and
            self.critical_multiplier > 1
        )


class VigilanceSystem:
    """
    Surveille la derive d'Ikario par rapport a x_ref (David).

    x_ref est un garde-fou, PAS un attracteur.

    Niveaux d'alerte :
    - "ok" : Pas de derive significative
    - "warning" : Derive detectee (> seuil)
    - "critical" : Derive importante (> 2x seuil)
    """

    def __init__(
        self,
        x_ref: StateTensor,
        config: Optional[VigilanceConfig] = None,
    ):
        """
        Initialise le systeme de vigilance.

        Args:
            x_ref: Tenseur de reference (profil de David, fixe)
            config: Configuration des seuils
        """
        self.x_ref = x_ref
        self.config = config or VigilanceConfig()
        self.cumulative_drift = 0.0
        self.X_prev: Optional[StateTensor] = None
        self.history: List[VigilanceAlert] = []
        self._alerts_count = {'ok': 0, 'warning': 0, 'critical': 0}

    def check_drift(self, X_t: StateTensor) -> VigilanceAlert:
        """
        Compare l'etat actuel X_t avec x_ref et l'etat precedent.

        Args:
            X_t: Etat actuel d'Ikario

        Returns:
            VigilanceAlert avec niveau et details de la derive.
        """
        # 1. Distance par dimension (cosine distance)
        dim_distances = self._distance_per_dimension(X_t)

        # 2. Distance globale normalisee
        global_distance = self._global_distance(X_t)

        # 3. Drift incremental (si etat precedent existe)
        per_cycle_drift = 0.0
        if self.X_prev is not None:
            per_cycle_drift = self._compute_distance(X_t, self.X_prev)
            self.cumulative_drift += per_cycle_drift

        self.X_prev = X_t.copy()

        # 4. Identifier les dimensions en derive
        drifting_dims = {
            dim: dist for dim, dist in dim_distances.items()
            if dist > self.config.threshold_per_dimension
        }

        # Top 3 dimensions en derive
        sorted_dims = sorted(dim_distances.items(), key=lambda x: x[1], reverse=True)
        top_drifting = [d[0] for d in sorted_dims[:3]]

        # 5. Determiner niveau d'alerte
        critical_threshold = self.config.threshold_cumulative * self.config.critical_multiplier
        warning_threshold = self.config.threshold_cumulative

        if self.cumulative_drift > critical_threshold:
            level = "critical"
            message = f"DERIVE CRITIQUE : {self.cumulative_drift:.2%} cumule (seuil: {warning_threshold:.2%})"
        elif self.cumulative_drift > warning_threshold or len(drifting_dims) > 2:
            level = "warning"
            message = f"Derive detectee : {self.cumulative_drift:.2%} cumule"
            if drifting_dims:
                message += f", dimensions en derive : {list(drifting_dims.keys())}"
        elif per_cycle_drift > self.config.threshold_per_cycle:
            level = "warning"
            message = f"Derive rapide ce cycle : {per_cycle_drift:.2%}"
        else:
            level = "ok"
            message = ""

        alert = VigilanceAlert(
            level=level,
            message=message,
            dimensions=dim_distances,
            cumulative_drift=self.cumulative_drift,
            per_cycle_drift=per_cycle_drift,
            state_id=X_t.state_id,
            top_drifting_dimensions=top_drifting,
        )

        self.history.append(alert)
        self._alerts_count[level] += 1

        if level != "ok":
            logger.warning(f"Vigilance {level}: {message}")

        return alert

    def _distance_per_dimension(self, X_t: StateTensor) -> Dict[str, float]:
        """
        Distance cosine par dimension (0=identique, 1=orthogonal, 2=oppose).

        Args:
            X_t: Etat actuel

        Returns:
            Dict dimension -> distance cosine
        """
        distances = {}

        for dim_name in DIMENSION_NAMES:
            vec_ikario = getattr(X_t, dim_name)
            vec_david = getattr(self.x_ref, dim_name)

            # Cosine distance = 1 - cosine_similarity
            norm_ikario = np.linalg.norm(vec_ikario)
            norm_david = np.linalg.norm(vec_david)

            if norm_ikario > 0 and norm_david > 0:
                cos_sim = np.dot(vec_ikario, vec_david) / (norm_ikario * norm_david)
                distances[dim_name] = 1 - cos_sim
            else:
                distances[dim_name] = 1.0  # Max distance si un vecteur est nul

        return distances

    def _global_distance(self, X_t: StateTensor) -> float:
        """
        Distance L2 normalisee sur les 8192 dimensions.

        Args:
            X_t: Etat actuel

        Returns:
            Distance L2 normalisee
        """
        flat_ikario = X_t.to_flat()  # 8192 dims
        flat_david = self.x_ref.to_flat()  # 8192 dims

        diff = flat_ikario - flat_david
        norm_david = np.linalg.norm(flat_david)

        if norm_david > 0:
            return np.linalg.norm(diff) / norm_david
        return np.linalg.norm(diff)

    def _compute_distance(self, X1: StateTensor, X2: StateTensor) -> float:
        """
        Distance normalisee entre deux etats.

        Args:
            X1: Premier etat
            X2: Second etat (reference pour normalisation)

        Returns:
            Distance L2 normalisee
        """
        diff = X1.to_flat() - X2.to_flat()
        norm_ref = np.linalg.norm(X2.to_flat())

        if norm_ref > 0:
            return np.linalg.norm(diff) / norm_ref
        return np.linalg.norm(diff)

    def reset_cumulative(self) -> None:
        """
        Reset le compteur de derive cumulative.
        A utiliser apres validation explicite de David.
        """
        logger.info(f"Reset cumulative drift from {self.cumulative_drift:.2%}")
        self.cumulative_drift = 0.0

    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques de vigilance."""
        return {
            'cumulative_drift': self.cumulative_drift,
            'total_checks': len(self.history),
            'alerts_count': self._alerts_count.copy(),
            'recent_alerts': [a.to_dict() for a in self.history[-10:]],
        }


class DavidReference:
    """
    Factory pour creer x_ref (profil de David) comme StateTensor.
    Sert de garde-fou (NOT attracteur) pour le systeme de vigilance.
    """

    @staticmethod
    def create_from_declared_profile(
        profile_path: str,
        embedding_model=None,
    ) -> StateTensor:
        """
        Cree x_ref a partir du profil declare (JSON).

        Le profil contient des valeurs [-10, +10] par direction.
        On utilise ces valeurs pour ponderer les directions du tenseur.

        Args:
            profile_path: Chemin vers le fichier JSON du profil
            embedding_model: Modele d'embedding (SentenceTransformer)

        Returns:
            StateTensor representant David
        """
        with open(profile_path, 'r', encoding='utf-8') as f:
            profile_data = json.load(f)

        profile = profile_data.get("profile", {})

        # Creer un tenseur vide
        x_ref = StateTensor(
            state_id=-1,  # ID special pour x_ref
            timestamp=datetime.now().isoformat() + "Z",
        )

        if embedding_model is None:
            # Mode sans modele : creer des vecteurs aleatoires deterministes
            # base sur les valeurs du profil
            np.random.seed(42)

            for dim_name in DIMENSION_NAMES:
                v = np.random.randn(EMBEDDING_DIM)
                v = v / np.linalg.norm(v)
                setattr(x_ref, dim_name, v)

            return x_ref

        # Avec modele : creer des embeddings depuis les descriptions
        # Mapping dimensions -> categories du profil
        dim_to_category = {
            'firstness': 'epistemic',
            'secondness': 'metacognitive',
            'thirdness': 'philosophical',
            'dispositions': 'affective',
            'orientations': 'temporal',
            'engagements': 'relational',
            'pertinences': 'thematic',
            'valeurs': 'ethical',
        }

        for dim_name in DIMENSION_NAMES:
            category = dim_to_category.get(dim_name, 'epistemic')
            category_profile = profile.get(category, {})

            # Construire une description textuelle basee sur les valeurs
            descriptions = []
            for trait, value in category_profile.items():
                if value > 5:
                    descriptions.append(f"tres {trait}")
                elif value > 2:
                    descriptions.append(f"moderement {trait}")
                elif value < -5:
                    descriptions.append(f"pas du tout {trait}")
                elif value < -2:
                    descriptions.append(f"peu {trait}")

            if descriptions:
                text = f"David est {', '.join(descriptions[:5])}."
            else:
                text = f"David a un profil {category} neutre."

            # Embedding du texte
            embedding = embedding_model.encode(text)
            if isinstance(embedding, list):
                embedding = np.array(embedding)

            # Normaliser
            norm = np.linalg.norm(embedding)
            if norm > 0:
                embedding = embedding / norm

            setattr(x_ref, dim_name, embedding)

        return x_ref

    @staticmethod
    def create_from_history(
        weaviate_client,
        n_sessions: int = 100,
    ) -> StateTensor:
        """
        Cree x_ref a partir de l'historique des conversations.
        x_ref = moyenne ponderee des etats pendant conversations authentiques.

        Args:
            weaviate_client: Client Weaviate v4
            n_sessions: Nombre de sessions a utiliser

        Returns:
            StateTensor moyenne ponderee
        """
        try:
            from weaviate.classes.query import Sort
        except ImportError:
            logger.warning("Weaviate classes not available, using empty tensor")
            return StateTensor(state_id=-1, timestamp=datetime.now().isoformat() + "Z")

        try:
            collection = weaviate_client.collections.get("StateTensor")

            results = collection.query.fetch_objects(
                limit=n_sessions,
                sort=Sort.by_property("timestamp", ascending=False),
                include_vector=True,
            )

            if not results.objects:
                raise ValueError("Aucun etat historique trouve")

            states = []
            for obj in results.objects:
                tensor = StateTensor(
                    state_id=obj.properties.get("state_id", 0),
                    timestamp=obj.properties.get("timestamp", ""),
                )
                # Extraire les vecteurs depuis named vectors
                if hasattr(obj, 'vector') and isinstance(obj.vector, dict):
                    for dim_name in DIMENSION_NAMES:
                        if dim_name in obj.vector:
                            setattr(tensor, dim_name, np.array(obj.vector[dim_name]))
                states.append(tensor)

            # Ponderation exponentielle (recents = plus de poids)
            weights = np.exp(-np.arange(len(states)) * 0.01)
            weights /= weights.sum()

            return StateTensor.weighted_mean(states, weights)

        except Exception as e:
            logger.error(f"Erreur creation x_ref depuis historique: {e}")
            return StateTensor(state_id=-1, timestamp=datetime.now().isoformat() + "Z")

    @staticmethod
    def create_hybrid(
        profile_path: str,
        weaviate_client,
        embedding_model=None,
        alpha: float = 0.7,
    ) -> StateTensor:
        """
        RECOMMANDE : 70% profil declare + 30% historique observe.

        Args:
            profile_path: Chemin vers le profil JSON
            weaviate_client: Client Weaviate
            embedding_model: Modele d'embedding
            alpha: Poids du profil declare (default 0.7)

        Returns:
            StateTensor mixte
        """
        x_declared = DavidReference.create_from_declared_profile(
            profile_path, embedding_model
        )
        x_observed = DavidReference.create_from_history(weaviate_client)

        return StateTensor.blend(x_declared, x_observed, alpha=alpha)


class VigilanceVisualizer:
    """Visualisation de la distance par dimension."""

    @staticmethod
    def format_distance_report(
        X_t: StateTensor,
        x_ref: StateTensor,
        cumulative_drift: float = 0.0,
    ) -> str:
        """
        Genere un rapport textuel de la distance.

        Args:
            X_t: Etat actuel d'Ikario
            x_ref: Reference David
            cumulative_drift: Derive cumulative actuelle

        Returns:
            Rapport formate en texte
        """
        lines = ["=== RAPPORT VIGILANCE ===", ""]
        lines.append(f"Derive cumulative : {cumulative_drift:.2%}")
        lines.append("")
        lines.append("Distance par dimension :")
        lines.append("-" * 50)

        distances = []
        for dim_name in DIMENSION_NAMES:
            vec_ikario = getattr(X_t, dim_name)
            vec_david = getattr(x_ref, dim_name)

            norm_i = np.linalg.norm(vec_ikario)
            norm_d = np.linalg.norm(vec_david)

            if norm_i > 0 and norm_d > 0:
                cos_sim = np.dot(vec_ikario, vec_david) / (norm_i * norm_d)
                distance = 1 - cos_sim
            else:
                distance = 1.0

            distances.append((dim_name, distance))

        # Trier par distance decroissante
        distances.sort(key=lambda x: x[1], reverse=True)

        for dim_name, distance in distances:
            # Barre de progression
            bar_len = 20
            filled = int(distance * bar_len)
            bar = "#" * filled + "-" * (bar_len - filled)

            # Indicateur de niveau
            if distance > 0.05:
                level = "[!]"
            elif distance > 0.02:
                level = "[~]"
            else:
                level = "[OK]"

            lines.append(f"  {dim_name:15} [{bar}] {distance:.3f} {level}")

        lines.append("")

        # Distance globale
        flat_i = X_t.to_flat()
        flat_d = x_ref.to_flat()
        global_dist = np.linalg.norm(flat_i - flat_d) / (np.linalg.norm(flat_d) + 1e-8)
        lines.append(f"Distance globale L2 : {global_dist:.4f}")

        return "\n".join(lines)

    @staticmethod
    def radar_chart(
        X_t: StateTensor,
        x_ref: StateTensor,
        save_path: Optional[str] = None,
    ):
        """
        Genere un radar chart des 8 dimensions.

        Args:
            X_t: Etat actuel d'Ikario
            x_ref: Reference David
            save_path: Chemin pour sauvegarder l'image (optionnel)

        Returns:
            Figure matplotlib ou None
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            logger.warning("matplotlib not available for radar chart")
            return None

        dimensions = DIMENSION_NAMES
        values = []

        for dim in dimensions:
            vec_ikario = getattr(X_t, dim)
            vec_david = getattr(x_ref, dim)

            norm_i = np.linalg.norm(vec_ikario)
            norm_d = np.linalg.norm(vec_david)

            if norm_i > 0 and norm_d > 0:
                cos_sim = np.dot(vec_ikario, vec_david) / (norm_i * norm_d)
                distance = 1 - cos_sim
            else:
                distance = 1.0

            values.append(distance)

        # Fermer le polygone
        values += values[:1]
        angles = np.linspace(0, 2 * np.pi, len(dimensions), endpoint=False).tolist()
        angles += angles[:1]

        fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(projection='polar'))
        ax.fill(angles, values, color='red', alpha=0.25)
        ax.plot(angles, values, color='red', linewidth=2)

        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(dimensions)
        ax.set_ylim(0, 1)
        ax.set_title(
            "Distance Ikario - David (x_ref) par dimension\n0=identique, 1=orthogonal",
            fontsize=12
        )

        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            plt.close()
            return None

        return fig


def create_vigilance_system(
    profile_path: str = None,
    weaviate_client=None,
    embedding_model=None,
    config: Optional[VigilanceConfig] = None,
) -> VigilanceSystem:
    """
    Factory pour creer un systeme de vigilance configure.

    Args:
        profile_path: Chemin vers le profil declare de David
        weaviate_client: Client Weaviate (optionnel, pour historique)
        embedding_model: Modele d'embedding (optionnel)
        config: Configuration des seuils

    Returns:
        VigilanceSystem configure
    """
    if profile_path and weaviate_client:
        # Mode hybride recommande
        x_ref = DavidReference.create_hybrid(
            profile_path, weaviate_client, embedding_model
        )
    elif profile_path:
        # Mode profil declare uniquement
        x_ref = DavidReference.create_from_declared_profile(
            profile_path, embedding_model
        )
    elif weaviate_client:
        # Mode historique uniquement
        x_ref = DavidReference.create_from_history(weaviate_client)
    else:
        # Mode test : tenseur aleatoire
        x_ref = StateTensor(
            state_id=-1,
            timestamp=datetime.now().isoformat() + "Z",
        )
        np.random.seed(42)
        for dim_name in DIMENSION_NAMES:
            v = np.random.randn(EMBEDDING_DIM)
            v = v / np.linalg.norm(v)
            setattr(x_ref, dim_name, v)

    return VigilanceSystem(x_ref=x_ref, config=config)
