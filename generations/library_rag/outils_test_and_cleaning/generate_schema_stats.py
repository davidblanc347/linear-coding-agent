#!/usr/bin/env python3
"""Generate statistics for WEAVIATE_SCHEMA.md documentation.

This script queries Weaviate and generates updated statistics to keep
the schema documentation in sync with reality.

Usage:
    python generate_schema_stats.py

Output:
    Prints formatted markdown table with current statistics that can be
    copy-pasted into WEAVIATE_SCHEMA.md
"""

import sys
from datetime import datetime
from typing import Dict

import weaviate


def get_collection_stats(client: weaviate.WeaviateClient) -> Dict[str, int]:
    """Get object counts for all collections.

    Args:
        client: Connected Weaviate client.

    Returns:
        Dict mapping collection name to object count.
    """
    stats: Dict[str, int] = {}

    collections = client.collections.list_all()

    for name in ["Work", "Document", "Chunk", "Summary"]:
        if name in collections:
            try:
                coll = client.collections.get(name)
                result = coll.aggregate.over_all(total_count=True)
                stats[name] = result.total_count
            except Exception as e:
                print(f"Warning: Could not get count for {name}: {e}", file=sys.stderr)
                stats[name] = 0
        else:
            stats[name] = 0

    return stats


def print_markdown_stats(stats: Dict[str, int]) -> None:
    """Print statistics in markdown table format for WEAVIATE_SCHEMA.md.

    Args:
        stats: Dict mapping collection name to object count.
    """
    total_vectors = stats["Chunk"] + stats["Summary"]
    ratio = stats["Summary"] / stats["Chunk"] if stats["Chunk"] > 0 else 0

    today = datetime.now().strftime("%d/%m/%Y")

    print(f"## Contenu actuel (au {today})")
    print()
    print(f"**Dernière vérification** : {datetime.now().strftime('%d %B %Y')} via `generate_schema_stats.py`")
    print()
    print("### Statistiques par collection")
    print()
    print("| Collection | Objets | Vectorisé | Utilisation |")
    print("|------------|--------|-----------|-------------|")
    print(f"| **Chunk** | **{stats['Chunk']:,}** | ✅ Oui | Recherche sémantique principale |")
    print(f"| **Summary** | **{stats['Summary']:,}** | ✅ Oui | Recherche hiérarchique (chapitres/sections) |")
    print(f"| **Document** | **{stats['Document']:,}** | ❌ Non | Métadonnées d'éditions |")
    print(f"| **Work** | **{stats['Work']:,}** | ✅ Oui* | Métadonnées d'œuvres (vide, prêt pour migration) |")
    print()
    print(f"**Total vecteurs** : {total_vectors:,} ({stats['Chunk']:,} chunks + {stats['Summary']:,} summaries)")
    print(f"**Ratio Summary/Chunk** : {ratio:.2f} ", end="")

    if ratio > 1:
        print("(plus de summaries que de chunks, bon pour recherche hiérarchique)")
    else:
        print("(plus de chunks que de summaries)")

    print()
    print("\\* *Work est configuré avec vectorisation (depuis migration 2026-01) mais n'a pas encore d'objets*")
    print()

    # Additional insights
    print("### Insights")
    print()

    if stats["Chunk"] > 0:
        avg_summaries_per_chunk = stats["Summary"] / stats["Chunk"]
        print(f"- **Granularité** : {avg_summaries_per_chunk:.1f} summaries par chunk en moyenne")

    if stats["Document"] > 0:
        avg_chunks_per_doc = stats["Chunk"] / stats["Document"]
        avg_summaries_per_doc = stats["Summary"] / stats["Document"]
        print(f"- **Taille moyenne document** : {avg_chunks_per_doc:.0f} chunks, {avg_summaries_per_doc:.0f} summaries")

    if stats["Chunk"] >= 50000:
        print("- **⚠️ Index Switch** : Collection Chunk a dépassé 50k → HNSW activé (Dynamic index)")
    elif stats["Chunk"] >= 40000:
        print(f"- **📊 Proche seuil** : {50000 - stats['Chunk']:,} chunks avant switch FLAT→HNSW (50k)")

    if stats["Summary"] >= 10000:
        print("- **⚠️ Index Switch** : Collection Summary a dépassé 10k → HNSW activé (Dynamic index)")
    elif stats["Summary"] >= 8000:
        print(f"- **📊 Proche seuil** : {10000 - stats['Summary']:,} summaries avant switch FLAT→HNSW (10k)")

    # Memory estimation
    vectors_total = total_vectors
    # BGE-M3: 1024 dim × 4 bytes (float32) = 4KB per vector
    # + metadata ~1KB per object
    estimated_ram_gb = (vectors_total * 5) / (1024 * 1024)  # 5KB per vector with metadata
    estimated_ram_with_rq_gb = estimated_ram_gb * 0.25  # RQ saves 75%

    print()
    print(f"- **RAM estimée** : ~{estimated_ram_gb:.1f} GB sans RQ, ~{estimated_ram_with_rq_gb:.1f} GB avec RQ (économie 75%)")

    print()


def main() -> None:
    """Main entry point."""
    # Fix encoding for Windows console
    if sys.platform == "win32" and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 80, file=sys.stderr)
    print("GÉNÉRATION DES STATISTIQUES WEAVIATE", file=sys.stderr)
    print("=" * 80, file=sys.stderr)
    print(file=sys.stderr)

    client: weaviate.WeaviateClient = weaviate.connect_to_local(
        host="localhost",
        port=8080,
        grpc_port=50051,
    )

    try:
        if not client.is_ready():
            print("❌ Weaviate is not ready. Ensure docker-compose is running.", file=sys.stderr)
            sys.exit(1)

        print("✓ Weaviate is ready", file=sys.stderr)
        print("✓ Querying collections...", file=sys.stderr)

        stats = get_collection_stats(client)

        print("✓ Statistics retrieved", file=sys.stderr)
        print(file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print("MARKDOWN OUTPUT (copy to WEAVIATE_SCHEMA.md):", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print(file=sys.stderr)

        # Print to stdout (can be redirected to file)
        print_markdown_stats(stats)

    finally:
        client.close()


if __name__ == "__main__":
    main()
