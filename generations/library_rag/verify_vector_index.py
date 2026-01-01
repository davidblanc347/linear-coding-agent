#!/usr/bin/env python3
"""Verify vector index configuration for Chunk and Summary collections.

This script checks if the dynamic index with RQ is properly configured
for vectorized collections. It displays:
- Index type (flat, hnsw, or dynamic)
- Quantization status (RQ enabled/disabled)
- Distance metric
- Dynamic threshold (if applicable)

Usage:
    python verify_vector_index.py
"""

import sys
from typing import Any, Dict

import weaviate


def check_collection_index(client: weaviate.WeaviateClient, collection_name: str) -> None:
    """Check and display vector index configuration for a collection.

    Args:
        client: Connected Weaviate client.
        collection_name: Name of the collection to check.
    """
    try:
        collections = client.collections.list_all()

        if collection_name not in collections:
            print(f"  ❌ Collection '{collection_name}' not found")
            return

        config = collections[collection_name]

        print(f"\n📦 {collection_name}")
        print("─" * 80)

        # Check vectorizer
        vectorizer_str: str = str(config.vectorizer)
        if "text2vec" in vectorizer_str.lower():
            print("  ✓ Vectorizer: text2vec-transformers")
        elif "none" in vectorizer_str.lower():
            print("  ℹ Vectorizer: NONE (metadata collection)")
            return
        else:
            print(f"  ⚠ Vectorizer: {vectorizer_str}")

        # Try to get vector index config (API structure varies)
        # Access via config object properties
        config_dict: Dict[str, Any] = {}

        # Try different API paths to get config info
        if hasattr(config, 'vector_index_config'):
            vector_config = config.vector_index_config
            config_dict['vector_config'] = str(vector_config)

            # Check for specific attributes
            if hasattr(vector_config, 'quantizer'):
                config_dict['quantizer'] = str(vector_config.quantizer)
            if hasattr(vector_config, 'distance_metric'):
                config_dict['distance_metric'] = str(vector_config.distance_metric)

        # Display available info
        if config_dict:
            print(f"  • Configuration détectée:")
            for key, value in config_dict.items():
                print(f"    - {key}: {value}")

        # Simplified detection based on config representation
        config_full_str = str(config)

        # Detect index type
        if "dynamic" in config_full_str.lower():
            print("  • Index Type: DYNAMIC")
        elif "hnsw" in config_full_str.lower():
            print("  • Index Type: HNSW")
        elif "flat" in config_full_str.lower():
            print("  • Index Type: FLAT")
        else:
            print("  • Index Type: UNKNOWN (default HNSW probable)")

        # Check for RQ
        if "rq" in config_full_str.lower() or "quantizer" in config_full_str.lower():
            print("  ✓ RQ (Rotational Quantization): Probablement ENABLED")
        else:
            print("  ⚠ RQ (Rotational Quantization): NOT DETECTED (ou désactivé)")

        # Check distance metric
        if "cosine" in config_full_str.lower():
            print("  • Distance Metric: COSINE (détecté)")
        elif "dot" in config_full_str.lower():
            print("  • Distance Metric: DOT PRODUCT (détecté)")
        elif "l2" in config_full_str.lower():
            print("  • Distance Metric: L2 SQUARED (détecté)")

        print("\n  Interpretation:")
        if "dynamic" in config_full_str.lower() and ("rq" in config_full_str.lower() or "quantizer" in config_full_str.lower()):
            print("  ✅ OPTIMIZED: Dynamic index with RQ enabled")
            print("     → Memory savings: ~75% at scale")
            print("     → Auto-switches from flat to HNSW at threshold")
        elif "hnsw" in config_full_str.lower():
            if "rq" in config_full_str.lower() or "quantizer" in config_full_str.lower():
                print("  ✅ HNSW with RQ: Good for large collections")
            else:
                print("  ⚠ HNSW without RQ: Consider enabling RQ for memory savings")
        elif "flat" in config_full_str.lower():
            print("  ℹ FLAT index: Good for small collections (<100k vectors)")
        else:
            print("  ⚠ Unknown index configuration (probably default HNSW)")
            print("     → Collections créées sans config explicite utilisent HNSW par défaut")

    except Exception as e:
        print(f"  ❌ Error checking {collection_name}: {e}")


def main() -> None:
    """Main entry point."""
    # Fix encoding for Windows console
    if sys.platform == "win32" and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 80)
    print("VÉRIFICATION DES INDEX VECTORIELS WEAVIATE")
    print("=" * 80)

    client: weaviate.WeaviateClient = weaviate.connect_to_local(
        host="localhost",
        port=8080,
        grpc_port=50051,
    )

    try:
        # Check if Weaviate is ready
        if not client.is_ready():
            print("\n❌ Weaviate is not ready. Ensure docker-compose is running.")
            return

        print("\n✓ Weaviate is ready")

        # Get all collections
        collections = client.collections.list_all()
        print(f"✓ Found {len(collections)} collections: {sorted(collections.keys())}")

        # Check vectorized collections (Chunk and Summary)
        print("\n" + "=" * 80)
        print("COLLECTIONS VECTORISÉES")
        print("=" * 80)

        check_collection_index(client, "Chunk")
        check_collection_index(client, "Summary")

        # Check non-vectorized collections (for reference)
        print("\n" + "=" * 80)
        print("COLLECTIONS MÉTADONNÉES (Non vectorisées)")
        print("=" * 80)

        check_collection_index(client, "Work")
        check_collection_index(client, "Document")

        print("\n" + "=" * 80)
        print("VÉRIFICATION TERMINÉE")
        print("=" * 80)

        # Count objects in each collection
        print("\n📊 STATISTIQUES:")
        for name in ["Work", "Document", "Chunk", "Summary"]:
            if name in collections:
                try:
                    coll = client.collections.get(name)
                    # Simple count using aggregate (works for all collections)
                    result = coll.aggregate.over_all(total_count=True)
                    count = result.total_count
                    print(f"  • {name:<12} {count:>8,} objets")
                except Exception as e:
                    print(f"  • {name:<12} Error: {e}")

    finally:
        client.close()
        print("\n✓ Connexion fermée\n")


if __name__ == "__main__":
    main()
