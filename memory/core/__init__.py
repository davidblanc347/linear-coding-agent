"""
Memory Core Module - GPU Embedding Service and Utilities.

This module provides core functionality for the unified RAG system:
    - GPU-accelerated embeddings (RTX 4070 + PyTorch CUDA)
    - Singleton embedding service
    - Weaviate connection utilities

Usage:
    from memory.core import get_embedder, embed_text

    # Get singleton embedder
    embedder = get_embedder()

    # Embed text
    embedding = embed_text("Hello world")
"""

from memory.core.embedding_service import (
    GPUEmbeddingService,
    get_embedder,
    embed_text,
    embed_texts,
)

__all__ = [
    "GPUEmbeddingService",
    "get_embedder",
    "embed_text",
    "embed_texts",
]
