"""Structuration de documents via LLM (Ollama ou Mistral API)."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, TypedDict, Union, cast

import requests
from dotenv import load_dotenv
import threading

# Import type definitions from central types module
from utils.types import LLMCostStats

# Charger les variables d'environnement
load_dotenv()

# Logger
logger: logging.Logger = logging.getLogger(__name__)
if not logging.getLogger().hasHandlers():
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(message)s"
    )


class LLMStructureError(RuntimeError):
    """Erreur lors de la structuration via LLM."""
    pass


# ═══════════════════════════════════════════════════════════════════════════════
# TypedDict Definitions
# ═══════════════════════════════════════════════════════════════════════════════

class MistralPricingEntry(TypedDict):
    """Mistral API pricing per million tokens."""
    input: float
    output: float


class LLMHierarchyPath(TypedDict, total=False):
    """Hierarchy path in structured output."""
    part: Optional[str]
    chapter: Optional[str]
    section: Optional[str]
    subsection: Optional[str]


class LLMChunkOutput(TypedDict, total=False):
    """Single chunk in LLM structured output."""
    chunk_id: str
    text: str
    hierarchy: LLMHierarchyPath
    type: str
    is_toc: bool


class LLMDocumentSection(TypedDict, total=False):
    """Document section in structured output."""
    path: LLMHierarchyPath
    type: str
    page_start: int
    page_end: int


class LLMStructuredResult(TypedDict, total=False):
    """Result from LLM document structuring."""
    document_structure: List[LLMDocumentSection]
    chunks: List[LLMChunkOutput]


class OllamaResultContainer(TypedDict):
    """Container for Ollama call result (internal use)."""
    response: Optional[str]
    error: Optional[Exception]
    done: bool


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════════

def _get_ollama_url() -> str:
    """Retourne l'URL de base d'Ollama."""
    return os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


def _get_default_model() -> str:
    """Retourne le modèle LLM par défaut."""
    return os.getenv("STRUCTURE_LLM_MODEL", "qwen2.5:7b")


def _get_mistral_api_key() -> Optional[str]:
    """Retourne la clé API Mistral."""
    return os.getenv("MISTRAL_API_KEY")


def _get_default_mistral_model() -> str:
    """Retourne le modèle Mistral par défaut pour les tâches LLM."""
    return os.getenv("MISTRAL_LLM_MODEL", "mistral-small-latest")


# ═══════════════════════════════════════════════════════════════════════════════
# Appel Mistral API (rapide, cloud) avec tracking des coûts
# ═══════════════════════════════════════════════════════════════════════════════

# Prix Mistral API par million de tokens (€)
MISTRAL_PRICING: Dict[str, MistralPricingEntry] = {
    "mistral-small-latest": {"input": 0.2, "output": 0.6},
    "mistral-medium-latest": {"input": 0.8, "output": 2.4},
    "mistral-large-latest": {"input": 2.0, "output": 6.0},
    # Fallback pour autres modèles
    "default": {"input": 0.5, "output": 1.5},
}

# Accumulateur de coûts global (thread-local pour safety)
_cost_tracker: threading.local = threading.local()


def reset_llm_cost() -> None:
    """Réinitialise le compteur de coût LLM."""
    _cost_tracker.total_cost = 0.0
    _cost_tracker.total_input_tokens = 0
    _cost_tracker.total_output_tokens = 0
    _cost_tracker.calls_count = 0


def get_llm_cost() -> LLMCostStats:
    """Retourne les statistiques de coût LLM accumulées."""
    return {
        "total_cost": getattr(_cost_tracker, "total_cost", 0.0),
        "total_input_tokens": getattr(_cost_tracker, "total_input_tokens", 0),
        "total_output_tokens": getattr(_cost_tracker, "total_output_tokens", 0),
        "calls_count": getattr(_cost_tracker, "calls_count", 0),
    }


def _calculate_mistral_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calcule le coût d'un appel Mistral API en euros."""
    pricing: MistralPricingEntry = MISTRAL_PRICING.get(model, MISTRAL_PRICING["default"])
    cost: float = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
    return cost


def _call_mistral_api(
    prompt: str,
    model: str = "mistral-small-latest",
    temperature: float = 0.2,
    max_tokens: int = 4096,
    timeout: int = 120,
) -> str:
    """Appelle l'API Mistral pour générer une réponse.
    
    Modèles disponibles (du plus rapide au plus puissant) :
    - mistral-small-latest : Rapide, économique (~0.2€/M tokens input)
    - mistral-medium-latest : Équilibré (~0.8€/M tokens input)
    - mistral-large-latest : Puissant (~2€/M tokens input)
    
    Args:
        prompt: Le prompt à envoyer
        model: Nom du modèle Mistral
        temperature: Température (0-1)
        max_tokens: Nombre max de tokens en réponse
        timeout: Timeout en secondes
    
    Returns:
        Réponse textuelle du LLM
    """
    api_key: Optional[str] = _get_mistral_api_key()
    if not api_key:
        raise LLMStructureError("MISTRAL_API_KEY non définie dans .env")
    
    logger.info(f"Appel Mistral API - modèle: {model}")
    
    url: str = "https://api.mistral.ai/v1/chat/completions"
    headers: Dict[str, str] = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    
    try:
        start: float = time.time()
        response: requests.Response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        elapsed: float = time.time() - start
        
        response.raise_for_status()
        data: Dict[str, Any] = response.json()
        
        content: str = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        usage: Dict[str, Any] = data.get("usage", {})
        
        input_tokens: int = usage.get("prompt_tokens", 0)
        output_tokens: int = usage.get("completion_tokens", 0)
        
        # Calculer et accumuler le coût
        call_cost: float = _calculate_mistral_cost(model, input_tokens, output_tokens)
        
        # Mettre à jour le tracker
        if not hasattr(_cost_tracker, "total_cost"):
            reset_llm_cost()
        
        _cost_tracker.total_cost += call_cost
        _cost_tracker.total_input_tokens += input_tokens
        _cost_tracker.total_output_tokens += output_tokens
        _cost_tracker.calls_count += 1
        
        logger.info(f"Mistral API terminé en {elapsed:.1f}s - {input_tokens}+{output_tokens} tokens = {call_cost:.6f}€")

        return content

    except requests.exceptions.Timeout:
        raise LLMStructureError(f"Timeout Mistral API ({timeout}s)")
    except requests.exceptions.HTTPError as e:
        raise LLMStructureError(f"Erreur HTTP Mistral: {e}")
    except Exception as e:
        raise LLMStructureError(f"Erreur Mistral API: {e}")


def _prepare_prompt(
    markdown: str,
    hierarchy: Dict[str, Any],
    max_chars: int = 8000,
) -> str:
    """Prépare le prompt pour le LLM.
    
    Args:
        markdown: Texte Markdown du document
        hierarchy: Structure hiérarchique initiale
        max_chars: Nombre max de caractères du Markdown à inclure
    
    Returns:
        Prompt formaté pour le LLM
    """
    # Tronquer le Markdown si nécessaire
    truncated: str = markdown[:max_chars]
    if len(markdown) > max_chars:
        truncated += f"\n\n... [tronqué à {max_chars} caractères]"
    
    # Sérialiser la hiérarchie
    outline_json: str = json.dumps(hierarchy, ensure_ascii=False, indent=2)
    
    prompt: str = f"""Tu es un expert en édition scientifique chargé d'analyser la structure logique d'un document.

IMPORTANT: Réponds UNIQUEMENT avec un objet JSON valide. Pas de texte avant ou après.

À partir du Markdown OCRisé et d'un premier découpage hiérarchique, tu dois :
1. Identifier les parties liminaires (préface, introduction...), le corps du document (parties, chapitres, sections) et les parties finales (conclusion, annexes, bibliographie...).
2. Reconstruire l'organisation réelle du texte.
3. Produire un JSON avec :
   - "document_structure": vue hiérarchique du document
   - "chunks": liste des chunks avec chunk_id, text, hierarchy, type

FORMAT DE RÉPONSE (entre balises <JSON></JSON>):
<JSON>
{{
  "document_structure": [
    {{
      "path": {{"part": "Titre"}},
      "type": "main_content",
      "page_start": 1,
      "page_end": 10
    }}
  ],
  "chunks": [
    {{
      "chunk_id": "chunk_00001",
      "text": "Contenu...",
      "hierarchy": {{
        "part": "Titre partie",
        "chapter": "Titre chapitre",
        "section": null,
        "subsection": null
      }},
      "type": "main_content",
      "is_toc": false
    }}
  ]
}}
</JSON>

### Hiérarchie initiale
{outline_json}

### Markdown OCR
{truncated}

Réponds UNIQUEMENT avec le JSON entre <JSON> et </JSON>."""

    return prompt.strip()


def _call_ollama(
    prompt: str,
    model: str,
    base_url: Optional[str] = None,
    temperature: float = 0.2,
    timeout: int = 300,
) -> str:
    """Appelle Ollama pour générer une réponse.
    
    Args:
        prompt: Le prompt à envoyer
        model: Nom du modèle Ollama
        base_url: URL de base d'Ollama
        temperature: Température du modèle
        timeout: Timeout en secondes
    
    Returns:
        Réponse textuelle du LLM
    
    Raises:
        LLMStructureError: En cas d'erreur d'appel
    """
    # Essayer d'abord le SDK ollama
    try:
        import ollama

        logger.info(f"Appel Ollama SDK - modèle: {model}, timeout: {timeout}s")

        # Note: Le SDK ollama ne supporte pas directement le timeout
        # On utilise un wrapper avec threading.Timer pour forcer le timeout
        result_container: OllamaResultContainer = {"response": None, "error": None, "done": False}

        def _run_ollama_call() -> None:
            try:
                resp: Any
                if hasattr(ollama, "generate"):
                    resp = ollama.generate(
                        model=model,
                        prompt=prompt,
                        stream=False,
                        options={"temperature": temperature}
                    )
                    if isinstance(resp, dict):
                        result_container["response"] = resp.get("response", json.dumps(resp))
                    elif hasattr(resp, "response"):
                        result_container["response"] = resp.response
                    else:
                        result_container["response"] = str(resp)
                else:
                    # Fallback sur chat
                    resp = ollama.chat(
                        model=model,
                        messages=[{"role": "user", "content": prompt}],
                        options={"temperature": temperature}
                    )
                    if isinstance(resp, dict):
                        result_container["response"] = resp.get("message", {}).get("content", str(resp))
                    else:
                        result_container["response"] = str(resp)
                result_container["done"] = True
            except Exception as e:
                result_container["error"] = e
                result_container["done"] = True

        thread: threading.Thread = threading.Thread(target=_run_ollama_call, daemon=True)
        thread.start()
        thread.join(timeout=timeout)

        if not result_container["done"]:
            raise LLMStructureError(f"Timeout Ollama SDK après {timeout}s (modèle: {model})")

        if result_container["error"]:
            raise result_container["error"]

        if result_container["response"]:
            return result_container["response"]

        raise LLMStructureError("Aucune réponse du SDK Ollama")
            
    except ImportError:
        logger.info("SDK ollama non disponible, utilisation de l'API HTTP")
    except Exception as e:
        logger.warning(f"Erreur SDK ollama: {e}, fallback HTTP")
    
    # Fallback HTTP
    base: str = base_url or _get_ollama_url()
    url: str = f"{base.rstrip('/')}/api/generate"
    
    payload: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }
    
    # Retry avec backoff
    max_retries: int = 2
    backoff: float = 1.0
    
    for attempt in range(max_retries + 1):
        try:
            logger.info(f"Appel HTTP Ollama (tentative {attempt + 1})")
            response: requests.Response = requests.post(url, json=payload, timeout=timeout)
            
            if response.status_code != 200:
                raise LLMStructureError(
                    f"Erreur Ollama ({response.status_code}): {response.text}"
                )
            
            data: Dict[str, Any] = response.json()
            if "response" not in data:
                raise LLMStructureError(f"Réponse Ollama inattendue: {data}")
            
            return cast(str, data["response"])
            
        except requests.RequestException as e:
            if attempt < max_retries:
                time.sleep(backoff)
                backoff *= 2
                continue
            raise LLMStructureError(f"Impossible de contacter Ollama: {e}") from e
    
    raise LLMStructureError("Échec après plusieurs tentatives")


# ═══════════════════════════════════════════════════════════════════════════════
# Fonction générique d'appel LLM
# ═══════════════════════════════════════════════════════════════════════════════

def call_llm(
    prompt: str,
    model: Optional[str] = None,
    provider: str = "ollama",  # "ollama" ou "mistral"
    temperature: float = 0.2,
    timeout: int = 300,
) -> str:
    """Appelle un LLM (Ollama local ou Mistral API).
    
    Args:
        prompt: Le prompt à envoyer
        model: Nom du modèle (auto-détecté si None)
        provider: "ollama" (local, lent) ou "mistral" (API, rapide)
        temperature: Température du modèle
        timeout: Timeout en secondes
    
    Returns:
        Réponse textuelle du LLM
    """
    resolved_model: str
    if provider == "mistral":
        # Mistral API (rapide, cloud)
        resolved_model = model or _get_default_mistral_model()
        return _call_mistral_api(
            prompt,
            model=resolved_model,
            temperature=temperature,
            timeout=timeout,
        )
    else:
        # Ollama (local, lent mais gratuit)
        resolved_model = model or _get_default_model()
        return _call_ollama(
            prompt,
            model=resolved_model,
            temperature=temperature,
            timeout=timeout,
        )


def _clean_json_string(json_str: str) -> str:
    """Nettoie une chaîne JSON des caractères de contrôle invalides.
    
    Stratégie robuste : Remplace TOUS les caractères de contrôle (x00-x1f)
    par des espaces, puis réduit les espaces multiples. Cela évite les erreurs
    "Invalid control character" de json.loads().
    """
    # Remplacer tous les caractères de contrôle par des espaces
    cleaned: str = re.sub(r'[\x00-\x1f]', ' ', json_str)
    # Réduire les espaces multiples
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned


def _extract_json(text: str) -> LLMStructuredResult:
    """Extrait le JSON de la réponse du LLM.
    
    Args:
        text: Réponse textuelle du LLM
    
    Returns:
        Dictionnaire JSON parsé
    
    Raises:
        LLMStructureError: Si le JSON est invalide ou absent
    """
    # Chercher entre balises <JSON> et </JSON>
    json_start: int = text.find("<JSON>")
    json_end: int = text.find("</JSON>")
    
    if json_start != -1 and json_end != -1 and json_end > json_start:
        json_content: str = text[json_start + 6:json_end].strip()
        json_content = _clean_json_string(json_content)
        
        try:
            result: Dict[str, Any] = json.loads(json_content)
            if "chunks" not in result:
                raise LLMStructureError(
                    f"JSON sans clé 'chunks'. Clés: {list(result.keys())}"
                )
            return cast(LLMStructuredResult, result)
        except json.JSONDecodeError:
            pass  # Fallback ci-dessous
    
    # Fallback: chercher par accolades
    start: int = text.find("{")
    end: int = text.rfind("}")
    
    if start == -1 or end == -1 or end <= start:
        raise LLMStructureError(
            f"Pas de JSON trouvé dans la réponse.\nDébut: {text[:500]}"
        )
    
    json_str: str = _clean_json_string(text[start:end + 1])
    
    try:
        result = json.loads(json_str)
        if "chunks" not in result:
            raise LLMStructureError(
                f"JSON sans clé 'chunks'. Clés: {list(result.keys())}"
            )
        return cast(LLMStructuredResult, result)
    except json.JSONDecodeError as e:
        raise LLMStructureError(f"JSON invalide: {e}\nContenu: {json_str[:500]}") from e


def structure_with_llm(
    markdown: str,
    hierarchy: Dict[str, Any],
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: float = 0.2,
    max_chars: int = 8000,
    timeout: int = 300,
) -> LLMStructuredResult:
    """Améliore la structure d'un document via LLM.
    
    Args:
        markdown: Texte Markdown du document
        hierarchy: Structure hiérarchique initiale (de build_hierarchy)
        model: Modèle Ollama à utiliser
        base_url: URL de base d'Ollama
        temperature: Température du modèle
        max_chars: Nombre max de caractères du Markdown
        timeout: Timeout en secondes
    
    Returns:
        Structure améliorée avec document_structure et chunks
    
    Raises:
        LLMStructureError: En cas d'erreur
    """
    resolved_model: str = model or _get_default_model()
    
    logger.info(f"Structuration LLM - modèle: {resolved_model}")
    
    # Préparer le prompt
    prompt: str = _prepare_prompt(markdown, hierarchy, max_chars)
    
    # Appeler le LLM
    raw_response: str = _call_ollama(
        prompt,
        model=resolved_model,
        base_url=base_url,
        temperature=temperature,
        timeout=timeout,
    )
    
    # Extraire le JSON
    return _extract_json(raw_response)

