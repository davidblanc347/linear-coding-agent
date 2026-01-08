"""Create missing Work entries for test documents."""

import json
import sys
from pathlib import Path

# Fix Windows encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent / "generations" / "library_rag"))

from utils.weaviate_ingest import create_or_get_work, get_weaviate_client

# Documents to create Works for
documents = [
    "A_Cartesian_critique_of_the_artificial_i",
    "Alan_Turing_and_John_von_Neumann_Their_B"
]

output_dir = Path(__file__).parent / "generations" / "library_rag" / "output"

print("Creating missing Work entries...\n")

with get_weaviate_client() as client:
    if client is None:
        print("Error: Could not connect to Weaviate")
        sys.exit(1)

    for doc_name in documents:
        print(f"Processing: {doc_name}")

        # Load metadata from chunks JSON
        chunks_file = output_dir / doc_name / f"{doc_name}_chunks.json"
        if not chunks_file.exists():
            print(f"  ✗ Chunks file not found")
            continue

        with open(chunks_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        metadata = data.get("metadata", {})
        pages = data.get("pages", 0)

        # Create or get Work
        work_uuid = create_or_get_work(client, doc_name, metadata, pages)

        if work_uuid:
            print(f"  ✓ Work created/retrieved: {work_uuid[:8]}...")
        else:
            print(f"  ✗ Failed to create Work")

        print()

print("=" * 70)
print("Done! Checking /documents page now should show the new works.")
