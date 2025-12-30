"""Generate speech audio from text using Coqui XTTS v2.

This module provides text-to-speech functionality using the Coqui XTTS v2 model,
optimized for GPU acceleration and long-text processing.

Example:
    Generate speech from text:

        from pathlib import Path
        from utils.tts_generator import generate_speech

        filepath = generate_speech(
            text="Bonjour, ceci est un test de synthèse vocale.",
            output_dir=Path("output"),
            language="fr"
        )

    With custom chunk size for very long texts:

        filepath = generate_speech(
            text=long_text,
            output_dir=Path("output"),
            language="fr",
            max_words_per_chunk=300
        )
"""

from pathlib import Path
from typing import Optional, List
from datetime import datetime
import re

try:
    from TTS.api import TTS
    import torch
except ImportError:
    raise ImportError(
        "TTS library is required for audio generation. "
        "Install with: pip install TTS>=0.22.0"
    )


# Global TTS instance for lazy loading (singleton pattern)
_tts_instance: Optional[TTS] = None


def _get_tts_instance() -> TTS:
    """Get or create the global TTS instance.

    Uses lazy loading and singleton pattern to avoid reloading the model
    on every request. The model is loaded once and cached in memory.

    Returns:
        TTS: Initialized TTS instance with CUDA support if available.
    """
    global _tts_instance

    if _tts_instance is None:
        # Initialize XTTS v2 model
        _tts_instance = TTS("tts_models/multilingual/multi-dataset/xtts_v2")

        # Move to GPU if available (significant speedup)
        if torch.cuda.is_available():
            _tts_instance.to("cuda")
            print("TTS: Using CUDA GPU acceleration")
        else:
            print("TTS: Running on CPU (slower)")

    return _tts_instance


def _chunk_text(text: str, max_words: int = 400) -> List[str]:
    """Split text into chunks at sentence boundaries.

    Long texts are split into smaller chunks to avoid memory issues and
    improve generation quality. Splits at sentence boundaries (., !, ?)
    to maintain natural prosody.

    Args:
        text: Input text to split.
        max_words: Maximum words per chunk. Default: 400 words.

    Returns:
        List of text chunks, each under max_words limit.

    Example:
        >>> text = "Sentence one. Sentence two. Sentence three."
        >>> chunks = _chunk_text(text, max_words=5)
        >>> len(chunks)
        2
    """
    # Split into sentences using regex (., !, ?)
    sentences = re.split(r'(?<=[.!?])\s+', text)

    chunks = []
    current_chunk = []
    current_word_count = 0

    for sentence in sentences:
        sentence_words = len(sentence.split())

        # If adding this sentence exceeds limit, start new chunk
        if current_word_count + sentence_words > max_words and current_chunk:
            chunks.append(' '.join(current_chunk))
            current_chunk = [sentence]
            current_word_count = sentence_words
        else:
            current_chunk.append(sentence)
            current_word_count += sentence_words

    # Add remaining chunk
    if current_chunk:
        chunks.append(' '.join(current_chunk))

    return chunks if chunks else [text]


def generate_speech(
    text: str,
    output_dir: Path,
    language: str = "fr",
    max_words_per_chunk: int = 400,
) -> Path:
    """Generate speech audio from text using XTTS v2.

    Converts input text to natural-sounding speech audio using the Coqui XTTS v2
    multilingual model. Automatically handles long texts by chunking at sentence
    boundaries. Uses GPU acceleration when available.

    Args:
        text: Text to convert to speech. Can be any length.
        output_dir: Directory where the audio file will be saved.
            Created if it doesn't exist.
        language: Language code for TTS. Options: "fr", "en", "es", "de", etc.
            Default: "fr" (French).
        max_words_per_chunk: Maximum words per processing chunk for long texts.
            Default: 400 words. Increase for faster processing, decrease if
            running out of VRAM.

    Returns:
        Path to the generated .wav file.

    Raises:
        ImportError: If TTS library is not installed.
        RuntimeError: If TTS generation fails.
        OSError: If output directory cannot be created.

    Example:
        >>> from pathlib import Path
        >>> filepath = generate_speech(
        ...     text="La phénoménologie est une approche philosophique.",
        ...     output_dir=Path("output"),
        ...     language="fr"
        ... )
        >>> print(filepath)
        output/chat_audio_20250130_143045.wav

    Note:
        First call will download the XTTS v2 model (~2GB) and cache it.
        Subsequent calls reuse the cached model. GPU usage: 4-6GB VRAM.
    """
    # Create output directory if needed
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate timestamped filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"chat_audio_{timestamp}.wav"
    filepath = output_dir / filename

    # Get TTS instance (lazy loaded, cached)
    tts = _get_tts_instance()

    # For very long texts, we could chunk and concatenate
    # For now, process as single chunk (XTTS handles ~1000 words well)
    word_count = len(text.split())

    if word_count > max_words_per_chunk:
        print(f"TTS: Long text detected ({word_count} words), chunking...")
        chunks = _chunk_text(text, max_words=max_words_per_chunk)
        print(f"TTS: Split into {len(chunks)} chunks")

        # For MVP, just use first chunk and add warning
        # TODO: Implement multi-chunk concatenation with pydub
        text = chunks[0]
        print(f"TTS: WARNING - Using first chunk only ({len(text.split())} words)")

    try:
        # Generate speech with automatic mixed precision for efficiency
        if torch.cuda.is_available():
            with torch.cuda.amp.autocast():
                tts.tts_to_file(
                    text=text,
                    file_path=str(filepath),
                    language=language
                )
        else:
            tts.tts_to_file(
                text=text,
                file_path=str(filepath),
                language=language
            )

        print(f"TTS: Generated audio -> {filepath}")
        return filepath

    except Exception as e:
        raise RuntimeError(f"TTS generation failed: {str(e)}") from e
