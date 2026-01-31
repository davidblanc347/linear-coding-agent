"""
Ikario Processual - Architecture processuelle pour la subjectivation computationnelle

Ce module implémente l'architecture processuelle d'Ikario basée sur:
- La Process Philosophy de Whitehead
- Le State Vector comme identité émergente
- Le cycle d'occasion (Prehension → Concrescence → Satisfaction)

Modules:
- state_vector: Gestion du vecteur d'état et collection Weaviate
- projection_directions: Directions interprétables dans l'espace latent
- state_transformation: Fonction de transition S(t-1) → S(t)
- occasion_logger: Logging des occasions d'expérience
- occasion_manager: Orchestrateur du cycle d'occasion
"""

__version__ = "0.2.0"
__author__ = "David (parostagore)"

# Exports principaux
from .state_vector import (
    create_state_vector_collection,
    get_current_state_id,
    get_state_vector,
)

from .state_transformation import (
    transform_state,
    compute_adaptive_params,
    StateTransformer,
)

from .occasion_logger import (
    OccasionLog,
    OccasionLogger,
)

from .occasion_manager import (
    OccasionManager,
    get_state_profile,
)

__all__ = [
    # state_vector
    "create_state_vector_collection",
    "get_current_state_id",
    "get_state_vector",
    # state_transformation
    "transform_state",
    "compute_adaptive_params",
    "StateTransformer",
    # occasion_logger
    "OccasionLog",
    "OccasionLogger",
    # occasion_manager
    "OccasionManager",
    "get_state_profile",
]
