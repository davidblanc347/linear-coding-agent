"""Weaviate schema definition for Library RAG - Philosophical Texts Database.

This module defines and manages the Weaviate vector database schema for the
Library RAG application. It provides functions to create, verify, and display
the schema configuration for indexing and searching philosophical texts.

Schema Architecture:
    The schema follows a normalized design with denormalized nested objects
    for efficient querying. The hierarchy is::

        Work (metadata only)
          └── Document (edition/translation instance)
                ├── Chunk (vectorized text fragments)
                └── Summary (vectorized chapter summaries)

Collections:
    **Work** (no vectorization):
        Represents a philosophical or scholarly work (e.g., Plato's Meno).
        Stores canonical metadata: title, author, year, language, genre.
        Not vectorized - used only for metadata and relationships.

    **Document** (no vectorization):
        Represents a specific edition or translation of a Work.
        Contains: sourceId, edition, language, pages, TOC, hierarchy.
        Includes nested Work reference for denormalized access.

    **Chunk** (vectorized with text2vec-transformers):
        Text fragments optimized for semantic search (200-800 chars).
        Vectorized fields: text, summary, keywords.
        Non-vectorized fields: sectionPath, chapterTitle, unitType, orderIndex.
        Includes nested Document and Work references.

    **Summary** (vectorized with text2vec-transformers):
        LLM-generated chapter/section summaries for high-level search.
        Vectorized fields: text, concepts.
        Includes nested Document reference.

Vectorization Strategy:
    - Only Chunk.text, Chunk.summary, Chunk.keywords, Summary.text, and Summary.concepts are vectorized
    - Uses text2vec-transformers (BAAI/bge-m3 with 1024-dim via Docker)
    - Metadata fields use skip_vectorization=True for filtering only
    - Work and Document collections have no vectorizer (metadata only)

Vector Index Configuration (2026-01):
    - **HNSW Index**: Hierarchical Navigable Small World for efficient search
    - **Rotational Quantization (RQ)**: Reduces memory footprint by ~75%
        - Minimal accuracy loss (<1%)
        - Essential for scaling to 100k+ chunks
    - **Distance Metric**: Cosine similarity (matches BGE-M3 training)

Migration Note (2024-12):
    Migrated from MiniLM-L6 (384-dim) to BAAI/bge-m3 (1024-dim) for:
    - 2.7x richer semantic representation
    - 8192 token context (vs 512)
    - Superior multilingual support (Greek, Latin, French, English)
    - Better performance on philosophical/academic texts

Nested Objects:
    Instead of using Weaviate cross-references, we use nested objects for
    denormalized data access. This allows single-query retrieval of chunk
    data with its Work/Document metadata without joins::

        Chunk.work = {title, author}
        Chunk.document = {sourceId, edition}
        Document.work = {title, author}
        Summary.document = {sourceId}

Usage:
    From command line::

        $ python schema.py

    Programmatically::

        import weaviate
        from schema import create_schema, verify_schema

        with weaviate.connect_to_local() as client:
            create_schema(client, delete_existing=True)
            verify_schema(client)

    Check existing schema::

        from schema import display_schema
        with weaviate.connect_to_local() as client:
            display_schema(client)

Dependencies:
    - Weaviate Python client v4+
    - Running Weaviate instance with text2vec-transformers module
    - Docker Compose setup from docker-compose.yml

See Also:
    - utils/weaviate_ingest.py : Functions to ingest data into this schema
    - utils/types.py : TypedDict definitions matching schema structure
    - docker-compose.yml : Weaviate + transformers container setup
"""

import sys
from typing import List, Set

import weaviate
import weaviate.classes.config as wvc


# =============================================================================
# Schema Creation Functions
# =============================================================================


def create_work_collection(client: weaviate.WeaviateClient) -> None:
    """Create the Work collection for philosophical works metadata.

    Args:
        client: Connected Weaviate client.

    Note:
        This collection has no vectorization - used only for metadata.
    """
    client.collections.create(
        name="Work",
        description="A philosophical or scholarly work (e.g., Meno, Republic, Apology).",
        vectorizer_config=wvc.Configure.Vectorizer.none(),
        properties=[
            wvc.Property(
                name="title",
                description="Title of the work.",
                data_type=wvc.DataType.TEXT,
            ),
            wvc.Property(
                name="author",
                description="Author of the work.",
                data_type=wvc.DataType.TEXT,
            ),
            wvc.Property(
                name="originalTitle",
                description="Original title in source language (optional).",
                data_type=wvc.DataType.TEXT,
            ),
            wvc.Property(
                name="year",
                description="Year of composition or publication (negative for BCE).",
                data_type=wvc.DataType.INT,
            ),
            wvc.Property(
                name="language",
                description="Original language (e.g., 'gr', 'la', 'fr').",
                data_type=wvc.DataType.TEXT,
            ),
            wvc.Property(
                name="genre",
                description="Genre or type (e.g., 'dialogue', 'treatise', 'commentary').",
                data_type=wvc.DataType.TEXT,
            ),
        ],
    )


def create_document_collection(client: weaviate.WeaviateClient) -> None:
    """Create the Document collection for edition/translation instances.

    Args:
        client: Connected Weaviate client.

    Note:
        Contains nested Work reference for denormalized access.
    """
    client.collections.create(
        name="Document",
        description="A specific edition or translation of a work (PDF, ebook, etc.).",
        vectorizer_config=wvc.Configure.Vectorizer.none(),
        properties=[
            wvc.Property(
                name="sourceId",
                description="Unique identifier for this document (filename without extension).",
                data_type=wvc.DataType.TEXT,
            ),
            wvc.Property(
                name="edition",
                description="Edition or translator (e.g., 'trad. Cousin', 'Loeb Classical Library').",
                data_type=wvc.DataType.TEXT,
            ),
            wvc.Property(
                name="language",
                description="Language of this edition (e.g., 'fr', 'en').",
                data_type=wvc.DataType.TEXT,
            ),
            wvc.Property(
                name="pages",
                description="Number of pages in the PDF/document.",
                data_type=wvc.DataType.INT,
            ),
            wvc.Property(
                name="chunksCount",
                description="Total number of chunks extracted from this document.",
                data_type=wvc.DataType.INT,
            ),
            wvc.Property(
                name="toc",
                description="Table of contents as JSON string [{title, level, page}, ...].",
                data_type=wvc.DataType.TEXT,
            ),
            wvc.Property(
                name="hierarchy",
                description="Full hierarchical structure as JSON string.",
                data_type=wvc.DataType.TEXT,
            ),
            wvc.Property(
                name="createdAt",
                description="Timestamp when this document was ingested.",
                data_type=wvc.DataType.DATE,
            ),
            # Nested Work reference
            wvc.Property(
                name="work",
                description="Reference to the Work this document is an instance of.",
                data_type=wvc.DataType.OBJECT,
                nested_properties=[
                    wvc.Property(name="title", data_type=wvc.DataType.TEXT),
                    wvc.Property(name="author", data_type=wvc.DataType.TEXT),
                ],
            ),
        ],
    )


def create_chunk_collection(client: weaviate.WeaviateClient) -> None:
    """Create the Chunk collection for vectorized text fragments.

    Args:
        client: Connected Weaviate client.

    Note:
        Uses text2vec-transformers for vectorizing 'text', 'summary', and 'keywords' fields.
        Other fields have skip_vectorization=True for filtering only.

        Vector Index Configuration:
            - HNSW index for efficient similarity search
            - Rotational Quantization (RQ): reduces memory by ~75% with minimal accuracy loss
            - Optimized for scaling to large (100k+) collections
    """
    client.collections.create(
        name="Chunk",
        description="A text chunk (paragraph, argument, etc.) vectorized for semantic search.",
        vectorizer_config=wvc.Configure.Vectorizer.text2vec_transformers(
            vectorize_collection_name=False,
        ),
        # HNSW index with RQ for optimal memory/performance trade-off
        vector_index_config=wvc.Configure.VectorIndex.hnsw(
            distance_metric=wvc.VectorDistances.COSINE,  # BGE-M3 uses cosine similarity
            quantizer=wvc.Configure.VectorIndex.Quantizer.rq(),
            # RQ provides ~75% memory reduction with <1% accuracy loss
            # Perfect for scaling philosophical text collections
        ),
        properties=[
            # Main content (vectorized)
            wvc.Property(
                name="text",
                description="The text content to be vectorized (200-800 chars optimal).",
                data_type=wvc.DataType.TEXT,
            ),
            wvc.Property(
                name="summary",
                description="LLM-generated summary of this chunk (100-200 words, VECTORIZED).",
                data_type=wvc.DataType.TEXT,
            ),
            # Hierarchical context (not vectorized, for filtering)
            wvc.Property(
                name="sectionPath",
                description="Full hierarchical path (e.g., 'Présentation > Qu'est-ce que la vertu?').",
                data_type=wvc.DataType.TEXT,
                skip_vectorization=True,
            ),
            wvc.Property(
                name="sectionLevel",
                description="Depth in hierarchy (1=top-level, 2=subsection, etc.).",
                data_type=wvc.DataType.INT,
            ),
            wvc.Property(
                name="chapterTitle",
                description="Title of the top-level chapter/section.",
                data_type=wvc.DataType.TEXT,
                skip_vectorization=True,
            ),
            wvc.Property(
                name="canonicalReference",
                description="Canonical academic reference (e.g., 'CP 1.628', 'Ménon 80a').",
                data_type=wvc.DataType.TEXT,
                skip_vectorization=True,
            ),
            # Classification (not vectorized, for filtering)
            wvc.Property(
                name="unitType",
                description="Type of logical unit (main_content, argument, exposition, transition, définition).",
                data_type=wvc.DataType.TEXT,
                skip_vectorization=True,
            ),
            wvc.Property(
                name="keywords",
                description="Key concepts extracted from this chunk (vectorized for semantic search).",
                data_type=wvc.DataType.TEXT_ARRAY,
            ),
            # Technical metadata (not vectorized)
            wvc.Property(
                name="orderIndex",
                description="Sequential position in the document (0-based).",
                data_type=wvc.DataType.INT,
            ),
            wvc.Property(
                name="language",
                description="Language of this chunk (e.g., 'fr', 'en', 'gr').",
                data_type=wvc.DataType.TEXT,
                skip_vectorization=True,
            ),
            # Cross references (nested objects)
            wvc.Property(
                name="document",
                description="Reference to parent Document with essential metadata.",
                data_type=wvc.DataType.OBJECT,
                nested_properties=[
                    wvc.Property(name="sourceId", data_type=wvc.DataType.TEXT),
                    wvc.Property(name="edition", data_type=wvc.DataType.TEXT),
                ],
            ),
            wvc.Property(
                name="work",
                description="Reference to the Work with essential metadata.",
                data_type=wvc.DataType.OBJECT,
                nested_properties=[
                    wvc.Property(name="title", data_type=wvc.DataType.TEXT),
                    wvc.Property(name="author", data_type=wvc.DataType.TEXT),
                ],
            ),
        ],
    )


def create_summary_collection(client: weaviate.WeaviateClient) -> None:
    """Create the Summary collection for chapter/section summaries.

    Args:
        client: Connected Weaviate client.

    Note:
        Uses text2vec-transformers for vectorizing summary text.

        Vector Index Configuration:
            - HNSW index for efficient similarity search
            - Rotational Quantization (RQ): reduces memory by ~75%
            - Optimized for summaries (shorter, more uniform text)
    """
    client.collections.create(
        name="Summary",
        description="Chapter or section summary, vectorized for high-level semantic search.",
        vectorizer_config=wvc.Configure.Vectorizer.text2vec_transformers(
            vectorize_collection_name=False,
        ),
        # HNSW index with RQ for optimal memory/performance trade-off
        vector_index_config=wvc.Configure.VectorIndex.hnsw(
            distance_metric=wvc.VectorDistances.COSINE,
            quantizer=wvc.Configure.VectorIndex.Quantizer.rq(),
            # RQ optimal for summaries (shorter, more uniform text)
        ),
        properties=[
            wvc.Property(
                name="sectionPath",
                description="Hierarchical path (e.g., 'Chapter 1 > Section 2').",
                data_type=wvc.DataType.TEXT,
                skip_vectorization=True,
            ),
            wvc.Property(
                name="title",
                description="Title of the section.",
                data_type=wvc.DataType.TEXT,
                skip_vectorization=True,
            ),
            wvc.Property(
                name="level",
                description="Hierarchy depth (1=chapter, 2=section, 3=subsection).",
                data_type=wvc.DataType.INT,
            ),
            wvc.Property(
                name="text",
                description="LLM-generated summary of the section content (VECTORIZED).",
                data_type=wvc.DataType.TEXT,
            ),
            wvc.Property(
                name="concepts",
                description="Key philosophical concepts in this section.",
                data_type=wvc.DataType.TEXT_ARRAY,
            ),
            wvc.Property(
                name="chunksCount",
                description="Number of chunks in this section.",
                data_type=wvc.DataType.INT,
            ),
            # Reference to Document
            wvc.Property(
                name="document",
                description="Reference to parent Document.",
                data_type=wvc.DataType.OBJECT,
                nested_properties=[
                    wvc.Property(name="sourceId", data_type=wvc.DataType.TEXT),
                ],
            ),
        ],
    )


def create_schema(client: weaviate.WeaviateClient, delete_existing: bool = True) -> None:
    """Create the complete Weaviate schema for Library RAG.

    Creates all four collections: Work, Document, Chunk, Summary.

    Args:
        client: Connected Weaviate client.
        delete_existing: If True, delete all existing collections first.

    Raises:
        Exception: If collection creation fails.
    """
    if delete_existing:
        print("\n[1/4] Suppression des collections existantes...")
        client.collections.delete_all()
        print("      ✓ Collections supprimées")

    print("\n[2/4] Création des collections...")

    print("      → Work (métadonnées œuvre)...")
    create_work_collection(client)

    print("      → Document (métadonnées édition)...")
    create_document_collection(client)

    print("      → Chunk (fragments vectorisés)...")
    create_chunk_collection(client)

    print("      → Summary (résumés de chapitres)...")
    create_summary_collection(client)

    print("      ✓ 4 collections créées")


def verify_schema(client: weaviate.WeaviateClient) -> bool:
    """Verify that all expected collections exist.

    Args:
        client: Connected Weaviate client.

    Returns:
        True if all expected collections exist, False otherwise.
    """
    print("\n[3/4] Vérification des collections...")
    collections = client.collections.list_all()

    expected: Set[str] = {"Work", "Document", "Chunk", "Summary"}
    actual: Set[str] = set(collections.keys())

    if expected == actual:
        print(f"      ✓ Toutes les collections créées: {sorted(actual)}")
        return True
    else:
        missing: Set[str] = expected - actual
        extra: Set[str] = actual - expected
        if missing:
            print(f"      ✗ Collections manquantes: {missing}")
        if extra:
            print(f"      ⚠ Collections inattendues: {extra}")
        return False


def display_schema(client: weaviate.WeaviateClient) -> None:
    """Display detailed information about schema collections.

    Args:
        client: Connected Weaviate client.
    """
    print("\n[4/4] Détail des collections créées:")
    print("=" * 80)

    collections = client.collections.list_all()

    for name in ["Work", "Document", "Chunk", "Summary"]:
        if name not in collections:
            continue

        config = collections[name]
        print(f"\n📦 {name}")
        print("─" * 80)
        print(f"Description: {config.description}")

        # Vectorizer
        vectorizer_str: str = str(config.vectorizer)
        if "text2vec" in vectorizer_str.lower():
            print("Vectorizer:  text2vec-transformers ✓")
        else:
            print("Vectorizer:  none")

        # Properties
        print("\nPropriétés:")
        for prop in config.properties:
            # Data type
            dtype: str = str(prop.data_type).split('.')[-1]

            # Skip vectorization flag
            skip: str = ""
            if hasattr(prop, 'skip_vectorization') and prop.skip_vectorization:
                skip = " [skip_vec]"

            # Nested properties
            nested: str = ""
            if hasattr(prop, 'nested_properties') and prop.nested_properties:
                nested_names: List[str] = [p.name for p in prop.nested_properties]
                nested = f" → {{{', '.join(nested_names)}}}"

            print(f"  • {prop.name:<20} {dtype:<15} {skip}{nested}")


def print_summary() -> None:
    """Print a summary of the schema architecture."""
    print("\n" + "=" * 80)
    print("SCHÉMA CRÉÉ AVEC SUCCÈS!")
    print("=" * 80)
    print("\n✓ Architecture:")
    print("  - Work: Source unique pour author/title")
    print("  - Document: Métadonnées d'édition avec référence vers Work")
    print("  - Chunk: Fragments vectorisés (text + summary + keywords)")
    print("  - Summary: Résumés de chapitres vectorisés (text + concepts)")
    print("\n✓ Vectorisation:")
    print("  - Work:    NONE")
    print("  - Document: NONE")
    print("  - Chunk:   text2vec (text + summary + keywords)")
    print("  - Summary: text2vec (text + concepts)")
    print("\n✓ Index Vectoriel (Optimisation 2026):")
    print("  - Chunk:   HNSW + RQ (~75% moins de RAM)")
    print("  - Summary: HNSW + RQ")
    print("  - Distance: Cosine (compatible BGE-M3)")
    print("=" * 80)


# =============================================================================
# Main Script Execution
# =============================================================================


def main() -> None:
    """Main entry point for schema creation script."""
    # Fix encoding for Windows console
    if sys.platform == "win32" and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 80)
    print("CRÉATION DU SCHÉMA WEAVIATE - BASE DE TEXTES PHILOSOPHIQUES")
    print("=" * 80)

    # Connect to local Weaviate
    client: weaviate.WeaviateClient = weaviate.connect_to_local(
        host="localhost",
        port=8080,
        grpc_port=50051,
    )

    try:
        create_schema(client, delete_existing=True)
        verify_schema(client)
        display_schema(client)
        print_summary()
    finally:
        client.close()
        print("\n✓ Connexion fermée\n")


if __name__ == "__main__":
    main()
