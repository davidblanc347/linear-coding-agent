"""
Migrate Chunk_v2 schema from TEXT2VEC_TRANSFORMERS to NONE vectorizer.

This allows pure manual vectorization with GPU embedder, removing dependency
on Docker text2vec-transformers service.

Steps:
1. Export all existing chunks with their vectors
2. Drop Chunk_v2 collection
3. Recreate Chunk_v2 with vectorizer=none()
4. Re-insert all chunks with their vectors
5. Verify data integrity
"""

import weaviate
import weaviate.classes as wvc
from weaviate.classes.config import Configure, Property, DataType, VectorDistances
import sys
from pathlib import Path
import json
from typing import List, Dict, Any
import time

# Add to path for imports
sys.path.insert(0, str(Path(__file__).parent))

def export_chunks():
    """Export all chunks with their vectors."""
    print("\n" + "="*70)
    print("STEP 1: Exporting existing chunks")
    print("="*70)

    client = weaviate.connect_to_local()

    try:
        chunk_coll = client.collections.get("Chunk_v2")

        # Count total
        count = chunk_coll.aggregate.over_all().total_count
        print(f"Total chunks to export: {count}")

        # Export all with vectors
        chunks = []
        batch_size = 1000

        for i, obj in enumerate(chunk_coll.iterator(include_vector=True)):
            if i % 100 == 0:
                print(f"  Exported {i}/{count} chunks...", end='\r')

            chunks.append({
                'uuid': str(obj.uuid),
                'properties': obj.properties,
                'vector': obj.vector
            })

        print(f"  Exported {len(chunks)}/{count} chunks... DONE")

        # Save to file
        backup_file = Path("chunk_v2_backup.json")
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(chunks, f, ensure_ascii=False, indent=2)

        print(f"\nBackup saved to: {backup_file}")
        print(f"  File size: {backup_file.stat().st_size / 1024 / 1024:.2f} MB")

        return chunks

    finally:
        client.close()

def recreate_schema():
    """Drop and recreate Chunk_v2 with vectorizer=none()."""
    print("\n" + "="*70)
    print("STEP 2: Recreating Chunk_v2 schema")
    print("="*70)

    client = weaviate.connect_to_local()

    try:
        # Drop existing collection
        print("Dropping existing Chunk_v2 collection...")
        try:
            client.collections.delete("Chunk_v2")
            print("  Collection dropped")
        except Exception as e:
            print(f"  Warning: {e}")

        time.sleep(2)

        # Create new collection with vectorizer=none()
        print("\nCreating new Chunk_v2 with vectorizer=none()...")

        client.collections.create(
            name="Chunk_v2",
            description="Document chunks with manual GPU vectorization (BAAI/bge-m3, 1024-dim)",
            vectorizer_config=Configure.Vectorizer.none(),  # MANUAL VECTORIZATION ONLY
            vector_index_config=Configure.VectorIndex.hnsw(
                distance_metric=VectorDistances.COSINE,
                ef_construction=128,
                max_connections=32,
                quantizer=Configure.VectorIndex.Quantizer.rq()
            ),
            properties=[
                Property(name="text", data_type=DataType.TEXT, description="Chunk text content"),
                Property(name="workTitle", data_type=DataType.TEXT, skip_vectorization=True, description="Work title"),
                Property(name="workAuthor", data_type=DataType.TEXT, skip_vectorization=True, description="Work author"),
                Property(name="sectionPath", data_type=DataType.TEXT, skip_vectorization=True, description="Section path"),
                Property(name="sectionLevel", data_type=DataType.INT, skip_vectorization=True, description="Section level"),
                Property(name="chapterTitle", data_type=DataType.TEXT, skip_vectorization=True, description="Chapter title"),
                Property(name="canonicalReference", data_type=DataType.TEXT, skip_vectorization=True, description="Canonical reference"),
                Property(name="unitType", data_type=DataType.TEXT, skip_vectorization=True, description="Unit type"),
                Property(name="keywords", data_type=DataType.TEXT_ARRAY, skip_vectorization=True, description="Keywords"),
                Property(name="language", data_type=DataType.TEXT, skip_vectorization=True, description="Language code"),
                Property(name="year", data_type=DataType.INT, skip_vectorization=True, description="Publication year"),
                Property(name="orderIndex", data_type=DataType.INT, skip_vectorization=True, description="Order index"),
            ]
        )

        print("  Collection created with vectorizer=none()")

        # Verify
        chunk_coll = client.collections.get("Chunk_v2")
        config = chunk_coll.config.get()
        print(f"\nVerification:")
        print(f"  Vectorizer: {config.vectorizer}")
        print(f"  Vector index: {config.vector_index_type}")

        if str(config.vectorizer) == "Vectorizers.NONE":
            print("  SUCCESS: Manual vectorization configured")
            return True
        else:
            print("  ERROR: Vectorizer not set to NONE")
            return False

    finally:
        client.close()

def reimport_chunks(chunks: List[Dict[str, Any]]):
    """Re-import all chunks with their vectors."""
    print("\n" + "="*70)
    print("STEP 3: Re-importing chunks with vectors")
    print("="*70)

    client = weaviate.connect_to_local()

    try:
        chunk_coll = client.collections.get("Chunk_v2")

        print(f"Total chunks to import: {len(chunks)}")

        # Batch import
        batch_size = 50
        total_inserted = 0

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i+batch_size]

            # Prepare DataObjects with vectors
            import weaviate.classes.data as wvd
            data_objects = []

            for chunk in batch:
                data_objects.append(
                    wvd.DataObject(
                        properties=chunk['properties'],
                        vector=chunk['vector']
                    )
                )

            # Insert batch
            try:
                response = chunk_coll.data.insert_many(data_objects)
                total_inserted += len(batch)
                print(f"  Imported {total_inserted}/{len(chunks)} chunks...", end='\r')
            except Exception as e:
                print(f"\n  ERROR in batch {i//batch_size + 1}: {e}")

        print(f"  Imported {total_inserted}/{len(chunks)} chunks... DONE")

        # Verify count
        time.sleep(2)
        final_count = chunk_coll.aggregate.over_all().total_count
        print(f"\nFinal count: {final_count}")

        if final_count == len(chunks):
            print("  SUCCESS: All chunks imported")
            return True
        else:
            print(f"  WARNING: Expected {len(chunks)}, got {final_count}")
            return False

    finally:
        client.close()

def verify_search():
    """Verify search still works with GPU embedder."""
    print("\n" + "="*70)
    print("STEP 4: Verifying search functionality")
    print("="*70)

    # Import GPU embedder
    from memory.core import get_embedder

    client = weaviate.connect_to_local()

    try:
        chunk_coll = client.collections.get("Chunk_v2")
        embedder = get_embedder()

        # Test query
        query = "Turing machine computation"
        print(f"Test query: '{query}'")

        # Generate query vector
        query_vector = embedder.embed_single(query)
        print(f"  Query vector shape: {query_vector.shape}")

        # Search
        results = chunk_coll.query.near_vector(
            near_vector=query_vector.tolist(),
            limit=5,
            return_metadata=wvc.query.MetadataQuery(distance=True)
        )

        print(f"\nSearch results: {len(results.objects)}")

        for i, obj in enumerate(results.objects[:3]):
            similarity = 1 - obj.metadata.distance
            print(f"  {i+1}. Work: {obj.properties.get('workTitle', 'N/A')[:50]}")
            print(f"     Similarity: {similarity:.3f}")

        if len(results.objects) > 0:
            print("\n  SUCCESS: Search works with GPU embedder")
            return True
        else:
            print("\n  ERROR: No search results")
            return False

    finally:
        client.close()

def test_new_insertion():
    """Test inserting new chunk with manual vector."""
    print("\n" + "="*70)
    print("STEP 5: Testing new chunk insertion")
    print("="*70)

    from memory.core import get_embedder

    client = weaviate.connect_to_local()

    try:
        chunk_coll = client.collections.get("Chunk_v2")
        embedder = get_embedder()

        # Create test chunk
        test_text = "This is a test chunk to verify manual vectorization works perfectly."
        test_vector = embedder.embed_single(test_text)

        print(f"Test text: '{test_text}'")
        print(f"Test vector shape: {test_vector.shape}")

        # Insert with manual vector
        import weaviate.classes.data as wvd

        uuid = chunk_coll.data.insert(
            properties={
                'text': test_text,
                'workTitle': 'TEST_MIGRATION',
                'workAuthor': 'Test Author',
                'sectionPath': 'Test Section',
                'language': 'en',
                'year': 2026,
                'orderIndex': 999999
            },
            vector=test_vector.tolist()
        )

        print(f"\nTest chunk inserted: {uuid}")

        # Verify insertion
        obj = chunk_coll.query.fetch_object_by_id(uuid, include_vector=True)

        if obj and obj.vector and len(obj.vector) == 1024:
            print(f"  SUCCESS: Chunk inserted with {len(obj.vector)}-dim vector")

            # Clean up test chunk
            chunk_coll.data.delete_by_id(uuid)
            print(f"  Test chunk deleted")

            return True
        else:
            print(f"  ERROR: Chunk insertion failed")
            return False

    finally:
        client.close()

def main():
    """Run full migration."""
    print("\n" + "="*70)
    print("CHUNK_V2 SCHEMA MIGRATION: TEXT2VEC_TRANSFORMERS -> NONE")
    print("GPU Embedder (BAAI/bge-m3) for Manual Vectorization")
    print("="*70)

    try:
        # Step 1: Export
        chunks = export_chunks()
        if not chunks:
            print("\nERROR: No chunks exported")
            return False

        # Step 2: Recreate schema
        if not recreate_schema():
            print("\nERROR: Schema recreation failed")
            return False

        # Step 3: Reimport
        if not reimport_chunks(chunks):
            print("\nERROR: Reimport failed")
            return False

        # Step 4: Verify search
        if not verify_search():
            print("\nERROR: Search verification failed")
            return False

        # Step 5: Test new insertion
        if not test_new_insertion():
            print("\nERROR: New insertion test failed")
            return False

        print("\n" + "="*70)
        print("MIGRATION COMPLETE - SUCCESS")
        print("="*70)
        print("\nChunk_v2 now uses:")
        print("  - Vectorizer: NONE (manual vectorization only)")
        print("  - GPU Embedder: BAAI/bge-m3 (1024-dim)")
        print("  - All existing chunks preserved")
        print("  - Search functionality verified")
        print("  - New insertions working")
        print("\nYou can now ingest documents with GPU embedder!")
        print("text2vec-transformers is GONE forever.")

        return True

    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
