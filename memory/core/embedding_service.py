#!/usr/bin/env python3
"""
GPU Embedding Service - Singleton for RTX 4070.

This module provides a singleton service for generating embeddings using
BAAI/bge-m3 model on GPU with FP16 precision.

Architecture:
    - Singleton pattern: One model instance shared across application
    - PyTorch CUDA: RTX 4070 with 8 GB VRAM
    - FP16 precision: Reduces VRAM usage by ~50%
    - Optimal batch size: 48 (tested for RTX 4070 with 5.3 GB available)

Performance (RTX 4070):
    - Single embedding: ~17 ms
    - Batch 48: ~34 ms (0.71 ms per item)
    - VRAM usage: ~2.6 GB peak

Usage:
    from memory.core.embedding_service import get_embedder

    embedder = get_embedder()

    # Single text
    embedding = embedder.embed_single("Test text")

    # Batch
    embeddings = embedder.embed_batch(["Text 1", "Text 2", ...])
"""

import torch
from sentence_transformers import SentenceTransformer
from typing import List, Union
import logging
import numpy as np

logger = logging.getLogger(__name__)


class GPUEmbeddingService:
    """Singleton GPU embedding service using BAAI/bge-m3."""

    _instance = None
    _initialized = False

    def __new__(cls):
        """Singleton pattern: only one instance."""
        if cls._instance is None:
            cls._instance = super(GPUEmbeddingService, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize GPU embedder (only once)."""
        if self._initialized:
            return

        logger.info("Initializing GPU Embedding Service...")

        # Check CUDA availability
        if not torch.cuda.is_available():
            raise RuntimeError(
                "CUDA not available! GPU embedding service requires PyTorch with CUDA.\n"
                "Install with: pip install torch --index-url https://download.pytorch.org/whl/cu124"
            )

        # Device configuration
        self.device = torch.device("cuda:0")
        logger.info(f"Using GPU: {torch.cuda.get_device_name(0)}")

        # Model configuration
        self.model_name = "BAAI/bge-m3"
        self.embedding_dim = 1024
        self.max_seq_length = 8192

        # Load model on GPU
        logger.info(f"Loading {self.model_name} on GPU...")
        self.model = SentenceTransformer(self.model_name, device=str(self.device))

        # Convert to FP16 for memory efficiency
        logger.info("Converting model to FP16 precision...")
        self.model.half()

        # Optimal batch size for RTX 4070 (5.3 GB VRAM available)
        # Tested: batch 48 uses ~3.5 GB VRAM, leaves ~1.8 GB buffer
        self.optimal_batch_size = 48

        # VRAM monitoring
        self._log_vram_usage()

        self._initialized = True
        logger.info("GPU Embedding Service initialized successfully")

    def _log_vram_usage(self):
        """Log current VRAM usage."""
        allocated = torch.cuda.memory_allocated(0) / 1024**3
        reserved = torch.cuda.memory_reserved(0) / 1024**3
        total = torch.cuda.get_device_properties(0).total_memory / 1024**3

        logger.info(
            f"VRAM: {allocated:.2f} GB allocated, "
            f"{reserved:.2f} GB reserved, "
            f"{total:.2f} GB total"
        )

    def embed_single(self, text: str) -> np.ndarray:
        """
        Embed a single text.

        Args:
            text: Text to embed.

        Returns:
            Embedding vector (1024 dimensions).

        Example:
            >>> embedder = get_embedder()
            >>> emb = embedder.embed_single("Hello world")
            >>> emb.shape
            (1024,)
        """
        # Use convert_to_numpy=False to keep tensor on GPU
        embedding_tensor = self.model.encode(
            text,
            convert_to_numpy=False,
            show_progress_bar=False
        )

        # Convert to numpy on CPU
        return embedding_tensor.cpu().numpy()

    def embed_batch(
        self,
        texts: List[str],
        batch_size: int = None,
        show_progress: bool = False
    ) -> np.ndarray:
        """
        Embed a batch of texts.

        Args:
            texts: List of texts to embed.
            batch_size: Batch size (default: optimal_batch_size=48).
            show_progress: Show progress bar.

        Returns:
            Array of embeddings, shape (len(texts), 1024).

        Example:
            >>> embedder = get_embedder()
            >>> texts = ["Text 1", "Text 2", "Text 3"]
            >>> embs = embedder.embed_batch(texts)
            >>> embs.shape
            (3, 1024)
        """
        if batch_size is None:
            batch_size = self.optimal_batch_size

        # Adjust batch size if VRAM is low
        if batch_size > self.optimal_batch_size:
            logger.warning(
                f"Batch size {batch_size} exceeds optimal {self.optimal_batch_size}, "
                f"reducing to avoid OOM"
            )
            batch_size = self.optimal_batch_size

        # Encode on GPU, keep as tensor
        embeddings_tensor = self.model.encode(
            texts,
            batch_size=batch_size,
            convert_to_numpy=False,
            show_progress_bar=show_progress
        )

        # Handle both tensor and list of tensors
        if isinstance(embeddings_tensor, list):
            embeddings_tensor = torch.stack(embeddings_tensor)

        # Convert to numpy on CPU
        return embeddings_tensor.cpu().numpy()

    def get_embedding_dimension(self) -> int:
        """Get embedding dimension (1024 for bge-m3)."""
        return self.embedding_dim

    def get_model_info(self) -> dict:
        """
        Get model information.

        Returns:
            Dictionary with model metadata.
        """
        return {
            "model_name": self.model_name,
            "embedding_dim": self.embedding_dim,
            "max_seq_length": self.max_seq_length,
            "device": str(self.device),
            "optimal_batch_size": self.optimal_batch_size,
            "precision": "FP16",
            "vram_allocated_gb": torch.cuda.memory_allocated(0) / 1024**3,
            "vram_reserved_gb": torch.cuda.memory_reserved(0) / 1024**3,
        }

    def clear_cache(self):
        """Clear CUDA cache to free VRAM."""
        torch.cuda.empty_cache()
        logger.info("CUDA cache cleared")
        self._log_vram_usage()

    def adjust_batch_size(self, new_batch_size: int):
        """
        Adjust optimal batch size (for OOM handling).

        Args:
            new_batch_size: New batch size to use.
        """
        logger.warning(
            f"Adjusting batch size from {self.optimal_batch_size} to {new_batch_size}"
        )
        self.optimal_batch_size = new_batch_size


# Singleton accessor
_embedder_instance = None


def get_embedder() -> GPUEmbeddingService:
    """
    Get the singleton GPU embedding service.

    Returns:
        Initialized GPUEmbeddingService instance.

    Example:
        >>> from memory.core.embedding_service import get_embedder
        >>> embedder = get_embedder()
        >>> emb = embedder.embed_single("Test")
    """
    global _embedder_instance

    if _embedder_instance is None:
        _embedder_instance = GPUEmbeddingService()

    return _embedder_instance


# Convenience functions
def embed_text(text: str) -> np.ndarray:
    """
    Convenience function to embed single text.

    Args:
        text: Text to embed.

    Returns:
        Embedding vector (1024 dimensions).
    """
    return get_embedder().embed_single(text)


def embed_texts(texts: List[str], batch_size: int = None) -> np.ndarray:
    """
    Convenience function to embed batch of texts.

    Args:
        texts: Texts to embed.
        batch_size: Batch size (default: optimal).

    Returns:
        Array of embeddings, shape (len(texts), 1024).
    """
    return get_embedder().embed_batch(texts, batch_size=batch_size)
