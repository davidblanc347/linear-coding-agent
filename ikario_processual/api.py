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
"""

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager

import numpy as np
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
from .state_to_language import StateToLanguage, ProjectionDirection
from .daemon import TriggerType, DaemonConfig
from .metrics import ProcessMetrics, create_metrics


# =============================================================================
# GLOBALS (chargés au démarrage)
# =============================================================================

_embedding_model = None
_current_state: Optional[StateTensor] = None
_initial_state: Optional[StateTensor] = None
_vigilance: Optional[VigilanceSystem] = None
_translator: Optional[StateToLanguage] = None
_metrics: Optional[ProcessMetrics] = None
_authority: Optional[Authority] = None
_startup_time: Optional[datetime] = None


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


def initialize_state():
    """Initialise l'état depuis le profil David ou crée un état aléatoire."""
    global _current_state, _initial_state, _vigilance, _metrics

    # Chercher le profil David
    profile_path = Path(__file__).parent / "david_profile_declared.json"

    if profile_path.exists():
        print(f"[API] Loading David profile from {profile_path}")
        from .vigilance import DavidReference
        x_ref = DavidReference.create_from_declared_profile(str(profile_path))

        # Créer l'état initial comme copie de x_ref
        _initial_state = x_ref.copy()
        _initial_state.state_id = 0
        _current_state = _initial_state.copy()

        # Créer le système de vigilance
        _vigilance = VigilanceSystem(x_ref=x_ref)
    else:
        print(f"[API] No David profile found, creating random state")
        _initial_state = StateTensor(
            state_id=0,
            timestamp=datetime.now().isoformat(),
        )
        # Initialiser avec des vecteurs aléatoires normalisés
        for dim_name in DIMENSION_NAMES:
            v = np.random.randn(EMBEDDING_DIM)
            v = v / np.linalg.norm(v)
            setattr(_initial_state, dim_name, v)

        _current_state = _initial_state.copy()
        _vigilance = create_vigilance_system()

    # Créer les métriques
    _metrics = create_metrics(S_0=_initial_state, x_ref=_vigilance.x_ref)

    print(f"[API] State initialized: S({_current_state.state_id})")


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
    global _current_state

    start_time = time.time()

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
    global _current_state

    _current_state = _initial_state.copy()
    _vigilance.reset_cumulative()
    _metrics.reset()

    return {"status": "ok", "state_id": _current_state.state_id}


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
