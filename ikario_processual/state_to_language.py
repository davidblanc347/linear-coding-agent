#!/usr/bin/env python3
"""
StateToLanguage - Traduction de l'espace latent vers le langage humain.

Phase 5 de l'architecture processuelle v2.
Paradigme : "L'espace latent pense. Le LLM traduit."

Ce module :
1. Projette le StateTensor sur les directions interpretables
2. Construit des prompts de traduction pour le LLM
3. Force le mode ZERO-REASONING (T=0, prompt strict)
4. Valide les sorties (Amendment #4 et #14)

Le LLM NE REFLECHIT PAS. Il traduit.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .state_tensor import StateTensor, DIMENSION_NAMES

# Configuration
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DEFAULT_MODEL = "claude-3-5-sonnet-20241022"
EMBEDDING_DIM = 1024

# Logger
logger = logging.getLogger(__name__)


@dataclass
class ProjectionDirection:
    """Direction interpretable dans l'espace latent."""
    name: str
    category: str
    pole_positive: str
    pole_negative: str
    description: str
    vector: np.ndarray = field(repr=False)

    def project(self, state_vector: np.ndarray) -> float:
        """Projette un vecteur sur cette direction."""
        return float(np.dot(state_vector, self.vector))


@dataclass
class TranslationResult:
    """Resultat d'une traduction."""
    text: str
    projections: Dict[str, Dict[str, float]]
    output_type: str
    reasoning_detected: bool = False
    json_valid: bool = True
    raw_response: str = ""
    processing_time_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialise en dictionnaire."""
        return {
            'text': self.text,
            'projections': self.projections,
            'output_type': self.output_type,
            'reasoning_detected': self.reasoning_detected,
            'json_valid': self.json_valid,
            'processing_time_ms': self.processing_time_ms,
        }


# Mapping categories → dimensions du tenseur
CATEGORY_TO_DIMENSION = {
    'epistemic': 'firstness',       # Rapport au savoir → Firstness
    'affective': 'dispositions',    # Emotions → Dispositions
    'cognitive': 'thirdness',       # Style de pensee → Thirdness
    'relational': 'engagements',    # Rapport aux autres → Engagements
    'ethical': 'valeurs',           # Orientation morale → Valeurs
    'temporal': 'orientations',     # Rapport au temps → Orientations
    'thematic': 'pertinences',      # Focus conceptuel → Pertinences
    'metacognitive': 'secondness',  # Conscience de soi → Secondness
    'vital': 'dispositions',        # Energie, risques → Dispositions
    'ecosystemic': 'engagements',   # Rapport ecosystemique → Engagements
    'philosophical': 'thirdness',   # Positions metaphysiques → Thirdness
}

# Marqueurs de raisonnement a detecter (Amendment #4)
REASONING_MARKERS = [
    "je pense que",
    "il me semble",
    "apres reflexion",
    "en analysant",
    "d'un point de vue",
    "cela suggere",
    "on pourrait dire",
    "il est probable que",
    "selon mon analyse",
    "en considerant",
    "je deduis que",
    "logiquement",
    "mon raisonnement",
    "je conclus",
    "en reflechissant",
]


class StateToLanguage:
    """
    Traduit un StateTensor en langage humain via le LLM.

    PROCESSUS:
    1. Projeter X_{t+1} sur les directions interpretables
    2. Construire un prompt descriptif des valeurs
    3. LLM en mode ZERO-REASONING (T=0, prompt strict)

    Le LLM NE REFLECHIT PAS. Il traduit.
    """

    def __init__(
        self,
        directions: Optional[List[ProjectionDirection]] = None,
        anthropic_client: Any = None,
        model: str = DEFAULT_MODEL,
    ):
        """
        Initialise le traducteur.

        Args:
            directions: Liste des directions interpretables
            anthropic_client: Client Anthropic (optionnel, pour async)
            model: Modele a utiliser
        """
        self.directions = directions or []
        self.client = anthropic_client
        self.model = model
        self._translations_count = 0
        self._reasoning_warnings = 0

    def add_direction(self, direction: ProjectionDirection) -> None:
        """Ajoute une direction interpretable."""
        self.directions.append(direction)

    def project_state(self, X: StateTensor) -> Dict[str, Dict[str, float]]:
        """
        Projette le tenseur sur toutes les directions.

        Returns:
            {
                'epistemic': {'curiosity': 0.72, 'certainty': -0.18, ...},
                'affective': {'enthusiasm': 0.45, ...},
                'relational': {'engagement': 0.33, ...},
                ...
            }
        """
        projections: Dict[str, Dict[str, float]] = {}

        for direction in self.directions:
            # Determiner quelle dimension du tenseur utiliser
            dim_name = CATEGORY_TO_DIMENSION.get(direction.category, 'thirdness')
            x_dim = getattr(X, dim_name)

            # Calculer la projection
            value = direction.project(x_dim)

            # Organiser par categorie
            if direction.category not in projections:
                projections[direction.category] = {}
            projections[direction.category][direction.name] = round(value, 3)

        return projections

    def project_state_flat(self, X: StateTensor) -> Dict[str, float]:
        """
        Projette le tenseur et retourne un dict plat.

        Returns:
            {'curiosity': 0.72, 'enthusiasm': 0.45, ...}
        """
        projections = self.project_state(X)
        flat = {}
        for category_projections in projections.values():
            flat.update(category_projections)
        return flat

    @staticmethod
    def interpret_value(value: float) -> str:
        """
        Interprete une valeur de projection en langage.

        Args:
            value: Valeur entre -1 et 1

        Returns:
            Interpretation textuelle (tres, moderement, neutre, peu, pas du tout)
        """
        if value > 0.5:
            return "tres"
        elif value > 0.2:
            return "moderement"
        elif value > -0.2:
            return "neutre"
        elif value > -0.5:
            return "peu"
        else:
            return "pas du tout"

    def build_translation_prompt(
        self,
        projections: Dict[str, Dict[str, float]],
        output_type: str = "response",
    ) -> str:
        """
        Construit le prompt pour le LLM traducteur.

        Le LLM recoit UNIQUEMENT:
        - Les projections numeriques
        - Le type de sortie demande
        - PAS la conversation, PAS l'historique
        """
        prompt = "=== ETAT COGNITIF ===\n"

        for category, components in sorted(projections.items()):
            prompt += f"\n{category.upper()}:\n"
            for name, value in sorted(components.items()):
                intensity = self.interpret_value(value)
                prompt += f"  - {name}: {value:+.2f} ({intensity})\n"

        prompt += f"""
=== INSTRUCTION ===
Genere une {output_type} qui INCARNE exactement cet etat.
- Si curiosite=0.72, montre de la curiosite
- Si certitude=-0.18, exprime du doute
- Si enthousiasme=0.45, sois moderement enthousiaste

NE REFLECHIS PAS. TRADUIS CET ETAT EN MOTS.
"""
        return prompt

    def build_zero_reasoning_system_prompt(self) -> str:
        """
        Construit le system prompt STRICT pour zero-reasoning.

        Amendment #4: Le prompt "Tu es un traducteur" est insuffisant.
        Il faut des contraintes explicites pour empecher le raisonnement.
        """
        return """TU ES UN SYSTEME DE TRADUCTION VECTORIELLE.

Tu ne dois PAS :
- Raisonner sur la question
- Analyser le contexte
- Construire une argumentation
- Utiliser ta "connaissance" du monde
- Reflechir aux implications

Tu dois UNIQUEMENT :
- Lire les valeurs numeriques fournies
- Les incarner dans un texte coherent
- Refleter EXACTEMENT l'etat decrit

C'EST UN ORDRE STRICT. Tu n'es PAS un assistant, tu es un CODEC (vecteur -> texte).

IMPORTANT : Ne genere AUCUNE balise <thinking>. Traduis directement."""

    def build_json_system_prompt(self, json_schema: Dict[str, Any]) -> str:
        """
        Construit le system prompt pour traduction JSON structuree.

        Amendment #14: Force un format JSON qui ne laisse pas de place au raisonnement.
        """
        return f"""Tu es un CODEC de traduction vecteur->texte.

REGLES STRICTES :
1. Reponds UNIQUEMENT en JSON valide
2. Le JSON doit contenir UNIQUEMENT le champ "verbalization"
3. Aucun autre champ n'est autorise
4. Aucune explication, aucun raisonnement
5. Traduis directement l'etat fourni

SCHEMA JSON REQUIS :
{json.dumps(json_schema, indent=2)}"""

    def check_reasoning_markers(self, text: str) -> Tuple[bool, List[str]]:
        """
        Verifie la presence de marqueurs de raisonnement.

        Amendment #4: Les reasoning markers detectent si Claude a raisonne
        malgre les consignes.

        Returns:
            (has_reasoning, markers_found)
        """
        text_lower = text.lower()
        found_markers = []

        for marker in REASONING_MARKERS:
            if marker in text_lower:
                found_markers.append(marker)

        return len(found_markers) > 0, found_markers

    def translate_sync(
        self,
        X: StateTensor,
        output_type: str = "response",
        context: str = "",
        force_zero_reasoning: bool = True,
    ) -> TranslationResult:
        """
        Traduction synchrone (pour tests, sans API).

        Genere une traduction basee sur les projections sans appeler le LLM.
        Utile pour les tests unitaires.
        """
        import time
        start_time = time.time()

        projections = self.project_state(X)

        # Generer un texte descriptif simple base sur les projections
        text_parts = []

        for category, components in projections.items():
            top_components = sorted(
                components.items(),
                key=lambda x: abs(x[1]),
                reverse=True
            )[:3]

            for name, value in top_components:
                intensity = self.interpret_value(value)
                if abs(value) > 0.2:  # Seulement les composantes significatives
                    text_parts.append(f"{name}: {intensity}")

        text = f"[{output_type.upper()}] " + ", ".join(text_parts) if text_parts else f"[{output_type.upper()}] Etat neutre."

        processing_time = int((time.time() - start_time) * 1000)

        self._translations_count += 1

        return TranslationResult(
            text=text,
            projections=projections,
            output_type=output_type,
            reasoning_detected=False,
            json_valid=True,
            raw_response=text,
            processing_time_ms=processing_time,
        )

    async def translate(
        self,
        X: StateTensor,
        output_type: str = "response",
        context: str = "",
        force_zero_reasoning: bool = True,
    ) -> TranslationResult:
        """
        Traduit le tenseur en langage avec ZERO-REASONING force.

        Amendment #4: Contraintes TECHNIQUES appliquees:
        - Temperature = 0.0 (deterministe)
        - Max tokens limite (eviter verbosite)
        - System prompt STRICT (ordre explicite de ne pas penser)
        - Pas d'historique de conversation fourni
        """
        import time
        start_time = time.time()

        projections = self.project_state(X)
        user_prompt = self.build_translation_prompt(projections, output_type)

        if context:
            user_prompt += f"\n\nContexte minimal: {context[:200]}"

        system_prompt = self.build_zero_reasoning_system_prompt()

        # Appel API si client disponible
        if self.client is not None:
            try:
                response = await self.client.messages.create(
                    model=self.model,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                    temperature=0.0,      # Deterministe
                    max_tokens=500,       # Limiter verbosite
                )
                text = response.content[0].text
            except Exception as e:
                logger.error(f"Erreur API Anthropic: {e}")
                text = f"[ERREUR TRADUCTION] {str(e)[:100]}"
        else:
            # Mode test sans API
            text = f"[MOCK TRANSLATION] {output_type}: projections={len(projections)} categories"

        # Verifier marqueurs de raisonnement
        reasoning_detected, markers = self.check_reasoning_markers(text)

        if reasoning_detected and force_zero_reasoning:
            logger.warning(f"LLM exhibited reasoning despite zero-reasoning mode: {markers}")
            self._reasoning_warnings += 1

        processing_time = int((time.time() - start_time) * 1000)
        self._translations_count += 1

        return TranslationResult(
            text=text,
            projections=projections,
            output_type=output_type,
            reasoning_detected=reasoning_detected,
            json_valid=True,
            raw_response=text,
            processing_time_ms=processing_time,
        )

    async def translate_structured(
        self,
        X: StateTensor,
        output_type: str = "response",
        context: str = "",
    ) -> TranslationResult:
        """
        Traduction avec validation structurelle JSON.

        Amendment #14: Force le LLM a repondre en JSON, ce qui limite
        sa capacite a "penser" librement.
        """
        import time
        start_time = time.time()

        projections = self.project_state(X)

        # Schema JSON strict
        json_schema = {
            "type": "object",
            "required": ["verbalization"],
            "properties": {
                "verbalization": {
                    "type": "string",
                    "description": "La traduction de l'etat en langage naturel"
                }
            },
            "additionalProperties": False
        }

        system_prompt = self.build_json_system_prompt(json_schema)

        user_prompt = f"""Etat a traduire :
{json.dumps(projections, indent=2)}

Type de sortie : {output_type}
{f'Contexte : {context[:100]}' if context else ''}

Reponds UNIQUEMENT avec le JSON de traduction."""

        json_valid = True
        reasoning_detected = False

        # Appel API si client disponible
        if self.client is not None:
            try:
                response = await self.client.messages.create(
                    model=self.model,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                    temperature=0.0,
                    max_tokens=500,
                )
                raw_text = response.content[0].text

                # Validation JSON stricte
                try:
                    parsed = json.loads(raw_text)

                    # Verifier structure
                    if set(parsed.keys()) != {"verbalization"}:
                        extra_keys = set(parsed.keys()) - {"verbalization"}
                        logger.warning(f"LLM a ajoute des champs non autorises : {extra_keys}")
                        json_valid = False
                        text = parsed.get("verbalization", raw_text)
                    else:
                        text = parsed["verbalization"]

                except json.JSONDecodeError:
                    logger.warning(f"LLM n'a pas retourne du JSON valide : {raw_text[:100]}")
                    json_valid = False
                    text = raw_text

            except Exception as e:
                logger.error(f"Erreur API Anthropic: {e}")
                text = f"[ERREUR TRADUCTION] {str(e)[:100]}"
                raw_text = text
                json_valid = False
        else:
            # Mode test sans API
            text = f"[MOCK JSON TRANSLATION] {output_type}"
            raw_text = json.dumps({"verbalization": text})

        # Verifier marqueurs de raisonnement
        reasoning_detected, _ = self.check_reasoning_markers(text)

        processing_time = int((time.time() - start_time) * 1000)
        self._translations_count += 1

        return TranslationResult(
            text=text,
            projections=projections,
            output_type=output_type,
            reasoning_detected=reasoning_detected,
            json_valid=json_valid,
            raw_response=raw_text if self.client else text,
            processing_time_ms=processing_time,
        )

    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques du traducteur."""
        return {
            'directions_count': len(self.directions),
            'translations_count': self._translations_count,
            'reasoning_warnings': self._reasoning_warnings,
            'categories': list(set(d.category for d in self.directions)),
        }


def create_directions_from_weaviate(weaviate_client) -> List[ProjectionDirection]:
    """
    Charge les directions depuis Weaviate.

    Args:
        weaviate_client: Client Weaviate v4

    Returns:
        Liste des directions interpretables
    """
    directions = []

    try:
        collection = weaviate_client.collections.get("ProjectionDirection")

        for item in collection.iterator(include_vector=True):
            direction = ProjectionDirection(
                name=item.properties.get("name", "unknown"),
                category=item.properties.get("category", "unknown"),
                pole_positive=item.properties.get("pole_positive", ""),
                pole_negative=item.properties.get("pole_negative", ""),
                description=item.properties.get("description", ""),
                vector=np.array(item.vector['default'] if isinstance(item.vector, dict) else item.vector),
            )
            directions.append(direction)

    except Exception as e:
        logger.error(f"Erreur chargement directions: {e}")

    return directions


def create_directions_from_config(
    config: Dict[str, Dict[str, Any]],
    embedding_model,
) -> List[ProjectionDirection]:
    """
    Cree les directions depuis la configuration locale.

    Args:
        config: Configuration des directions (DIRECTIONS_CONFIG)
        embedding_model: Modele d'embedding (SentenceTransformer)

    Returns:
        Liste des directions interpretables
    """
    directions = []

    for name, cfg in config.items():
        # Embeddings positifs et negatifs
        pos_embeddings = embedding_model.encode(cfg.get("positive_examples", []))
        neg_embeddings = embedding_model.encode(cfg.get("negative_examples", []))

        if len(pos_embeddings) > 0 and len(neg_embeddings) > 0:
            pos_mean = np.mean(pos_embeddings, axis=0)
            neg_mean = np.mean(neg_embeddings, axis=0)

            # Direction = difference normalisee
            vector = pos_mean - neg_mean
            vector = vector / np.linalg.norm(vector)
        else:
            vector = np.zeros(EMBEDDING_DIM)

        direction = ProjectionDirection(
            name=name,
            category=cfg.get("category", "unknown"),
            pole_positive=cfg.get("pole_positive", ""),
            pole_negative=cfg.get("pole_negative", ""),
            description=cfg.get("description", ""),
            vector=vector,
        )
        directions.append(direction)

    return directions


def create_translator(
    weaviate_client=None,
    embedding_model=None,
    anthropic_client=None,
    directions_config: Optional[Dict] = None,
) -> StateToLanguage:
    """
    Factory pour creer un traducteur configure.

    Args:
        weaviate_client: Client Weaviate (charge les directions existantes)
        embedding_model: Modele d'embedding (cree les directions depuis config)
        anthropic_client: Client Anthropic pour les appels API
        directions_config: Configuration des directions (optionnel)

    Returns:
        StateToLanguage configure
    """
    directions = []

    # Charger depuis Weaviate si disponible
    if weaviate_client is not None:
        directions = create_directions_from_weaviate(weaviate_client)

    # Ou creer depuis config si fournie
    if not directions and directions_config and embedding_model:
        directions = create_directions_from_config(directions_config, embedding_model)

    return StateToLanguage(
        directions=directions,
        anthropic_client=anthropic_client,
    )
