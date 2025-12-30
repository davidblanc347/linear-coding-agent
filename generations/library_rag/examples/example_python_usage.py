#!/usr/bin/env python3
"""
Exemple d'utilisation de Library RAG depuis une application Python.

Le MCP server est uniquement pour Claude Desktop.
Pour Python, appelez directement les handlers!
"""

import asyncio
from pathlib import Path

# Import direct des handlers
from mcp_tools import (
    parse_pdf_handler,
    ParsePdfInput,
    search_chunks_handler,
    SearchChunksInput,
)


async def example_parse_pdf():
    """Exemple: Traiter un PDF ou Markdown."""

    # Depuis un chemin local
    input_data = ParsePdfInput(
        pdf_path="C:/Users/david/Documents/platon.pdf"
    )

    # OU depuis une URL
    # input_data = ParsePdfInput(
    #     pdf_path="https://example.com/aristotle.pdf"
    # )

    # OU un fichier Markdown
    # input_data = ParsePdfInput(
    #     pdf_path="/path/to/peirce.md"
    # )

    result = await parse_pdf_handler(input_data)

    if result.success:
        print(f"✓ Document traité: {result.document_name}")
        print(f"  Pages: {result.pages}")
        print(f"  Chunks: {result.chunks_count}")
        print(f"  Coût: {result.cost_total:.4f}€")
    else:
        print(f"✗ Erreur: {result.error}")


async def example_search():
    """Exemple: Rechercher dans les chunks."""

    input_data = SearchChunksInput(
        query="nominalism and realism",
        limit=10,
        author_filter="Charles Sanders Peirce",  # Optionnel
    )

    result = await search_chunks_handler(input_data)

    print(f"Trouvé {result.total_count} résultats:")
    for i, chunk in enumerate(result.results[:5], 1):
        print(f"\n[{i}] Similarité: {chunk.similarity:.3f}")
        print(f"    {chunk.text[:200]}...")


async def main():
    """Point d'entrée principal."""

    # Exemple 1: Traiter un PDF
    # await example_parse_pdf()

    # Exemple 2: Rechercher
    await example_search()


if __name__ == "__main__":
    asyncio.run(main())
