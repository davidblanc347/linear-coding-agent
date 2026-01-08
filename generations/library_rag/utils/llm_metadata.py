r"""LLM-based bibliographic metadata extraction from documents.

This module extracts bibliographic metadata (title, author, publisher, year, etc.)
from document text using Large Language Models. It supports both local (Ollama)
and cloud-based (Mistral API) LLM providers.

The extraction process:
    1. Takes the first N characters of the document markdown (typically first pages)
    2. Sends a structured prompt to the LLM requesting JSON-formatted metadata
    3. Parses the LLM response to extract the JSON data
    4. Applies default values and cleanup for missing/invalid fields

Supported metadata fields:
    - title: Document title (including subtitle if present)
    - author: Primary author name
    - collection: Series or collection name
    - publisher: Publisher name
    - year: Publication year
    - doi: Digital Object Identifier
    - isbn: ISBN number
    - language: ISO 639-1 language code (default: "fr")
    - confidence: Dict of confidence scores per field (0.0-1.0)

LLM Provider Differences:
    - **Ollama** (local): Free, slower, requires local installation.
      Uses models like "mistral", "llama2", "mixtral".
    - **Mistral API** (cloud): Fast, paid (~0.002€/call for small prompts).
      Uses models like "mistral-small-latest", "mistral-medium-latest".

Cost Implications:
    - Ollama: No API cost, only local compute resources
    - Mistral API: ~0.002€ per metadata extraction call (small prompt)

Example:
    >>> from utils.llm_metadata import extract_metadata
    >>>
    >>> markdown = '''
    ... # La technique et le temps
    ... ## Tome 1 : La faute d'Épiméthée
    ...
    ... Bernard Stiegler
    ...
    ... Éditions Galilée, 1994
    ... '''
    >>>
    >>> metadata = extract_metadata(markdown, provider="ollama")
    >>> print(metadata)
    {
        'title': 'La technique et le temps. Tome 1 : La faute d\'Épiméthée',
        'author': 'Bernard Stiegler',
        'publisher': 'Éditions Galilée',
        'year': 1994,
        'language': 'fr',
        'confidence': {'title': 0.95, 'author': 0.98}
    }

See Also:
    - llm_toc: Table of contents extraction via LLM
    - llm_structurer: Core LLM call infrastructure
    - pdf_pipeline: Orchestration using this module (Step 4)
"""

import json
import logging
import re
from typing import Any, Dict, Optional

from .llm_structurer import (
    _clean_json_string,
    _get_default_mistral_model,
    _get_default_model,
    call_llm,
)
from .types import LLMProvider

logger: logging.Logger = logging.getLogger(__name__)


def _extract_json_from_response(text: str) -> Dict[str, Any]:
    """Extract JSON data from an LLM response string.

    Attempts to parse JSON from the LLM response using two strategies:
    1. First, looks for JSON enclosed in <JSON></JSON> tags (preferred format)
    2. Falls back to finding the first {...} block in the response

    The function applies JSON string cleaning to handle common LLM quirks
    like trailing commas, unescaped quotes, etc.

    Args:
        text: Raw LLM response text that may contain JSON data.

    Returns:
        Parsed JSON as a dictionary. Returns empty dict if no valid
        JSON could be extracted.

    Example:
        >>> response = '<JSON>{"title": "Test", "author": "Smith"}</JSON>'
        >>> _extract_json_from_response(response)
        {'title': 'Test', 'author': 'Smith'}

        >>> response = 'Here is the metadata: {"title": "Test"}'
        >>> _extract_json_from_response(response)
        {'title': 'Test'}
    """
    # Chercher entre balises <JSON> et </JSON>
    json_match: Optional[re.Match[str]] = re.search(r'<JSON>\s*(.*?)\s*</JSON>', text, re.DOTALL)
    if json_match:
        json_str: str = _clean_json_string(json_match.group(1))
        try:
            result: Dict[str, Any] = json.loads(json_str)
            return result
        except json.JSONDecodeError:
            pass

    # Fallback: chercher le premier objet JSON
    start: int = text.find("{")
    end: int = text.rfind("}")
    if start != -1 and end > start:
        json_str = _clean_json_string(text[start:end + 1])
        try:
            result = json.loads(json_str)
            return result
        except json.JSONDecodeError as e:
            logger.warning(f"JSON invalide: {e}")

    return {}


def extract_metadata(
    markdown: str,
    model: Optional[str] = None,
    provider: LLMProvider = "ollama",
    temperature: float = 0.1,
    max_chars: int = 6000,
) -> Dict[str, Any]:
    """Extract bibliographic metadata from a document using an LLM.

    Analyzes the beginning of a document (typically first few pages) to extract
    bibliographic metadata including title, author, publisher, year, and more.
    Uses a structured prompt that guides the LLM to distinguish between
    document title vs. collection name vs. publisher name.

    The LLM is instructed to return confidence scores for extracted fields,
    allowing downstream processing to handle uncertain extractions appropriately.

    Args:
        markdown: Document text in Markdown format. For best results, provide
            at least the first 2-3 pages containing title page and colophon.
        model: LLM model name to use. If None, uses the default model for the
            selected provider (e.g., "mistral" for Ollama, "mistral-small-latest"
            for Mistral API).
        provider: LLM provider to use. Options are:
            - "ollama": Local LLM (free, slower, requires Ollama installation)
            - "mistral": Mistral API (fast, paid, requires API key)
        temperature: Model temperature for generation. Lower values (0.0-0.3)
            produce more consistent, deterministic results. Default 0.1.
        max_chars: Maximum number of characters to send to the LLM. Longer
            documents are truncated. Default 6000 (~2 pages).

    Returns:
        Dictionary containing extracted metadata with the following keys:
            - title (str | None): Document title with subtitle if present
            - author (str | None): Primary author name
            - collection (str | None): Series or collection name
            - publisher (str | None): Publisher name
            - year (int | None): Publication year
            - doi (str | None): Digital Object Identifier
            - isbn (str | None): ISBN number
            - language (str): ISO 639-1 language code (default "fr")
            - confidence (dict): Confidence scores per field (0.0-1.0)
            - error (str): Error message if extraction failed (only on error)

    Raises:
        No exceptions are raised; errors are captured in the return dict.

    Note:
        - Cost for Mistral API: ~0.002€ per call (6000 chars input)
        - Ollama is free but requires local GPU/CPU resources
        - The prompt is in French as most processed documents are French texts
        - Low temperature (0.1) is used for consistent metadata extraction

    Example:
        >>> # Extract from first pages of a philosophy book
        >>> markdown = Path("output/stiegler/stiegler.md").read_text()[:6000]
        >>> metadata = extract_metadata(markdown, provider="ollama")
        >>> print(f"Title: {metadata['title']}")
        Title: La technique et le temps

        >>> # Using Mistral API for faster extraction
        >>> metadata = extract_metadata(markdown, provider="mistral")
        >>> print(f"Author: {metadata['author']} (confidence: {metadata['confidence'].get('author', 'N/A')})")
        Author: Bernard Stiegler (confidence: 0.98)
    """
    if model is None:
        model = _get_default_mistral_model() if provider == "mistral" else _get_default_model()
    
    # Prendre les premières pages (métadonnées souvent au début)
    content: str = markdown[:max_chars]
    if len(markdown) > max_chars:
        content += "\n\n[... document tronqué ...]"
    
    prompt: str = f"""Tu es un expert en bibliographie et édition scientifique.

TÂCHE: Extraire les métadonnées bibliographiques de ce document.

ATTENTION - PIÈGES COURANTS:
- Le titre n'est PAS forcément le premier titre H1 (peut être le nom de la collection)
- Le sous-titre fait partie du titre
- L'auteur peut apparaître sous le titre, dans les métadonnées éditeur, ou ailleurs
- Distingue bien: titre de l'œuvre ≠ nom de la collection/série ≠ nom de l'éditeur

INDICES POUR TROUVER LE VRAI TITRE:
- Souvent en plus grand / plus visible
- Accompagné du nom de l'auteur juste après
- Répété sur la page de garde et la page de titre
- Peut contenir un sous-titre après ":"

RÈGLES CRITIQUES - FORMAT DES DONNÉES:
❌ INTERDIT: N'ajoute JAMAIS d'annotations, commentaires ou instructions dans les valeurs
❌ INTERDIT: "(correct)", "(à confirmer)", "(possiblement)", "(ex:)", "(si c'est bien...)"
❌ INTERDIT: "À confirmer avec...", "Vérifier si...", "Possiblement...", "Titre corrigé..."
❌ INTERDIT: "Auteur à identifier", "Nom de l'auteur si disponible"

✅ OBLIGATOIRE: Retourne UNIQUEMENT le titre exact tel qu'il apparaît dans le document
✅ OBLIGATOIRE: Retourne UNIQUEMENT le nom de l'auteur tel qu'il apparaît
✅ Si incertain: utilise le champ "confidence" avec un score bas (0.3-0.6)
✅ Si vraiment introuvable: utilise null (pas de phrase descriptive)

EXEMPLE DE BONNE RÉPONSE (extrait d'un vrai livre):
<JSON>
{{
    "title": "La technique et le temps: La faute d'Épiméthée",
    "author": "Bernard Stiegler",
    "collection": "Philosophie",
    "publisher": "Éditions Galilée",
    "year": 1994,
    "doi": null,
    "isbn": "978-2-7186-0489-8",
    "language": "fr",
    "confidence": {{
        "title": 0.95,
        "author": 0.98
    }}
}}
</JSON>

EXEMPLE si métadonnées incertaines:
<JSON>
{{
    "title": "Between Past and Future",
    "author": "Hannah Arendt",
    "collection": null,
    "publisher": null,
    "year": null,
    "doi": null,
    "isbn": null,
    "language": "en",
    "confidence": {{
        "title": 0.7,
        "author": 0.85
    }}
}}
</JSON>

DOCUMENT À ANALYSER:
{content}

RAPPEL: Retourne UNIQUEMENT le JSON avec les valeurs EXACTES du document, SANS commentaires ni annotations.

<JSON>
{{
    "title": "",
    "author": "",
    "collection": null,
    "publisher": null,
    "year": null,
    "doi": null,
    "isbn": null,
    "language": "fr",
    "confidence": {{}}
}}
</JSON>"""

    logger.info(f"Extraction métadonnées via {provider.upper()} ({model})")
    
    try:
        response: str = call_llm(prompt, model=model, provider=provider, temperature=temperature)
        metadata: Dict[str, Any] = _extract_json_from_response(response)
        
        # Valeurs par défaut si non trouvées
        defaults: Dict[str, Optional[str]] = {
            "title": None,
            "author": None,
            "collection": None,
            "publisher": None,
            "year": None,
            "doi": None,
            "isbn": None,
            "language": "fr",
        }
        
        for key, default in defaults.items():
            if key not in metadata or metadata[key] == "":
                metadata[key] = default
        
        # Nettoyer les valeurs "null" string
        for key in metadata:
            if metadata[key] == "null" or metadata[key] == "None":
                metadata[key] = None
        
        logger.info(f"Métadonnées extraites: titre='{metadata.get('title')}', auteur='{metadata.get('author')}'")
        return metadata
        
    except Exception as e:
        logger.error(f"Erreur extraction métadonnées: {e}")
        return {
            "title": None,
            "author": None,
            "collection": None,
            "publisher": None,
            "year": None,
            "doi": None,
            "isbn": None,
            "language": "fr",
            "error": str(e),
        }

