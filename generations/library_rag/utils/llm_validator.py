"""Document validation and enrichment using Large Language Models.

This module provides comprehensive validation, correction, and enrichment
functionality for parsed documents. It uses LLMs to verify document coherence,
detect inconsistencies, suggest corrections, and extract key concepts from
text chunks.

Overview:
    The module performs three main functions:

    1. **Document Validation** (validate_document):
       Verifies the coherence of parsed documents by checking metadata,
       table of contents, and chunk content quality. Returns detailed
       validation results with issues, corrections, and confidence scores.

    2. **Content Enrichment** (enrich_chunks_with_concepts, generate_section_summary):
       Enhances document content by extracting key philosophical concepts
       from chunks and generating concise summaries for sections.

    3. **Correction Application** (apply_corrections, clean_validation_annotations):
       Applies suggested corrections from validation results and cleans
       LLM-generated annotation artifacts from text.

Validation Criteria:
    The validator checks several aspects of document quality:

    - **Metadata Quality**: Verifies title and author are correctly identified
      (not collection names, not "Unknown" when visible in text)
    - **TOC Coherence**: Checks for duplicates, proper ordering, completeness
    - **Chunk Content**: Ensures chunks contain substantive content, not just
      metadata fragments or headers

Validation Result Structure:
    The ValidationResult TypedDict contains:

    - valid (bool): Overall validation pass/fail
    - errors (List[str]): Critical issues requiring attention
    - warnings (List[str]): Non-critical suggestions
    - corrections (Dict[str, str]): Suggested field corrections
    - concepts (List[str]): Extracted key concepts
    - score (float): Confidence score (0.0 to 1.0)

LLM Provider Support:
    - ollama: Local LLM (free, slower, privacy-preserving)
    - mistral: Mistral API (faster, requires API key, ~0.001 per validation)

Example:
    >>> from utils.llm_validator import validate_document, apply_corrections
    >>>
    >>> # Validate a parsed document
    >>> parsed_doc = {
    ...     "metadata": {"title": "Phenomenologie", "author": "Hegel"},
    ...     "toc": [{"title": "Preface", "level": 1, "page": 1}],
    ...     "chunks": [{"text": "La conscience...", "section_path": "Preface"}]
    ... }
    >>> result = validate_document(parsed_doc, provider="ollama")
    >>> print(f"Valid: {result['valid']}, Score: {result['score']}")
    Valid: True, Score: 0.85

See Also:
    utils.llm_cleaner: Text cleaning and validation
    utils.llm_chunker: Semantic chunking of sections
    utils.pdf_pipeline: Main pipeline orchestration
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Match

from .llm_structurer import call_llm, _get_default_model, _get_default_mistral_model, _clean_json_string
from .types import LLMProvider, ValidationResult, ParsedDocument, ChunkData

logger: logging.Logger = logging.getLogger(__name__)


def _extract_json_from_response(text: str) -> Dict[str, Any]:
    """Extract JSON from an LLM response text.

    Attempts to parse JSON from the response using two strategies:
    1. Look for content wrapped in <JSON></JSON> tags
    2. Find the first { and last } to extract raw JSON

    Args:
        text: LLM response text potentially containing JSON data.
            May include markdown, explanatory text, or XML-style tags.

    Returns:
        Parsed dictionary from the JSON content. Returns an empty dict
        if no valid JSON is found or parsing fails.

    Example:
        >>> response = '<JSON>{"valid": true, "score": 0.9}</JSON>'
        >>> _extract_json_from_response(response)
        {'valid': True, 'score': 0.9}
    """
    json_match: Optional[Match[str]] = re.search(r'<JSON>\s*(.*?)\s*</JSON>', text, re.DOTALL)
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

    return {}


def validate_document(
    parsed_doc: Dict[str, Any],
    model: Optional[str] = None,
    provider: LLMProvider = "ollama",
    temperature: float = 0.1,
) -> ValidationResult:
    """Validate a parsed document's coherence and suggest corrections.

    Uses an LLM to analyze the document structure and content, checking
    for common issues like incorrect metadata, inconsistent TOC, or
    low-quality chunk content.

    Args:
        parsed_doc: Dictionary containing the parsed document with keys:
            - metadata: Dict with title, author, year, language
            - toc: List of TOC entries with title, level, page
            - chunks: List of text chunks with content and metadata
        model: LLM model name. If None, uses provider's default model.
        provider: LLM provider, either "ollama" (local) or "mistral" (API).
        temperature: Model temperature for response generation (0.0-1.0).
            Lower values produce more deterministic results.

    Returns:
        ValidationResult TypedDict containing:
            - valid: Overall validation status (True if no critical errors)
            - errors: List of critical issues as strings
            - warnings: List of non-critical suggestions
            - corrections: Dict mapping field names to suggested corrections
            - concepts: Extracted key concepts (empty for this function)
            - score: Confidence score from 0.0 to 1.0

    Note:
        The function always returns a valid result, even on LLM errors.
        Check the 'score' field - a score of 0.0 indicates an error occurred.
    """
    if model is None:
        model = _get_default_mistral_model() if provider == "mistral" else _get_default_model()

    # Extraire les infos clés
    metadata: Dict[str, Any] = parsed_doc.get("metadata", {})
    toc: List[Dict[str, Any]] = parsed_doc.get("toc", [])
    chunks: List[Dict[str, Any]] = parsed_doc.get("chunks", [])
    
    # Préparer le résumé du document
    doc_summary: Dict[str, Any] = {
        "title": metadata.get("title"),
        "author": metadata.get("author"),
        "toc_count": len(toc),
        "toc_preview": [t.get("title") for t in toc[:10]] if toc else [],
        "chunks_count": len(chunks),
        "first_chunks_preview": [
            c.get("text", "")[:100] for c in chunks[:5]
        ] if chunks else [],
    }
    
    prompt: str = f"""Tu es un expert en validation de documents structurés.

TÂCHE: Vérifier la cohérence de ce document parsé et détecter les erreurs.

DOCUMENT PARSÉ:
{json.dumps(doc_summary, ensure_ascii=False, indent=2)}

VÉRIFICATIONS À EFFECTUER:
1. Le titre correspond-il au contenu? (pas le nom d'une collection)
2. L'auteur est-il correctement identifié? (pas "Inconnu" si visible)
3. La TOC est-elle cohérente? (pas de doublons, bon ordre)
4. Les chunks contiennent-ils du vrai contenu? (pas que des métadonnées)

RÉPONDS avec un JSON entre <JSON></JSON>:

<JSON>
{{
    "is_valid": true,
    "confidence": 0.85,
    "issues": [
        {{
            "field": "title",
            "severity": "warning",
            "message": "Le titre semble être le nom de la collection",
            "suggestion": "Vrai titre suggéré"
        }}
    ],
    "corrections": {{
        "title": "Titre corrigé si nécessaire",
        "author": "Auteur corrigé si nécessaire"
    }},
    "quality_score": {{
        "metadata": 0.8,
        "toc": 0.9,
        "chunks": 0.7
    }}
}}
</JSON>
"""

    logger.info(f"Validation du document parsé via {provider.upper()}")

    try:
        response: str = call_llm(
            prompt, model=model, provider=provider, temperature=temperature, timeout=180
        )
        result: Dict[str, Any] = _extract_json_from_response(response)

        # Construire ValidationResult avec valeurs par défaut
        is_valid: bool = result.get("is_valid", True)
        issues: List[str] = result.get("issues", [])
        corrections: Dict[str, str] = result.get("corrections", {})
        confidence: float = result.get("confidence", 0.5)

        logger.info(f"Validation terminée: valid={is_valid}, issues={len(issues)}")

        validation_result: ValidationResult = {
            "valid": is_valid,
            "errors": [str(issue) for issue in issues] if issues else [],
            "warnings": [],
            "corrections": corrections,
            "concepts": [],
            "score": confidence,
        }
        return validation_result

    except Exception as e:
        logger.error(f"Erreur validation document: {e}")
        error_result: ValidationResult = {
            "valid": True,
            "errors": [str(e)],
            "warnings": [],
            "corrections": {},
            "concepts": [],
            "score": 0.0,
        }
        return error_result


def generate_section_summary(
    section_content: str,
    section_title: str,
    model: Optional[str] = None,
    provider: LLMProvider = "ollama",
    max_words: int = 50,
) -> str:
    """Generate a concise summary for a document section using LLM.

    Creates a single-sentence summary capturing the main idea of the section.
    For very short sections (< 100 characters), returns the section title
    instead of calling the LLM.

    Args:
        section_content: Full text content of the section to summarize.
        section_title: Title of the section, used as fallback if summarization
            fails or content is too short.
        model: LLM model name. If None, uses provider's default model.
        provider: LLM provider, either "ollama" (local) or "mistral" (API).
        max_words: Maximum number of words for the generated summary.
            Defaults to 50 words.

    Returns:
        Generated summary string, truncated to max_words if necessary.
        Returns section_title if content is too short or on error.

    Note:
        Only the first 2000 characters of section_content are sent to the LLM
        to manage context window limits and costs.
    """
    if model is None:
        model = _get_default_mistral_model() if provider == "mistral" else _get_default_model()

    if len(section_content) < 100:
        return section_title

    prompt: str = f"""Résume cette section en maximum {max_words} mots.
Le résumé doit capturer l'idée principale.

Titre: {section_title}
Contenu:
{section_content[:2000]}

Résumé (en une phrase):"""

    try:
        response: str = call_llm(
            prompt, model=model, provider=provider, temperature=0.2, timeout=60
        )

        # Nettoyer la réponse
        summary: str = response.strip()

        # Limiter la longueur
        words: List[str] = summary.split()
        if len(words) > max_words:
            summary = ' '.join(words[:max_words]) + '...'

        return summary or section_title

    except Exception as e:
        logger.warning(f"Erreur génération résumé: {e}")
        return section_title


def enrich_chunks_with_concepts(
    chunks: List[Dict[str, Any]],
    model: Optional[str] = None,
    provider: LLMProvider = "ollama",
) -> List[Dict[str, Any]]:
    """Enrich text chunks with extracted key concepts using LLM.

    Processes each chunk to extract 3-5 key philosophical or thematic
    concepts, adding them to the chunk's 'concepts' field. Skips chunks
    that already have concepts or are too short (< 100 characters).

    Args:
        chunks: List of chunk dictionaries, each containing at minimum:
            - text: The chunk's text content
            May also contain existing 'concepts' field (will be skipped).
        model: LLM model name. If None, uses provider's default model.
        provider: LLM provider, either "ollama" (local) or "mistral" (API).

    Returns:
        The same list of chunks, modified in-place with 'concepts' field
        added to each chunk. Each concepts field is a list of 0-5 strings.

    Note:
        - Chunks are processed individually with logging every 10 chunks.
        - Only the first 1000 characters of each chunk are analyzed.
        - The function modifies chunks in-place AND returns them.
        - On extraction error, sets concepts to an empty list.
    """
    if model is None:
        model = _get_default_mistral_model() if provider == "mistral" else _get_default_model()

    # Limiter le nombre de chunks à traiter en une fois
    batch_size: int = 10

    i: int
    chunk: Dict[str, Any]
    for i, chunk in enumerate(chunks):
        if "concepts" in chunk and chunk["concepts"]:
            continue  # Déjà enrichi

        text: str = chunk.get("text", "")
        if len(text) < 100:
            chunk["concepts"] = []
            continue

        # Traiter par batch pour optimiser
        if i % batch_size == 0:
            logger.info(f"Enrichissement concepts: chunks {i} à {min(i+batch_size, len(chunks))}")

        prompt: str = f"""Extrait 3-5 concepts clés de ce texte.
Réponds avec une liste JSON: ["concept1", "concept2", ...]

Texte:
{text[:1000]}

Concepts:"""

        try:
            response: str = call_llm(
                prompt, model=model, provider=provider, temperature=0.1, timeout=30
            )

            # Chercher la liste JSON
            match: Optional[Match[str]] = re.search(r'\[.*?\]', response, re.DOTALL)
            if match:
                concepts: List[str] = json.loads(match.group())
                chunk["concepts"] = concepts[:5]
            else:
                chunk["concepts"] = []

        except Exception as e:
            logger.warning(f"Erreur extraction concepts chunk {i}: {e}")
            chunk["concepts"] = []

    return chunks


def clean_validation_annotations(text: str) -> str:
    """Remove LLM-generated validation annotations from text.

    Cleans common annotation patterns that LLMs may add when validating
    or correcting text, such as confidence markers or verification notes.

    Patterns removed:
        - "(correct)" or "(a confirmer)" at end of text
        - "(a confirmer comme titre principal)"
        - "(possiblement...)" or "(probablement...)"
        - Isolated "(correct)" or "(a confirmer)" mid-text

    Args:
        text: Text potentially containing LLM annotation artifacts.

    Returns:
        Cleaned text with annotations removed and whitespace normalized.
        Returns the original text if input is None or empty.

    Example:
        >>> clean_validation_annotations("Phenomenologie (a confirmer)")
        "Phenomenologie"
        >>> clean_validation_annotations("G.W.F. Hegel (correct)")
        'G.W.F. Hegel'
    """
    if not text:
        return text

    # Supprimer les annotations à la fin du texte
    text = re.sub(
        r'\s*\([^)]*(?:correct|à confirmer|possiblement|probablement)[^)]*\)\s*$',
        '',
        text,
        flags=re.IGNORECASE
    )

    # Nettoyer aussi les annotations au milieu si elles sont isolées
    text = re.sub(r'\s*\((?:correct|à confirmer)\)\s*', ' ', text, flags=re.IGNORECASE)

    return text.strip()


def apply_corrections(
    parsed_doc: Dict[str, Any],
    validation_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Apply validation corrections to a parsed document.

    Takes the corrections suggested by validate_document() and applies them
    to the document's metadata. Also cleans any LLM annotation artifacts
    from existing metadata fields.

    Args:
        parsed_doc: Parsed document dictionary containing at minimum:
            - metadata: Dict with title, author, and other fields
            May also contain 'work' field as fallback title source.
        validation_result: Result from validate_document() containing:
            - corrections: Dict mapping field names to corrected values
            If None, only cleans existing metadata annotations.

    Returns:
        The modified parsed_doc with:
            - Corrected metadata fields applied
            - Original values preserved in 'original_<field>' keys
            - LLM annotations cleaned from all text fields
            - 'validation' key added with the validation_result

    Note:
        - Modifies parsed_doc in-place AND returns it
        - Empty correction values are ignored
        - If title contains validation phrases and 'work' field exists,
          the work field value is used as the corrected title
    """
    corrections: Dict[str, str] = (
        validation_result.get("corrections", {}) if validation_result else {}
    )

    metadata: Dict[str, Any] = parsed_doc.get("metadata", {})

    # Appliquer les corrections de métadonnées
    if "title" in corrections and corrections["title"]:
        old_title: Optional[str] = metadata.get("title")
        # Nettoyer les annotations de validation
        clean_title: str = clean_validation_annotations(corrections["title"])
        metadata["title"] = clean_title
        metadata["original_title"] = old_title
        logger.info(f"Titre corrigé: '{old_title}' -> '{clean_title}'")

    if "author" in corrections and corrections["author"]:
        old_author: Optional[str] = metadata.get("author")
        # Nettoyer les annotations de validation
        clean_author: str = clean_validation_annotations(corrections["author"])
        metadata["author"] = clean_author
        metadata["original_author"] = old_author
        logger.info(f"Auteur corrigé: '{old_author}' -> '{clean_author}'")

    # Nettoyer aussi les métadonnées existantes si pas de corrections
    if "title" in metadata and metadata["title"]:
        title: str = metadata["title"]
        # Si le titre contient des phrases de validation, utiliser le champ "work" à la place
        validation_phrases: List[str] = ["à confirmer", "confirmer avec", "vérifier"]
        if title and any(phrase in title.lower() for phrase in validation_phrases):
            if "work" in metadata and metadata["work"]:
                logger.info(f"Titre remplacé par 'work': '{title}' -> '{metadata['work']}'")
                metadata["original_title"] = title
                metadata["title"] = metadata["work"]
        else:
            metadata["title"] = clean_validation_annotations(title)

    if "author" in metadata and metadata["author"]:
        metadata["author"] = clean_validation_annotations(metadata["author"])

    parsed_doc["metadata"] = metadata
    parsed_doc["validation"] = validation_result

    return parsed_doc

