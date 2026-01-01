#!/usr/bin/env python3
"""Ajouter le Work manquant pour le chunk avec titre générique.

Ce script crée un Work pour "Titre corrigé si nécessaire (ex: 'The Fixation of Belief')"
qui a 1 chunk mais pas de Work correspondant.
"""

import sys
import weaviate

# Fix encoding for Windows console
if sys.platform == "win32" and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

print("=" * 80)
print("CRÉATION DU WORK MANQUANT")
print("=" * 80)
print()

client = weaviate.connect_to_local(
    host="localhost",
    port=8080,
    grpc_port=50051,
)

try:
    if not client.is_ready():
        print("❌ Weaviate is not ready. Ensure docker-compose is running.")
        sys.exit(1)

    print("✓ Weaviate is ready")
    print()

    work_collection = client.collections.get("Work")

    # Créer le Work avec le titre générique exact (pour correspondance avec chunk)
    work_obj = {
        "title": "Titre corrigé si nécessaire (ex: 'The Fixation of Belief')",
        "author": "C. S. Peirce",
        "originalTitle": "The Fixation of Belief",
        "year": 1877,
        "language": "en",
        "genre": "philosophical article",
    }

    print("Création du Work manquant...")
    print(f"   Titre : {work_obj['title']}")
    print(f"   Auteur : {work_obj['author']}")
    print(f"   Titre original : {work_obj['originalTitle']}")
    print(f"   Année : {work_obj['year']}")
    print()

    uuid = work_collection.data.insert(work_obj)

    print(f"✅ Work créé avec UUID {uuid}")
    print()

    # Vérifier le résultat
    work_result = work_collection.aggregate.over_all(total_count=True)
    print(f"📊 Works totaux : {work_result.total_count}")
    print()

    print("=" * 80)
    print("✅ WORK AJOUTÉ AVEC SUCCÈS")
    print("=" * 80)
    print()

finally:
    client.close()
