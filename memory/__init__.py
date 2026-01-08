"""
Ikario Unified Memory System.

This package provides the unified RAG system combining:
    - Personal memory (thoughts, conversations)
    - Philosophical library (works, documents, chunks)

Architecture:
    - Weaviate 1.34.4 vector database
    - GPU embeddings (BAAI/bge-m3 on RTX 4070)
    - 7 collections: Thought, Conversation, Message, Work, Document, Chunk, Summary
    - 17 MCP tools (9 memory + 8 library)

See: PLAN_MIGRATION_WEAVIATE_GPU.md
"""

__version__ = "2.0.0"
__author__ = "Ikario Project"
