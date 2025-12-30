#!/usr/bin/env python3
"""
Test simple du client MCP (sans LLM).

Teste la communication directe avec le MCP server.

Usage:
    python test_mcp_client.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Ajouter le parent au path pour import
sys.path.insert(0, str(Path(__file__).parent))

from mcp_client_reference import MCPClient


async def test_basic_communication():
    """Test: Communication basique avec le server."""
    print("TEST 1: Basic Communication")
    print("-" * 80)

    library_rag_path = Path(__file__).parent.parent
    server_path = library_rag_path / "mcp_server.py"

    client = MCPClient(
        server_path=str(server_path),
        env={"MISTRAL_API_KEY": os.getenv("MISTRAL_API_KEY", "")},
    )

    try:
        await client.start()
        print("[OK] Server started\n")

        # Liste des outils
        tools = await client.list_tools()
        print(f"[OK] Found {len(tools)} tools:")
        for tool in tools:
            print(f"  - {tool.name}: {tool.description}")

        print("\n[OK] Test passed")

    finally:
        await client.stop()


async def test_search_chunks():
    """Test: Recherche sémantique."""
    print("\n\nTEST 2: Search Chunks")
    print("-" * 80)

    library_rag_path = Path(__file__).parent.parent
    server_path = library_rag_path / "mcp_server.py"

    client = MCPClient(
        server_path=str(server_path),
        env={"MISTRAL_API_KEY": os.getenv("MISTRAL_API_KEY", "")},
    )

    try:
        await client.start()

        # Recherche
        result = await client.call_tool(
            "search_chunks",
            {
                "query": "nominalism and realism",
                "limit": 3,
                "author_filter": "Charles Sanders Peirce",
            },
        )

        print(f"[OK] Query: nominalism and realism")
        print(f"[OK] Found {result['total_count']} results")

        for i, chunk in enumerate(result["results"][:3], 1):
            print(f"\n  [{i}] Similarity: {chunk['similarity']:.3f}")
            print(f"      Section: {chunk['section_path']}")
            print(f"      Preview: {chunk['text'][:150]}...")

        print("\n[OK] Test passed")

    finally:
        await client.stop()


async def test_list_documents():
    """Test: Liste des documents."""
    print("\n\nTEST 3: List Documents")
    print("-" * 80)

    library_rag_path = Path(__file__).parent.parent
    server_path = library_rag_path / "mcp_server.py"

    client = MCPClient(
        server_path=str(server_path),
        env={"MISTRAL_API_KEY": os.getenv("MISTRAL_API_KEY", "")},
    )

    try:
        await client.start()

        result = await client.call_tool("list_documents", {"limit": 10})

        print(f"[OK] Total documents: {result['total_count']}")

        for doc in result["documents"][:5]:
            print(f"\n  - {doc['source_id']}")
            print(f"    Author: {doc['author']}")
            print(f"    Chunks: {doc['chunks_count']}")

        print("\n[OK] Test passed")

    finally:
        await client.stop()


async def test_get_document():
    """Test: Récupérer un document spécifique."""
    print("\n\nTEST 4: Get Document")
    print("-" * 80)

    library_rag_path = Path(__file__).parent.parent
    server_path = library_rag_path / "mcp_server.py"

    client = MCPClient(
        server_path=str(server_path),
        env={"MISTRAL_API_KEY": os.getenv("MISTRAL_API_KEY", "")},
    )

    try:
        await client.start()

        # D'abord lister pour trouver un document
        list_result = await client.call_tool("list_documents", {"limit": 1})

        if list_result["documents"]:
            doc_id = list_result["documents"][0]["source_id"]

            # Récupérer le document
            result = await client.call_tool(
                "get_document",
                {"source_id": doc_id, "include_chunks": True, "chunk_limit": 5},
            )

            print(f"[OK] Document: {result['source_id']}")
            print(f"  Author: {result['author']}")
            print(f"  Pages: {result['pages']}")
            print(f"  Chunks: {result['chunks_count']}")

            if result.get("chunks"):
                print(f"\n  First chunk preview:")
                print(f"  {result['chunks'][0]['text'][:200]}...")

            print("\n[OK] Test passed")
        else:
            print("[WARN] No documents in database")

    finally:
        await client.stop()


async def main():
    """Exécuter tous les tests."""
    print("=" * 80)
    print("MCP CLIENT TESTS")
    print("=" * 80)

    try:
        await test_basic_communication()
        await test_search_chunks()
        await test_list_documents()
        await test_get_document()

        print("\n" + "=" * 80)
        print("ALL TESTS PASSED [OK]")
        print("=" * 80)

    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
