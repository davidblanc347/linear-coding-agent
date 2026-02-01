#!/usr/bin/env python3
"""
LatentEngine - Moteur de pensée latent d'Ikario.

Phase 4 du plan processuel v2.

Implémente le cycle sémiotique Peircien :
1. FIRSTNESS  : Vectoriser l'entrée, extraire saillances
2. SECONDNESS : Calculer dissonance, créer Impacts si choc
3. THIRDNESS  : Appliquer fixation, calculer δ, mettre à jour X_t
4. SÉMIOSE    : Créer Thoughts, préparer cycle suivant

C'est ici que la pensée a lieu - PAS dans le LLM.
Le LLM ne fait que traduire le résultat en langage.
"""

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import json

import numpy as np

from .state_tensor import (
    StateTensor,
    StateTensorRepository,
    DIMENSION_NAMES,
    EMBEDDING_DIM,
)
from .dissonance import (
    DissonanceConfig,
    DissonanceResult,
    compute_dissonance_enhanced,
    Impact,
    ImpactRepository,
    create_impact_from_dissonance,
)
from .fixation import (
    FixationConfig,
    FixationResult,
    Authority,
    compute_delta,
    apply_delta_all_dimensions,
)


# ============================================================================
# THOUGHT - Pensée créée pendant un cycle
# ============================================================================

@dataclass
class Thought:
    """
    Une pensée créée pendant un cycle sémiotique.

    Les Thoughts sont les "traces" du processus de pensée latent.
    Elles ne sont pas le produit du LLM, mais du cycle vectoriel.
    """
    thought_id: int
    timestamp: str
    state_id: int  # État au moment de la création

    # Contenu
    content: str  # Description textuelle (générée pour logging)
    thought_type: str  # reflection, insight, question, resolution

    # Origine
    trigger_type: str
    trigger_summary: str

    # Métriques
    delta_magnitude: float
    dissonance_total: float
    dimensions_affected: List[str]

    # Vecteur
    vector: Optional[np.ndarray] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire pour Weaviate."""
        ts = self.timestamp
        if ts and not ts.endswith('Z') and '+' not in ts:
            ts = ts + 'Z'

        return {
            'thought_id': self.thought_id,
            'timestamp': ts,
            'state_id': self.state_id,
            'content': self.content,
            'thought_type': self.thought_type,
            'trigger_type': self.trigger_type,
            'trigger_summary': self.trigger_summary[:200],
            'delta_magnitude': self.delta_magnitude,
            'dissonance_total': self.dissonance_total,
            'dimensions_affected': self.dimensions_affected,
        }


# ============================================================================
# CYCLE RESULT
# ============================================================================

@dataclass
class CycleResult:
    """Résultat complet d'un cycle sémiotique."""

    # Nouvel état
    new_state: StateTensor
    previous_state_id: int

    # Dissonance
    dissonance: DissonanceResult

    # Fixation
    fixation: FixationResult

    # Impacts créés
    impacts: List[Impact]

    # Thoughts créées
    thoughts: List[Thought]

    # Verbalisation
    should_verbalize: bool
    verbalization_reason: str

    # Métriques
    processing_time_ms: int
    cycle_number: int

    # Saillances extraites
    saillances: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Résumé du cycle."""
        return {
            'cycle_number': self.cycle_number,
            'new_state_id': self.new_state.state_id,
            'previous_state_id': self.previous_state_id,
            'dissonance_total': self.dissonance.total,
            'is_choc': self.dissonance.is_choc,
            'delta_magnitude': self.fixation.magnitude,
            'was_clamped': self.fixation.was_clamped,
            'impacts_count': len(self.impacts),
            'thoughts_count': len(self.thoughts),
            'should_verbalize': self.should_verbalize,
            'verbalization_reason': self.verbalization_reason,
            'processing_time_ms': self.processing_time_ms,
        }


# ============================================================================
# CYCLE LOGGER
# ============================================================================

class CycleLogger:
    """Logger pour les cycles sémiotiques."""

    def __init__(self, max_history: int = 100):
        self.history: List[Dict[str, Any]] = []
        self.max_history = max_history
        self.total_cycles = 0

    def log_cycle(self, result: CycleResult) -> None:
        """Enregistre un cycle."""
        self.total_cycles += 1

        entry = {
            'cycle_number': self.total_cycles,
            'timestamp': datetime.now().isoformat(),
            **result.to_dict(),
        }

        self.history.append(entry)

        # Limiter la taille
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques."""
        if not self.history:
            return {'total_cycles': 0}

        dissonances = [h['dissonance_total'] for h in self.history]
        times = [h['processing_time_ms'] for h in self.history]

        return {
            'total_cycles': self.total_cycles,
            'recent_cycles': len(self.history),
            'avg_dissonance': float(np.mean(dissonances)),
            'max_dissonance': float(max(dissonances)),
            'avg_processing_time_ms': float(np.mean(times)),
            'total_impacts': sum(h['impacts_count'] for h in self.history),
            'total_thoughts': sum(h['thoughts_count'] for h in self.history),
        }


# ============================================================================
# LATENT ENGINE
# ============================================================================

class LatentEngine:
    """
    Moteur de pensée latent d'Ikario.

    Implémente le cycle sémiotique Peircien.
    C'est ici que la pensée a lieu - PAS dans le LLM.

    Usage:
        engine = LatentEngine(client, model)
        result = engine.run_cycle({
            'type': 'user',
            'content': 'Que penses-tu de Whitehead?'
        })
    """

    def __init__(
        self,
        weaviate_client,
        embedding_model,
        dissonance_config: DissonanceConfig = None,
        fixation_config: FixationConfig = None,
        authority: Authority = None,
        vigilance_system=None,  # Pour Phase 6
    ):
        """
        Args:
            weaviate_client: Client Weaviate connecté
            embedding_model: Modèle SentenceTransformer
            dissonance_config: Configuration dissonance
            fixation_config: Configuration fixation
            authority: Instance Authority pré-configurée
            vigilance_system: Système de vigilance x_ref (Phase 6)
        """
        self.client = weaviate_client
        self.model = embedding_model

        self.dissonance_config = dissonance_config or DissonanceConfig()
        self.fixation_config = fixation_config or FixationConfig()

        # Authority avec les vecteurs du Pacte
        self.authority = authority or Authority(
            embedding_model=embedding_model,
            config=self.fixation_config
        )

        self.vigilance = vigilance_system

        # Repositories
        self.state_repo = StateTensorRepository(weaviate_client)
        self.impact_repo = ImpactRepository(weaviate_client)

        # Logger
        self.logger = CycleLogger()

        # Compteurs
        self._impact_counter = 0
        self._thought_counter = 0

    def run_cycle(self, trigger: Dict[str, Any]) -> CycleResult:
        """
        Exécute un cycle sémiotique complet.

        Args:
            trigger: {
                'type': 'user' | 'corpus' | 'veille' | 'internal' | 'timer',
                'content': str,
                'metadata': dict (optional)
            }

        Returns:
            CycleResult avec tous les détails du cycle
        """
        start_time = time.time()

        # Valider le trigger
        trigger_type = trigger.get('type', 'unknown')
        trigger_content = trigger.get('content', '')

        if not trigger_content:
            raise ValueError("Trigger content is required")

        # === PHASE 1: FIRSTNESS ===
        # Récupérer l'état actuel
        X_t = self._get_current_state()
        previous_state_id = X_t.state_id

        # Vectoriser l'entrée
        e_input = self._vectorize_input(trigger_content)

        # Extraire les saillances
        saillances = self._extract_saillances(e_input, X_t)

        # === PHASE 2: SECONDNESS ===
        # Récupérer contexte RAG
        rag_results = self._retrieve_context(e_input, trigger_content)

        # Calculer dissonance avec hard negatives
        dissonance = compute_dissonance_enhanced(
            e_input,
            X_t,
            rag_results,
            self.dissonance_config
        )

        # Créer Impact si choc
        impacts = []
        if dissonance.is_choc:
            impact = self._create_impact(
                trigger_type=trigger_type,
                trigger_content=trigger_content,
                trigger_vector=e_input,
                dissonance=dissonance,
                state_id=X_t.state_id
            )
            impacts.append(impact)

        # === PHASE 3: THIRDNESS ===
        # Calculer delta via les 4 méthodes de fixation
        fixation_result = compute_delta(
            e_input=e_input,
            X_t=X_t,
            dissonance=dissonance,
            rag_results=rag_results,
            config=self.fixation_config,
            authority=self.authority
        )

        # Appliquer le delta pour créer X_{t+1}
        X_new = apply_delta_all_dimensions(
            X_t=X_t,
            e_input=e_input,
            fixation_result=fixation_result
        )

        # Mettre à jour les métadonnées
        X_new.trigger_type = trigger_type
        X_new.trigger_content = trigger_content[:500]
        X_new.timestamp = datetime.now().isoformat()

        # Persister le nouvel état
        self._persist_state(X_new)

        # === PHASE 4: SÉMIOSE ===
        # Créer Thought si delta significatif
        thoughts = []
        if fixation_result.magnitude > 0.0005:
            thought = self._create_thought(
                trigger_type=trigger_type,
                trigger_content=trigger_content,
                fixation_result=fixation_result,
                dissonance=dissonance,
                state_id=X_new.state_id
            )
            thoughts.append(thought)

        # Décider si verbalisation nécessaire
        should_verbalize, reason = self._should_verbalize(
            trigger=trigger,
            dissonance=dissonance,
            fixation_result=fixation_result,
            X_new=X_new
        )

        # Calculer le temps
        processing_time_ms = int((time.time() - start_time) * 1000)

        # Créer le résultat
        result = CycleResult(
            new_state=X_new,
            previous_state_id=previous_state_id,
            dissonance=dissonance,
            fixation=fixation_result,
            impacts=impacts,
            thoughts=thoughts,
            should_verbalize=should_verbalize,
            verbalization_reason=reason,
            processing_time_ms=processing_time_ms,
            cycle_number=self.logger.total_cycles + 1,
            saillances=saillances,
        )

        # Logger le cycle
        self.logger.log_cycle(result)

        return result

    def _get_current_state(self) -> StateTensor:
        """Récupère l'état actuel depuis Weaviate."""
        current = self.state_repo.get_current()
        if current is None:
            raise RuntimeError(
                "No current state found. Run create_initial_tensor.py first."
            )
        return current

    def _vectorize_input(self, content: str) -> np.ndarray:
        """Vectorise le contenu d'entrée."""
        # Tronquer si trop long
        if len(content) > 2000:
            content = content[:2000]

        embedding = self.model.encode(content)
        # Normaliser
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        return embedding

    def _extract_saillances(
        self,
        e_input: np.ndarray,
        X_t: StateTensor
    ) -> Dict[str, float]:
        """
        Extrait les saillances de l'entrée par rapport à l'état.

        Les saillances indiquent quelles dimensions sont les plus
        "touchées" par l'entrée.
        """
        saillances = {}

        for dim_name in DIMENSION_NAMES:
            dim_vec = getattr(X_t, dim_name)
            # Similarité = saillance
            sim = float(np.dot(e_input, dim_vec))
            saillances[dim_name] = sim

        return saillances

    def _retrieve_context(
        self,
        e_input: np.ndarray,
        content: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Récupère le contexte RAG pertinent.

        Cherche dans Thought et Message les contenus similaires.
        """
        rag_results = []

        try:
            # Chercher dans Thought
            thought_collection = self.client.collections.get("Thought")
            thought_results = thought_collection.query.near_vector(
                near_vector=e_input.tolist(),
                limit=limit,
                include_vector=True,
            )

            for obj in thought_results.objects:
                rag_results.append({
                    'content': obj.properties.get('content', ''),
                    'vector': obj.vector.get('default') if isinstance(obj.vector, dict) else obj.vector,
                    'source': 'thought',
                })

        except Exception:
            pass  # Collection might not exist

        try:
            # Chercher dans Message
            message_collection = self.client.collections.get("Message")
            message_results = message_collection.query.near_vector(
                near_vector=e_input.tolist(),
                limit=limit,
                include_vector=True,
            )

            for obj in message_results.objects:
                rag_results.append({
                    'content': obj.properties.get('content', ''),
                    'vector': obj.vector.get('default') if isinstance(obj.vector, dict) else obj.vector,
                    'source': 'message',
                    'input_text': content,  # Pour NLI si nécessaire
                })

        except Exception:
            pass

        return rag_results

    def _create_impact(
        self,
        trigger_type: str,
        trigger_content: str,
        trigger_vector: np.ndarray,
        dissonance: DissonanceResult,
        state_id: int
    ) -> Impact:
        """Crée et sauvegarde un Impact."""
        self._impact_counter += 1

        impact = create_impact_from_dissonance(
            dissonance=dissonance,
            trigger_type=trigger_type,
            trigger_content=trigger_content,
            trigger_vector=trigger_vector,
            state_id=state_id,
            impact_id=self._impact_counter
        )

        # Sauvegarder dans Weaviate
        try:
            self.impact_repo.save(impact)
        except Exception as e:
            print(f"[WARN] Could not save impact: {e}")

        return impact

    def _create_thought(
        self,
        trigger_type: str,
        trigger_content: str,
        fixation_result: FixationResult,
        dissonance: DissonanceResult,
        state_id: int
    ) -> Thought:
        """Crée une Thought basée sur le cycle."""
        self._thought_counter += 1

        # Déterminer le type de thought
        if dissonance.is_choc:
            thought_type = 'insight'
        elif fixation_result.was_clamped:
            thought_type = 'resolution'
        else:
            thought_type = 'reflection'

        # Dimensions les plus affectées
        contributions = fixation_result.contributions
        affected = sorted(contributions.keys(), key=lambda k: contributions[k], reverse=True)[:3]

        # Générer un contenu descriptif
        content = self._generate_thought_content(
            trigger_type=trigger_type,
            trigger_content=trigger_content,
            dissonance=dissonance,
            fixation_result=fixation_result,
            thought_type=thought_type
        )

        thought = Thought(
            thought_id=self._thought_counter,
            timestamp=datetime.now().isoformat(),
            state_id=state_id,
            content=content,
            thought_type=thought_type,
            trigger_type=trigger_type,
            trigger_summary=trigger_content[:100],
            delta_magnitude=fixation_result.magnitude,
            dissonance_total=dissonance.total,
            dimensions_affected=affected,
        )

        return thought

    def _generate_thought_content(
        self,
        trigger_type: str,
        trigger_content: str,
        dissonance: DissonanceResult,
        fixation_result: FixationResult,
        thought_type: str
    ) -> str:
        """Génère le contenu textuel d'une thought (sans LLM)."""
        # Description basée sur les métriques
        if thought_type == 'insight':
            return (
                f"Choc détecté (dissonance={dissonance.total:.3f}). "
                f"L'entrée '{trigger_content[:50]}...' a provoqué une tension "
                f"avec {len(dissonance.hard_negatives)} contradictions potentielles."
            )
        elif thought_type == 'resolution':
            return (
                f"Résolution d'une tension. Delta limité à {fixation_result.magnitude:.6f} "
                f"pour maintenir la stabilité. Contributions: "
                f"Science={fixation_result.contributions['science']:.4f}, "
                f"Authority={fixation_result.contributions['authority']:.4f}."
            )
        else:
            return (
                f"Réflexion sur '{trigger_content[:50]}...'. "
                f"Dissonance={dissonance.total:.3f}, "
                f"intégration via les 4 méthodes de fixation."
            )

    def _persist_state(self, X_new: StateTensor) -> None:
        """Sauvegarde le nouvel état dans Weaviate."""
        self.state_repo.save(X_new)

    def _should_verbalize(
        self,
        trigger: Dict[str, Any],
        dissonance: DissonanceResult,
        fixation_result: FixationResult,
        X_new: StateTensor
    ) -> Tuple[bool, str]:
        """
        Décide si le cycle doit produire une verbalisation.

        TOUJOURS verbaliser si:
        - trigger.type == 'user' (conversation)

        PEUT verbaliser si (mode autonome):
        - Dissonance très haute (découverte importante)
        - Alerte de dérive (vigilance)
        - Question à poser (tension irrésoluble)
        """
        trigger_type = trigger.get('type', 'unknown')

        # Mode conversation → toujours verbaliser
        if trigger_type == 'user':
            return True, "conversation_mode"

        # Mode autonome : vérifier critères
        if dissonance.total > 0.6:
            return True, "high_dissonance_discovery"

        # Vérifier vigilance si disponible
        if self.vigilance is not None:
            alert = self.vigilance.check_drift(X_new)
            if alert.level in ('warning', 'critical'):
                return True, f"drift_alert_{alert.level}"

        # Hard negatives nombreux → potentielle découverte
        if len(dissonance.hard_negatives) >= 3:
            return True, "multiple_contradictions"

        return False, "silent_processing"

    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques du moteur."""
        return {
            **self.logger.get_stats(),
            'impacts_created': self._impact_counter,
            'thoughts_created': self._thought_counter,
        }


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def create_engine(
    weaviate_client,
    embedding_model,
    load_authority: bool = True
) -> LatentEngine:
    """
    Factory pour créer un LatentEngine configuré.

    Args:
        weaviate_client: Client Weaviate connecté
        embedding_model: Modèle SentenceTransformer
        load_authority: Si True, charge les vecteurs du Pacte

    Returns:
        LatentEngine configuré
    """
    authority = None
    if load_authority:
        authority = Authority(embedding_model=embedding_model)

    return LatentEngine(
        weaviate_client=weaviate_client,
        embedding_model=embedding_model,
        authority=authority
    )
