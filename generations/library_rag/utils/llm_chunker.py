"""Semantic chunking of documents via LLM.

This module provides intelligent semantic chunking capabilities for academic and
philosophical texts, using Large Language Models (LLM) to identify coherent units
of meaning (argumentative units, definitions, examples, citations, etc.).

Overview:
    The module offers two chunking strategies:

    1. **LLM-based semantic chunking** (chunk_section_with_llm):
       Uses an LLM to identify semantic boundaries and create chunks that preserve
       argumentative coherence. Each chunk is annotated with summary, concepts, type.

    2. **Simple paragraph-based chunking** (simple_chunk_by_paragraphs):
       A fast fallback that splits text by paragraph boundaries.

Semantic Unit Types:
    - argument: A logical argument or reasoning sequence
    - definition: A definition or conceptual clarification
    - example: An illustrative example or case study
    - citation: A quoted passage from another source
    - exposition: Expository content presenting ideas
    - transition: Transitional text between sections

Chunk Size Guidelines:
    - Target size: 300-500 words per chunk (configurable)
    - Chunks are never split mid-sentence or mid-paragraph
    - Short sections (< 80% of target) are kept as single chunks

LLM Provider Support:
    - ollama: Local LLM (free, slower, default)
    - mistral: Mistral API (faster, requires API key)

See Also:
    utils.llm_cleaner: Chunk cleaning and validation
    utils.llm_classifier: Section type classification
    utils.pdf_pipeline: Main pipeline orchestration
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Literal, Optional, TypedDict

from .llm_structurer import (
    _clean_json_string,
    _get_default_mistral_model,
    _get_default_model,
    call_llm,
)
from .llm_cleaner import clean_page_markers, is_chunk_valid
from .types import LLMProvider, SemanticChunk
from .llm_chunker_improved import simple_chunk_with_overlap, validate_chunk_size

logger: logging.Logger = logging.getLogger(__name__)

# Chunk size limits (2024-01 optimization)
MAX_CHUNK_WORDS = 1000  # Hard limit to stay within BGE-M3 context
OVERLAP_WORDS = 100     # Overlap for context preservation
FORCE_SIMPLE_CHUNKING_THRESHOLD = 1500  # Words - force simple chunking above this


# =============================================================================
# Type Definitions for LLM Chunker
# =============================================================================

#: Unit type for semantic chunking (specific to this module's LLM output)
ChunkUnitType = Literal[
    "argument",
    "definition",
    "example",
    "citation",
    "exposition",
    "transition",
    "main_content",
]


class LLMChunkResponse(TypedDict, total=False):
    """Individual chunk structure as returned by LLM.

    Attributes:
        text: Chunk text content (exact copy from source)
        summary: Brief one-sentence summary
        concepts: Key concepts extracted (3-5 items)
        type: Semantic unit type
    """

    text: str
    summary: str
    concepts: List[str]
    type: str


class LLMChunksResult(TypedDict):
    """Complete response structure from LLM chunking.

    Attributes:
        chunks: List of chunk objects
    """

    chunks: List[LLMChunkResponse]


# Note: SemanticChunk is imported from utils.types


def extract_paragraph_number(text: str) -> Optional[int]:
    """Extract paragraph number from the beginning of text.

    Many philosophical texts use numbered paragraphs. This function
    detects various numbering formats.

    Args:
        text: Text content that may start with a paragraph number.

    Returns:
        The paragraph number if detected, None otherwise.

    Example:
        >>> extract_paragraph_number("9 On presente...")
        9
        >>> extract_paragraph_number("Normal text")
        None
    """
    text = text.strip()
    
    # Patterns possibles pour les numéros de paragraphe
    patterns: List[str] = [
        r'^(\d+)\s+[A-ZÀ-Ü]',  # "9 On présente..."
        r'^(\d+)[A-ZÀ-Ü]',      # "10Dans la classification..."
        r'^§\s*(\d+)',          # "§ 15 ..."
        r'^\[(\d+)\]',          # "[9] ..."
        r'^(\d+)\.',            # "9. ..."
        r'^(\d+)\)',            # "9) ..."
    ]

    for pattern in patterns:
        match: Optional[re.Match[str]] = re.match(pattern, text)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                continue
    
    return None


def _extract_json_from_response(text: str) -> Dict[str, Any]:
    """Extract JSON from LLM response text.

    Handles both wrapped JSON (in <JSON></JSON> tags) and raw JSON responses.
    Falls back to empty chunks list if parsing fails.

    Args:
        text: Response text from LLM containing JSON.

    Returns:
        Parsed JSON as dictionary with 'chunks' key. Returns
        {"chunks": []} if parsing fails.
    """
    json_match: Optional[re.Match[str]] = re.search(
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

    return {"chunks": []}


def chunk_section_with_llm(
    section_content: str,
    section_title: str,
    chapter_title: Optional[str] = None,
    subsection_title: Optional[str] = None,
    section_level: int = 1,
    model: Optional[str] = None,
    provider: LLMProvider = "ollama",
    temperature: float = 0.2,
    target_chunk_size: int = 400,
) -> List[SemanticChunk]:
    """Split a section into semantically coherent chunks using an LLM.

    This is the main semantic chunking function. It uses an LLM to identify
    natural semantic boundaries in academic/philosophical texts, preserving
    argumentative coherence and annotating each chunk with metadata.

    Args:
        section_content: The text content of the section to chunk.
        section_title: Title of the current section being chunked.
        chapter_title: Title of the parent chapter (level 1) for context.
        subsection_title: Title of parent subsection (level 2) if applicable.
        section_level: Hierarchy level (1=chapter, 2=section, etc.).
        model: LLM model name. If None, uses provider default.
        provider: LLM provider ("ollama" for local, "mistral" for API).
        temperature: LLM temperature (lower = more deterministic).
        target_chunk_size: Target number of words per chunk.

    Returns:
        List of SemanticChunk dictionaries containing text, summary,
        concepts, type, section_level, and optionally paragraph_number.

    Note:
        If section is shorter than 80% of target_chunk_size, it is returned
        as a single chunk. If LLM fails, returns section with error field.
    """
    if model is None:
        model = _get_default_mistral_model() if provider == "mistral" else _get_default_model()

    # Nettoyer le contenu
    content: str = clean_page_markers(section_content)

    # Compter les mots
    word_count: int = len(content.split())

    # FORCE SIMPLE CHUNKING if section is too long (> 1500 words)
    # This prevents giant chunks that exceed BGE-M3 limits
    if word_count > FORCE_SIMPLE_CHUNKING_THRESHOLD:
        logger.warning(
            f"Section '{section_title}' is too long ({word_count} words), "
            f"forcing simple chunking with overlap"
        )
        simple_texts = simple_chunk_with_overlap(
            content,
            max_words=MAX_CHUNK_WORDS,
            overlap_words=OVERLAP_WORDS
        )

        # Convert to SemanticChunk format
        result_chunks: List[SemanticChunk] = []
        for i, text in enumerate(simple_texts):
            para_num = extract_paragraph_number(text)
            chunk: SemanticChunk = {
                "text": text,
                "summary": f"{section_title} (partie {i+1}/{len(simple_texts)})",
                "concepts": [],
                "type": "main_content",
                "section_level": section_level,
            }
            if para_num is not None:
                chunk["paragraph_number"] = para_num
            if subsection_title and subsection_title != section_title:
                chunk["subsection_title"] = subsection_title
            result_chunks.append(chunk)

        logger.info(f"Section split into {len(result_chunks)} chunks with overlap")
        return result_chunks

    # Si le contenu est court, ne pas découper
    if word_count < target_chunk_size * 0.8:
        para_num: Optional[int] = extract_paragraph_number(content)
        chunk: SemanticChunk = {
            "text": content,
            "summary": section_title,
            "concepts": [],
            "type": "main_content",
            "section_level": section_level,
        }
        if para_num is not None:
            chunk["paragraph_number"] = para_num
        if subsection_title and subsection_title != section_title:
            chunk["subsection_title"] = subsection_title
        return [chunk]

    chapter_info: str = f"Chapitre: {chapter_title}\n" if chapter_title else ""
    
    prompt = f"""Tu es un expert en analyse de textes académiques.

TÂCHE: Découper ce texte en unités sémantiques cohérentes.

{chapter_info}Section: {section_title}

RÈGLES DE DÉCOUPAGE:
1. Chaque chunk doit avoir un SENS COMPLET (une idée, un argument)
2. Taille idéale: {target_chunk_size - 100} à {target_chunk_size + 100} mots
3. NE PAS couper au milieu d'une phrase ou d'un paragraphe
4. NE PAS couper au milieu d'une citation
5. Regrouper les paragraphes qui développent la même idée
6. Un chunk peut être plus long si nécessaire pour préserver le sens

POUR CHAQUE CHUNK, INDIQUE:
- text: le texte exact (copié, pas reformulé)
- summary: résumé en 1 phrase courte
- concepts: 3-5 concepts clés (mots ou expressions)
- type: argument | définition | exemple | citation | exposition | transition

TEXTE À DÉCOUPER:
{content}

RÉPONDS avec un JSON entre <JSON></JSON>:

<JSON>
{{
    "chunks": [
        {{
            "text": "Premier paragraphe ou groupe de paragraphes...",
            "summary": "Présentation de l'idée principale",
            "concepts": ["concept1", "concept2", "concept3"],
            "type": "exposition"
        }},
        {{
            "text": "Deuxième partie du texte...",
            "summary": "Développement de l'argument",
            "concepts": ["concept4", "concept5"],
            "type": "argument"
        }}
    ]
}}
</JSON>
"""

    logger.info(f"Chunking sémantique de '{section_title}' ({word_count} mots) via {provider.upper()}")

    try:
        response: str = call_llm(
            prompt, model=model, provider=provider, temperature=temperature, timeout=300
        )
        result: Dict[str, Any] = _extract_json_from_response(response)
        chunks: List[Dict[str, Any]] = result.get("chunks", [])

        # Valider les chunks et extraire les numéros de paragraphe
        valid_chunks: List[SemanticChunk] = []
        for raw_chunk in chunks:
            text: str = raw_chunk.get("text", "")
            if is_chunk_valid(text):
                # Extraire le numéro de paragraphe s'il existe
                para_num = extract_paragraph_number(text)

                chunk_data: SemanticChunk = {
                    "text": text,
                    "summary": raw_chunk.get("summary", ""),
                    "concepts": raw_chunk.get("concepts", []),
                    "type": raw_chunk.get("type", "main_content"),
                    "section_level": section_level,
                }

                # Ajouter le numéro de paragraphe si détecté
                if para_num is not None:
                    chunk_data["paragraph_number"] = para_num

                # Ajouter la hiérarchie complète
                if subsection_title and subsection_title != section_title:
                    chunk_data["subsection_title"] = subsection_title

                valid_chunks.append(chunk_data)

        # Si aucun chunk valide, utiliser simple chunking avec overlap
        if not valid_chunks:
            logger.warning(
                f"Aucun chunk valide pour '{section_title}', "
                f"fallback vers simple chunking avec overlap"
            )
            simple_texts = simple_chunk_with_overlap(
                content,
                max_words=MAX_CHUNK_WORDS,
                overlap_words=OVERLAP_WORDS
            )

            fallback_chunks: List[SemanticChunk] = []
            for i, text in enumerate(simple_texts):
                para_num = extract_paragraph_number(text)
                chunk_data: SemanticChunk = {
                    "text": text,
                    "summary": f"{section_title} (partie {i+1}/{len(simple_texts)})",
                    "concepts": [],
                    "type": "main_content",
                    "section_level": section_level,
                }
                if para_num is not None:
                    chunk_data["paragraph_number"] = para_num
                fallback_chunks.append(chunk_data)

            logger.info(f"Fallback: section split into {len(fallback_chunks)} chunks")
            return fallback_chunks

        logger.info(f"Section '{section_title}' découpée en {len(valid_chunks)} chunks")
        return valid_chunks

    except Exception as e:
        logger.error(f"Erreur chunking LLM: {e}")
        # Fallback: utiliser simple chunking avec overlap
        logger.warning(f"Exception LLM, fallback vers simple chunking avec overlap")

        simple_texts = simple_chunk_with_overlap(
            content,
            max_words=MAX_CHUNK_WORDS,
            overlap_words=OVERLAP_WORDS
        )

        error_chunks: List[SemanticChunk] = []
        for i, text in enumerate(simple_texts):
            para_num = extract_paragraph_number(text)
            chunk_data: SemanticChunk = {
                "text": text,
                "summary": f"{section_title} (partie {i+1}/{len(simple_texts)})",
                "concepts": [],
                "type": "main_content",
                "section_level": section_level,
                "error": f"LLM failed: {str(e)}",
            }
            if para_num is not None:
                chunk_data["paragraph_number"] = para_num
            error_chunks.append(chunk_data)

        logger.info(f"Error fallback: section split into {len(error_chunks)} chunks")
        return error_chunks


def simple_chunk_by_paragraphs(
    content: str,
    max_words: int = 500,
    min_words: int = 100,
) -> List[str]:
    """Split text into chunks by paragraph boundaries (no LLM required).

    This is a fast fallback chunking method that respects paragraph and
    sentence boundaries. Use when LLM processing is not desired.

    The algorithm:
    1. Split by double newlines (paragraph boundaries)
    2. Merge small paragraphs until max_words is reached
    3. Split long paragraphs at sentence boundaries
    4. Filter chunks below min_words threshold

    Args:
        content: Text content to split into chunks.
        max_words: Maximum words per chunk. Defaults to 500.
        min_words: Minimum words per chunk. Defaults to 100.

    Returns:
        List of text chunks as strings.

    Example:
        >>> chunks = simple_chunk_by_paragraphs(text, max_words=400)
        >>> len(chunks)
        3
    """
    content = clean_page_markers(content)

    # Découper par paragraphes (double saut de ligne)
    paragraphs: List[str] = re.split(r'\n\n+', content)

    chunks: List[str] = []
    current_chunk: List[str] = []
    current_words: int = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        para_words: int = len(para.split())

        # Si le paragraphe seul est trop long, le découper par phrases
        if para_words > max_words:
            if current_chunk:
                chunks.append('\n\n'.join(current_chunk))
                current_chunk = []
                current_words = 0

            # Découper par phrases
            sentences: List[str] = re.split(r'(?<=[.!?])\s+', para)
            for sentence in sentences:
                sentence_words: int = len(sentence.split())
                if current_words + sentence_words > max_words and current_chunk:
                    chunks.append('\n\n'.join(current_chunk))
                    current_chunk = [sentence]
                    current_words = sentence_words
                else:
                    current_chunk.append(sentence)
                    current_words += sentence_words

        # Si ajouter ce paragraphe dépasse la limite
        elif current_words + para_words > max_words:
            if current_chunk:
                chunks.append('\n\n'.join(current_chunk))
            current_chunk = [para]
            current_words = para_words

        else:
            current_chunk.append(para)
            current_words += para_words

    # Dernier chunk
    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))

    # Filtrer les chunks trop courts
    return [c for c in chunks if len(c.split()) >= min_words or len(chunks) == 1]


def extract_concepts_from_chunk(
    chunk_text: str,
    model: Optional[str] = None,
    provider: LLMProvider = "ollama",
) -> List[str]:
    """Extract key concepts from a text chunk using an LLM.

    Useful for enriching chunks created without LLM processing or for
    extracting additional concepts from existing chunks.

    Args:
        chunk_text: The text content to analyze for concepts.
        model: LLM model name. If None, uses provider default.
        provider: LLM provider ("ollama" or "mistral").

    Returns:
        List of 3-5 key concepts (words or short phrases). Returns
        empty list if extraction fails or text is too short (< 100 chars).

    Example:
        >>> concepts = extract_concepts_from_chunk("L'etre-pour-la-mort...")
        >>> concepts
        ['etre-pour-la-mort', 'structure existentiale', 'Dasein']
    """
    if model is None:
        model = _get_default_mistral_model() if provider == "mistral" else _get_default_model()
    
    if len(chunk_text) < 100:
        return []
    
    prompt: str = f"""Extrait les 3-5 concepts clés de ce texte.
Un concept = un mot ou une expression courte (2-3 mots max).

Texte:
{chunk_text[:1500]}

Réponds avec une liste JSON simple:
["concept1", "concept2", "concept3"]
"""

    try:
        response: str = call_llm(prompt, model=model, provider=provider, temperature=0.1, timeout=60)

        # Chercher la liste JSON
        match: Optional[re.Match[str]] = re.search(r'\[.*?\]', response, re.DOTALL)
        if match:
            concepts: List[str] = json.loads(match.group())
            return concepts[:5]  # Max 5 concepts

        return []
        
    except Exception as e:
        logger.warning(f"Erreur extraction concepts: {e}")
        return []

