"""Text cleaning and validation for OCR-extracted content.

This module provides utilities for cleaning OCR artifacts from extracted text,
validating chunk content, and optionally using LLM for intelligent corrections.
It handles common OCR issues like page markers, isolated page numbers,
repeated headers/footers, and character recognition errors.

Overview:
    The module offers three levels of cleaning:

    1. **Basic cleaning** (clean_page_markers, clean_ocr_artifacts):
       Fast regex-based cleaning for common issues. Always applied.

    2. **LLM-enhanced cleaning** (clean_content_with_llm):
       Uses an LLM to correct subtle OCR errors while preserving meaning.
       Only applied when explicitly requested and for medium-length texts.

    3. **Validation** (is_chunk_valid):
       Checks if a text chunk contains meaningful content.

Cleaning Operations:
    - Remove page markers (<!-- Page X -->)
    - Remove isolated page numbers
    - Remove short/repetitive header/footer lines
    - Normalize multiple spaces and blank lines
    - Correct obvious OCR character errors (LLM mode)
    - Preserve citations, technical vocabulary, paragraph structure

Validation Criteria:
    - Minimum character count (default: 20)
    - Minimum word count (default: 5)
    - Not pure metadata (URLs, ISBNs, DOIs, copyright notices)

LLM Provider Support:
    - ollama: Local LLM (free, slower, default)
    - mistral: Mistral API (faster, requires API key)

Example:
    >>> from utils.llm_cleaner import clean_chunk, is_chunk_valid
    >>> 
    >>> # Clean a chunk with basic cleaning only
    >>> text = "<!-- Page 42 --> Some philosophical content..."
    >>> cleaned = clean_chunk(text)
    >>> print(cleaned)
    'Some philosophical content...'
    >>> 
    >>> # Validate chunk before processing
    >>> if is_chunk_valid(cleaned):
    ...     process_chunk(cleaned)

See Also:
    utils.llm_chunker: Semantic chunking of sections
    utils.llm_validator: Document validation and concept extraction
    utils.pdf_pipeline: Main pipeline orchestration
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional, Pattern

from .llm_structurer import call_llm, _get_default_model, _get_default_mistral_model
from .types import LLMProvider

logger: logging.Logger = logging.getLogger(__name__)

# Type alias for compiled regex patterns
RegexPattern = Pattern[str]


def clean_page_markers(text: str) -> str:
    r"""Remove page markers and normalize blank lines from text.

    Page markers are HTML comments inserted during OCR processing to track
    page boundaries. This function removes them along with excessive blank
    lines that may result from the removal.

    Args:
        text: Text content potentially containing page markers like
            '<!-- Page 42 -->' and multiple consecutive newlines.

    Returns:
        Cleaned text with page markers removed and no more than two
        consecutive newlines. Text is stripped of leading/trailing whitespace.

    Example:
        >>> text = "<!-- Page 1 -->\nContent here\n\n\n\n<!-- Page 2 -->"
        >>> clean_page_markers(text)
        'Content here'
    """
    # Supprimer les marqueurs <!-- Page X -->
    text = re.sub(r'<!--\s*Page\s*\d+\s*-->', '', text)
    
    # Supprimer les lignes vides multiples
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()


def clean_ocr_artifacts(text: str) -> str:
    r"""Remove common OCR artifacts without using LLM.

    This function performs fast, rule-based cleaning of typical OCR issues:
    - Isolated page numbers (1-4 digits on their own line)
    - Very short lines likely to be headers/footers (<=3 chars)
    - Multiple consecutive spaces
    - Excessive blank lines (>2)

    Lines starting with '#' (markdown headers) are preserved regardless
    of length. Empty lines are preserved (single blank lines only).

    Args:
        text: Raw OCR-extracted text potentially containing artifacts
            like isolated page numbers, repeated headers, and irregular spacing.

    Returns:
        Cleaned text with artifacts removed and spacing normalized.
        Leading/trailing whitespace is stripped.

    Example:
        >>> text = "42\n\nActual content here\n\n\n\n\nMore text"
        >>> clean_ocr_artifacts(text)
        'Actual content here\n\nMore text'

    Note:
        This function is always called as part of clean_chunk() and provides
        a baseline level of cleaning even when LLM cleaning is disabled.
    """
    # Supprimer les numéros de page isolés
    text = re.sub(r'^\d{1,4}\s*$', '', text, flags=re.MULTILINE)

    # Supprimer les en-têtes/pieds de page répétés (lignes très courtes isolées)
    lines: List[str] = text.split('\n')
    cleaned_lines: List[str] = []
    for line in lines:
        # Garder les lignes non vides et significatives
        stripped: str = line.strip()
        if stripped and (len(stripped) > 3 or stripped.startswith('#')):
            cleaned_lines.append(line)
        elif not stripped:
            cleaned_lines.append('')  # Préserver les lignes vides simples

    text = '\n'.join(cleaned_lines)

    # Normaliser les espaces
    text = re.sub(r' {2,}', ' ', text)

    # Supprimer les lignes vides multiples
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def clean_content_with_llm(
    text: str,
    context: Optional[str] = None,
    model: Optional[str] = None,
    provider: LLMProvider = "ollama",
    temperature: float = 0.1,
) -> str:
    """Clean text content using an LLM for intelligent OCR error correction.

    Uses a language model to correct subtle OCR errors that rule-based
    cleaning cannot handle, such as misrecognized characters in context.
    The LLM is instructed to preserve the intellectual content exactly
    while fixing obvious technical errors.

    The function includes safeguards:
    - Texts < 50 chars: Only basic cleaning (LLM skipped)
    - Texts > 3000 chars: Only basic cleaning (timeout risk)
    - If LLM changes text by >50%: Fallback to basic cleaning

    Args:
        text: Text content to clean. Should be between 50-3000 characters
            for LLM processing.
        context: Optional context about the document (title, subject) to
            help the LLM make better corrections. Example: "Heidegger's
            Being and Time, Chapter 2".
        model: LLM model name. If None, uses provider default
            (qwen2.5:7b for ollama, mistral-small-latest for mistral).
        provider: LLM provider to use. Options: "ollama" (local, free)
            or "mistral" (API, faster).
        temperature: LLM temperature for response generation. Lower values
            (0.1) produce more deterministic corrections. Defaults to 0.1.

    Returns:
        Cleaned text with OCR errors corrected. If LLM fails or produces
        suspicious output (too short/long), returns basic-cleaned text.

    Raises:
        No exceptions raised - all errors caught and handled with fallback.

    Example:
        >>> text = "Heidegger's concept of Dase1n is central..."  # '1' should be 'i'
        >>> clean_content_with_llm(text, context="Being and Time")
        "Heidegger's concept of Dasein is central..."

    Note:
        The LLM is explicitly instructed NOT to:
        - Modify meaning or intellectual content
        - Rephrase or summarize
        - Add any new content
        - Alter citations or technical vocabulary
    """
    if model is None:
        model = _get_default_mistral_model() if provider == "mistral" else _get_default_model()

    # Ne pas traiter les textes trop courts
    if len(text.strip()) < 50:
        return clean_page_markers(text)

    # Limiter la taille pour éviter les timeouts
    max_chars: int = 3000
    if len(text) > max_chars:
        # Pour les longs textes, nettoyer sans LLM
        return clean_page_markers(clean_ocr_artifacts(text))

    context_info: str = f"Contexte: {context}\n" if context else ""

    prompt: str = f"""Tu es un expert en correction de textes OCRisés.

TÂCHE: Nettoyer ce texte extrait par OCR.

{context_info}
ACTIONS À EFFECTUER:
1. Supprimer les marqueurs de page (<!-- Page X -->)
2. Corriger les erreurs OCR ÉVIDENTES (caractères mal reconnus)
3. Supprimer les artefacts (numéros de page isolés, en-têtes répétés)
4. Normaliser la ponctuation et les espaces

RÈGLES STRICTES:
- NE PAS modifier le sens ou le contenu intellectuel
- NE PAS reformuler ou résumer
- NE PAS ajouter de contenu
- Préserver les citations et le vocabulaire technique
- Garder la structure des paragraphes

TEXTE À NETTOYER:
{text}

RÉPONDS UNIQUEMENT avec le texte nettoyé, sans commentaires ni balises."""

    try:
        response: str = call_llm(
            prompt, model=model, provider=provider, temperature=temperature, timeout=120
        )

        # Vérifier que la réponse est valide
        cleaned: str = response.strip()

        # Si la réponse est trop différente (LLM a trop modifié), garder l'original nettoyé basiquement
        if len(cleaned) < len(text) * 0.5 or len(cleaned) > len(text) * 1.5:
            logger.warning("LLM a trop modifié le texte, utilisation du nettoyage basique")
            return clean_page_markers(clean_ocr_artifacts(text))

        return cleaned

    except Exception as e:
        logger.warning(f"Erreur nettoyage LLM: {e}, utilisation du nettoyage basique")
        return clean_page_markers(clean_ocr_artifacts(text))


def clean_chunk(
    chunk_text: str,
    use_llm: bool = False,
    context: Optional[str] = None,
    model: Optional[str] = None,
    provider: LLMProvider = "ollama",
) -> str:
    r"""Clean a text chunk with optional LLM enhancement.

    This is the main entry point for chunk cleaning. It always applies
    basic cleaning (page markers, OCR artifacts) and optionally uses
    LLM for more intelligent error correction.

    Cleaning pipeline:
    1. Remove page markers (always)
    2. Remove OCR artifacts (always)
    3. LLM correction (if use_llm=True and text >= 50 chars)

    Args:
        chunk_text: Raw text content of the chunk to clean.
        use_llm: Whether to use LLM for enhanced cleaning. Defaults to
            False. Set to True for higher quality but slower processing.
        context: Optional document context (title, chapter) passed to LLM
            for better corrections. Ignored if use_llm=False.
        model: LLM model name. If None, uses provider default.
            Ignored if use_llm=False.
        provider: LLM provider ("ollama" or "mistral"). Defaults to
            "ollama". Ignored if use_llm=False.

    Returns:
        Cleaned chunk text ready for indexing or further processing.

    Example:
        >>> # Basic cleaning only (fast)
        >>> chunk = "<!-- Page 5 -->\n42\n\nThe concept of being..."
        >>> clean_chunk(chunk)
        'The concept of being...'
        >>>
        >>> # With LLM enhancement (slower, higher quality)
        >>> clean_chunk(chunk, use_llm=True, context="Heidegger analysis")
        'The concept of being...'

    See Also:
        is_chunk_valid: Validate cleaned chunks before processing
        clean_page_markers: Basic page marker removal
        clean_ocr_artifacts: Basic artifact removal
    """
    # Nettoyage de base toujours appliqué
    text: str = clean_page_markers(chunk_text)
    text = clean_ocr_artifacts(text)

    # Nettoyage LLM optionnel
    if use_llm and len(text) >= 50:
        text = clean_content_with_llm(text, context=context, model=model, provider=provider)

    return text


def is_chunk_valid(chunk_text: str, min_chars: int = 20, min_words: int = 5) -> bool:
    """Check if a text chunk contains meaningful content.

    Validates that a chunk has sufficient length and is not purely
    metadata or boilerplate content. Used to filter out non-content
    chunks before indexing.

    Validation criteria:
    1. Character count >= min_chars (after page marker removal)
    2. Word count >= min_words
    3. Not matching metadata patterns (URLs, ISBNs, DOIs, dates, copyright)

    Args:
        chunk_text: Text content of the chunk to validate. Page markers
            are removed before validation.
        min_chars: Minimum number of characters required. Defaults to 20.
            Chunks shorter than this are considered invalid.
        min_words: Minimum number of words required. Defaults to 5.
            Chunks with fewer words are considered invalid.

    Returns:
        True if the chunk passes all validation criteria and contains
        meaningful content suitable for indexing. False otherwise.

    Example:
        >>> is_chunk_valid("The concept of Dasein is central to Heidegger.")
        True
        >>> is_chunk_valid("42")  # Too short
        False
        >>> is_chunk_valid("ISBN 978-0-123456-78-9")  # Metadata
        False
        >>> is_chunk_valid("https://example.com/page")  # URL
        False

    Note:
        Metadata patterns checked:
        - URLs (http://, https://)
        - Dates (YYYY-MM-DD format)
        - ISBN numbers
        - DOI identifiers
        - Copyright notices (©)
    """
    text: str = clean_page_markers(chunk_text).strip()

    # Vérifier la longueur
    if len(text) < min_chars:
        return False

    # Compter les mots
    words: List[str] = text.split()
    if len(words) < min_words:
        return False

    # Vérifier que ce n'est pas juste des métadonnées
    metadata_patterns: List[str] = [
        r'^https?://',
        r'^\d{4}-\d{2}-\d{2}$',
        r'^ISBN',
        r'^DOI',
        r'^©',
    ]
    pattern: str
    for pattern in metadata_patterns:
        if re.match(pattern, text, re.IGNORECASE):
            return False

    return True

