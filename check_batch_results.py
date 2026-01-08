"""Check batch upload results in Weaviate."""

import sys
from pathlib import Path

# Fix Windows encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent / "generations" / "library_rag"))

import weaviate

print("Connecting to Weaviate...")
client = weaviate.connect_to_local(host="localhost", port=8080, grpc_port=50051)

try:
    chunk_collection = client.collections.get("Chunk_v2")

    # Fetch recent chunks and look for the new documents
    print("\n1. Fetching recent chunks (last 50)...")
    all_chunks = chunk_collection.query.fetch_objects(limit=50)

    # Group by work title
    works = {}
    for chunk in all_chunks.objects:
        work_info = chunk.properties.get('work', {})
        title = work_info.get('title', 'N/A')
        author = work_info.get('author', 'N/A')
        if title not in works:
            works[title] = {'author': author, 'count': 0}
        works[title]['count'] += 1

    # Check for our test documents
    cartesian_found = False
    turing_found = False

    print("\n2. Looking for test documents in recent chunks...")
    for title, info in works.items():
        if 'Cartesian' in title or 'artificial intelligence' in title.lower():
            print(f"   ✓ Found: {title[:70]}")
            print(f"     Author: {info['author']}")
            print(f"     Chunks: {info['count']}")
            cartesian_found = True
        if 'Turing' in title or 'von Neumann' in title:
            print(f"   ✓ Found: {title[:70]}")
            print(f"     Author: {info['author']}")
            print(f"     Chunks: {info['count']}")
            turing_found = True

    if not cartesian_found:
        print("   ✗ Cartesian document not found in recent chunks")
    if not turing_found:
        print("   ✗ Turing document not found in recent chunks")

    # Count all chunks
    print("\n3. Total chunks in database:")
    result = chunk_collection.aggregate.over_all()
    print(f"   Total: {result.total_count}")

    # List recent works (last 5)
    print("\n4. Recent works (showing first 5 chunks by creation time):")
    all_chunks = chunk_collection.query.fetch_objects(limit=5)
    for i, chunk in enumerate(all_chunks.objects, 1):
        work_title = chunk.properties.get('work', {}).get('title', 'N/A')
        print(f"   {i}. {work_title[:60]}...")

finally:
    client.close()
    print("\n✓ Done")
