"""
Fix Turings_Machines ingestion with corrected metadata.

The LLM returned prompt instructions instead of actual metadata.
This script:
1. Loads chunks from Turings_Machines_chunks.json
2. Corrects workTitle and workAuthor
3. Re-ingests to Weaviate with GPU embedder
"""

import json
import sys
from pathlib import Path

# Add current directory to path for imports
current_dir = Path(__file__).parent.absolute()
sys.path.insert(0, str(current_dir))

# Now import can work
import utils.weaviate_ingest as weaviate_ingest

def fix_turings_machines():
    """Fix and re-ingest Turings_Machines with corrected metadata."""

    # Load chunks JSON
    chunks_file = Path("output/Turings_Machines/Turings_Machines_chunks.json")

    if not chunks_file.exists():
        print(f"ERROR: File not found: {chunks_file}")
        return

    with open(chunks_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    print("Loaded chunks JSON")
    print(f"   - Chunks: {len(data.get('chunks', []))}")
    print(f"   - Current title: {data.get('metadata', {}).get('title', 'N/A')[:80]}")
    print(f"   - Current author: {data.get('metadata', {}).get('author', 'N/A')[:80]}")

    # Correct metadata
    corrected_metadata = {
        "title": "Turing's Machines",
        "author": "Dorian Wiszniewski, Richard Coyne, Christopher Pierce",
        "year": 2000,  # Approximate - from references (Coyne 1999, etc.)
        "language": "en"
    }

    # Update metadata
    data["metadata"] = corrected_metadata

    # Update all chunks with corrected metadata
    for chunk in data.get("chunks", []):
        chunk["workTitle"] = corrected_metadata["title"]
        chunk["workAuthor"] = corrected_metadata["author"]
        chunk["year"] = corrected_metadata["year"]

    print("\nCorrected metadata:")
    print(f"   - Title: {corrected_metadata['title']}")
    print(f"   - Author: {corrected_metadata['author']}")
    print(f"   - Year: {corrected_metadata['year']}")

    # Prepare chunks for ingestion (format expected by ingest_document)
    chunks_for_ingestion = []
    for i, chunk in enumerate(data.get("chunks", [])):
        chunks_for_ingestion.append({
            "text": chunk["text"],
            "sectionPath": chunk.get("section", ""),
            "sectionLevel": chunk.get("section_level", 1),
            "chapterTitle": "",
            "canonicalReference": "",
            "unitType": chunk.get("type", "main_content"),
            "keywords": chunk.get("concepts", []),
            "language": "en",
            "orderIndex": i,
        })

    print(f"\nPrepared {len(chunks_for_ingestion)} chunks for ingestion")

    # Re-ingest to Weaviate
    print("\nStarting re-ingestion with GPU embedder...")

    result = weaviate_ingest.ingest_document(
        doc_name="Turings_Machines",
        chunks=chunks_for_ingestion,
        metadata=corrected_metadata,
        language="en"
    )

    if result.get("success"):
        print(f"\nRe-ingestion successful!")
        print(f"   - Chunks inserted: {result.get('count', 0)}")
        print(f"   - Work UUID: {result.get('work_uuid', 'N/A')}")
    else:
        print(f"\nRe-ingestion failed!")
        print(f"   - Error: {result.get('error', 'Unknown')}")

    # Save corrected chunks JSON
    corrected_file = chunks_file.parent / f"{chunks_file.stem}_corrected.json"
    with open(corrected_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\nSaved corrected chunks to: {corrected_file}")

    return result

if __name__ == "__main__":
    print("=" * 70)
    print("Fix Turings_Machines Ingestion")
    print("=" * 70)

    result = fix_turings_machines()

    if result and result.get("success"):
        print("\n" + "=" * 70)
        print("FIX COMPLETED SUCCESSFULLY")
        print("=" * 70)
        sys.exit(0)
    else:
        print("\n" + "=" * 70)
        print("FIX FAILED")
        print("=" * 70)
        sys.exit(1)
