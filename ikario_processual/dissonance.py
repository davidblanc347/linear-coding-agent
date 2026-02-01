#!/usr/bin/env python3
"""
Dissonance - Calcul du "choc" entre une entrée et l'état actuel.

Phase 2 du plan processuel v2.

La dissonance E(e_input, X_t) mesure :
1. La distance dimensionnelle aux 8 composantes du tenseur
2. Les hard negatives (contradictions dans le corpus)
3. La nouveauté radicale (absence de corroboration)

Formule :
    E_total = E_dimensionnelle + E_contradictions + E_nouveauté

Un Impact est créé quand E_total > seuil de choc.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np

from .state_tensor import StateTensor, DIMENSION_NAMES, EMBEDDING_DIM


@dataclass
class DissonanceConfig:
    """Configuration pour le calcul de dissonance."""

    # Poids par dimension (doivent sommer à ~1.0)
    w_firstness: float = 0.15      # Dissonance avec intuitions
    w_secondness: float = 0.25     # Dissonance avec résistances connues
    w_thirdness: float = 0.20      # Dissonance avec habitudes
    w_dispositions: float = 0.10   # Contre-disposition
    w_orientations: float = 0.10   # Hors-direction
    w_engagements: float = 0.05    # Contradiction engagement
    w_pertinences: float = 0.05    # Hors-pertinence
    w_valeurs: float = 0.10        # Conflit de valeurs

    # Seuils
    choc_threshold: float = 0.3    # Seuil pour créer un Impact

    # Amendement #2 : Hard negatives
    contradiction_weight: float = 0.2   # Poids des contradictions détectées
    novelty_weight: float = 0.1         # Poids de la nouveauté radicale
    hard_negative_threshold: float = 0.1  # Seuil similarité pour hard negative

    # Amendement #8 : NLI (optionnel)
    use_nli: bool = False           # Activer détection NLI
    nli_threshold: float = 0.5      # Seuil confiance NLI

    def get_dimension_weights(self) -> Dict[str, float]:
        """Retourne les poids par dimension."""
        return {
            'firstness': self.w_firstness,
            'secondness': self.w_secondness,
            'thirdness': self.w_thirdness,
            'dispositions': self.w_dispositions,
            'orientations': self.w_orientations,
            'engagements': self.w_engagements,
            'pertinences': self.w_pertinences,
            'valeurs': self.w_valeurs,
        }


@dataclass
class DissonanceResult:
    """Résultat du calcul de dissonance."""

    # Scores
    total: float
    base_dissonance: float
    contradiction_score: float
    novelty_penalty: float

    # Flags
    is_choc: bool

    # Détails par dimension
    dissonances_by_dimension: Dict[str, float]

    # Hard negatives
    hard_negatives: List[Dict[str, Any]]

    # Corpus stats
    max_similarity_to_corpus: float
    rag_results_count: int

    # Metadata
    config_used: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire."""
        return {
            'total': self.total,
            'base_dissonance': self.base_dissonance,
            'contradiction_score': self.contradiction_score,
            'novelty_penalty': self.novelty_penalty,
            'is_choc': self.is_choc,
            'dissonances_by_dimension': self.dissonances_by_dimension,
            'hard_negatives_count': len(self.hard_negatives),
            'max_similarity_to_corpus': self.max_similarity_to_corpus,
            'rag_results_count': self.rag_results_count,
        }

    def to_json(self) -> str:
        """Sérialise en JSON."""
        return json.dumps(self.to_dict(), indent=2)


def cosine_similarity(v1: np.ndarray, v2: np.ndarray) -> float:
    """Calcule la similarité cosine entre deux vecteurs."""
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(np.dot(v1, v2) / (norm1 * norm2))


def compute_dissonance(
    e_input: np.ndarray,
    X_t: StateTensor,
    config: DissonanceConfig = None
) -> DissonanceResult:
    """
    Calcule la dissonance basique entre une entrée et l'état actuel.

    Version simplifiée sans RAG/hard negatives.

    Args:
        e_input: Vecteur d'entrée (1024-dim, normalisé)
        X_t: État actuel du tenseur
        config: Configuration des poids

    Returns:
        DissonanceResult avec les scores
    """
    config = config or DissonanceConfig()
    weights = config.get_dimension_weights()

    # Calculer la dissonance par dimension
    dissonances = {}
    base_dissonance = 0.0

    for dim_name, weight in weights.items():
        x_dim = getattr(X_t, dim_name)
        cos_sim = cosine_similarity(e_input, x_dim)
        dissonance = 1.0 - cos_sim  # Distance cosine
        dissonances[dim_name] = dissonance
        base_dissonance += weight * dissonance

    return DissonanceResult(
        total=base_dissonance,
        base_dissonance=base_dissonance,
        contradiction_score=0.0,
        novelty_penalty=0.0,
        is_choc=base_dissonance > config.choc_threshold,
        dissonances_by_dimension=dissonances,
        hard_negatives=[],
        max_similarity_to_corpus=0.0,
        rag_results_count=0,
        config_used=weights,
    )


def compute_dissonance_enhanced(
    e_input: np.ndarray,
    X_t: StateTensor,
    rag_results: List[Dict[str, Any]],
    config: DissonanceConfig = None,
    nli_detector: Any = None  # Optional NLI detector (Amendment #8)
) -> DissonanceResult:
    """
    Calcule la dissonance enrichie avec hard negatives et nouveauté radicale.

    AMENDEMENT #2 : Implémente la détection de contradictions et nouveauté.

    Formule :
        E_total = E_dimensionnelle + w_contradiction * E_contradictions + w_novelty * E_nouveauté

    Args:
        e_input: Vecteur d'entrée (1024-dim, normalisé)
        X_t: État actuel du tenseur
        rag_results: Résultats RAG avec 'vector' et optionnel 'content'
        config: Configuration des poids
        nli_detector: Détecteur NLI optionnel (Amendment #8)

    Returns:
        DissonanceResult avec tous les détails
    """
    config = config or DissonanceConfig()
    weights = config.get_dimension_weights()

    # === PARTIE 1 : Dissonance dimensionnelle ===
    dissonances = {}
    base_dissonance = 0.0

    for dim_name, weight in weights.items():
        x_dim = getattr(X_t, dim_name)
        cos_sim = cosine_similarity(e_input, x_dim)
        dissonance = 1.0 - cos_sim
        dissonances[dim_name] = dissonance
        base_dissonance += weight * dissonance

    # === PARTIE 2 : HARD NEGATIVES (contradictions) ===
    hard_negatives = []
    contradiction_score = 0.0

    if rag_results:
        for result in rag_results:
            result_vector = result.get('vector')
            if result_vector is None:
                continue

            # Convertir en numpy si nécessaire
            if not isinstance(result_vector, np.ndarray):
                result_vector = np.array(result_vector)

            similarity = cosine_similarity(e_input, result_vector)

            # Détection basique : similarité très faible = potentielle contradiction
            is_hard_negative = similarity < config.hard_negative_threshold

            # Amendement #8 : Si NLI disponible et similarité moyenne, vérifier
            nli_contradiction_score = None
            if (not is_hard_negative and
                nli_detector is not None and
                config.use_nli and
                0.3 <= similarity <= 0.7):

                input_text = result.get('input_text', '')
                result_text = result.get('content', '')

                if input_text and result_text:
                    is_contradiction, nli_score = nli_detector.detect_contradiction(
                        input_text, result_text
                    )
                    if is_contradiction:
                        is_hard_negative = True
                        nli_contradiction_score = nli_score

            if is_hard_negative:
                hard_negatives.append({
                    'content': result.get('content', '')[:200],  # Tronquer
                    'similarity': similarity,
                    'source': result.get('source', 'unknown'),
                    'nli_score': nli_contradiction_score,
                })

        # Score de contradiction = proportion de hard negatives
        contradiction_score = len(hard_negatives) / max(len(rag_results), 1)

    # === PARTIE 3 : NOUVEAUTÉ RADICALE ===
    novelty_penalty = 0.0
    max_sim_to_corpus = 0.0

    if rag_results:
        similarities = []
        for result in rag_results:
            result_vector = result.get('vector')
            if result_vector is not None:
                if not isinstance(result_vector, np.ndarray):
                    result_vector = np.array(result_vector)
                sim = cosine_similarity(e_input, result_vector)
                similarities.append(sim)

        if similarities:
            max_sim_to_corpus = max(similarities)

            # Si max similarité < 0.3 → très nouveau, terra incognita
            if max_sim_to_corpus < 0.3:
                novelty_penalty = 1.0 - max_sim_to_corpus
    else:
        # Pas de résultats RAG → nouveauté totale
        novelty_penalty = 1.0

    # === CALCUL TOTAL ===
    total_dissonance = (
        base_dissonance +
        config.contradiction_weight * contradiction_score +
        config.novelty_weight * novelty_penalty
    )

    return DissonanceResult(
        total=total_dissonance,
        base_dissonance=base_dissonance,
        contradiction_score=contradiction_score,
        novelty_penalty=novelty_penalty,
        is_choc=total_dissonance > config.choc_threshold,
        dissonances_by_dimension=dissonances,
        hard_negatives=hard_negatives,
        max_similarity_to_corpus=max_sim_to_corpus,
        rag_results_count=len(rag_results) if rag_results else 0,
        config_used=weights,
    )


def compute_self_dissonance(X_t: StateTensor, config: DissonanceConfig = None) -> float:
    """
    Calcule la dissonance interne du tenseur (tensions entre dimensions).

    Utile pour détecter les conflits internes.

    Returns:
        Score de cohérence interne (0 = parfait, >0 = tensions)
    """
    config = config or DissonanceConfig()

    # Calculer les similarités entre paires de dimensions
    tensions = []

    # Paires qui devraient être cohérentes
    coherent_pairs = [
        ('valeurs', 'engagements'),
        ('orientations', 'dispositions'),
        ('thirdness', 'valeurs'),
    ]

    for dim1, dim2 in coherent_pairs:
        v1 = getattr(X_t, dim1)
        v2 = getattr(X_t, dim2)
        sim = cosine_similarity(v1, v2)
        tension = 1.0 - sim
        tensions.append(tension)

    return float(np.mean(tensions)) if tensions else 0.0


# ============================================================================
# IMPACT CREATION
# ============================================================================

@dataclass
class Impact:
    """
    Représente un événement de choc (Secondness).

    Un Impact est créé quand la dissonance dépasse le seuil.
    Il reste "non résolu" jusqu'à intégration dans l'état.
    """
    impact_id: int
    timestamp: str
    state_id_at_impact: int

    # Déclencheur
    trigger_type: str  # user, corpus, veille, internal
    trigger_content: str
    trigger_vector: Optional[np.ndarray] = None

    # Dissonance
    dissonance_total: float = 0.0
    dissonance_breakdown: str = ""  # JSON

    # Hard negatives (Amendment #2)
    hard_negatives_count: int = 0
    novelty_score: float = 0.0

    # Résolution
    resolved: bool = False
    resolution_state_id: int = -1

    # Rumination (Amendment #9)
    last_rumination: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire pour Weaviate."""
        d = {
            'impact_id': self.impact_id,
            'timestamp': self.timestamp if self.timestamp.endswith('Z') else self.timestamp + 'Z',
            'state_id_at_impact': self.state_id_at_impact,
            'trigger_type': self.trigger_type,
            'trigger_content': self.trigger_content,
            'dissonance_total': self.dissonance_total,
            'dissonance_breakdown': self.dissonance_breakdown,
            'hard_negatives_count': self.hard_negatives_count,
            'novelty_score': self.novelty_score,
            'resolved': self.resolved,
            'resolution_state_id': self.resolution_state_id,
        }
        if self.last_rumination:
            d['last_rumination'] = self.last_rumination
        return d


def create_impact_from_dissonance(
    dissonance: DissonanceResult,
    trigger_type: str,
    trigger_content: str,
    trigger_vector: np.ndarray,
    state_id: int,
    impact_id: int
) -> Impact:
    """
    Crée un Impact à partir d'un résultat de dissonance.

    Args:
        dissonance: Résultat du calcul de dissonance
        trigger_type: Type de déclencheur (user, corpus, veille, internal)
        trigger_content: Contenu textuel du déclencheur
        trigger_vector: Vecteur du déclencheur
        state_id: ID de l'état au moment de l'impact
        impact_id: ID unique de l'impact

    Returns:
        Impact créé
    """
    return Impact(
        impact_id=impact_id,
        timestamp=datetime.now().isoformat(),
        state_id_at_impact=state_id,
        trigger_type=trigger_type,
        trigger_content=trigger_content[:1000],  # Tronquer si trop long
        trigger_vector=trigger_vector,
        dissonance_total=dissonance.total,
        dissonance_breakdown=dissonance.to_json(),
        hard_negatives_count=len(dissonance.hard_negatives),
        novelty_score=dissonance.novelty_penalty,
        resolved=False,
        resolution_state_id=-1,
    )


# ============================================================================
# IMPACT REPOSITORY
# ============================================================================

class ImpactRepository:
    """Repository pour les opérations CRUD sur Impact."""

    def __init__(self, client):
        """
        Args:
            client: Client Weaviate connecté
        """
        self.client = client
        self.collection = client.collections.get("Impact")

    def save(self, impact: Impact) -> str:
        """Sauvegarde un Impact dans Weaviate."""
        vector = impact.trigger_vector
        if vector is not None:
            vector = vector.tolist() if isinstance(vector, np.ndarray) else vector

        result = self.collection.data.insert(
            properties=impact.to_dict(),
            vector=vector,
        )
        return str(result)

    def get_by_id(self, impact_id: int) -> Optional[Impact]:
        """Récupère un impact par son ID."""
        from weaviate.classes.query import Filter

        results = self.collection.query.fetch_objects(
            filters=Filter.by_property("impact_id").equal(impact_id),
            include_vector=True,
            limit=1,
        )

        if not results.objects:
            return None

        obj = results.objects[0]
        return self._object_to_impact(obj)

    def get_unresolved(self, limit: int = 10) -> List[Impact]:
        """Récupère les impacts non résolus."""
        from weaviate.classes.query import Filter, Sort

        results = self.collection.query.fetch_objects(
            filters=Filter.by_property("resolved").equal(False),
            sort=Sort.by_property("timestamp", ascending=False),
            include_vector=True,
            limit=limit,
        )

        return [self._object_to_impact(obj) for obj in results.objects]

    def mark_resolved(self, impact_id: int, resolution_state_id: int) -> bool:
        """Marque un impact comme résolu."""
        from weaviate.classes.query import Filter

        results = self.collection.query.fetch_objects(
            filters=Filter.by_property("impact_id").equal(impact_id),
            limit=1,
        )

        if not results.objects:
            return False

        uuid = results.objects[0].uuid
        self.collection.data.update(
            uuid=uuid,
            properties={
                "resolved": True,
                "resolution_state_id": resolution_state_id,
            }
        )
        return True

    def update_rumination(self, impact_id: int) -> bool:
        """Met à jour la date de dernière rumination (Amendment #9)."""
        from weaviate.classes.query import Filter

        results = self.collection.query.fetch_objects(
            filters=Filter.by_property("impact_id").equal(impact_id),
            limit=1,
        )

        if not results.objects:
            return False

        uuid = results.objects[0].uuid
        self.collection.data.update(
            uuid=uuid,
            properties={
                "last_rumination": datetime.now().isoformat() + 'Z',
            }
        )
        return True

    def count_unresolved(self) -> int:
        """Compte les impacts non résolus."""
        from weaviate.classes.query import Filter
        from weaviate.classes.aggregate import GroupByAggregate

        result = self.collection.aggregate.over_all(
            filters=Filter.by_property("resolved").equal(False),
            total_count=True,
        )
        return result.total_count

    def _object_to_impact(self, obj) -> Impact:
        """Convertit un objet Weaviate en Impact."""
        props = obj.properties
        vector = obj.vector if hasattr(obj, 'vector') else None

        if isinstance(vector, dict):
            # Named vectors - prendre le premier
            vector = list(vector.values())[0] if vector else None

        return Impact(
            impact_id=props.get('impact_id', 0),
            timestamp=str(props.get('timestamp', '')),
            state_id_at_impact=props.get('state_id_at_impact', 0),
            trigger_type=props.get('trigger_type', ''),
            trigger_content=props.get('trigger_content', ''),
            trigger_vector=np.array(vector) if vector else None,
            dissonance_total=props.get('dissonance_total', 0.0),
            dissonance_breakdown=props.get('dissonance_breakdown', ''),
            hard_negatives_count=props.get('hard_negatives_count', 0),
            novelty_score=props.get('novelty_score', 0.0),
            resolved=props.get('resolved', False),
            resolution_state_id=props.get('resolution_state_id', -1),
            last_rumination=str(props.get('last_rumination', '')) or None,
        )
