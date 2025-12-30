"""LLM-based section classification module for document structure analysis.

This module provides functionality to classify document sections by type
(front_matter, chapter, appendix, etc.) using Large Language Models and
determine which sections should be indexed for semantic search.

Key Features:
    - Section classification via LLM (classify_sections)
    - Automatic TOC/metadata section exclusion (is_excluded_section)
    - Post-classification validation (validate_classified_sections)
    - Filtering for indexable content (filter_indexable_sections)

Section Types:
    The following section types are recognized:

    **Indexable Content (should_index=True):**
        - chapter: Main document content, essays, articles, book reviews
        - introduction: Document introductions
        - conclusion: Document conclusions
        - preface: Prefaces, forewords, warnings (intellectual content)
        - abstract: Summaries, abstracts

    **Non-Indexable Content (should_index=False):**
        - front_matter: Title pages, copyright, credits, colophon
        - toc_display: Table of contents display (not content)
        - appendix: Document appendices
        - bibliography: References, bibliography
        - index: Document index
        - notes: End notes
        - ignore: Ads, empty pages, technical metadata

Classification Strategy:
    1. LLM analyzes section titles and content previews
    2. Automatic exclusion rules catch common TOC/metadata patterns
    3. Post-classification validation detects false positives
    4. Filtering extracts only indexable content

Typical Usage:
    >>> from utils.llm_classifier import classify_sections, filter_indexable_sections
    >>> sections = [
    ...     {"title": "Table of Contents", "content": "...", "level": 1},
    ...     {"title": "Introduction", "content": "...", "level": 1},
    ...     {"title": "Chapter 1", "content": "...", "level": 1}
    ... ]
    >>> classified = classify_sections(sections, provider="ollama")
    >>> indexable = filter_indexable_sections(classified)
    >>> print([s["title"] for s in indexable])
    ['Introduction', 'Chapter 1']

LLM Provider Options:
    - "ollama": Local processing, free but slower
    - "mistral": Cloud API, faster but incurs costs

Note:
    The classifier is designed to handle edge cases like:
    - Book reviews with analytical content (classified as chapter)
    - Editor's notes without analysis (classified as front_matter)
    - TOC fragments embedded in content (detected and excluded)

See Also:
    - llm_toc: Table of contents extraction
    - llm_chunker: Semantic chunking of classified sections
    - llm_metadata: Document metadata extraction
"""

from __future__ import annotations

import json
import logging
import re
from typing import cast, Any, Dict, Final

from .llm_structurer import (
    _clean_json_string,
    _get_default_mistral_model,
    _get_default_model,
    call_llm,
)
from .types import LLMProvider

logger: logging.Logger = logging.getLogger(__name__)


# Types de sections possibles
SECTION_TYPES: Final[dict[str, str]] = {
    "front_matter": "Métadonnées, page de titre, copyright, crédits, NOTE DE L'ÉDITEUR, colophon",
    "toc_display": "Table des matières affichée (pas le contenu)",
    "preface": "Préface, avant-propos, avertissement (contenu intellectuel à indexer)",
    "abstract": "Résumé, abstract",
    "introduction": "Introduction de l'œuvre",
    "chapter": "Chapitre principal du document",
    "conclusion": "Conclusion de l'œuvre",
    "appendix": "Annexes",
    "bibliography": "Bibliographie, références",
    "index": "Index",
    "notes": "Notes de fin",
    "ignore": "À ignorer (publicités, pages vides, métadonnées techniques)",
}


def _extract_json_from_response(text: str) -> dict[str, Any]:
    """Extract JSON from LLM response text.

    Handles two formats:
    1. JSON wrapped in <JSON></JSON> tags
    2. Raw JSON object in the response

    Args:
        text: Raw LLM response text.

    Returns:
        Parsed JSON as dictionary. Returns {"classifications": []} on failure.
    """
    json_match: re.Match[str] | None = re.search(
        r'<JSON>\s*(.*?)\s*</JSON>', text, re.DOTALL
    )
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

    return {"classifications": []}


def classify_sections(
    sections: list[dict[str, Any]],
    document_title: str | None = None,
    model: str | None = None,
    provider: LLMProvider = "ollama",
    temperature: float = 0.1,
) -> list[dict[str, Any]]:
    """Classify document sections by type using LLM.

    Uses an LLM to analyze section titles and content previews to determine
    the type of each section (chapter, front_matter, toc_display, etc.) and
    whether it should be indexed for semantic search.

    Args:
        sections: List of section dictionaries with keys:
            - title: Section title
            - content: Section content (preview used)
            - level: Hierarchy level (1=chapter, 2=section, etc.)
        document_title: Optional document title for context.
        model: LLM model name. If None, uses provider default.
        provider: LLM provider ("ollama" or "mistral").
        temperature: Model temperature (0.0-1.0). Lower = more deterministic.

    Returns:
        Same sections list with added classification fields:
            - type: Section type (SectionType literal)
            - should_index: Whether to include in vector index
            - chapter_number: Chapter number if applicable
            - classification_reason: Explanation for the classification

    Example:
        >>> sections = [{"title": "Introduction", "content": "...", "level": 1}]
        >>> classified = classify_sections(sections, provider="ollama")
        >>> classified[0]["type"]
        'introduction'
        >>> classified[0]["should_index"]
        True
    """
    if model is None:
        model = _get_default_mistral_model() if provider == "mistral" else _get_default_model()

    # Préparer les sections pour le prompt
    sections_for_prompt: list[dict[str, Any]] = []
    for i, section in enumerate(sections[:50]):  # Limiter à 50 sections
        sections_for_prompt.append({
            "index": i,
            "title": section.get("title", ""),
            "preview": section.get("content", "")[:200] if section.get("content") else "",
            "level": section.get("level", 1),
        })

    types_description: str = "\n".join([f"- {k}: {v}" for k, v in SECTION_TYPES.items()])
    title_context: str = f"Titre du document: {document_title}\n" if document_title else ""

    prompt: str = f"""Tu es un expert en analyse de structure documentaire.

TÂCHE: Classifier chaque section selon son type.

{title_context}
TYPES DISPONIBLES:
{types_description}

RÈGLES:
1. "front_matter": UNIQUEMENT pages de titre SANS contenu, copyright, colophon (métadonnées pures)
2. "toc_display": la TABLE DES MATIÈRES elle-même (pas son contenu)
3. "preface": préface, avant-propos, avertissement (À INDEXER car contenu intellectuel)
4. "chapter": TOUT contenu principal - chapitres, sections, articles, revues de livre, essais
5. "ignore": publicités, pages vides, métadonnées techniques sans valeur

IMPORTANT - REVUES DE LIVRE ET ARTICLES:
- Une REVUE DE LIVRE ("Book Review") avec analyse critique → chapter, should_index = true
- Un ARTICLE académique avec contenu substantiel → chapter, should_index = true
- Les métadonnées éditoriales (auteur, affiliation, journal) au début d'un article NE sont PAS un motif pour classer comme "front_matter"
- Si le document contient un TEXTE ANALYTIQUE développé → chapter

CAS PARTICULIERS:
- "NOTE DE L'ÉDITEUR" (infos édition, réimpression, SANS analyse) → front_matter, should_index = false
- "PRÉFACE" ou "AVANT-PROPOS" (texte intellectuel) → preface, should_index = true
- "Book Review" ou "Article" avec paragraphes d'analyse → chapter, should_index = true

INDEXATION:
- should_index = true pour: preface, introduction, chapter, conclusion, abstract
- should_index = false pour: front_matter, toc_display, ignore

⚠️ ATTENTION AUX FAUX POSITIFS - LISTE DE TITRES VS CONTENU RÉEL:

LISTE DE TITRES (toc_display, should_index=false):
- Suite de titres courts sans texte explicatif
- Lignes commençant par "Comment...", "Où...", "Les dispositions à..."
- Énumération de sections sans phrase complète
- Exemple: "Comment fixer la croyance?\\nOù la croyance s'oppose au savoir\\nL'idéal de rationalité"

CONTENU RÉEL (chapter, should_index=true):
- Texte avec phrases complètes et verbes conjugués
- Paragraphes développés avec arguments
- Explications, définitions, raisonnements
- Exemple: "Comment fixer la croyance? Cette question se pose dès lors que..."

SECTIONS À CLASSIFIER:
{json.dumps(sections_for_prompt, ensure_ascii=False, indent=2)}

RÉPONDS avec un JSON entre <JSON></JSON>:

<JSON>
{{
    "classifications": [
        {{
            "index": 0,
            "type": "front_matter",
            "should_index": false,
            "chapter_number": null,
            "reason": "Page de titre avec métadonnées éditeur"
        }},
        {{
            "index": 1,
            "type": "chapter",
            "should_index": true,
            "chapter_number": 1,
            "reason": "Premier chapitre du document"
        }}
    ]
}}
</JSON>
"""

    logger.info(f"Classification de {len(sections_for_prompt)} sections via {provider.upper()} ({model})")

    try:
        response: str = call_llm(prompt, model=model, provider=provider, temperature=temperature, timeout=300)
        result: dict[str, Any] = _extract_json_from_response(response)
        classifications: list[dict[str, Any]] = result.get("classifications", [])

        # Créer un mapping index -> classification
        class_map: dict[int, dict[str, Any]] = {
            c["index"]: c for c in classifications if "index" in c
        }

        # Appliquer les classifications
        for i, section in enumerate(sections):
            if i in class_map:
                c: dict[str, Any] = class_map[i]
                section["type"] = c.get("type", "chapter")
                section["should_index"] = c.get("should_index", True)
                section["chapter_number"] = c.get("chapter_number")
                section["classification_reason"] = c.get("reason", "")
            else:
                # Défaut: traiter comme contenu
                section["type"] = "chapter"
                section["should_index"] = True
                section["chapter_number"] = None

        # Stats
        types_count: dict[str, int] = {}
        for s in sections:
            t: str = s.get("type", "unknown")
            types_count[t] = types_count.get(t, 0) + 1

        logger.info(f"Classification terminée: {types_count}")

        return sections

    except Exception as e:
        logger.error(f"Erreur classification sections: {e}")
        # En cas d'erreur, marquer tout comme indexable
        for section in sections:
            section["type"] = "chapter"
            section["should_index"] = True
        return sections


# Titres à exclure automatiquement (insensible à la casse)
EXCLUDED_SECTION_TITLES: Final[list[str]] = [
    "table des matières",
    "table des matieres",
    "sommaire",
    "table of contents",
    "contents",
    "toc",
    "index",
    "liste des figures",
    "liste des tableaux",
    "list of figures",
    "list of tables",
    "note de l'éditeur",
    "note de l'editeur",
    "note de la rédaction",
    "copyright",
    "mentions légales",
    "crédits",
    "colophon",
    "achevé d'imprimer",
]


def is_excluded_section(section: dict[str, Any]) -> bool:
    """Check if a section should be automatically excluded from indexing.

    Excludes sections based on:
    1. Title matching known TOC/metadata patterns
    2. Content analysis detecting TOC-like structure (short lines, title patterns)

    Args:
        section: Section dictionary with optional keys:
            - title: Section title
            - chapterTitle: Parent chapter title
            - content: Section content

    Returns:
        True if section should be excluded from indexing.

    Example:
        >>> is_excluded_section({"title": "Table des matières"})
        True
        >>> is_excluded_section({"title": "Introduction", "content": "..."})
        False
    """
    title: str = (section.get("title") or "").lower().strip()
    chapter_title: str = (section.get("chapterTitle") or "").lower().strip()

    # Vérifier le titre de la section
    for excluded in EXCLUDED_SECTION_TITLES:
        if excluded in title or title == excluded:
            return True
        if excluded in chapter_title or chapter_title == excluded:
            return True

    # Vérifier si le contenu ressemble à une liste de titres (TOC)
    content: str = section.get("content", "")
    if content:
        lines: list[str] = [l.strip() for l in content.split("\n") if l.strip()]

        # Si pas assez de lignes, pas de détection
        if len(lines) < 3:
            return False

        # Critère 1: Lignes courtes (moyenne < 50 chars)
        avg_len: float = sum(len(l) for l in lines) / len(lines)

        # Critère 2: Toutes les lignes sont courtes (< 100 chars)
        all_short: bool = all(len(l) < 100 for l in lines[:10])

        # Critère 3: Patterns typiques de titres de sections
        title_patterns: list[str] = [
            r'^Comment\s+.+\?',           # "Comment fixer la croyance?"
            r'^Où\s+.+',                  # "Où la croyance s'oppose"
            r'^Les?\s+\w+\s+à\s+',        # "Les dispositions à penser"
            r'^Que\s+.+\?',               # "Que peut-on savoir?"
            r'^L[ae]\s+\w+\s+(de|du)\s+', # "La critique de l'intuition"
            r'^Entre\s+.+\s+et\s+',       # "Entre nature et norme"
        ]

        # Compter combien de lignes matchent les patterns de titres
        title_like_count: int = 0
        for line in lines[:10]:
            for pattern in title_patterns:
                if re.match(pattern, line, re.IGNORECASE):
                    title_like_count += 1
                    break

        # Critère 4: Pas de verbes conjugués typiques du contenu narratif
        narrative_verbs: list[str] = [
            r'\best\b', r'\bsont\b', r'\bétait\b', r'\bsera\b',
            r'\ba\b', r'\bont\b', r'\bavait\b', r'\bavaient\b',
            r'\bfait\b', r'\bdit\b', r'\bpense\b', r'\bexplique\b'
        ]

        has_narrative: bool = False
        for line in lines[:5]:
            for verb_pattern in narrative_verbs:
                if re.search(verb_pattern, line, re.IGNORECASE):
                    has_narrative = True
                    break
            if has_narrative:
                break

        # Décision: C'est une liste de titres (TOC) si:
        # - Lignes courtes ET toutes < 100 chars ET (beaucoup de patterns de titres OU pas de verbes narratifs)
        if len(lines) >= 5 and avg_len < 50 and all_short:
            if title_like_count >= len(lines) * 0.4 or not has_narrative:
                logger.debug(f"Section '{title}' exclue: ressemble à une TOC (lignes courtes, {title_like_count}/{len(lines)} titres)")
                return True

    return False


def filter_indexable_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter sections to keep only those that should be indexed.

    Applies multiple exclusion criteria:
    1. Automatic exclusion by title pattern (TOC, index, etc.)
    2. Parent chapter exclusion (if parent is TOC)
    3. LLM classification (should_index flag)

    Args:
        sections: List of classified section dictionaries.

    Returns:
        Filtered list containing only indexable sections.

    Example:
        >>> sections = [
        ...     {"title": "TOC", "should_index": False},
        ...     {"title": "Chapter 1", "should_index": True}
        ... ]
        >>> filtered = filter_indexable_sections(sections)
        >>> len(filtered)
        1
    """
    filtered: list[dict[str, Any]] = []
    excluded_count: int = 0

    for s in sections:
        # Vérifier l'exclusion automatique
        if is_excluded_section(s):
            logger.info(f"Section exclue automatiquement: '{s.get('title', 'Sans titre')}'")
            excluded_count += 1
            continue

        # Vérifier si le chapitre parent est une TOC
        chapter_title: str = (s.get("chapterTitle") or "").lower().strip()
        if any(excluded in chapter_title for excluded in EXCLUDED_SECTION_TITLES):
            logger.info(f"Section exclue (chapitre TOC): '{s.get('title', 'Sans titre')}' dans '{chapter_title}'")
            excluded_count += 1
            continue

        # Vérifier la classification LLM
        if s.get("should_index", True):
            filtered.append(s)
        else:
            excluded_count += 1

    if excluded_count > 0:
        logger.info(f"Sections exclues: {excluded_count}, indexables: {len(filtered)}")

    return filtered


def validate_classified_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Post-classification validation to detect false positives.

    Performs additional checks on sections marked should_index=True to catch
    TOC fragments that escaped initial classification:
    1. Parent chapter is TOC -> exclude
    2. Content is mostly short title-like lines -> reclassify as toc_display

    Args:
        sections: List of already-classified section dictionaries.

    Returns:
        Validated sections with corrections applied. Corrections are logged
        and stored in 'validation_correction' field.

    Example:
        >>> sections = [{"title": "Part 1", "should_index": True, "content": "..."}]
        >>> validated = validate_classified_sections(sections)
        >>> # May reclassify sections with TOC-like content
    """
    validated: list[dict[str, Any]] = []
    fixed_count: int = 0

    for section in sections:
        # Vérifier d'abord si le titre du chapitre parent est une TOC
        chapter_title: str = (section.get("chapter_title") or "").lower().strip()
        section_title: str = (section.get("title") or "").lower().strip()

        # Exclure si le chapitre parent est une TOC
        is_toc_chapter: bool = False
        for excluded in EXCLUDED_SECTION_TITLES:
            if excluded in chapter_title:
                logger.warning(f"Section '{section.get('title', 'Sans titre')}' exclue: chapitre parent est '{chapter_title}'")
                section["should_index"] = False
                section["type"] = "toc_display"
                section["validation_correction"] = f"Exclue car chapitre parent = {chapter_title}"
                fixed_count += 1
                is_toc_chapter = True
                break

        if is_toc_chapter:
            validated.append(section)
            continue

        # Si déjà marquée comme non-indexable, garder tel quel
        if not section.get("should_index", True):
            validated.append(section)
            continue

        content: str = section.get("content", "")

        # Validation supplémentaire sur le contenu
        if content:
            lines: list[str] = [l.strip() for l in content.split("\n") if l.strip()]

            # Si très peu de lignes, probablement pas un problème
            if len(lines) < 3:
                validated.append(section)
                continue

            # Calculer le ratio de lignes qui ressemblent à des titres
            title_question_pattern: str = r'^(Comment|Où|Que|Quelle|Quel|Les?\s+\w+\s+(de|du|à)|Entre\s+.+\s+et)\s+'
            title_like: int = sum(1 for l in lines if re.match(title_question_pattern, l, re.IGNORECASE))

            # Si > 50% des lignes ressemblent à des titres ET lignes courtes
            avg_len: float = sum(len(l) for l in lines) / len(lines)

            if len(lines) >= 4 and title_like >= len(lines) * 0.5 and avg_len < 55:
                # C'est probablement une liste de titres extraite de la TOC
                logger.warning(f"Section '{section.get('title', 'Sans titre')}' reclassée: détectée comme liste de titres TOC")
                section["should_index"] = False
                section["type"] = "toc_display"
                section["validation_correction"] = "Reclassée comme toc_display (liste de titres)"
                fixed_count += 1
                validated.append(section)
                continue

        validated.append(section)

    if fixed_count > 0:
        logger.info(f"Validation post-classification: {fixed_count} section(s) reclassée(s)")

    return validated


def get_chapter_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter sections to return only chapter-type content.

    Returns sections with types that contain main document content:
    chapter, introduction, conclusion, abstract, preface.

    Args:
        sections: List of classified section dictionaries.

    Returns:
        Filtered list containing only chapter-type sections.

    Example:
        >>> sections = [
        ...     {"title": "TOC", "type": "toc_display"},
        ...     {"title": "Chapter 1", "type": "chapter"}
        ... ]
        >>> chapters = get_chapter_sections(sections)
        >>> len(chapters)
        1
    """
    chapter_types: set[str] = {"chapter", "introduction", "conclusion", "abstract", "preface"}
    return [s for s in sections if s.get("type") in chapter_types]
