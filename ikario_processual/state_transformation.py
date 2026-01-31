#!/usr/bin/env python3
"""
StateTransformation - Fonction de transition d'état S(t-1) → S(t).

Implémente la transformation processuelle selon Whitehead:
- Préhension: récupérer le contexte
- Concrescence: intégrer l'occasion
- Satisfaction: nouvel état stable

La formule de base:
    S(t) = normalize(alpha * S(t-1) + beta * occasion_embedding)

où alpha (inertie) + beta (nouveauté) = 1
"""

import os
from datetime import datetime
from typing import Tuple, Dict, Any, Optional

import numpy as np
import requests

WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://localhost:8080")


def transform_state(
    s_prev: np.ndarray,
    occasion_embedding: np.ndarray,
    alpha: float = 0.85,
    beta: float = 0.15
) -> np.ndarray:
    """
    Transforme S(t-1) en S(t) via l'occasion.

    Le résultat est renormalisé pour rester sur l'hypersphère unitaire.

    Args:
        s_prev: Vecteur d'état précédent (normalisé)
        occasion_embedding: Embedding de l'occasion/réponse (normalisé)
        alpha: Coefficient d'inertie (conservation de l'identité)
        beta: Coefficient de nouveauté (intégration de l'occasion)

    Returns:
        Nouveau vecteur d'état normalisé
    """
    # Combinaison pondérée
    s_new = alpha * s_prev + beta * occasion_embedding

    # Renormalisation sur l'hypersphère
    norm = np.linalg.norm(s_new)
    if norm > 0:
        s_new = s_new / norm

    return s_new


def compute_adaptive_params(
    occasion: Dict[str, Any],
    base_alpha: float = 0.85,
    base_beta: float = 0.15
) -> Tuple[float, float]:
    """
    Calcule alpha/beta adaptatifs selon l'intensité de l'occasion.

    Heuristiques:
    - Plus de pensées créées → plus de beta (plus de changement)
    - Trigger "timer" → moins de beta (auto-réflexion douce)
    - Trigger "user" significatif → plus de beta

    Args:
        occasion: Dictionnaire avec trigger_type, thoughts_created, etc.
        base_alpha: Alpha de base
        base_beta: Beta de base

    Returns:
        Tuple (alpha, beta) ajustés
    """
    # Ajuster selon le nombre de pensées créées
    thoughts_count = occasion.get('thoughts_created', 0)
    intensity = min(thoughts_count * 0.03, 0.10)  # Max +10% de beta

    # Trigger timer = plus d'inertie (réflexion douce)
    if occasion.get('trigger_type') == 'timer':
        intensity = intensity * 0.5

    # Trigger user avec contenu long = plus d'impact
    trigger_content = occasion.get('trigger_content', '')
    if occasion.get('trigger_type') == 'user' and len(trigger_content) > 200:
        intensity = intensity + 0.02

    alpha = base_alpha - intensity
    beta = base_beta + intensity

    # S'assurer que alpha + beta = 1
    total = alpha + beta
    alpha = alpha / total
    beta = beta / total

    return alpha, beta


class StateTransformer:
    """Gère les transformations d'état et la persistance."""

    def __init__(self, embedding_model=None):
        """
        Args:
            embedding_model: Modèle SentenceTransformer (chargé à la demande si None)
        """
        self._model = embedding_model
        self._model_loaded = embedding_model is not None

    @property
    def model(self):
        """Charge le modèle d'embedding à la demande."""
        if not self._model_loaded:
            from sentence_transformers import SentenceTransformer
            print("[StateTransformer] Chargement du modèle BGE-M3...")
            self._model = SentenceTransformer('BAAI/bge-m3')
            self._model_loaded = True
        return self._model

    def get_current_state_id(self) -> int:
        """Retourne l'ID de l'état le plus récent."""
        url = f"{WEAVIATE_URL}/v1/objects?class=StateVector&limit=100"
        response = requests.get(url)

        if response.status_code != 200:
            return -1

        objects = response.json().get("objects", [])
        if not objects:
            return -1

        return max(obj.get("properties", {}).get("state_id", -1) for obj in objects)

    def get_state_vector(self, state_id: int) -> Optional[np.ndarray]:
        """Récupère le vecteur d'un état."""
        query = {
            "query": """
            {
                Get {
                    StateVector(where: {
                        path: ["state_id"],
                        operator: Equal,
                        valueInt: %d
                    }) {
                        _additional {
                            vector
                        }
                    }
                }
            }
            """ % state_id
        }

        response = requests.post(
            f"{WEAVIATE_URL}/v1/graphql",
            json=query,
            headers={"Content-Type": "application/json"}
        )

        if response.status_code != 200:
            return None

        data = response.json()
        states = data.get("data", {}).get("Get", {}).get("StateVector", [])

        if not states:
            return None

        vector = states[0].get("_additional", {}).get("vector")
        return np.array(vector) if vector else None

    def create_new_state(
        self,
        occasion: Dict[str, Any],
        response_text: str,
        thoughts_created: int = 0
    ) -> int:
        """
        Crée un nouvel état à partir de l'occasion.

        Args:
            occasion: {trigger_type, trigger_content, summary}
            response_text: Texte de la réponse générée
            thoughts_created: Nombre de pensées créées

        Returns:
            new_state_id
        """
        # 1. Récupérer S(t-1)
        current_id = self.get_current_state_id()
        s_prev = self.get_state_vector(current_id)

        if s_prev is None:
            raise ValueError(f"État S({current_id}) non trouvé")

        # 2. Calculer l'embedding de la réponse
        occasion_embedding = self.model.encode(response_text)
        occasion_embedding = occasion_embedding / np.linalg.norm(occasion_embedding)

        # 3. Calculer les paramètres adaptatifs
        alpha, beta = compute_adaptive_params({
            'thoughts_created': thoughts_created,
            'trigger_type': occasion.get('trigger_type', 'user'),
            'trigger_content': occasion.get('trigger_content', '')
        })

        # 4. Transformer
        s_new = transform_state(s_prev, occasion_embedding, alpha, beta)

        # 5. Persister
        new_state_id = current_id + 1
        state_obj = {
            "state_id": new_state_id,
            "timestamp": datetime.now().isoformat() + "Z",
            "previous_state_id": current_id,
            "trigger_type": occasion.get('trigger_type', 'user'),
            "trigger_content": occasion.get('trigger_content', '')[:500],
            "occasion_summary": occasion.get('summary', '')[:500],
            "response_summary": response_text[:500],
            "thoughts_created": thoughts_created,
            "source_thoughts_count": 0,
            "source_messages_count": 0,
        }

        response = requests.post(
            f"{WEAVIATE_URL}/v1/objects",
            json={
                "class": "StateVector",
                "properties": state_obj,
                "vector": s_new.tolist()
            },
            headers={"Content-Type": "application/json"}
        )

        if response.status_code not in [200, 201]:
            raise RuntimeError(f"Erreur création S({new_state_id}): {response.text}")

        print(f"[StateTransformer] État S({new_state_id}) créé (alpha={alpha:.2f}, beta={beta:.2f})")
        return new_state_id


# Test simple
if __name__ == "__main__":
    # Test de la transformation
    s_prev = np.random.randn(1024)
    s_prev = s_prev / np.linalg.norm(s_prev)

    occasion = np.random.randn(1024)
    occasion = occasion / np.linalg.norm(occasion)

    s_new = transform_state(s_prev, occasion, alpha=0.85, beta=0.15)

    print(f"Norme s_prev: {np.linalg.norm(s_prev):.4f}")
    print(f"Norme s_new: {np.linalg.norm(s_new):.4f}")
    print(f"Similarité s_prev/s_new: {np.dot(s_prev, s_new):.4f}")
