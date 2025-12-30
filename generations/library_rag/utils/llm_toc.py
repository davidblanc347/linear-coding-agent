"""LLM-based Table of Contents (TOC) extraction module.

This module provides functionality to extract hierarchical table of contents
from markdown documents using Large Language Models. It intelligently parses
document structure and creates both hierarchical and flat representations
of the TOC.

Key Features:
    - Hierarchical TOC extraction with chapters, sections, and subsections
    - Flat TOC generation with full paths for navigation
    - Content-to-TOC matching for associating sections with TOC entries
    - Support for multiple LLM providers (Ollama local, Mistral API)

TOC Structure Levels:
    - Level 1: Introduction, main chapters, Conclusion, Bibliography
    - Level 2: Sections listed under a chapter (same visual level)
    - Level 3: Only if explicit indentation or subsection visible

Typical Usage:
    >>> from utils.llm_toc import extract_toc
    >>> result = extract_toc(
    ...     markdown=document_text,
    ...     document_title="The Republic",
    ...     provider="ollama"
    ... )
    >>> print(result["toc"])  # Hierarchical structure
    [
        {
            "title": "Introduction",
            "level": 1,
            "children": []
        },
        {
            "title": "Book I: Justice",
            "level": 1,
            "chapter_number": 1,
            "children": [
                {"title": "The Nature of Justice", "level": 2, "children": []}
            ]
        }
    ]
    >>> print(result["flat_toc"])  # Flat list with paths
    [
        {"title": "Introduction", "level": 1, "path": "Introduction"},
        {"title": "Book I: Justice", "level": 1, "path": "Book I: Justice"},
        {
            "title": "The Nature of Justice",
            "level": 2,
            "path": "Book I: Justice > The Nature of Justice"
        }
    ]

LLM Provider Options:
    - "ollama": Local processing, free but slower
    - "mistral": Cloud API, faster but incurs costs

Note:
    For documents without a clear TOC (short articles, book reviews),
    the module returns an empty TOC list rather than inventing structure.

See Also:
    - llm_metadata: Document metadata extraction
    - llm_classifier: Section classification
    - toc_extractor: Non-LLM TOC extraction alternatives
"""

import json
import logging
import re
from typing import cast, Any, Dict, List, Optional

from .llm_structurer import (
    _clean_json_string,
    _get_default_mistral_model,
    _get_default_model,
    call_llm,
)
from .types import FlatTOCEntry, LLMProvider, TOCEntry, TOCResult

logger: logging.Logger = logging.getLogger(__name__)


def _extract_json_from_response(text: str) -> Dict[str, Any]:
    """Extract JSON data from an LLM response.

    Parses the LLM response to extract JSON content, handling both
    explicitly tagged JSON (between <JSON></JSON> tags) and raw JSON
    embedded in the response text.

    Args:
        text: The raw LLM response text that may contain JSON.

    Returns:
        A dictionary containing the parsed JSON data. Returns
        {"toc": []} if no valid JSON can be extracted.

    Note:
        This function attempts two parsing strategies:
        1. Look for JSON between <JSON></JSON> tags
        2. Find JSON by locating first '{' and last '}'
    """
    json_match: Optional[re.Match[str]] = re.search(r'<JSON>\s*(.*?)\s*</JSON>', text, re.DOTALL)
    if json_match:
        json_str: str = _clean_json_string(json_match.group(1))
        try:
            result: Dict[str, Any] = json.loads(json_str)
            return result
        except json.JSONDecodeError:
            pass

    start: int = text.find("{")
    end: int = text.rfind("}")
    if start != -1 and end > start:
        json_str = _clean_json_string(text[start:end + 1])
        try:
            result = json.loads(json_str)
            return result
        except json.JSONDecodeError as e:
            logger.warning(f"JSON invalide: {e}")

    return {"toc": []}


def extract_toc(
    markdown: str,
    document_title: Optional[str] = None,
    model: Optional[str] = None,
    provider: LLMProvider = "ollama",
    temperature: float = 0.1,
) -> Dict[str, Any]:
    r"""Extract a structured table of contents from a document using LLM.

    Analyzes markdown content to identify the document's hierarchical
    structure and generates both a nested TOC (with children) and a
    flat TOC (with navigation paths).

    Args:
        markdown: Complete markdown text of the document to analyze.
        document_title: Optional title of the document for context.
            Helps the LLM better understand the document structure.
        model: LLM model name to use. If None, uses the default model
            for the specified provider.
        provider: LLM provider to use. Either "ollama" for local
            processing or "mistral" for cloud API.
        temperature: Model temperature for response generation.
            Lower values (0.1) produce more consistent results.

    Returns:
        A dictionary containing:
            - toc: Hierarchical list of TOC entries, each with:
                - title: Section title
                - level: Hierarchy level (1, 2, or 3)
                - chapter_number: Optional chapter number
                - children: List of nested TOC entries
            - flat_toc: Flat list of all TOC entries with paths:
                - title: Section title
                - level: Hierarchy level
                - path: Full navigation path (e.g., "Chapter 1 > Section 1")
            - error: Error message string (only if extraction failed)

    Raises:
        No exceptions are raised; errors are captured in the return dict.

    Example:
        >>> result = extract_toc(
        ...     markdown="# Introduction\n...\n# Chapter 1\n## Section 1.1",
        ...     document_title="My Book",
        ...     provider="ollama"
        ... )
        >>> len(result["toc"])
        2
        >>> result["toc"][0]["title"]
        'Introduction'

    Note:
        - Documents longer than 12,000 characters are truncated
        - Short articles without clear TOC return empty lists
        - The LLM is instructed to never invent structure
    """
    if model is None:
        model = _get_default_mistral_model() if provider == "mistral" else _get_default_model()

    # Tronquer si trop long mais garder les sections importantes
    max_chars: int = 12000
    content: str = markdown[:max_chars]
    if len(markdown) > max_chars:
        content += "\n\n[... suite du document ...]"

    title_context: str = f"Titre du document: {document_title}\n" if document_title else ""

    prompt: str = f"""Tu es un expert en structuration de documents académiques.

TÂCHE: Extraire la table des matières FIDÈLE au document fourni.

{title_context}
⚠️ RÈGLES CRITIQUES:

1. **ANALYSER LE DOCUMENT RÉEL** - Ne JAMAIS copier les exemples ci-dessous!
2. **DOCUMENTS SANS TOC** - Si le document est un article court, une revue de livre, ou n'a pas de table des matières explicite, retourner {{"toc": []}}
3. **RESPECTER LA STRUCTURE PLATE** - Ne pas inventer de hiérarchie entre des lignes au même niveau
4. **IGNORER** - Métadonnées éditoriales (DOI, ISBN, éditeur, copyright, numéros de page)

NIVEAUX DE STRUCTURE:
- level 1: Introduction, Chapitres principaux, Conclusion, Bibliographie
- level 2: Sections listées sous un chapitre (même niveau visuel)
- level 3: UNIQUEMENT si indentation ou sous-titre explicite visible

FORMAT DE RÉPONSE (JSON entre balises <JSON></JSON>):

Pour un livre avec TOC:
<JSON>
{{
    "toc": [
        {{
            "title": "Titre Chapitre 1",
            "level": 1,
            "chapter_number": 1,
            "children": [
                {{"title": "Section 1.1", "level": 2, "children": []}},
                {{"title": "Section 1.2", "level": 2, "children": []}}
            ]
        }}
    ]
}}
</JSON>

Pour un article SANS TOC (revue de livre, article court, etc.):
<JSON>
{{
    "toc": []
}}
</JSON>

⚠️ NE PAS COPIER CES EXEMPLES ! Analyser uniquement le DOCUMENT RÉEL ci-dessous.

DOCUMENT À ANALYSER:
{content}

Réponds UNIQUEMENT avec le JSON correspondant à CE document (pas aux exemples)."""

    logger.info(f"Extraction TOC via {provider.upper()} ({model})")

    try:
        response: str = call_llm(prompt, model=model, provider=provider, temperature=temperature, timeout=360)
        result: Dict[str, Any] = _extract_json_from_response(response)

        toc: List[Dict[str, Any]] = result.get("toc", [])

        # Générer la version plate de la TOC
        flat_toc: List[Dict[str, Any]] = _flatten_toc(toc)

        logger.info(f"TOC extraite: {len(toc)} entrées niveau 1, {len(flat_toc)} entrées totales")

        return {
            "toc": toc,
            "flat_toc": flat_toc,
        }

    except Exception as e:
        logger.error(f"Erreur extraction TOC: {e}")
        return {
            "toc": [],
            "flat_toc": [],
            "error": str(e),
        }


def _flatten_toc(
    toc: List[Dict[str, Any]],
    parent_path: str = "",
    result: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """Flatten a hierarchical TOC into a list with navigation paths.

    Recursively traverses a nested TOC structure and produces a flat
    list where each entry includes its full path from the root.

    Args:
        toc: Hierarchical TOC list with nested children.
        parent_path: Path accumulated from parent entries. Used
            internally during recursion.
        result: Accumulator list for results. Used internally
            during recursion.

    Returns:
        A flat list of TOC entries, each containing:
            - title: The section title
            - level: Hierarchy level (1, 2, or 3)
            - path: Full navigation path (e.g., "Chapter > Section")
            - chapter_number: Optional chapter number if present

    Example:
        >>> hierarchical_toc = [
        ...     {
        ...         "title": "Chapter 1",
        ...         "level": 1,
        ...         "children": [
        ...             {"title": "Section 1.1", "level": 2, "children": []}
        ...         ]
        ...     }
        ... ]
        >>> flat = _flatten_toc(hierarchical_toc)
        >>> flat[0]["path"]
        'Chapter 1'
        >>> flat[1]["path"]
        'Chapter 1 > Section 1.1'
    """
    if result is None:
        result = []

    for item in toc:
        title: str = item.get("title", "")
        level: int = item.get("level", 1)

        # Construire le chemin
        path: str
        if parent_path:
            path = f"{parent_path} > {title}"
        else:
            path = title

        result.append({
            "title": title,
            "level": level,
            "path": path,
            "chapter_number": item.get("chapter_number"),
        })

        # Récursion sur les enfants
        children: List[Dict[str, Any]] = item.get("children", [])
        if children:
            _flatten_toc(children, path, result)

    return result


def match_content_to_toc(
    content_sections: List[Dict[str, Any]],
    flat_toc: List[Dict[str, Any]],
    model: Optional[str] = None,
    provider: LLMProvider = "ollama",
) -> List[Dict[str, Any]]:
    """Match content sections to TOC entries using LLM.

    Uses an LLM to intelligently associate extracted content sections
    with their corresponding entries in the table of contents. This
    enables navigation and context-aware content organization.

    Args:
        content_sections: List of content sections extracted from
            the document. Each section should have a "title" key.
        flat_toc: Flat TOC list as returned by extract_toc()["flat_toc"].
            Each entry should have a "title" key.
        model: LLM model name to use. If None, uses the default
            model for the specified provider.
        provider: LLM provider to use. Either "ollama" for local
            processing or "mistral" for cloud API.

    Returns:
        The input content_sections list with a "toc_match" key added
        to each section. The value is either:
            - The matched TOC entry dict (if a match was found)
            - None (if no match was found)

    Example:
        >>> sections = [{"title": "Introduction"}, {"title": "Methods"}]
        >>> toc = [{"title": "Introduction", "level": 1, "path": "Introduction"}]
        >>> matched = match_content_to_toc(sections, toc)
        >>> matched[0]["toc_match"]["title"]
        'Introduction'
        >>> matched[1]["toc_match"] is None
        True

    Note:
        - Only the first 30 content sections are processed to limit costs
        - Failed matches are silently handled (sections get toc_match=None)
    """
    if model is None:
        model = _get_default_mistral_model() if provider == "mistral" else _get_default_model()

    # Préparer les données pour le prompt
    toc_titles: List[str] = [item["title"] for item in flat_toc]
    section_titles: List[str] = [s.get("title", "") for s in content_sections[:30]]  # Limiter

    prompt: str = f"""Tu dois associer les sections de contenu aux entrées de la table des matières.

TABLE DES MATIÈRES:
{json.dumps(toc_titles, ensure_ascii=False, indent=2)}

SECTIONS DE CONTENU:
{json.dumps(section_titles, ensure_ascii=False, indent=2)}

Pour chaque section de contenu, indique l'index (0-based) de l'entrée TOC correspondante.
Si pas de correspondance, indique -1.

RÉPONDS avec un JSON:
<JSON>
{{
    "matches": [0, 1, 2, -1, 3, ...]
}}
</JSON>
"""

    try:
        response: str = call_llm(prompt, model=model, provider=provider, temperature=0.1)
        result: Dict[str, Any] = _extract_json_from_response(response)
        matches: List[int] = result.get("matches", [])

        # Appliquer les correspondances
        for i, section in enumerate(content_sections):
            if i < len(matches) and matches[i] >= 0 and matches[i] < len(flat_toc):
                section["toc_match"] = flat_toc[matches[i]]
            else:
                section["toc_match"] = None

        return content_sections

    except Exception as e:
        logger.warning(f"Erreur correspondance TOC: {e}")
        return content_sections
