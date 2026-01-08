"""Improved semantic chunking with strict size limits and overlap.

This module adds strict chunk size constraints (max 1000 words) and overlap
functionality (100 words) to prevent giant chunks that exceed BGE-M3 limits.

Key improvements:
    - MAX_CHUNK_WORDS = 1000 (hard limit)
    - OVERLAP_WORDS = 100 (context preservation)
    - Fallback to simple chunking if section > 1500 words
    - Fallback to simple chunking if LLM fails
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional

from .llm_cleaner import clean_page_markers

logger: logging.Logger = logging.getLogger(__name__)

# Constants
MAX_CHUNK_WORDS = 1000  # Hard limit per chunk (~2500 tokens)
OVERLAP_WORDS = 100  # Overlap between chunks for context
MIN_CHUNK_WORDS = 100  # Minimum chunk size


def simple_chunk_with_overlap(
    content: str,
    max_words: int = MAX_CHUNK_WORDS,
    min_words: int = MIN_CHUNK_WORDS,
    overlap_words: int = OVERLAP_WORDS,
) -> List[str]:
    """Split text into chunks with overlap for context preservation.

    This is an improved version of simple_chunk_by_paragraphs that adds
    overlap between consecutive chunks to maintain context.

    Algorithm:
        1. Split by paragraph boundaries (double newlines)
        2. Merge small paragraphs until max_words is reached
        3. Split long paragraphs at sentence boundaries
        4. Add overlap_words from previous chunk to next chunk
        5. Filter chunks below min_words threshold

    Args:
        content: Text content to split into chunks.
        max_words: Maximum words per chunk. Defaults to 1000.
        min_words: Minimum words per chunk. Defaults to 100.
        overlap_words: Words to overlap between chunks. Defaults to 100.

    Returns:
        List of text chunks as strings with overlap.

    Example:
        >>> chunks = simple_chunk_with_overlap(text, max_words=1000, overlap_words=100)
        >>> # Each chunk overlaps with 100 words from previous chunk
    """
    content = clean_page_markers(content)

    # Split by paragraphs
    paragraphs: List[str] = re.split(r'\n\n+', content)

    chunks: List[str] = []
    current_chunk: List[str] = []
    current_words: int = 0
    overlap_buffer: List[str] = []  # Store last sentences for overlap

    def finalize_chunk() -> None:
        """Finalize current chunk and prepare overlap."""
        nonlocal current_chunk, current_words, overlap_buffer

        if not current_chunk:
            return

        chunk_text = '\n\n'.join(current_chunk)
        chunks.append(chunk_text)

        # Extract last sentences for overlap
        sentences = re.split(r'(?<=[.!?])\s+', chunk_text)
        overlap_buffer = []
        overlap_word_count = 0

        # Take last sentences until we reach overlap_words
        for sentence in reversed(sentences):
            sentence_words = len(sentence.split())
            if overlap_word_count + sentence_words <= overlap_words:
                overlap_buffer.insert(0, sentence)
                overlap_word_count += sentence_words
            else:
                break

        current_chunk = []
        current_words = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        para_words: int = len(para.split())

        # If paragraph is too long, split by sentences
        if para_words > max_words:
            # Finalize current chunk first
            if current_chunk:
                finalize_chunk()

            # Add overlap if exists
            if overlap_buffer and chunks:
                current_chunk.extend(overlap_buffer)
                current_words = sum(len(s.split()) for s in overlap_buffer)

            # Split long paragraph by sentences
            sentences: List[str] = re.split(r'(?<=[.!?])\s+', para)
            for sentence in sentences:
                sentence_words: int = len(sentence.split())

                if current_words + sentence_words > max_words and current_chunk:
                    finalize_chunk()

                    # Add overlap
                    if overlap_buffer:
                        current_chunk.extend(overlap_buffer)
                        current_words = sum(len(s.split()) for s in overlap_buffer)

                    current_chunk.append(sentence)
                    current_words += sentence_words
                else:
                    current_chunk.append(sentence)
                    current_words += sentence_words

        # If adding paragraph exceeds limit
        elif current_words + para_words > max_words:
            if current_chunk:
                finalize_chunk()

            # Add overlap
            if overlap_buffer and chunks:
                current_chunk.extend(overlap_buffer)
                current_words = sum(len(s.split()) for s in overlap_buffer)

            current_chunk.append(para)
            current_words += para_words

        else:
            current_chunk.append(para)
            current_words += para_words

    # Last chunk
    if current_chunk:
        chunk_text = '\n\n'.join(current_chunk)
        chunks.append(chunk_text)

    # Filter chunks that are too short (unless it's the only chunk)
    if len(chunks) > 1:
        chunks = [c for c in chunks if len(c.split()) >= min_words]

    return chunks


def get_chunk_text_with_context(
    chunks: List[str],
    index: int,
    context_words: int = 50
) -> tuple[str, str, str]:
    """Get chunk with before/after context for better LLM processing.

    Args:
        chunks: List of chunk texts.
        index: Index of the chunk to process.
        context_words: Words of context to include from adjacent chunks.

    Returns:
        Tuple of (before_context, chunk_text, after_context).
    """
    chunk = chunks[index]

    before_context = ""
    if index > 0:
        prev_chunk = chunks[index - 1]
        words = prev_chunk.split()
        before_context = " ".join(words[-context_words:]) if len(words) > context_words else prev_chunk

    after_context = ""
    if index < len(chunks) - 1:
        next_chunk = chunks[index + 1]
        words = next_chunk.split()
        after_context = " ".join(words[:context_words]) if len(words) > context_words else next_chunk

    return before_context, chunk, after_context


def estimate_tokens(text: str) -> int:
    """Estimate token count from text.

    Uses approximation of 1 token ≈ 4 characters.

    Args:
        text: Text to estimate.

    Returns:
        Estimated token count.
    """
    return len(text) // 4


def validate_chunk_size(text: str, max_tokens: int = 2500) -> bool:
    """Validate that chunk size is within acceptable limits.

    Args:
        text: Chunk text to validate.
        max_tokens: Maximum allowed tokens (default 2500 for safety margin below BGE-M3's 8192).

    Returns:
        True if chunk is valid size, False otherwise.
    """
    tokens = estimate_tokens(text)
    return tokens <= max_tokens


# Export key functions
__all__ = [
    'simple_chunk_with_overlap',
    'get_chunk_text_with_context',
    'estimate_tokens',
    'validate_chunk_size',
    'MAX_CHUNK_WORDS',
    'OVERLAP_WORDS',
    'MIN_CHUNK_WORDS',
]
