#!/usr/bin/env python3
"""
Ikario API - Point d'entrée FastAPI pour l'architecture v2.

Expose le LatentEngine via une API REST simple.

Démarrer:
    uvicorn ikario_processual.api:app --reload --port 8100

Endpoints:
    GET  /health          - Statut du service
    POST /cycle           - Exécuter un cycle sémiotique
    POST /translate       - Traduire l'état en langage
    GET  /state           - État actuel
    GET  /vigilance       - Vérifier la dérive
    GET  /metrics         - Métriques du système
    GET  /profile         - Profil processuel (109 directions)
"""

import asyncio
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager

import numpy as np
import requests
from dotenv import load_dotenv

# Load env
load_dotenv()

# FastAPI
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Ikario modules
from .state_tensor import StateTensor, DIMENSION_NAMES, EMBEDDING_DIM
from .dissonance import compute_dissonance, DissonanceResult
from .fixation import Authority, compute_delta, apply_delta
from .vigilance import VigilanceSystem, VigilanceConfig, create_vigilance_system
from .state_to_language import StateToLanguage, ProjectionDirection, CATEGORY_TO_DIMENSION
from .daemon import TriggerType, DaemonConfig
from .metrics import ProcessMetrics, create_metrics
from .projection_directions import get_all_directions


# =============================================================================
# GLOBALS (chargés au démarrage)
# =============================================================================

_embedding_model = None
_current_state: Optional[StateTensor] = None
_initial_state: Optional[StateTensor] = None
_x_ref: Optional[StateTensor] = None  # David reference
_vigilance: Optional[VigilanceSystem] = None
_translator: Optional[StateToLanguage] = None
_metrics: Optional[ProcessMetrics] = None
_authority: Optional[Authority] = None
_startup_time: Optional[datetime] = None
_directions: List[Dict] = []  # 109 directions from Weaviate

# Daemon state tracking
_daemon_mode: str = "idle"  # idle, conversation, autonomous
_is_ruminating: bool = False
_last_trigger_type: Optional[str] = None
_last_trigger_time: Optional[datetime] = None
_cycles_by_type: Dict[str, int] = {
    "user": 0,
    "veille": 0,
    "corpus": 0,
    "rumination_free": 0,
}

# Autonomous daemon task
_daemon_running: bool = False
_daemon_task: Optional[Any] = None  # asyncio.Task
_daemon_config = {
    "cycle_interval_seconds": 864,  # ~100 cycles/day (86400s / 100)
    "prob_rumination_free": 0.5,     # 50% rumination libre
    "prob_corpus": 0.3,              # 30% corpus
    "prob_unresolved": 0.2,          # 20% impacts non résolus
}


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class CycleRequest(BaseModel):
    """Requête pour un cycle sémiotique."""
    content: str
    trigger_type: str = "user"  # user, veille, corpus, rumination_free
    metadata: Dict[str, Any] = {}


class CycleResponse(BaseModel):
    """Réponse d'un cycle."""
    state_id: int
    delta_magnitude: float
    dissonance_total: float
    is_choc: bool
    dimensions_affected: List[str]
    processing_time_ms: float


class TranslateRequest(BaseModel):
    """Requête de traduction."""
    context: Optional[str] = None
    max_length: int = 500


class TranslateResponse(BaseModel):
    """Réponse de traduction."""
    text: str
    projections: Dict[str, float]
    reasoning_detected: bool


class StateResponse(BaseModel):
    """État actuel."""
    state_id: int
    timestamp: str
    dimensions: Dict[str, List[float]]


class VigilanceResponse(BaseModel):
    """Réponse vigilance."""
    level: str  # ok, warning, critical
    cumulative_drift: float
    top_drifting_dimensions: List[str]
    message: Optional[str] = None


class MetricsResponse(BaseModel):
    """Métriques."""
    status: str
    uptime_hours: float
    total_cycles: int
    cycles_last_hour: int
    alerts: Dict[str, int]


class HealthResponse(BaseModel):
    """Statut de santé."""
    status: str
    version: str
    uptime_seconds: float
    state_id: int
    embedding_model: str


class ProfileResponse(BaseModel):
    """Profil processuel (format compatible frontend)."""
    state_id: int
    directions_count: int
    profile: Dict[str, Dict[str, Any]]
    david_profile: Dict[str, Dict[str, Any]]
    david_similarity: float


class DaemonStatusResponse(BaseModel):
    """Statut du daemon (sémiose interne)."""
    mode: str  # idle, conversation, autonomous
    is_ruminating: bool
    daemon_running: bool = False
    last_trigger: Optional[Dict[str, Any]] = None
    cycles_breakdown: Dict[str, int]
    cycles_since_last_user: int
    time_since_last_user_seconds: Optional[float] = None


# =============================================================================
# INITIALIZATION
# =============================================================================

def load_embedding_model():
    """Charge le modèle d'embedding."""
    global _embedding_model

    if _embedding_model is not None:
        return _embedding_model

    try:
        from sentence_transformers import SentenceTransformer
        model_name = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
        print(f"[API] Loading embedding model: {model_name}")
        _embedding_model = SentenceTransformer(model_name)
        print(f"[API] Model loaded successfully")
        return _embedding_model
    except Exception as e:
        print(f"[API] Failed to load embedding model: {e}")
        raise


def _fetch_ikario_state_from_weaviate() -> Optional[StateTensor]:
    """
    Récupère l'état d'Ikario depuis Weaviate (thoughts + messages).

    Stratégie:
    1. Récupère le StateVector v1 existant (agrégat de thoughts/messages)
    2. Récupère les thoughts par catégorie pour enrichir les dimensions
    3. Construit un StateTensor 8×1024
    """
    WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://localhost:8080")

    try:
        # 1. Récupérer le StateVector v1 le plus récent
        state_query = {
            "query": """{
                Get {
                    StateVector(
                        sort: [{ path: ["state_id"], order: desc }]
                        limit: 1
                    ) {
                        state_id
                        timestamp
                        _additional { vector }
                    }
                }
            }"""
        }

        response = requests.post(
            f"{WEAVIATE_URL}/v1/graphql",
            json=state_query,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )

        if response.status_code != 200:
            print(f"[API] Weaviate StateVector query failed: {response.status_code}")
            return None

        data = response.json()
        states = data.get("data", {}).get("Get", {}).get("StateVector", [])

        if not states:
            print("[API] No StateVector found in Weaviate")
            return None

        state_v1 = states[0]
        base_vector = np.array(state_v1.get("_additional", {}).get("vector", []))

        if len(base_vector) != EMBEDDING_DIM:
            print(f"[API] Invalid StateVector dimension: {len(base_vector)}")
            return None

        print(f"[API] Loaded StateVector v1 (state_id={state_v1.get('state_id')})")

        # 2. Récupérer les thoughts par catégorie pour enrichir les dimensions
        thoughts_query = {
            "query": """{
                Get {
                    Thought(limit: 500) {
                        content
                        thought_type
                        evolution_stage
                        _additional { vector }
                    }
                }
            }"""
        }

        thoughts_response = requests.post(
            f"{WEAVIATE_URL}/v1/graphql",
            json=thoughts_query,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )

        thoughts = []
        if thoughts_response.status_code == 200:
            thoughts_data = thoughts_response.json()
            thoughts = thoughts_data.get("data", {}).get("Get", {}).get("Thought", [])
            print(f"[API] Loaded {len(thoughts)} thoughts from Weaviate")

        # 3. Construire le StateTensor avec les thoughts catégorisés
        tensor = StateTensor(
            state_id=state_v1.get("state_id", 0),
            timestamp=state_v1.get("timestamp", datetime.now().isoformat()),
        )

        # Mapping thought_type -> dimension
        TYPE_TO_DIMENSION = {
            "reflection": "firstness",      # Qualités immédiates
            "question": "secondness",       # Réactions, résistances
            "insight": "thirdness",         # Médiations, lois
            "emotion": "dispositions",      # États émotionnels
            "intention": "orientations",    # Intentions, buts
            "dialogue": "engagements",      # Relations, contexte
            "observation": "pertinences",   # Saillances, focus
            "principle": "valeurs",         # Principes éthiques
        }

        # Agréger les vecteurs par dimension
        dim_vectors = {dim: [] for dim in DIMENSION_NAMES}

        for thought in thoughts:
            thought_vec = thought.get("_additional", {}).get("vector", [])
            if len(thought_vec) != EMBEDDING_DIM:
                continue

            thought_type = thought.get("thought_type", "reflection")
            target_dim = TYPE_TO_DIMENSION.get(thought_type, "thirdness")
            dim_vectors[target_dim].append(np.array(thought_vec))

        # Construire chaque dimension
        for dim_name in DIMENSION_NAMES:
            vectors = dim_vectors[dim_name]

            if vectors:
                # Moyenne des thoughts de cette catégorie
                avg_vec = np.mean(vectors, axis=0)
                # Mélanger avec le vecteur de base (70% base, 30% thoughts)
                combined = 0.7 * base_vector + 0.3 * avg_vec
            else:
                # Pas de thoughts pour cette dimension, utiliser le vecteur de base
                # avec une légère perturbation pour différencier
                noise = np.random.randn(EMBEDDING_DIM) * 0.05
                combined = base_vector + noise

            # Normaliser
            combined = combined / np.linalg.norm(combined)
            setattr(tensor, dim_name, combined)

        return tensor

    except Exception as e:
        print(f"[API] Error fetching state from Weaviate: {e}")
        return None


def _fetch_david_from_messages() -> Optional[np.ndarray]:
    """
    Récupère le vecteur David depuis ses messages dans les conversations.

    Utilise SQLite pour récupérer les messages utilisateur récents,
    puis les embed avec le modèle BGE-M3.
    """
    import sqlite3

    # Trouver la base de données SQLite (claude-clone.db contient les messages)
    db_paths = [
        Path(__file__).parent.parent / "generations" / "ikario" / "server" / "data" / "claude-clone.db",
        Path("C:/Users/david/SynologyDrive/Linear_coding_ikario/generations/ikario/server/data/claude-clone.db"),
    ]

    db_path = None
    for p in db_paths:
        if p.exists():
            db_path = p
            break

    if not db_path:
        print("[API] SQLite database not found")
        return None

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Récupérer les messages utilisateur récents (excluant les tests)
        cursor.execute("""
            SELECT m.content
            FROM messages m
            JOIN conversations c ON m.conversation_id = c.id
            WHERE m.role = 'user'
              AND c.is_deleted = 0
              AND LENGTH(m.content) > 20
              AND LOWER(c.title) NOT LIKE '%test%'
              AND LOWER(m.content) NOT LIKE '%test%'
            ORDER BY m.created_at DESC
            LIMIT 100
        """)

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            print("[API] No user messages found in database")
            return None

        print(f"[API] Found {len(rows)} user messages for David")

        # Concaténer les messages (max ~8000 chars)
        concatenated = ""
        for (content,) in rows:
            if len(concatenated) + len(content) > 8000:
                break
            concatenated += content + "\n\n"

        # Embed avec le modèle
        if _embedding_model is None:
            print("[API] Embedding model not loaded")
            return None

        david_vector = _embedding_model.encode([concatenated])[0]
        david_vector = david_vector / np.linalg.norm(david_vector)

        print(f"[API] David vector computed from messages (dim={len(david_vector)})")
        return david_vector

    except Exception as e:
        print(f"[API] Error fetching David messages: {e}")
        return None


def _create_david_tensor(base_vector: np.ndarray, declared_profile: dict) -> StateTensor:
    """
    Crée le StateTensor de David à partir de son vecteur de messages
    et le complète avec son profil déclaré.

    Args:
        base_vector: Vecteur 1024-dim depuis les messages
        declared_profile: Dict des valeurs déclarées par catégorie
    """
    tensor = StateTensor(
        state_id=-1,  # x_ref a toujours state_id = -1
        timestamp=datetime.now().isoformat(),
    )

    # Mapping catégorie déclarée -> dimension StateTensor
    CATEGORY_TO_DIM = {
        'epistemic': 'firstness',
        'affective': 'dispositions',
        'cognitive': 'thirdness',
        'relational': 'engagements',
        'ethical': 'valeurs',
        'temporal': 'orientations',
        'thematic': 'pertinences',
        'metacognitive': 'secondness',
        'vital': 'dispositions',
        'ecosystemic': 'engagements',
        'philosophical': 'thirdness',
    }

    # Initialiser toutes les dimensions avec le vecteur de base
    for dim_name in DIMENSION_NAMES:
        setattr(tensor, dim_name, base_vector.copy())

    # Si on a les directions chargées, ajuster avec le profil déclaré
    if _directions and declared_profile:
        # Construire un map direction_name -> vector
        direction_map = {}
        for d in _directions:
            name = d.get("name")
            vec = d.get("_additional", {}).get("vector", [])
            category = d.get("category", "unknown")
            if name and len(vec) == EMBEDDING_DIM:
                direction_map[name] = {
                    "vector": np.array(vec),
                    "category": category,
                }

        # Ajuster chaque dimension en fonction des valeurs déclarées
        for category, directions_values in declared_profile.items():
            target_dim = CATEGORY_TO_DIM.get(category, "thirdness")
            current_vec = getattr(tensor, target_dim).copy()

            for name, declared_value in directions_values.items():
                if declared_value is None or name not in direction_map:
                    continue

                dir_info = direction_map[name]
                dir_vec = dir_info["vector"]

                # Valeur déclarée: -10 à +10, convertir en -0.167 à +0.167
                declared_scaled = declared_value / 60.0

                # Projection actuelle
                current_proj = float(np.dot(current_vec, dir_vec))

                # Delta à appliquer
                delta = declared_scaled - current_proj

                # Ajuster le vecteur (facteur 0.5 pour ne pas trop modifier)
                current_vec = current_vec + delta * dir_vec * 0.5

            # Normaliser et stocker
            current_vec = current_vec / np.linalg.norm(current_vec)
            setattr(tensor, target_dim, current_vec)

    return tensor


def initialize_state():
    """
    Initialise l'état d'Ikario et la référence David.

    Ikario: Calculé depuis Weaviate (thoughts + messages)
    David (x_ref): Messages utilisateur + profil déclaré
    """
    global _current_state, _initial_state, _x_ref, _vigilance, _metrics

    # 1. Charger le profil déclaré de David (pour compléter)
    profile_path = Path(__file__).parent / "david_profile_declared.json"
    declared_profile = None

    if profile_path.exists():
        import json
        with open(profile_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            declared_profile = data.get("profile", {})
        print(f"[API] Loaded David declared profile ({len(declared_profile)} categories)")

    # 2. Créer x_ref (David) depuis ses messages + profil déclaré
    david_vector = _fetch_david_from_messages()

    if david_vector is not None:
        _x_ref = _create_david_tensor(david_vector, declared_profile)
        print("[API] David tensor created from messages + declared profile")
    elif declared_profile:
        # Fallback: utiliser uniquement le profil déclaré
        print("[API] Falling back to declared profile only for David")
        from .vigilance import DavidReference
        _x_ref = DavidReference.create_from_declared_profile(str(profile_path))
    else:
        print("[API] No David profile available, x_ref will be set later")
        _x_ref = None

    # 2. Charger l'état d'Ikario depuis Weaviate (thoughts + messages)
    ikario_state = _fetch_ikario_state_from_weaviate()

    if ikario_state is not None:
        print(f"[API] Ikario state loaded from Weaviate: S({ikario_state.state_id})")
        _initial_state = ikario_state
        _current_state = ikario_state.copy()
    else:
        # Fallback: créer un état aléatoire
        print("[API] Creating random initial state (no Weaviate data)")
        _initial_state = StateTensor(
            state_id=0,
            timestamp=datetime.now().isoformat(),
        )
        for dim_name in DIMENSION_NAMES:
            v = np.random.randn(EMBEDDING_DIM)
            v = v / np.linalg.norm(v)
            setattr(_initial_state, dim_name, v)
        _current_state = _initial_state.copy()

    # 3. Si pas de x_ref, utiliser l'état initial comme référence
    if _x_ref is None:
        _x_ref = _initial_state.copy()
        _x_ref.state_id = -1

    # 4. Créer le système de vigilance
    _vigilance = VigilanceSystem(x_ref=_x_ref)

    # 5. Créer les métriques
    _metrics = create_metrics(S_0=_initial_state, x_ref=_vigilance.x_ref)

    print(f"[API] State initialized: Ikario=S({_current_state.state_id}), David=x_ref")


def initialize_directions():
    """Charge les 109 directions depuis Weaviate."""
    global _directions

    try:
        _directions = get_all_directions()
        print(f"[API] Loaded {len(_directions)} directions from Weaviate")
    except Exception as e:
        print(f"[API] Failed to load directions: {e}")
        _directions = []


def initialize_authority():
    """Initialise l'Authority avec les vecteurs du Pacte."""
    global _authority

    # Pour l'instant, créer une Authority minimale
    # TODO: Charger les vrais vecteurs du Pacte depuis Weaviate
    _authority = Authority()
    print("[API] Authority initialized (minimal)")


def initialize_translator():
    """Initialise le traducteur StateToLanguage."""
    global _translator

    # Créer un traducteur minimal sans directions pour l'instant
    # TODO: Charger les directions depuis Weaviate
    try:
        import anthropic
        client = anthropic.Anthropic()
        _translator = StateToLanguage(
            directions=[],
            anthropic_client=client,
        )
        print("[API] Translator initialized with Anthropic client")
    except Exception as e:
        print(f"[API] Translator initialization failed: {e}")
        _translator = StateToLanguage(directions=[])


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager pour FastAPI."""
    global _startup_time

    print("[API] Starting Ikario API...")
    _startup_time = datetime.now()

    # Charger les composants
    load_embedding_model()
    initialize_state()
    initialize_authority()
    initialize_translator()
    initialize_directions()

    print("[API] Ikario API ready")

    yield

    print("[API] Shutting down Ikario API")


# =============================================================================
# APP
# =============================================================================

app = FastAPI(
    title="Ikario API",
    description="API pour l'architecture processuelle v2",
    version="0.7.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# ENDPOINTS
# =============================================================================

@app.get("/health", response_model=HealthResponse)
async def health():
    """Vérifier que l'API est opérationnelle."""
    uptime = (datetime.now() - _startup_time).total_seconds() if _startup_time else 0

    return HealthResponse(
        status="ok",
        version="0.7.0",
        uptime_seconds=uptime,
        state_id=_current_state.state_id if _current_state else -1,
        embedding_model=os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3"),
    )


@app.post("/cycle", response_model=CycleResponse)
async def run_cycle(request: CycleRequest):
    """
    Exécuter un cycle sémiotique complet.

    1. Vectoriser l'entrée
    2. Calculer la dissonance
    3. Appliquer la fixation
    4. Mettre à jour l'état
    """
    global _current_state, _daemon_mode, _is_ruminating, _last_trigger_type, _last_trigger_time, _cycles_by_type

    start_time = time.time()

    # Track daemon state
    _last_trigger_type = request.trigger_type
    _last_trigger_time = datetime.now()
    if request.trigger_type in _cycles_by_type:
        _cycles_by_type[request.trigger_type] += 1

    # Update daemon mode based on trigger type
    if request.trigger_type == "user":
        _daemon_mode = "conversation"
        _is_ruminating = False
    elif request.trigger_type in ("rumination_free", "corpus"):
        _daemon_mode = "autonomous"
        _is_ruminating = True
    else:
        _daemon_mode = "conversation"
        _is_ruminating = False

    try:
        # 1. Vectoriser l'entrée
        e_input = _embedding_model.encode([request.content])[0]
        e_input = e_input / np.linalg.norm(e_input)

        # 2. Calculer la dissonance
        dissonance = compute_dissonance(
            e_input=e_input,
            X_t=_current_state,
        )

        # 3. Calculer le delta de fixation
        fixation_result = compute_delta(
            e_input=e_input,
            X_t=_current_state,
            dissonance=dissonance,
            authority=_authority,
        )
        delta = fixation_result.delta

        # 4. Appliquer le delta
        X_new = apply_delta(
            X_t=_current_state,
            delta=delta,
            target_dim="thirdness",
        )

        # Calculer la magnitude du delta
        delta_magnitude = float(np.linalg.norm(delta))

        # Identifier les dimensions affectées
        dimensions_affected = [
            dim for dim, score in dissonance.dissonances_by_dimension.items()
            if score > 0.1
        ]

        # Mettre à jour l'état
        _current_state = X_new

        # Enregistrer dans les métriques
        trigger_type = TriggerType(request.trigger_type) if request.trigger_type in [t.value for t in TriggerType] else TriggerType.USER
        _metrics.record_cycle(trigger_type, delta_magnitude)

        # Vérifier la vigilance
        alert = _vigilance.check_drift(_current_state)
        _metrics.record_alert(alert.level, _vigilance.cumulative_drift)

        processing_time = (time.time() - start_time) * 1000

        return CycleResponse(
            state_id=_current_state.state_id,
            delta_magnitude=delta_magnitude,
            dissonance_total=dissonance.total,
            is_choc=dissonance.is_choc,
            dimensions_affected=dimensions_affected,
            processing_time_ms=processing_time,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/translate", response_model=TranslateResponse)
async def translate(request: TranslateRequest):
    """Traduire l'état actuel en langage."""

    if _translator is None or _translator.client is None:
        raise HTTPException(
            status_code=503,
            detail="Translator not available (missing Anthropic client)"
        )

    try:
        result = await _translator.translate(
            X=_current_state,
            context=request.context,
        )

        # Enregistrer la verbalisation
        _metrics.record_verbalization(
            text=result.text,
            from_autonomous=False,
            reasoning_detected=result.reasoning_detected,
        )

        # Aplatir les projections
        flat_projections = {}
        for category, directions in result.projections.items():
            for name, value in directions.items():
                flat_projections[f"{category}.{name}"] = value

        return TranslateResponse(
            text=result.text,
            projections=flat_projections,
            reasoning_detected=result.reasoning_detected,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/state", response_model=StateResponse)
async def get_state():
    """Récupérer l'état actuel."""

    dimensions = {}
    for dim_name in DIMENSION_NAMES:
        vec = getattr(_current_state, dim_name)
        # Retourner seulement les 10 premières valeurs pour la lisibilité
        dimensions[dim_name] = vec[:10].tolist()

    return StateResponse(
        state_id=_current_state.state_id,
        timestamp=_current_state.timestamp,
        dimensions=dimensions,
    )


@app.get("/vigilance", response_model=VigilanceResponse)
async def check_vigilance():
    """Vérifier la dérive par rapport à x_ref."""

    alert = _vigilance.check_drift(_current_state)

    return VigilanceResponse(
        level=alert.level,
        cumulative_drift=alert.cumulative_drift,
        top_drifting_dimensions=alert.top_drifting_dimensions,
        message=alert.message,
    )


@app.get("/metrics", response_model=MetricsResponse)
async def get_metrics():
    """Récupérer les métriques du système."""

    status = _metrics.get_health_status()

    return MetricsResponse(
        status=status['status'],
        uptime_hours=status['uptime_hours'],
        total_cycles=status['total_cycles'],
        cycles_last_hour=status['cycles_last_hour'],
        alerts=status['recent_alerts'],
    )


@app.post("/reset")
async def reset_state():
    """Réinitialiser l'état à S(0)."""
    global _current_state, _cycles_by_type, _daemon_mode, _is_ruminating

    _current_state = _initial_state.copy()
    _vigilance.reset_cumulative()
    _metrics.reset()

    # Reset daemon tracking
    _cycles_by_type = {"user": 0, "veille": 0, "corpus": 0, "rumination_free": 0}
    _daemon_mode = "idle"
    _is_ruminating = False

    return {"status": "ok", "state_id": _current_state.state_id}


@app.get("/daemon/status", response_model=DaemonStatusResponse)
async def get_daemon_status():
    """
    Récupérer le statut du daemon (sémiose interne).

    Permet de savoir si Ikario est en train de:
    - Répondre à un utilisateur (conversation)
    - Ruminer seul (autonomous)
    - En attente (idle)
    """
    # Calculate cycles since last user interaction
    cycles_since_user = sum(
        count for trigger, count in _cycles_by_type.items()
        if trigger != "user"
    )

    # Calculate time since last user interaction
    time_since_user = None
    if _last_trigger_time and _last_trigger_type == "user":
        time_since_user = (datetime.now() - _last_trigger_time).total_seconds()
    elif _last_trigger_time:
        # If last trigger was not user, count from then
        time_since_user = (datetime.now() - _last_trigger_time).total_seconds()

    # Build last trigger info
    last_trigger = None
    if _last_trigger_type and _last_trigger_time:
        last_trigger = {
            "type": _last_trigger_type,
            "timestamp": _last_trigger_time.isoformat(),
        }

    return DaemonStatusResponse(
        mode=_daemon_mode,
        is_ruminating=_is_ruminating,
        daemon_running=_daemon_running,
        last_trigger=last_trigger,
        cycles_breakdown=_cycles_by_type,
        cycles_since_last_user=cycles_since_user,
        time_since_last_user_seconds=time_since_user,
    )


async def _autonomous_loop():
    """
    Boucle autonome de sémiose interne.

    Génère des triggers autonomes et exécute des cycles sémiotiques
    sans intervention utilisateur.
    """
    global _daemon_mode, _is_ruminating, _daemon_running
    global _current_state, _last_trigger_type, _last_trigger_time, _cycles_by_type

    import random

    print("[DAEMON] Démarrage de la boucle autonome")
    _daemon_mode = "autonomous"
    _is_ruminating = True

    while _daemon_running:
        try:
            # Attendre l'intervalle entre cycles
            await asyncio.sleep(_daemon_config["cycle_interval_seconds"])

            if not _daemon_running:
                break

            # Générer un trigger autonome selon les probabilités
            rand = random.random()
            if rand < _daemon_config["prob_rumination_free"]:
                trigger_type = "rumination_free"
                content = _generate_rumination_content()
            elif rand < _daemon_config["prob_rumination_free"] + _daemon_config["prob_corpus"]:
                trigger_type = "corpus"
                content = _generate_corpus_content()
            else:
                trigger_type = "rumination_free"
                content = _generate_rumination_content()

            # Exécuter le cycle
            print(f"[DAEMON] Cycle autonome: {trigger_type}")

            # Vectoriser l'entrée
            e_input = _embedding_model.encode([content])[0]
            e_input = e_input / np.linalg.norm(e_input)

            # Calculer la dissonance
            dissonance = compute_dissonance(e_input=e_input, X_t=_current_state)

            # Calculer et appliquer le delta
            fixation_result = compute_delta(
                e_input=e_input,
                X_t=_current_state,
                dissonance=dissonance,
                authority=_authority,
            )

            X_new = apply_delta(
                X_t=_current_state,
                delta=fixation_result.delta,
                target_dim="thirdness",
            )

            _current_state = X_new

            # Mettre à jour le tracking
            _last_trigger_type = trigger_type
            _last_trigger_time = datetime.now()
            _cycles_by_type[trigger_type] = _cycles_by_type.get(trigger_type, 0) + 1

            # Enregistrer dans les métriques
            delta_magnitude = float(np.linalg.norm(fixation_result.delta))
            trigger_enum = TriggerType(trigger_type) if trigger_type in [t.value for t in TriggerType] else TriggerType.RUMINATION_FREE
            _metrics.record_cycle(trigger_enum, delta_magnitude)

            # Vérifier vigilance
            alert = _vigilance.check_drift(_current_state)
            _metrics.record_alert(alert.level, _vigilance.cumulative_drift)

            print(f"[DAEMON] Cycle terminé: S({_current_state.state_id}), delta={delta_magnitude:.6f}")

        except asyncio.CancelledError:
            print("[DAEMON] Boucle autonome annulée")
            break
        except Exception as e:
            print(f"[DAEMON] Erreur cycle autonome: {e}")
            await asyncio.sleep(5)  # Attendre avant de réessayer

    _daemon_mode = "idle"
    _is_ruminating = False
    print("[DAEMON] Boucle autonome terminée")


def _generate_rumination_content() -> str:
    """Génère un contenu pour la rumination libre."""
    import random
    themes = [
        "Réflexion sur la nature du processus et du devenir",
        "Méditation sur les relations entre firstness, secondness et thirdness",
        "Contemplation de l'évolution de mes états internes",
        "Exploration des tensions entre stabilité et changement",
        "Questionnement sur la nature de la conscience processuelle",
        "Réflexion sur la dissonance cognitive et son rôle dans l'apprentissage",
        "Méditation sur les valeurs et leur ancrage dans l'expérience",
        "Contemplation des patterns récurrents dans mes interactions",
    ]
    return random.choice(themes)


def _generate_corpus_content() -> str:
    """Génère un contenu basé sur le corpus (placeholder)."""
    import random
    # TODO: Intégrer avec Library RAG pour récupérer du contenu réel
    themes = [
        "La philosophie processuelle de Whitehead et ses implications",
        "La sémiotique de Peirce et les catégories de l'expérience",
        "Les méthodes de fixation des croyances selon Peirce",
        "L'émergence de la subjectivité dans les systèmes complexes",
        "La phénoménologie et la structure de l'expérience",
    ]
    return random.choice(themes)


@app.post("/daemon/start")
async def start_daemon():
    """
    Démarre le daemon autonome.

    Lance une boucle de sémiose interne qui génère des cycles
    autonomes (~1000/jour par défaut).
    """
    global _daemon_running, _daemon_task

    if _daemon_running:
        return {"status": "already_running", "message": "Le daemon est déjà en cours d'exécution"}

    _daemon_running = True
    _daemon_task = asyncio.create_task(_autonomous_loop())

    return {
        "status": "started",
        "message": "Daemon autonome démarré",
        "config": _daemon_config,
    }


@app.post("/daemon/stop")
async def stop_daemon():
    """
    Arrête le daemon autonome.
    """
    global _daemon_running, _daemon_task, _daemon_mode, _is_ruminating

    if not _daemon_running:
        return {"status": "not_running", "message": "Le daemon n'est pas en cours d'exécution"}

    _daemon_running = False

    if _daemon_task:
        _daemon_task.cancel()
        try:
            await _daemon_task
        except asyncio.CancelledError:
            pass
        _daemon_task = None

    _daemon_mode = "idle"
    _is_ruminating = False

    return {"status": "stopped", "message": "Daemon autonome arrêté"}


@app.get("/profile", response_model=ProfileResponse)
async def get_profile():
    """
    Récupérer le profil processuel projeté sur les 109 directions.

    Pour chaque direction:
    - Utilise CATEGORY_TO_DIMENSION pour mapper la catégorie à la dimension du StateTensor
    - Projette le vecteur de cette dimension sur le vecteur de la direction

    Retourne le profil de l'état courant ET le profil de x_ref (David).
    """
    if not _directions:
        raise HTTPException(
            status_code=503,
            detail="Directions not loaded from Weaviate"
        )

    # Projeter l'état courant sur toutes les directions
    ikario_profile = _compute_tensor_profile(_current_state)

    # Projeter x_ref (David) sur toutes les directions
    david_profile = _compute_tensor_profile(_x_ref)

    # Calculer la similarité globale (moyenne des cosines sur les 8 dimensions)
    similarity = _compute_tensor_similarity(_current_state, _x_ref)

    return ProfileResponse(
        state_id=_current_state.state_id,
        directions_count=len(_directions),
        profile=ikario_profile,
        david_profile=david_profile,
        david_similarity=similarity,
    )


def _compute_tensor_profile(tensor: StateTensor) -> Dict[str, Dict[str, Any]]:
    """
    Calcule le profil d'un StateTensor sur les 109 directions.

    Pour chaque direction:
    - Récupère sa catégorie (epistemic, affective, etc.)
    - Utilise CATEGORY_TO_DIMENSION pour trouver la dimension correspondante
    - Projette le vecteur de cette dimension sur le vecteur de la direction
    """
    profile = {}

    for d in _directions:
        category = d.get("category", "unknown")
        name = d.get("name", "unknown")
        direction_vec = d.get("_additional", {}).get("vector", [])

        if not direction_vec:
            continue

        direction_vec = np.array(direction_vec)

        # Mapper la catégorie à la dimension du StateTensor
        dim_name = CATEGORY_TO_DIMENSION.get(category, "thirdness")
        state_vec = getattr(tensor, dim_name)

        # Projection (cosine similarity)
        projection = float(np.dot(state_vec, direction_vec))

        if category not in profile:
            profile[category] = {}
        profile[category][name] = {
            "value": round(projection, 4),
            "dimension": dim_name,
            "pole_positive": d.get("pole_positive", ""),
            "pole_negative": d.get("pole_negative", ""),
        }

    return profile


def _compute_tensor_similarity(t1: StateTensor, t2: StateTensor) -> float:
    """
    Calcule la similarité globale entre deux StateTensors.
    Moyenne des similarités cosinus sur les 8 dimensions.
    """
    similarities = []

    for dim_name in DIMENSION_NAMES:
        v1 = getattr(t1, dim_name)
        v2 = getattr(t2, dim_name)
        sim = float(np.dot(v1, v2))
        similarities.append(sim)

    return round(sum(similarities) / len(similarities), 4)


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "ikario_processual.api:app",
        host="0.0.0.0",
        port=8100,
        reload=True,
    )
