#!/usr/bin/env python3
"""
OccasionManager - Orchestrateur du cycle d'occasion Ikario.

Gère le cycle complet:
    Préhension → Concrescence → Satisfaction

Ce module coordonne:
- La récupération du contexte (pensées, documents)
- L'appel au LLM pour générer la réponse
- La création du nouvel état
- Le logging de l'occasion
"""

import os
import time
from datetime import datetime
from typing import Dict, Any, List, Optional

import numpy as np
import requests

from .state_transformation import StateTransformer, compute_adaptive_params
from .occasion_logger import OccasionLogger, OccasionLog

WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://localhost:8080")


def get_state_profile(state_id: int) -> Dict[str, Dict[str, float]]:
    """
    Calcule le profil d'un état (projections sur les directions).

    Args:
        state_id: ID de l'état

    Returns:
        Dictionnaire {category: {component: value}}
    """
    # Récupérer le vecteur d'état
    state_query = {
        "query": """
        {
            Get {
                StateVector(where: {
                    path: ["state_id"],
                    operator: Equal,
                    valueInt: %d
                }) {
                    _additional { vector }
                }
            }
        }
        """ % state_id
    }

    response = requests.post(
        f"{WEAVIATE_URL}/v1/graphql",
        json=state_query,
        headers={"Content-Type": "application/json"}
    )

    if response.status_code != 200:
        return {}

    data = response.json()
    states = data.get("data", {}).get("Get", {}).get("StateVector", [])
    if not states:
        return {}

    state_vector = np.array(states[0]["_additional"]["vector"])

    # Récupérer toutes les directions
    dir_query = {
        "query": """
        {
            Get {
                ProjectionDirection {
                    name
                    category
                    _additional { vector }
                }
            }
        }
        """
    }

    response = requests.post(
        f"{WEAVIATE_URL}/v1/graphql",
        json=dir_query,
        headers={"Content-Type": "application/json"}
    )

    if response.status_code != 200:
        return {}

    data = response.json()
    directions = data.get("data", {}).get("Get", {}).get("ProjectionDirection", [])

    # Calculer les projections
    profile = {}
    for d in directions:
        direction_vector = np.array(d["_additional"]["vector"])
        projection = float(np.dot(state_vector, direction_vector))

        category = d.get("category", "unknown")
        if category not in profile:
            profile[category] = {}

        profile[category][d["name"]] = round(projection, 4)

    return profile


class OccasionManager:
    """
    Orchestrateur du cycle d'occasion Ikario.

    Gère Préhension → Concrescence → Satisfaction.
    """

    def __init__(
        self,
        log_dir: str = "logs/occasions",
        embedding_model=None
    ):
        """
        Args:
            log_dir: Répertoire pour les logs d'occasions
            embedding_model: Modèle SentenceTransformer (optionnel)
        """
        self.transformer = StateTransformer(embedding_model)
        self.logger = OccasionLogger(log_dir)
        self.current_occasion_id = self.logger.get_last_occasion_id() + 1

    def run_occasion(self, trigger: Dict[str, Any]) -> Dict[str, Any]:
        """
        Exécute un cycle complet d'occasion.

        Args:
            trigger: {
                "type": "user" | "timer" | "event",
                "content": str,
                "metadata": dict (optionnel)
            }

        Returns:
            {
                "occasion_id": int,
                "response": str,
                "new_state_id": int,
                "profile": dict,
                "processing_time_ms": int
            }
        """
        start_time = time.time()
        occasion_id = self.current_occasion_id
        self.current_occasion_id += 1

        print(f"\n[OccasionManager] === Occasion {occasion_id} ===")
        print(f"[OccasionManager] Trigger: {trigger['type']} - {trigger['content'][:50]}...")

        # ===== PHASE 1: PRÉHENSION =====
        print("[OccasionManager] Phase 1: Préhension...")
        prehension = self._prehend(trigger)
        profile_before = get_state_profile(prehension['previous_state_id'])

        # ===== PHASE 2: CONCRESCENCE =====
        print("[OccasionManager] Phase 2: Concrescence...")
        concrescence = self._concresce(trigger, prehension)

        # ===== PHASE 3: SATISFACTION =====
        print("[OccasionManager] Phase 3: Satisfaction...")
        satisfaction = self._satisfy(occasion_id, trigger, prehension, concrescence)

        # Profil après
        profile_after = get_state_profile(satisfaction['new_state_id'])

        # Logger l'occasion
        processing_time = int((time.time() - start_time) * 1000)

        log_entry = OccasionLog(
            occasion_id=occasion_id,
            timestamp=datetime.now().isoformat(),
            trigger_type=trigger['type'],
            trigger_content=trigger['content'][:500],
            previous_state_id=prehension['previous_state_id'],
            prehended_thoughts_count=len(prehension['thoughts']),
            prehended_docs_count=len(prehension['documents']),
            prehended_thoughts=[t.get('content', '')[:100] for t in prehension['thoughts'][:5]],
            response_summary=concrescence['response'][:500],
            new_thoughts=concrescence['new_thoughts'],
            tools_used=concrescence['tools_used'],
            new_state_id=satisfaction['new_state_id'],
            alpha_used=satisfaction['alpha'],
            beta_used=satisfaction['beta'],
            profile_before=profile_before,
            profile_after=profile_after,
            processing_time_ms=processing_time
        )

        self.logger.log(log_entry)

        print(f"[OccasionManager] Occasion {occasion_id} terminée en {processing_time}ms")
        print(f"[OccasionManager] Nouvel état: S({satisfaction['new_state_id']})")

        return {
            'occasion_id': occasion_id,
            'response': concrescence['response'],
            'new_state_id': satisfaction['new_state_id'],
            'profile': profile_after,
            'processing_time_ms': processing_time
        }

    def _prehend(self, trigger: Dict[str, Any]) -> Dict[str, Any]:
        """
        Phase de Préhension - récupération du contexte.

        Récupère:
        - L'état précédent
        - Les pensées pertinentes
        - Les documents pertinents
        """
        current_state_id = self.transformer.get_current_state_id()

        # Recherche sémantique dans les pensées
        thoughts = self._search_thoughts(trigger['content'], limit=10)

        # Recherche dans la bibliothèque
        documents = self._search_library(trigger['content'], limit=5)

        return {
            'previous_state_id': current_state_id,
            'previous_state_vector': self.transformer.get_state_vector(current_state_id),
            'thoughts': thoughts,
            'documents': documents
        }

    def _search_thoughts(self, query: str, limit: int = 10) -> List[Dict]:
        """Recherche sémantique dans les pensées."""
        gql = {
            "query": """
            {
                Get {
                    Thought(
                        nearText: {concepts: ["%s"]},
                        limit: %d
                    ) {
                        content
                        timestamp
                        thought_type
                    }
                }
            }
            """ % (query.replace('"', '\\"'), limit)
        }

        try:
            response = requests.post(
                f"{WEAVIATE_URL}/v1/graphql",
                json=gql,
                headers={"Content-Type": "application/json"}
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("data", {}).get("Get", {}).get("Thought", []) or []
        except Exception as e:
            print(f"[OccasionManager] Erreur recherche pensées: {e}")

        return []

    def _search_library(self, query: str, limit: int = 5) -> List[Dict]:
        """Recherche sémantique dans la bibliothèque (Chunks)."""
        gql = {
            "query": """
            {
                Get {
                    Chunk(
                        nearText: {concepts: ["%s"]},
                        limit: %d
                    ) {
                        content
                        source
                        chunk_type
                    }
                }
            }
            """ % (query.replace('"', '\\"'), limit)
        }

        try:
            response = requests.post(
                f"{WEAVIATE_URL}/v1/graphql",
                json=gql,
                headers={"Content-Type": "application/json"}
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("data", {}).get("Get", {}).get("Chunk", []) or []
        except Exception as e:
            print(f"[OccasionManager] Erreur recherche bibliothèque: {e}")

        return []

    def _concresce(
        self,
        trigger: Dict[str, Any],
        prehension: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Phase de Concrescence - génération de la réponse.

        NOTE: Dans cette version, on simule la concrescence.
        L'intégration avec Claude Code SDK viendra en Phase 6.
        """
        # Simulation - à remplacer par le SDK en Phase 6
        context_summary = f"État S({prehension['previous_state_id']}), "
        context_summary += f"{len(prehension['thoughts'])} pensées, "
        context_summary += f"{len(prehension['documents'])} documents"

        response = f"[Simulation] Réponse à: {trigger['content'][:100]}\n"
        response += f"Contexte: {context_summary}"

        return {
            'response': response,
            'new_thoughts': [],  # Pas de pensées en simulation
            'tools_used': ['search_thoughts', 'search_library'],  # Simulation
            'state_delta': {}
        }

    def _satisfy(
        self,
        occasion_id: int,
        trigger: Dict[str, Any],
        prehension: Dict[str, Any],
        concrescence: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Phase de Satisfaction - création du nouvel état.

        Persiste les nouvelles pensées et crée le nouvel état.
        """
        # Persister les nouvelles pensées
        for thought_content in concrescence['new_thoughts']:
            self._add_thought(thought_content, occasion_id)

        # Créer le nouvel état
        new_state_id = self.transformer.create_new_state(
            occasion={
                'trigger_type': trigger['type'],
                'trigger_content': trigger['content'],
                'summary': concrescence['response'][:200]
            },
            response_text=concrescence['response'],
            thoughts_created=len(concrescence['new_thoughts'])
        )

        # Récupérer les paramètres utilisés
        alpha, beta = compute_adaptive_params({
            'thoughts_created': len(concrescence['new_thoughts']),
            'trigger_type': trigger['type'],
            'trigger_content': trigger['content']
        })

        return {
            'new_state_id': new_state_id,
            'alpha': alpha,
            'beta': beta,
            'thoughts_persisted': len(concrescence['new_thoughts'])
        }

    def _add_thought(self, content: str, occasion_id: int):
        """Ajoute une nouvelle pensée dans Weaviate."""
        thought = {
            "content": content,
            "timestamp": datetime.now().isoformat() + "Z",
            "occasion_id": occasion_id,
            "thought_type": "reflection"
        }

        # Générer l'embedding
        embedding = self.transformer.model.encode(content)
        embedding = embedding / np.linalg.norm(embedding)

        response = requests.post(
            f"{WEAVIATE_URL}/v1/objects",
            json={
                "class": "Thought",
                "properties": thought,
                "vector": embedding.tolist()
            },
            headers={"Content-Type": "application/json"}
        )

        if response.status_code in [200, 201]:
            print(f"[OccasionManager] Pensée ajoutée: {content[:50]}...")
        else:
            print(f"[OccasionManager] Erreur ajout pensée: {response.status_code}")


# Test
if __name__ == "__main__":
    manager = OccasionManager(log_dir="tests/temp_logs")

    result = manager.run_occasion({
        "type": "user",
        "content": "Bonjour Ikario, parle-moi de ta vision processuelle selon Whitehead.",
        "metadata": {}
    })

    print(f"\nRésultat:")
    print(f"  Occasion ID: {result['occasion_id']}")
    print(f"  Nouvel état: S({result['new_state_id']})")
    print(f"  Temps: {result['processing_time_ms']}ms")
    print(f"  Réponse: {result['response'][:100]}...")
