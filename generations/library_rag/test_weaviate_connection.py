#!/usr/bin/env python3
"""Test Weaviate connection from Flask context."""

import weaviate

try:
    print("Tentative de connexion à Weaviate...")
    client = weaviate.connect_to_local(
        host="localhost",
        port=8080,
        grpc_port=50051,
    )
    print("[OK] Connexion etablie!")
    print(f"[OK] Weaviate est pret: {client.is_ready()}")

    # Test query
    collections = client.collections.list_all()
    print(f"[OK] Collections disponibles: {list(collections.keys())}")

    client.close()
    print("[OK] Test reussi!")

except Exception as e:
    print(f"[ERREUR] {e}")
    print(f"Type d'erreur: {type(e).__name__}")
    import traceback
    traceback.print_exc()
