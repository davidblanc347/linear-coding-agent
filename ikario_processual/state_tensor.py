#!/usr/bin/env python3
"""
StateTensor - Tenseur d'état 8×1024 d'Ikario v2.

Le tenseur d'état représente l'identité processuelle d'Ikario avec 8 dimensions :
- firstness    : Qualia, saillances, possibles (Peirce)
- secondness   : Chocs, tensions, irritations (Peirce)
- thirdness    : Habitudes, positions, valeurs (Peirce)
- dispositions : Tendances à agir
- orientations : Vers quoi je tends
- engagements  : Positions prises
- pertinences  : Ce qui compte pour moi
- valeurs      : Ce que je défends

Architecture: L'espace latent pense. Le LLM traduit.
"""

import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import numpy as np
import weaviate
import weaviate.classes.config as wvc
from weaviate.classes.query import Filter

# Configuration
WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://localhost:8080")
EMBEDDING_DIM = 1024  # BGE-M3


class TensorDimension(Enum):
    """Les 8 dimensions du tenseur d'état."""
    FIRSTNESS = "firstness"         # Qualia, saillances, possibles
    SECONDNESS = "secondness"       # Chocs, tensions, irritations
    THIRDNESS = "thirdness"         # Habitudes, positions, valeurs
    DISPOSITIONS = "dispositions"   # Tendances à agir
    ORIENTATIONS = "orientations"   # Vers quoi je tends
    ENGAGEMENTS = "engagements"     # Positions prises
    PERTINENCES = "pertinences"     # Ce qui compte pour moi
    VALEURS = "valeurs"             # Ce que je défends


DIMENSION_NAMES = [d.value for d in TensorDimension]


@dataclass
class StateTensor:
    """
    Tenseur d'état X_t ∈ ℝ^(8×1024).

    Chaque dimension est un vecteur BGE-M3 normalisé.
    """
    state_id: int
    timestamp: str

    # Les 8 dimensions (chacune ∈ ℝ^1024)
    firstness: np.ndarray = field(default_factory=lambda: np.zeros(EMBEDDING_DIM))
    secondness: np.ndarray = field(default_factory=lambda: np.zeros(EMBEDDING_DIM))
    thirdness: np.ndarray = field(default_factory=lambda: np.zeros(EMBEDDING_DIM))
    dispositions: np.ndarray = field(default_factory=lambda: np.zeros(EMBEDDING_DIM))
    orientations: np.ndarray = field(default_factory=lambda: np.zeros(EMBEDDING_DIM))
    engagements: np.ndarray = field(default_factory=lambda: np.zeros(EMBEDDING_DIM))
    pertinences: np.ndarray = field(default_factory=lambda: np.zeros(EMBEDDING_DIM))
    valeurs: np.ndarray = field(default_factory=lambda: np.zeros(EMBEDDING_DIM))

    # Métadonnées
    previous_state_id: int = -1
    trigger_type: str = ""
    trigger_content: str = ""
    embedding_model: str = "BAAI/bge-m3"  # Traçabilité (Amendement #13)

    def to_matrix(self) -> np.ndarray:
        """Retourne le tenseur complet (8, 1024)."""
        return np.stack([
            self.firstness,
            self.secondness,
            self.thirdness,
            self.dispositions,
            self.orientations,
            self.engagements,
            self.pertinences,
            self.valeurs
        ])

    def to_flat(self) -> np.ndarray:
        """Retourne le tenseur aplati (8192,)."""
        return self.to_matrix().flatten()

    def get_dimension(self, dim: TensorDimension) -> np.ndarray:
        """Récupère une dimension par enum."""
        return getattr(self, dim.value)

    def set_dimension(self, dim: TensorDimension, vector: np.ndarray) -> None:
        """Définit une dimension par enum."""
        if vector.shape != (EMBEDDING_DIM,):
            raise ValueError(f"Vector must be {EMBEDDING_DIM}-dim, got {vector.shape}")
        # Normaliser
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
        setattr(self, dim.value, vector)

    def copy(self) -> 'StateTensor':
        """Crée une copie profonde."""
        return StateTensor(
            state_id=self.state_id,
            timestamp=self.timestamp,
            firstness=self.firstness.copy(),
            secondness=self.secondness.copy(),
            thirdness=self.thirdness.copy(),
            dispositions=self.dispositions.copy(),
            orientations=self.orientations.copy(),
            engagements=self.engagements.copy(),
            pertinences=self.pertinences.copy(),
            valeurs=self.valeurs.copy(),
            previous_state_id=self.previous_state_id,
            trigger_type=self.trigger_type,
            trigger_content=self.trigger_content,
            embedding_model=self.embedding_model,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire pour stockage."""
        # S'assurer que le timestamp est au format RFC3339
        ts = self.timestamp
        if ts and not ts.endswith('Z') and '+' not in ts:
            ts = ts + 'Z'  # Ajouter le suffixe UTC si absent

        return {
            "state_id": self.state_id,
            "timestamp": ts,
            "previous_state_id": self.previous_state_id,
            "trigger_type": self.trigger_type,
            "trigger_content": self.trigger_content,
            "embedding_model": self.embedding_model,
        }

    def get_vectors_dict(self) -> Dict[str, List[float]]:
        """Retourne les 8 vecteurs comme dict pour Weaviate named vectors."""
        return {
            "firstness": self.firstness.tolist(),
            "secondness": self.secondness.tolist(),
            "thirdness": self.thirdness.tolist(),
            "dispositions": self.dispositions.tolist(),
            "orientations": self.orientations.tolist(),
            "engagements": self.engagements.tolist(),
            "pertinences": self.pertinences.tolist(),
            "valeurs": self.valeurs.tolist(),
        }

    @classmethod
    def from_dict(cls, props: Dict[str, Any], vectors: Dict[str, List[float]] = None) -> 'StateTensor':
        """Crée un StateTensor depuis un dictionnaire (Weaviate object)."""
        tensor = cls(
            state_id=props.get("state_id", 0),
            timestamp=props.get("timestamp", datetime.now().isoformat()),
            previous_state_id=props.get("previous_state_id", -1),
            trigger_type=props.get("trigger_type", ""),
            trigger_content=props.get("trigger_content", ""),
            embedding_model=props.get("embedding_model", "BAAI/bge-m3"),
        )

        if vectors:
            for dim_name in DIMENSION_NAMES:
                if dim_name in vectors:
                    setattr(tensor, dim_name, np.array(vectors[dim_name]))

        return tensor

    @classmethod
    def from_matrix(cls, matrix: np.ndarray, state_id: int, timestamp: str) -> 'StateTensor':
        """Crée un StateTensor depuis une matrice (8, 1024)."""
        if matrix.shape != (8, EMBEDDING_DIM):
            raise ValueError(f"Matrix must be (8, {EMBEDDING_DIM}), got {matrix.shape}")

        return cls(
            state_id=state_id,
            timestamp=timestamp,
            firstness=matrix[0],
            secondness=matrix[1],
            thirdness=matrix[2],
            dispositions=matrix[3],
            orientations=matrix[4],
            engagements=matrix[5],
            pertinences=matrix[6],
            valeurs=matrix[7],
        )

    @staticmethod
    def weighted_mean(tensors: List['StateTensor'], weights: np.ndarray) -> 'StateTensor':
        """Calcule la moyenne pondérée de plusieurs tenseurs."""
        if len(tensors) != len(weights):
            raise ValueError("Number of tensors must match number of weights")

        weights = np.array(weights) / np.sum(weights)  # Normaliser

        result = StateTensor(
            state_id=-1,  # À définir par l'appelant
            timestamp=datetime.now().isoformat(),
        )

        for dim_name in DIMENSION_NAMES:
            weighted_sum = np.zeros(EMBEDDING_DIM)
            for tensor, weight in zip(tensors, weights):
                weighted_sum += weight * getattr(tensor, dim_name)
            # Normaliser le résultat
            norm = np.linalg.norm(weighted_sum)
            if norm > 0:
                weighted_sum = weighted_sum / norm
            setattr(result, dim_name, weighted_sum)

        return result

    @staticmethod
    def blend(t1: 'StateTensor', t2: 'StateTensor', alpha: float = 0.5) -> 'StateTensor':
        """Mélange deux tenseurs : alpha * t1 + (1-alpha) * t2."""
        return StateTensor.weighted_mean([t1, t2], [alpha, 1 - alpha])


# ============================================================================
# WEAVIATE COLLECTION SCHEMA (API v4)
# ============================================================================

def create_state_tensor_collection(client: weaviate.WeaviateClient) -> bool:
    """
    Crée la collection StateTensor dans Weaviate avec 8 vecteurs nommés.

    Utilise l'API Weaviate v4 avec named vectors.

    Returns:
        True si créée, False si existait déjà
    """
    collection_name = "StateTensor"

    # Vérifier si existe déjà
    if collection_name in client.collections.list_all():
        print(f"[StateTensor] Collection existe déjà")
        return False

    # Créer la collection avec 8 vecteurs nommés
    client.collections.create(
        name=collection_name,
        description="Tenseur d'état 8×1024 - Identité processuelle d'Ikario v2",

        # 8 vecteurs nommés (Weaviate v4 API)
        vector_config={
            "firstness": wvc.Configure.NamedVectors.none(
                name="firstness",
                vector_index_config=wvc.Configure.VectorIndex.hnsw(
                    distance_metric=wvc.VectorDistances.COSINE
                ),
            ),
            "secondness": wvc.Configure.NamedVectors.none(
                name="secondness",
                vector_index_config=wvc.Configure.VectorIndex.hnsw(
                    distance_metric=wvc.VectorDistances.COSINE
                ),
            ),
            "thirdness": wvc.Configure.NamedVectors.none(
                name="thirdness",
                vector_index_config=wvc.Configure.VectorIndex.hnsw(
                    distance_metric=wvc.VectorDistances.COSINE
                ),
            ),
            "dispositions": wvc.Configure.NamedVectors.none(
                name="dispositions",
                vector_index_config=wvc.Configure.VectorIndex.hnsw(
                    distance_metric=wvc.VectorDistances.COSINE
                ),
            ),
            "orientations": wvc.Configure.NamedVectors.none(
                name="orientations",
                vector_index_config=wvc.Configure.VectorIndex.hnsw(
                    distance_metric=wvc.VectorDistances.COSINE
                ),
            ),
            "engagements": wvc.Configure.NamedVectors.none(
                name="engagements",
                vector_index_config=wvc.Configure.VectorIndex.hnsw(
                    distance_metric=wvc.VectorDistances.COSINE
                ),
            ),
            "pertinences": wvc.Configure.NamedVectors.none(
                name="pertinences",
                vector_index_config=wvc.Configure.VectorIndex.hnsw(
                    distance_metric=wvc.VectorDistances.COSINE
                ),
            ),
            "valeurs": wvc.Configure.NamedVectors.none(
                name="valeurs",
                vector_index_config=wvc.Configure.VectorIndex.hnsw(
                    distance_metric=wvc.VectorDistances.COSINE
                ),
            ),
        },

        # Propriétés (métadonnées)
        properties=[
            wvc.Property(
                name="state_id",
                data_type=wvc.DataType.INT,
                description="Numéro séquentiel de l'état (0, 1, 2...)",
            ),
            wvc.Property(
                name="timestamp",
                data_type=wvc.DataType.DATE,
                description="Moment de création de cet état",
            ),
            wvc.Property(
                name="previous_state_id",
                data_type=wvc.DataType.INT,
                description="ID de l'état précédent (-1 pour X_0)",
            ),
            wvc.Property(
                name="trigger_type",
                data_type=wvc.DataType.TEXT,
                skip_vectorization=True,
                description="Type: user, timer, event, initialization",
            ),
            wvc.Property(
                name="trigger_content",
                data_type=wvc.DataType.TEXT,
                skip_vectorization=True,
                description="Contenu du déclencheur",
            ),
            wvc.Property(
                name="embedding_model",
                data_type=wvc.DataType.TEXT,
                skip_vectorization=True,
                description="Modèle d'embedding utilisé (traçabilité)",
            ),
        ],
    )

    print(f"[StateTensor] Collection créée avec 8 vecteurs nommés")
    return True


def delete_state_tensor_collection(client: weaviate.WeaviateClient) -> bool:
    """Supprime la collection StateTensor (pour reset)."""
    try:
        client.collections.delete("StateTensor")
        print("[StateTensor] Collection supprimée")
        return True
    except Exception as e:
        print(f"[StateTensor] Erreur suppression: {e}")
        return False


# ============================================================================
# CRUD OPERATIONS
# ============================================================================

class StateTensorRepository:
    """
    Repository pour les opérations CRUD sur StateTensor.

    Utilise l'API Weaviate v4.
    """

    def __init__(self, client: weaviate.WeaviateClient):
        self.client = client
        self.collection = client.collections.get("StateTensor")

    def save(self, tensor: StateTensor) -> str:
        """
        Sauvegarde un StateTensor dans Weaviate.

        Returns:
            UUID de l'objet créé
        """
        result = self.collection.data.insert(
            properties=tensor.to_dict(),
            vector=tensor.get_vectors_dict(),
        )
        return str(result)

    def get_by_state_id(self, state_id: int) -> Optional[StateTensor]:
        """Récupère un tenseur par son state_id."""
        results = self.collection.query.fetch_objects(
            filters=Filter.by_property("state_id").equal(state_id),
            include_vector=True,
            limit=1,
        )

        if not results.objects:
            return None

        obj = results.objects[0]
        return StateTensor.from_dict(obj.properties, obj.vector)

    def get_current(self) -> Optional[StateTensor]:
        """Récupère l'état le plus récent (state_id max)."""
        from weaviate.classes.query import Sort

        results = self.collection.query.fetch_objects(
            sort=Sort.by_property("state_id", ascending=False),
            include_vector=True,
            limit=1,
        )

        if not results.objects:
            return None

        obj = results.objects[0]
        return StateTensor.from_dict(obj.properties, obj.vector)

    def get_current_state_id(self) -> int:
        """Retourne l'ID de l'état le plus récent (-1 si aucun)."""
        current = self.get_current()
        return current.state_id if current else -1

    def get_history(self, limit: int = 10) -> List[StateTensor]:
        """Récupère les N derniers états."""
        from weaviate.classes.query import Sort

        results = self.collection.query.fetch_objects(
            sort=Sort.by_property("state_id", ascending=False),
            include_vector=True,
            limit=limit,
        )

        return [
            StateTensor.from_dict(obj.properties, obj.vector)
            for obj in results.objects
        ]

    def count(self) -> int:
        """Compte le nombre total d'états."""
        result = self.collection.aggregate.over_all(total_count=True)
        return result.total_count


# ============================================================================
# IMPACT COLLECTION (pour Secondness)
# ============================================================================

def create_impact_collection(client: weaviate.WeaviateClient) -> bool:
    """
    Crée la collection Impact pour les événements de dissonance.

    Un Impact représente un "choc" (Secondness) - une tension non résolue
    qui demande à être intégrée.
    """
    collection_name = "Impact"

    if collection_name in client.collections.list_all():
        print(f"[Impact] Collection existe déjà")
        return False

    client.collections.create(
        name=collection_name,
        description="Événements de dissonance (chocs, tensions) - Secondness",

        # Vecteur unique pour l'impact
        vectorizer_config=wvc.Configure.Vectorizer.none(),
        vector_index_config=wvc.Configure.VectorIndex.hnsw(
            distance_metric=wvc.VectorDistances.COSINE
        ),

        properties=[
            wvc.Property(
                name="trigger_content",
                data_type=wvc.DataType.TEXT,
                description="Contenu déclencheur de l'impact",
            ),
            wvc.Property(
                name="trigger_type",
                data_type=wvc.DataType.TEXT,
                skip_vectorization=True,
                description="Type: user, corpus, veille, internal",
            ),
            wvc.Property(
                name="dissonance_score",
                data_type=wvc.DataType.NUMBER,
                description="Score de dissonance E() [0-1]",
            ),
            wvc.Property(
                name="state_id_at_impact",
                data_type=wvc.DataType.INT,
                description="state_id au moment de l'impact",
            ),
            wvc.Property(
                name="dimensions_affected",
                data_type=wvc.DataType.TEXT_ARRAY,
                skip_vectorization=True,
                description="Dimensions du tenseur affectées",
            ),
            wvc.Property(
                name="is_hard_negative",
                data_type=wvc.DataType.BOOL,
                description="True si contradiction détectée (NLI)",
            ),
            wvc.Property(
                name="resolved",
                data_type=wvc.DataType.BOOL,
                description="True si l'impact a été intégré",
            ),
            wvc.Property(
                name="resolution_state_id",
                data_type=wvc.DataType.INT,
                description="state_id où l'impact a été résolu",
            ),
            wvc.Property(
                name="timestamp",
                data_type=wvc.DataType.DATE,
                description="Moment de l'impact",
            ),
            wvc.Property(
                name="last_rumination",
                data_type=wvc.DataType.DATE,
                description="Dernière rumination (cooldown 24h - Amendement #9)",
            ),
        ],
    )

    print(f"[Impact] Collection créée")
    return True


# ============================================================================
# SETUP ALL COLLECTIONS
# ============================================================================

def create_all_processual_collections(client: weaviate.WeaviateClient) -> Dict[str, bool]:
    """
    Crée toutes les collections pour le système processuel v2.

    Returns:
        Dict avec le statut de chaque collection
    """
    print("=" * 60)
    print("Création des collections processuelles v2")
    print("=" * 60)

    results = {
        "StateTensor": create_state_tensor_collection(client),
        "Impact": create_impact_collection(client),
    }

    print("\n" + "=" * 60)
    print("Resume:")
    for name, created in results.items():
        status = "[OK] Creee" if created else "[WARN] Existait deja"
        print(f"  {name}: {status}")

    return results


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Gestion des collections StateTensor")
    parser.add_argument("--create", action="store_true", help="Créer les collections")
    parser.add_argument("--delete", action="store_true", help="Supprimer les collections")
    parser.add_argument("--status", action="store_true", help="Afficher le statut")

    args = parser.parse_args()

    # Connexion Weaviate
    client = weaviate.connect_to_local()

    try:
        if args.create:
            create_all_processual_collections(client)

        elif args.delete:
            delete_state_tensor_collection(client)
            try:
                client.collections.delete("Impact")
                print("[Impact] Collection supprimée")
            except Exception:
                pass

        elif args.status:
            collections = client.collections.list_all()
            print("Collections existantes:")
            for name in sorted(collections.keys()):
                if name in ["StateTensor", "Impact"]:
                    print(f"  [OK] {name}")

            if "StateTensor" in collections:
                repo = StateTensorRepository(client)
                print(f"\nStateTensor: {repo.count()} états")
                current = repo.get_current()
                if current:
                    print(f"  État actuel: X_{current.state_id} ({current.timestamp})")

        else:
            parser.print_help()

    finally:
        client.close()
