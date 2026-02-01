"""
Ikario Processual - Architecture processuelle pour la subjectivation computationnelle

Ce module implémente l'architecture processuelle d'Ikario basée sur:
- La Process Philosophy de Whitehead
- La Sémiotique de Peirce (Firstness, Secondness, Thirdness)
- Le StateTensor 8×1024 comme identité émergente
- Le cycle sémiotique (Firstness → Secondness → Thirdness → Sémiose)

Architecture v2 : "L'espace latent pense. Le LLM traduit."

Modules v1 (legacy):
- state_vector: Vecteur d'état unique 1024-dim
- projection_directions: Directions interprétables
- state_transformation: Transition S(t-1) → S(t)
- occasion_logger: Logging des occasions
- occasion_manager: Orchestrateur du cycle

Modules v2 (nouveau):
- state_tensor: Tenseur d'état 8×1024 (8 dimensions Peirce)
- dissonance: Fonction E() avec hard negatives
- contradiction_detector: Détection NLI (optionnel)
- fixation: 4 méthodes de Peirce (Tenacity, Authority, A Priori, Science)
- latent_engine: Orchestrateur du cycle sémiotique
- state_to_language: Traduction vecteur→texte (LLM zero-reasoning)
- vigilance: Système x_ref (David) comme garde-fou
- daemon: Boucle autonome avec modes CONVERSATION et AUTONOMOUS
- metrics: Métriques de suivi et rapports quotidiens
"""

__version__ = "0.7.0"
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

# === V2 MODULES ===
from .state_tensor import (
    StateTensor,
    TensorDimension,
    DIMENSION_NAMES,
    StateTensorRepository,
    create_state_tensor_collection,
    create_impact_collection,
)

from .dissonance import (
    DissonanceConfig,
    DissonanceResult,
    compute_dissonance,
    compute_dissonance_enhanced,
    compute_self_dissonance,
    Impact,
    ImpactRepository,
    create_impact_from_dissonance,
)

from .fixation import (
    FixationConfig,
    FixationResult,
    Tenacity,
    Authority,
    APriori,
    Science,
    compute_delta,
    apply_delta,
    apply_delta_all_dimensions,
    PACTE_ARTICLES,
    CRITICAL_ARTICLES,
    PHILOSOPHICAL_ANCHORS,
)

from .latent_engine import (
    Thought,
    CycleResult,
    CycleLogger,
    LatentEngine,
    create_engine,
)

# === V2 Phase 5 ===
from .state_to_language import (
    ProjectionDirection,
    TranslationResult,
    StateToLanguage,
    REASONING_MARKERS,
    CATEGORY_TO_DIMENSION,
    create_directions_from_weaviate,
    create_directions_from_config,
    create_translator,
)

# === V2 Phase 6 ===
from .vigilance import (
    VigilanceAlert,
    VigilanceConfig,
    VigilanceSystem,
    DavidReference,
    VigilanceVisualizer,
    create_vigilance_system,
)

# === V2 Phase 7 ===
from .daemon import (
    TriggerType,
    DaemonMode,
    DaemonConfig,
    DaemonStats,
    Trigger,
    VerbalizationEvent,
    TriggerGenerator,
    IkarioDaemon,
    create_daemon,
)

# === V2 Phase 8 ===
from .metrics import (
    MetricPeriod,
    StateEvolutionMetrics,
    CycleMetrics,
    VerbalizationMetrics,
    ImpactMetrics,
    AlertMetrics,
    DailyReport,
    ProcessMetrics,
    create_metrics,
)

__all__ = [
    # === V1 (legacy) ===
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
    # === V2 (nouveau) ===
    # state_tensor
    "StateTensor",
    "TensorDimension",
    "DIMENSION_NAMES",
    "StateTensorRepository",
    "create_state_tensor_collection",
    "create_impact_collection",
    # dissonance
    "DissonanceConfig",
    "DissonanceResult",
    "compute_dissonance",
    "compute_dissonance_enhanced",
    "compute_self_dissonance",
    "Impact",
    "ImpactRepository",
    "create_impact_from_dissonance",
    # fixation
    "FixationConfig",
    "FixationResult",
    "Tenacity",
    "Authority",
    "APriori",
    "Science",
    "compute_delta",
    "apply_delta",
    "apply_delta_all_dimensions",
    "PACTE_ARTICLES",
    "CRITICAL_ARTICLES",
    "PHILOSOPHICAL_ANCHORS",
    # latent_engine
    "Thought",
    "CycleResult",
    "CycleLogger",
    "LatentEngine",
    "create_engine",
    # state_to_language (Phase 5)
    "ProjectionDirection",
    "TranslationResult",
    "StateToLanguage",
    "REASONING_MARKERS",
    "CATEGORY_TO_DIMENSION",
    "create_directions_from_weaviate",
    "create_directions_from_config",
    "create_translator",
    # vigilance (Phase 6)
    "VigilanceAlert",
    "VigilanceConfig",
    "VigilanceSystem",
    "DavidReference",
    "VigilanceVisualizer",
    "create_vigilance_system",
    # daemon (Phase 7)
    "TriggerType",
    "DaemonMode",
    "DaemonConfig",
    "DaemonStats",
    "Trigger",
    "VerbalizationEvent",
    "TriggerGenerator",
    "IkarioDaemon",
    "create_daemon",
    # metrics (Phase 8)
    "MetricPeriod",
    "StateEvolutionMetrics",
    "CycleMetrics",
    "VerbalizationMetrics",
    "ImpactMetrics",
    "AlertMetrics",
    "DailyReport",
    "ProcessMetrics",
    "create_metrics",
]
