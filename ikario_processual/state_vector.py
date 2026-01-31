#!/usr/bin/env python3
"""
StateVector - Gestion du vecteur d'etat d'Ikario.

Le vecteur d'etat represente l'identite processuelle d'Ikario.
Il evolue a chaque occasion d'experience selon:
    S(t) = f(S(t-1), occasion)

Ce module gere:
- Le schema Weaviate pour StateVector
- La creation de S(0) a partir de l'historique
- Les operations CRUD sur les etats
"""

import os
from datetime import datetime
from typing import Any

import numpy as np
import requests

# Configuration
WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://localhost:8080")

# Schema de la collection StateVector
STATE_VECTOR_SCHEMA = {
    "class": "StateVector",
    "description": "Vecteurs d'etat - identite processuelle d'Ikario",
    "vectorizer": "none",  # Embedding BGE-M3 fourni manuellement
    "properties": [
        {
            "name": "state_id",
            "dataType": ["int"],
            "description": "Numero sequentiel de l'etat (0, 1, 2...)"
        },
        {
            "name": "timestamp",
            "dataType": ["date"],
            "description": "Moment de creation de cet etat"
        },
        {
            "name": "previous_state_id",
            "dataType": ["int"],
            "description": "ID de l'etat precedent (None pour S(0))"
        },
        {
            "name": "trigger_type",
            "dataType": ["text"],
            "description": "Type de declencheur: user, timer, event, initialization"
        },
        {
            "name": "trigger_content",
            "dataType": ["text"],
            "description": "Contenu du declencheur"
        },
        {
            "name": "occasion_summary",
            "dataType": ["text"],
            "description": "Resume de l'occasion"
        },
        {
            "name": "response_summary",
            "dataType": ["text"],
            "description": "Resume de la reponse"
        },
        {
            "name": "thoughts_created",
            "dataType": ["int"],
            "description": "Nombre de pensees generees lors de cette occasion"
        },
        {
            "name": "source_thoughts_count",
            "dataType": ["int"],
            "description": "Nombre de pensees utilisees pour construire cet etat (S(0))"
        },
        {
            "name": "source_messages_count",
            "dataType": ["int"],
            "description": "Nombre de messages utilises pour construire cet etat (S(0))"
        },
    ],
    "vectorIndexConfig": {
        "distance": "cosine"
    }
}


def check_weaviate_ready() -> bool:
    """Verifie que Weaviate est accessible."""
    try:
        response = requests.get(f"{WEAVIATE_URL}/v1/.well-known/ready", timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False


def get_existing_classes() -> list[str]:
    """Recupere la liste des classes existantes."""
    response = requests.get(f"{WEAVIATE_URL}/v1/schema")
    response.raise_for_status()
    schema = response.json()
    return [c["class"] for c in schema.get("classes", [])]


def create_state_vector_collection() -> bool:
    """
    Cree la collection StateVector dans Weaviate.

    Returns:
        True si creee, False si existait deja
    """
    existing = get_existing_classes()

    if "StateVector" in existing:
        print("[StateVector] Collection existe deja")
        return False

    response = requests.post(
        f"{WEAVIATE_URL}/v1/schema",
        json=STATE_VECTOR_SCHEMA,
        headers={"Content-Type": "application/json"}
    )

    if response.status_code == 200:
        print("[StateVector] Collection creee avec succes")
        return True
    else:
        print(f"[StateVector] Erreur creation: {response.status_code}")
        print(response.text)
        return False


def delete_state_vector_collection() -> bool:
    """Supprime la collection StateVector (pour reset)."""
    response = requests.delete(f"{WEAVIATE_URL}/v1/schema/StateVector")
    return response.status_code == 200


def get_all_thoughts() -> list[dict]:
    """Recupere toutes les pensees de Weaviate."""
    objects = []
    limit = 100
    offset = 0

    while True:
        url = f"{WEAVIATE_URL}/v1/objects?class=Thought&limit={limit}&offset={offset}"
        response = requests.get(url)

        if response.status_code != 200:
            break

        batch = response.json().get("objects", [])
        if not batch:
            break

        objects.extend(batch)
        offset += limit

    return objects


def get_all_messages() -> list[dict]:
    """Recupere tous les messages de Weaviate."""
    objects = []
    limit = 100
    offset = 0

    while True:
        url = f"{WEAVIATE_URL}/v1/objects?class=Message&limit={limit}&offset={offset}"
        response = requests.get(url)

        if response.status_code != 200:
            break

        batch = response.json().get("objects", [])
        if not batch:
            break

        objects.extend(batch)
        offset += limit

    return objects


def filter_thoughts(thoughts: list[dict]) -> list[dict]:
    """
    Filtre les pensees en enlevant celles liees aux tests.

    Criteres d'exclusion:
    - Contenu contenant "test", "debug", "TODO"
    - Pensees tres courtes (< 20 caracteres)
    - Pensees de type "test" ou "debug"
    """
    filtered = []

    # Mots-cles a exclure
    exclude_keywords = [
        "test", "debug", "todo", "fixme", "xxx",
        "lorem ipsum", "example", "placeholder"
    ]

    for thought in thoughts:
        props = thought.get("properties", {})
        content = props.get("content", "").lower()
        thought_type = props.get("thought_type", "").lower()

        # Exclure les pensees de test
        if thought_type in ["test", "debug", "example"]:
            continue

        # Exclure les pensees trop courtes
        if len(content) < 20:
            continue

        # Exclure si contient des mots-cles de test
        if any(kw in content for kw in exclude_keywords):
            continue

        filtered.append(thought)

    return filtered


def filter_assistant_messages(messages: list[dict]) -> list[dict]:
    """
    Filtre pour ne garder que les messages d'Ikario (assistant).

    Criteres:
    - role = "assistant"
    - Contenu non vide et significatif (> 50 caracteres)
    """
    filtered = []

    for msg in messages:
        props = msg.get("properties", {})
        role = props.get("role", "").lower()
        content = props.get("content", "")

        # Ne garder que les messages assistant
        if role != "assistant":
            continue

        # Exclure les messages trop courts
        if len(content) < 50:
            continue

        # Exclure les messages d'erreur ou systeme
        if content.startswith("[Error") or content.startswith("[System"):
            continue

        filtered.append(msg)

    return filtered


def compute_aggregate_embedding(
    thoughts: list[dict],
    messages: list[dict],
    model
) -> np.ndarray:
    """
    Calcule l'embedding agrege a partir des pensees et messages.

    Strategie:
    1. Extraire le contenu textuel de chaque element
    2. Calculer l'embedding de chaque texte
    3. Faire la moyenne ponderee (pensees ont plus de poids)
    4. Normaliser le vecteur final

    Args:
        thoughts: Liste des pensees filtrees
        messages: Liste des messages filtres
        model: Modele SentenceTransformer

    Returns:
        Vecteur normalise 1024-dim
    """
    embeddings = []
    weights = []

    # Traiter les pensees (poids = 2.0 car plus significatives)
    print(f"  Traitement de {len(thoughts)} pensees...")
    for thought in thoughts:
        content = thought.get("properties", {}).get("content", "")
        if content:
            emb = model.encode(content)
            embeddings.append(emb)
            weights.append(2.0)  # Poids double pour les pensees

    # Traiter les messages (poids = 1.0)
    print(f"  Traitement de {len(messages)} messages...")
    for msg in messages:
        content = msg.get("properties", {}).get("content", "")
        if content:
            # Tronquer les messages tres longs
            if len(content) > 2000:
                content = content[:2000]
            emb = model.encode(content)
            embeddings.append(emb)
            weights.append(1.0)

    if not embeddings:
        raise ValueError("Aucun contenu a encoder!")

    # Convertir en arrays numpy
    embeddings = np.array(embeddings)
    weights = np.array(weights)

    # Moyenne ponderee
    weights = weights / weights.sum()  # Normaliser les poids
    aggregate = np.average(embeddings, axis=0, weights=weights)

    # Normaliser le vecteur final
    aggregate = aggregate / np.linalg.norm(aggregate)

    return aggregate


def create_initial_state(
    thoughts: list[dict],
    messages: list[dict],
    embedding: np.ndarray
) -> dict:
    """
    Cree l'etat initial S(0) dans Weaviate.

    Args:
        thoughts: Pensees utilisees pour construire S(0)
        messages: Messages utilises pour construire S(0)
        embedding: Vecteur d'etat calcule

    Returns:
        Objet S(0) cree
    """
    s0_data = {
        "state_id": 0,
        "timestamp": datetime.now().isoformat() + "Z",
        "previous_state_id": -1,  # Pas d'etat precedent
        "trigger_type": "initialization",
        "trigger_content": "Creation de l'etat initial a partir de l'historique",
        "occasion_summary": f"Naissance processuelle d'Ikario - agregation de {len(thoughts)} pensees et {len(messages)} messages",
        "response_summary": "Etat initial S(0) cree avec succes",
        "thoughts_created": 0,
        "source_thoughts_count": len(thoughts),
        "source_messages_count": len(messages),
    }

    # Creer l'objet avec le vecteur
    response = requests.post(
        f"{WEAVIATE_URL}/v1/objects",
        json={
            "class": "StateVector",
            "properties": s0_data,
            "vector": embedding.tolist()
        },
        headers={"Content-Type": "application/json"}
    )

    if response.status_code in [200, 201]:
        result = response.json()
        s0_data["id"] = result.get("id")
        print(f"[StateVector] S(0) cree avec ID: {s0_data['id']}")
        return s0_data
    else:
        print(f"[StateVector] Erreur creation S(0): {response.status_code}")
        print(response.text)
        raise RuntimeError("Impossible de creer S(0)")


def get_current_state_id() -> int:
    """Retourne l'ID de l'etat le plus recent."""
    # Recuperer tous les StateVector et trouver le max state_id
    url = f"{WEAVIATE_URL}/v1/objects?class=StateVector&limit=100"
    response = requests.get(url)

    if response.status_code != 200:
        return -1

    objects = response.json().get("objects", [])
    if not objects:
        return -1

    max_id = max(obj.get("properties", {}).get("state_id", -1) for obj in objects)
    return max_id


def get_state_vector(state_id: int) -> dict | None:
    """
    Recupere un etat par son state_id.

    Args:
        state_id: Numero de l'etat

    Returns:
        Objet StateVector ou None
    """
    # GraphQL query pour recuperer par state_id
    query = {
        "query": """
        {
            Get {
                StateVector(where: {
                    path: ["state_id"],
                    operator: Equal,
                    valueInt: %d
                }) {
                    state_id
                    timestamp
                    previous_state_id
                    trigger_type
                    trigger_content
                    occasion_summary
                    response_summary
                    thoughts_created
                    source_thoughts_count
                    source_messages_count
                    _additional {
                        id
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

    return states[0] if states else None
