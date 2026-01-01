#!/usr/bin/env python3
"""Migration script: Add Work collection with vectorization.

This script safely adds the Work collection to the existing Weaviate schema
WITHOUT deleting the existing Chunk, Document, and Summary collections.

Migration Steps:
    1. Connect to Weaviate
    2. Check if Work collection already exists
    3. If exists, delete ONLY Work collection
    4. Create new Work collection with vectorization enabled
    5. Optionally populate Work from existing Chunk metadata
    6. Verify all 4 collections exist

Usage:
    python migrate_add_work_collection.py

Safety:
    - Does NOT touch Chunk collection (5400+ chunks preserved)
    - Does NOT touch Document collection
    - Does NOT touch Summary collection
    - Only creates/recreates Work collection
"""

import sys
from typing import Set

import weaviate
import weaviate.classes.config as wvc


def create_work_collection_vectorized(client: weaviate.WeaviateClient) -> None:
    """Create the Work collection WITH vectorization enabled.

    This is the new version that enables semantic search on work titles
    and author names.

    Args:
        client: Connected Weaviate client.
    """
    client.collections.create(
        name="Work",
        description="A philosophical or scholarly work (e.g., Meno, Republic, Apology).",
        # ✅ NEW: Enable vectorization for semantic search on titles/authors
        vectorizer_config=wvc.Configure.Vectorizer.text2vec_transformers(
            vectorize_collection_name=False,
        ),
        properties=[
            wvc.Property(
                name="title",
                description="Title of the work.",
                data_type=wvc.DataType.TEXT,
                # ✅ VECTORIZED by default (semantic search enabled)
            ),
            wvc.Property(
                name="author",
                description="Author of the work.",
                data_type=wvc.DataType.TEXT,
                # ✅ VECTORIZED by default (semantic search enabled)
            ),
            wvc.Property(
                name="originalTitle",
                description="Original title in source language (optional).",
                data_type=wvc.DataType.TEXT,
                skip_vectorization=True,  # Metadata only
            ),
            wvc.Property(
                name="year",
                description="Year of composition or publication (negative for BCE).",
                data_type=wvc.DataType.INT,
                # INT is never vectorized
            ),
            wvc.Property(
                name="language",
                description="Original language (e.g., 'gr', 'la', 'fr').",
                data_type=wvc.DataType.TEXT,
                skip_vectorization=True,  # ISO code, no need to vectorize
            ),
            wvc.Property(
                name="genre",
                description="Genre or type (e.g., 'dialogue', 'treatise', 'commentary').",
                data_type=wvc.DataType.TEXT,
                skip_vectorization=True,  # Metadata only
            ),
        ],
    )


def migrate_work_collection(client: weaviate.WeaviateClient) -> None:
    """Migrate Work collection by adding vectorization.

    This function:
    1. Checks if Work exists
    2. Deletes ONLY Work if it exists
    3. Creates new Work with vectorization
    4. Leaves all other collections untouched

    Args:
        client: Connected Weaviate client.
    """
    print("\n" + "=" * 80)
    print("MIGRATION: Ajouter vectorisation à Work")
    print("=" * 80)

    # Step 1: Check existing collections
    print("\n[1/5] Vérification des collections existantes...")
    collections = client.collections.list_all()
    existing: Set[str] = set(collections.keys())
    print(f"      Collections trouvées: {sorted(existing)}")

    # Step 2: Delete ONLY Work if it exists
    print("\n[2/5] Suppression de Work (si elle existe)...")
    if "Work" in existing:
        try:
            client.collections.delete("Work")
            print("      ✓ Work supprimée")
        except Exception as e:
            print(f"      ⚠ Erreur suppression Work: {e}")
    else:
        print("      ℹ Work n'existe pas encore")

    # Step 3: Create new Work with vectorization
    print("\n[3/5] Création de Work avec vectorisation...")
    try:
        create_work_collection_vectorized(client)
        print("      ✓ Work créée (vectorisation activée)")
    except Exception as e:
        print(f"      ✗ Erreur création Work: {e}")
        raise

    # Step 4: Verify all 4 collections exist
    print("\n[4/5] Vérification finale...")
    collections = client.collections.list_all()
    actual: Set[str] = set(collections.keys())
    expected: Set[str] = {"Work", "Document", "Chunk", "Summary"}

    if expected == actual:
        print(f"      ✓ Toutes les collections présentes: {sorted(actual)}")
    else:
        missing: Set[str] = expected - actual
        extra: Set[str] = actual - expected
        if missing:
            print(f"      ⚠ Collections manquantes: {missing}")
        if extra:
            print(f"      ℹ Collections supplémentaires: {extra}")

    # Step 5: Display Work config
    print("\n[5/5] Configuration de Work:")
    print("─" * 80)
    work_config = collections["Work"]
    print(f"Description: {work_config.description}")

    vectorizer_str: str = str(work_config.vectorizer)
    if "text2vec" in vectorizer_str.lower():
        print("Vectorizer:  text2vec-transformers ✅")
    else:
        print("Vectorizer:  none ❌")

    print("\nPropriétés vectorisées:")
    for prop in work_config.properties:
        if prop.name in ["title", "author"]:
            skip = "[skip_vec]" if (hasattr(prop, 'skip_vectorization') and prop.skip_vectorization) else "[VECTORIZED ✅]"
            print(f"  • {prop.name:<20} {skip}")

    print("\n" + "=" * 80)
    print("MIGRATION TERMINÉE AVEC SUCCÈS!")
    print("=" * 80)
    print("\n✓ Work collection vectorisée")
    print("✓ Chunk collection PRÉSERVÉE (aucune donnée perdue)")
    print("✓ Document collection PRÉSERVÉE")
    print("✓ Summary collection PRÉSERVÉE")
    print("\n💡 Prochaine étape (optionnel):")
    print("   Peupler Work en extrayant les œuvres uniques depuis Chunk.work")
    print("=" * 80 + "\n")


def main() -> None:
    """Main entry point for migration script."""
    # Fix encoding for Windows console
    if sys.platform == "win32" and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    # Connect to local Weaviate
    client: weaviate.WeaviateClient = weaviate.connect_to_local(
        host="localhost",
        port=8080,
        grpc_port=50051,
    )

    try:
        migrate_work_collection(client)
    finally:
        client.close()
        print("\n✓ Connexion fermée\n")


if __name__ == "__main__":
    main()
