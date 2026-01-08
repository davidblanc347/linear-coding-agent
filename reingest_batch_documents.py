"""Reingest documents that failed to ingest due to collection name bug."""

import json
import sys
from pathlib import Path

# Fix Windows encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent / "generations" / "library_rag"))

from utils.weaviate_ingest import ingest_document

# Documents to reingest
documents = [
    "A_Cartesian_critique_of_the_artificial_i",
    "Alan_Turing_and_John_von_Neumann_Their_B"
]

output_dir = Path(__file__).parent / "generations" / "library_rag" / "output"

print("🔄 Reingesting batch upload documents with fixed collection names...\n")

for doc_name in documents:
    print(f"📄 Processing: {doc_name}")

    # Load chunks JSON
    chunks_file = output_dir / doc_name / f"{doc_name}_chunks.json"
    if not chunks_file.exists():
        print(f"   ✗ Chunks file not found: {chunks_file}")
        continue

    with open(chunks_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    chunks = data.get("chunks", [])
    metadata = data.get("metadata", {})
    toc = data.get("toc", [])
    pages = data.get("pages", 0)
    language = metadata.get("language", "en")

    if not chunks:
        print(f"   ⚠️  No chunks found in file")
        continue

    print(f"   • Chunks: {len(chunks)}")
    print(f"   • Title: {metadata.get('title', 'N/A')}")
    print(f"   • Author: {metadata.get('author', 'N/A')}")
    print(f"   • Language: {language}")

    # Ingest to Weaviate
    print(f"   🚀 Ingesting to Weaviate...")
    result = ingest_document(
        doc_name=doc_name,
        chunks=chunks,
        metadata=metadata,
        language=language,
        toc=toc,
        pages=pages,
        ingest_document_collection=True,
        ingest_summary_collection=False,
    )

    if result["success"]:
        print(f"   ✅ Success! Inserted {result['count']} chunks")
    else:
        print(f"   ✗ Failed: {result.get('error', 'Unknown error')}")

    print()

print("=" * 70)
print("✓ Reingestion complete!")
print()

# Verify total count
import weaviate
print("🔍 Verifying total chunks in Weaviate...")
client = weaviate.connect_to_local()
try:
    chunk_coll = client.collections.get("Chunk_v2")
    total = chunk_coll.aggregate.over_all().total_count
    print(f"   Total chunks: {total}")
    print(f"   Expected: {5304 + 7 + 11} = 5,322")
finally:
    client.close()
