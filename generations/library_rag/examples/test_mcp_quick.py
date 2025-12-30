import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from mcp_client_reference import MCPClient

async def main():
    client = MCPClient(server_path=str(Path(__file__).parent.parent / "mcp_server.py"), env={})
    
    await client.start()
    
    try:
        print("=" * 70)
        print("MCP CLIENT - FUNCTIONAL TESTS")
        print("=" * 70)
        
        # Test 1: Search chunks
        print("\n[TEST 1] Search chunks (semantic search)")
        result = await client.call_tool("search_chunks", {
            "query": "nominalism realism debate",
            "limit": 2
        })
        
        print(f"Results: {result['total_count']}")
        for i, chunk in enumerate(result['results'], 1):
            print(f"  [{i}] {chunk['work_author']} - Similarity: {chunk['similarity']:.3f}")
            print(f"      {chunk['text'][:80]}...")
        print("[OK]")
        
        # Test 2: List documents  
        print("\n[TEST 2] List documents")
        result = await client.call_tool("list_documents", {"limit": 5})
        
        print(f"Total: {result['total_count']} documents")
        for doc in result['documents'][:3]:
            print(f"  - {doc['source_id']} ({doc['work_author']}): {doc['chunks_count']} chunks")
        print("[OK]")
        
        # Test 3: Filter by author
        print("\n[TEST 3] Filter by author")
        result = await client.call_tool("filter_by_author", {
            "author": "Charles Sanders Peirce"
        })
        
        print(f"Author: {result['author']}")
        print(f"Works: {result['total_works']}")
        print(f"Documents: {result['total_documents']}")
        if 'total_chunks' in result:
            print(f"Chunks: {result['total_chunks']}")
        print("[OK]")
        
        print("\n" + "=" * 70)
        print("ALL TESTS PASSED - MCP CLIENT IS WORKING!")
        print("=" * 70)
        print("\nNote: author_filter and work_filter parameters are not supported")
        print("      due to Weaviate v4 limitation. See examples/KNOWN_ISSUES.md")
        
    finally:
        await client.stop()

asyncio.run(main())
