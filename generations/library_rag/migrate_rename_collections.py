#!/usr/bin/env python3
"""
Rename collections: Chunk_v2 -> Chunk, Summary_v2 -> Summary

Weaviate doesn't support renaming collections directly, so this script:
1. Creates new collections (Chunk, Summary) with identical schema
2. Copies all objects with their vectors (batch insert)
3. Validates the migration (count check)
4. Optionally deletes old collections (--cleanup flag)

Usage:
    python migrate_rename_collections.py --dry-run    # Preview without changes
    python migrate_rename_collections.py              # Execute migration
    python migrate_rename_collections.py --cleanup    # Delete old collections after validation
"""

import weaviate
import weaviate.classes as wvc
from weaviate.classes.config import Configure, Property, DataType, VectorDistances
from weaviate.classes.query import Filter
import sys
import argparse
from typing import Any
import time

MIGRATIONS = [
    ("Chunk_v2", "Chunk"),
    ("Summary_v2", "Summary"),
]

BATCH_SIZE = 100


def get_collection_count(client: weaviate.WeaviateClient, name: str) -> int:
    """Get the number of objects in a collection."""
    try:
        coll = client.collections.get(name)
        return coll.aggregate.over_all().total_count
    except Exception:
        return 0


def collection_exists(client: weaviate.WeaviateClient, name: str) -> bool:
    """Check if a collection exists."""
    try:
        client.collections.get(name)
        return True
    except Exception:
        return False


def create_chunk_collection(client: weaviate.WeaviateClient) -> None:
    """Create the new Chunk collection with schema from Chunk_v2."""
    print("  Creating Chunk collection...")

    client.collections.create(
        name="Chunk",
        description="Document chunks with manual GPU vectorization (BAAI/bge-m3, 1024-dim)",
        vectorizer_config=Configure.Vectorizer.none(),
        vector_index_config=Configure.VectorIndex.hnsw(
            distance_metric=VectorDistances.COSINE,
            ef_construction=128,
            max_connections=32,
            quantizer=Configure.VectorIndex.Quantizer.rq(),
        ),
        properties=[
            Property(name="text", data_type=DataType.TEXT, description="Chunk text content"),
            Property(name="workTitle", data_type=DataType.TEXT, description="Work title"),
            Property(name="workAuthor", data_type=DataType.TEXT, description="Work author"),
            Property(name="sectionPath", data_type=DataType.TEXT, description="Section path"),
            Property(name="sectionLevel", data_type=DataType.INT, description="Section level"),
            Property(name="chapterTitle", data_type=DataType.TEXT, description="Chapter title"),
            Property(name="canonicalReference", data_type=DataType.TEXT, description="Canonical reference"),
            Property(name="unitType", data_type=DataType.TEXT, description="Unit type"),
            Property(name="keywords", data_type=DataType.TEXT_ARRAY, description="Keywords"),
            Property(name="language", data_type=DataType.TEXT, description="Language code"),
            Property(name="year", data_type=DataType.INT, description="Publication year"),
            Property(name="orderIndex", data_type=DataType.INT, description="Order index"),
            Property(name="summary", data_type=DataType.TEXT, description="Chunk summary"),
            Property(name="document", data_type=DataType.TEXT, description="Document reference"),
        ],
    )
    print("  [OK] Chunk collection created")


def create_summary_collection(client: weaviate.WeaviateClient) -> None:
    """Create the new Summary collection with schema from Summary_v2."""
    print("  Creating Summary collection...")

    client.collections.create(
        name="Summary",
        description="Section summaries (v2 - sans Document)",
        vectorizer_config=Configure.Vectorizer.none(),
        vector_index_config=Configure.VectorIndex.hnsw(
            distance_metric=VectorDistances.COSINE,
            ef_construction=128,
            max_connections=32,
            quantizer=Configure.VectorIndex.Quantizer.rq(),
        ),
        properties=[
            Property(name="text", data_type=DataType.TEXT, description="Summary text (vectorized)"),
            Property(name="concepts", data_type=DataType.TEXT_ARRAY, description="Key concepts"),
            Property(name="workTitle", data_type=DataType.TEXT, description="Work title"),
            Property(name="sectionPath", data_type=DataType.TEXT, description="Section path"),
            Property(name="title", data_type=DataType.TEXT, description="Section title"),
            Property(name="level", data_type=DataType.INT, description="Hierarchy level"),
            Property(name="chunksCount", data_type=DataType.INT, description="Chunks count"),
            Property(name="language", data_type=DataType.TEXT, description="Language code"),
            Property(name="workAuthor", data_type=DataType.TEXT, description="Work author"),
            Property(name="year", data_type=DataType.NUMBER, description="Publication year"),
        ],
    )
    print("  [OK] Summary collection created")


def clean_properties(props: dict[str, Any], collection_name: str) -> dict[str, Any]:
    """Clean properties to ensure correct types."""
    cleaned = dict(props)

    # Integer fields that may have been stored as float
    int_fields = ["sectionLevel", "year", "orderIndex", "level", "chunksCount"]

    for field in int_fields:
        if field in cleaned and cleaned[field] is not None:
            try:
                cleaned[field] = int(cleaned[field])
            except (ValueError, TypeError):
                pass

    return cleaned


def migrate_objects(
    client: weaviate.WeaviateClient,
    source_name: str,
    target_name: str,
    dry_run: bool = False
) -> int:
    """Copy all objects from source to target collection with vectors."""
    source = client.collections.get(source_name)
    target = client.collections.get(target_name)

    total = source.aggregate.over_all().total_count
    print(f"  Migrating {total} objects from {source_name} -> {target_name}")

    if dry_run:
        print(f"  [DRY-RUN] Would migrate {total} objects")
        return total

    migrated = 0
    errors = 0
    batch_objects: list[dict[str, Any]] = []

    for obj in source.iterator(include_vector=True):
        # Get vector (handle both dict and direct vector)
        vector = obj.vector
        if isinstance(vector, dict):
            vector = vector.get("default", list(vector.values())[0] if vector else None)

        # Clean properties to ensure correct types
        cleaned_props = clean_properties(obj.properties, target_name)

        batch_objects.append({
            "uuid": obj.uuid,
            "properties": cleaned_props,
            "vector": vector,
        })

        if len(batch_objects) >= BATCH_SIZE:
            # Insert batch
            with target.batch.dynamic() as batch:
                for item in batch_objects:
                    batch.add_object(
                        uuid=item["uuid"],
                        properties=item["properties"],
                        vector=item["vector"],
                    )
            migrated += len(batch_objects)
            print(f"    Progress: {migrated}/{total} ({100*migrated//total}%)", end='\r')
            batch_objects = []

    # Insert remaining objects
    if batch_objects:
        with target.batch.dynamic() as batch:
            for item in batch_objects:
                batch.add_object(
                    uuid=item["uuid"],
                    properties=item["properties"],
                    vector=item["vector"],
                )
        migrated += len(batch_objects)

    print(f"    Progress: {migrated}/{total} (100%)      ")
    print(f"  [OK] Migrated {migrated} objects")

    return migrated


def validate_migration(
    client: weaviate.WeaviateClient,
    source_name: str,
    target_name: str
) -> bool:
    """Validate that source and target have same object count."""
    source_count = get_collection_count(client, source_name)
    target_count = get_collection_count(client, target_name)

    if source_count == target_count:
        print(f"  [OK] Validation passed: {source_name}={source_count}, {target_name}={target_count}")
        return True
    else:
        print(f"  [ERROR] Validation FAILED: {source_name}={source_count}, {target_name}={target_count}")
        return False


def cleanup_old_collections(client: weaviate.WeaviateClient, dry_run: bool = False) -> None:
    """Delete old collections after successful migration."""
    print("\n" + "="*70)
    print("CLEANUP: Deleting old collections")
    print("="*70)

    for source_name, target_name in MIGRATIONS:
        if not collection_exists(client, source_name):
            print(f"  {source_name}: Already deleted")
            continue

        if not collection_exists(client, target_name):
            print(f"  [ERROR] Cannot delete {source_name}: {target_name} doesn't exist!")
            continue

        # Validate before deleting
        if not validate_migration(client, source_name, target_name):
            print(f"  [ERROR] Skipping {source_name} deletion: validation failed")
            continue

        if dry_run:
            print(f"  [DRY-RUN] Would delete {source_name}")
        else:
            client.collections.delete(source_name)
            print(f"  [OK] Deleted {source_name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Rename Weaviate collections")
    parser.add_argument("--dry-run", action="store_true", help="Preview without making changes")
    parser.add_argument("--cleanup", action="store_true", help="Delete old collections after validation")
    args = parser.parse_args()

    print("="*70)
    print("WEAVIATE COLLECTION RENAME: Chunk_v2 -> Chunk, Summary_v2 -> Summary")
    print("="*70)
    print(f"Mode: {'DRY-RUN' if args.dry_run else 'LIVE'}")
    print(f"Cleanup: {'YES' if args.cleanup else 'NO'}")
    print()

    client = weaviate.connect_to_local()

    try:
        # Show current state
        print("Current collections:")
        for source_name, target_name in MIGRATIONS:
            source_count = get_collection_count(client, source_name)
            target_exists = collection_exists(client, target_name)
            target_count = get_collection_count(client, target_name) if target_exists else 0
            print(f"  {source_name}: {source_count} objects")
            print(f"  {target_name}: {'exists (' + str(target_count) + ' objects)' if target_exists else 'does not exist'}")
        print()

        if args.cleanup:
            cleanup_old_collections(client, dry_run=args.dry_run)
            return

        # Migration
        for source_name, target_name in MIGRATIONS:
            print("="*70)
            print(f"MIGRATING: {source_name} -> {target_name}")
            print("="*70)

            # Check source exists
            if not collection_exists(client, source_name):
                print(f"  [ERROR] Source collection {source_name} does not exist!")
                continue

            # Check if target already exists
            if collection_exists(client, target_name):
                target_count = get_collection_count(client, target_name)
                if target_count > 0:
                    print(f"  Target {target_name} already exists with {target_count} objects")
                    print(f"  Skipping (already migrated)")
                    continue
                else:
                    print(f"  Target {target_name} exists but empty, will populate")
            else:
                # Create target collection
                if not args.dry_run:
                    if target_name == "Chunk":
                        create_chunk_collection(client)
                    elif target_name == "Summary":
                        create_summary_collection(client)
                else:
                    print(f"  [DRY-RUN] Would create {target_name} collection")

            # Migrate objects
            if not args.dry_run:
                migrate_objects(client, source_name, target_name, dry_run=False)
            else:
                migrate_objects(client, source_name, target_name, dry_run=True)

            # Validate
            if not args.dry_run:
                validate_migration(client, source_name, target_name)

            print()

        # Final status
        print("="*70)
        print("MIGRATION COMPLETE")
        print("="*70)
        print("\nFinal state:")
        for source_name, target_name in MIGRATIONS:
            source_count = get_collection_count(client, source_name)
            target_count = get_collection_count(client, target_name)
            print(f"  {source_name}: {source_count} objects")
            print(f"  {target_name}: {target_count} objects")

        if not args.dry_run:
            print("\nNext steps:")
            print("  1. Update code: replace 'Chunk_v2' -> 'Chunk', 'Summary_v2' -> 'Summary'")
            print("  2. Test the application")
            print("  3. Run: python migrate_rename_collections.py --cleanup")

    finally:
        client.close()


if __name__ == "__main__":
    main()
