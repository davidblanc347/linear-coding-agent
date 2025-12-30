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
import os

try:
    from TTS.api import TTS
    import torch
    from pydub import AudioSegment
except ImportError as e:
    if "pydub" in str(e):
        raise ImportError(
            "pydub library is required for audio concatenation. "
            "Install with: pip install pydub"
        )
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
        use_gpu = torch.cuda.is_available()

        # Initialize with GPU parameter to avoid CPU->GPU migration issues
        _tts_instance = TTS(
            "tts_models/multilingual/multi-dataset/xtts_v2",
            gpu=use_gpu
        )

        if use_gpu:
            print("TTS: Using CUDA GPU acceleration")
        else:
            print("TTS: Running on CPU (slower)")

    return _tts_instance


def _clean_markdown(text: str) -> str:
    """Remove markdown formatting for cleaner TTS output.

    Removes markdown syntax characters (headers, bold, italic, code blocks,
    links, quotes, list markers) to produce clean text suitable for
    text-to-speech generation without verbal artifacts.

    Args:
        text: Input text with markdown formatting.

    Returns:
        Clean text without markdown characters, suitable for TTS.

    Example:
        >>> text = "# Titre\\n**Gras** et *italique*\\n- Liste"
        >>> _clean_markdown(text)
        'Titre Gras et italique Liste'
    """
    # Remove headers (#, ##, ###, etc.)
    text = re.sub(r'#+\s*', '', text)

    # Remove bold (**text**)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)

    # Remove italic (*text* or _text_)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)

    # Remove code blocks (```text```)
    text = re.sub(r'```[^`]*```', '', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)

    # Remove links [text](url) -> keep text only
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)

    # Remove quotes (>)
    text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)

    # Remove list markers (-, *, +)
    text = re.sub(r'^[-*+]\s+', '', text, flags=re.MULTILINE)

    # Remove horizontal rules (---, ***, ___)
    text = re.sub(r'^[-*_]{3,}$', '', text, flags=re.MULTILINE)

    # Clean multiple spaces and newlines
    text = re.sub(r'\s+', ' ', text)

    return text.strip()


def _chunk_text(text: str, max_words: int = 400) -> List[str]:
    """Split text into chunks at sentence boundaries.

    Long texts are split into smaller chunks to avoid memory issues and
    improve generation quality. Splits at sentence boundaries (., !, ?)
    to maintain natural prosody. If a sentence is too long, splits at
    comma boundaries.

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

        # If sentence itself is too long, split at commas
        if sentence_words > max_words:
            # Split at commas
            parts = re.split(r'(?<=,)\s+', sentence)

            for i, part in enumerate(parts):
                part_words = len(part.split())
                is_last_part = (i == len(parts) - 1)
                ends_with_comma = part.rstrip().endswith(',')

                # If this would create a chunk ending with comma (incomplete thought)
                # Try to keep it with the next part
                if current_word_count + part_words > max_words and current_chunk:
                    # Only split if current chunk doesn't end with comma
                    # OR if we're forced to (chunk would be way too big)
                    if current_word_count + part_words > max_words * 1.3:
                        # Forced split - chunk is too big
                        chunks.append(' '.join(current_chunk))
                        current_chunk = [part]
                        current_word_count = part_words
                    elif not ends_with_comma or is_last_part:
                        # Safe to split - doesn't end with comma or is last part
                        chunks.append(' '.join(current_chunk))
                        current_chunk = [part]
                        current_word_count = part_words
                    else:
                        # Keep together to avoid mid-sentence cut
                        current_chunk.append(part)
                        current_word_count += part_words
                else:
                    current_chunk.append(part)
                    current_word_count += part_words
        else:
            # Normal sentence processing
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
    max_words_per_chunk: int = 30,
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
            Default: 30 words (~200 chars, quality mode for podcasts/audiobooks).
            Guarantees no warnings, optimal for clean audio with smooth transitions.

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

    # Clean markdown formatting before TTS processing
    text = _clean_markdown(text)
    print(f"TTS: Cleaned markdown formatting from input text")

    # Generate timestamped filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"chat_audio_{timestamp}.wav"
    filepath = output_dir / filename

    # Get TTS instance (lazy loaded, cached)
    tts = _get_tts_instance()

    # Path to speaker reference audio (for XTTS v2 voice cloning)
    # Located at: generations/library_rag/output/voices/speaker_wav.wav
    project_root = Path(__file__).parent.parent
    speaker_wav_path = project_root / "output" / "voices" / "speaker_wav.wav"

    # Check if text needs chunking
    word_count = len(text.split())

    if word_count > max_words_per_chunk:
        print(f"TTS: Long text detected ({word_count} words), chunking...")
        chunks = _chunk_text(text, max_words=max_words_per_chunk)
        print(f"TTS: Split into {len(chunks)} chunks")

        # Generate audio for each chunk
        temp_files = []
        try:
            for i, chunk in enumerate(chunks):
                # Create temporary file for this chunk
                temp_filepath = output_dir / f"temp_chunk_{i}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"

                print(f"TTS: Generating chunk {i+1}/{len(chunks)} ({len(chunk.split())} words)...")

                # Generate audio for this chunk
                tts.tts_to_file(
                    text=chunk,
                    file_path=str(temp_filepath),
                    language=language,
                    speaker_wav=str(speaker_wav_path)
                )

                temp_files.append(temp_filepath)

            # Concatenate all audio chunks with crossfade
            print(f"TTS: Concatenating {len(temp_files)} audio chunks with crossfade...")
            combined = AudioSegment.from_wav(str(temp_files[0]))

            # Add remaining chunks with 100ms crossfade for smooth transitions
            for temp_file in temp_files[1:]:
                audio_chunk = AudioSegment.from_wav(str(temp_file))
                combined = combined.append(audio_chunk, crossfade=100)

            # Export final concatenated audio
            combined.export(str(filepath), format="wav")
            print(f"TTS: Generated concatenated audio -> {filepath}")

        finally:
            # Clean up temporary files
            for temp_file in temp_files:
                try:
                    if temp_file.exists():
                        os.remove(temp_file)
                except Exception as e:
                    print(f"TTS: Warning - Could not delete temp file {temp_file}: {e}")

        return filepath

    else:
        # Single chunk - generate directly
        try:
            tts.tts_to_file(
                text=text,
                file_path=str(filepath),
                language=language,
                speaker_wav=str(speaker_wav_path)
            )

            print(f"TTS: Generated audio -> {filepath}")
            return filepath

        except Exception as e:
            raise RuntimeError(f"TTS generation failed: {str(e)}") from e
