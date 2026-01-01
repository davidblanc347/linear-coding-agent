#!/usr/bin/env python3
"""Peupler la collection Work depuis les nested objects des Chunks.

Ce script :
1. Extrait les œuvres uniques depuis les nested objects (work.title, work.author) des Chunks
2. Enrichit avec les métadonnées depuis Document si disponibles
3. Insère les objets Work dans la collection Work (avec vectorisation)

La collection Work doit avoir été migrée avec vectorisation au préalable.
Si ce n'est pas fait : python migrate_add_work_collection.py

Usage:
    # Dry-run (affiche ce qui serait inséré, sans rien faire)
    python populate_work_collection.py

    # Exécution réelle (insère les Works)
    python populate_work_collection.py --execute
"""

import sys
import argparse
from typing import Any, Dict, List, Set, Tuple, Optional
from collections import defaultdict

import weaviate
from weaviate.classes.data import DataObject


def extract_unique_works_from_chunks(
    client: weaviate.WeaviateClient
) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """Extraire les œuvres uniques depuis les nested objects des Chunks.

    Args:
        client: Connected Weaviate client.

    Returns:
        Dict mapping (title, author) tuple to work metadata dict.
    """
    print("📊 Récupération de tous les chunks...")

    chunk_collection = client.collections.get("Chunk")
    chunks_response = chunk_collection.query.fetch_objects(
        limit=10000,
        # Nested objects retournés automatiquement
    )

    print(f"   ✓ {len(chunks_response.objects)} chunks récupérés")
    print()

    # Extraire les œuvres uniques
    works_data: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for chunk_obj in chunks_response.objects:
        props = chunk_obj.properties

        if "work" in props and isinstance(props["work"], dict):
            work = props["work"]
            title = work.get("title")
            author = work.get("author")

            if title and author:
                key = (title, author)

                # Première occurrence : initialiser
                if key not in works_data:
                    works_data[key] = {
                        "title": title,
                        "author": author,
                        "chunk_count": 0,
                        "languages": set(),
                    }

                # Compter les chunks
                works_data[key]["chunk_count"] += 1

                # Collecter les langues (depuis chunk.language si disponible)
                if "language" in props and props["language"]:
                    works_data[key]["languages"].add(props["language"])

    print(f"📚 {len(works_data)} œuvres uniques détectées")
    print()

    return works_data


def enrich_works_from_documents(
    client: weaviate.WeaviateClient,
    works_data: Dict[Tuple[str, str], Dict[str, Any]],
) -> None:
    """Enrichir les métadonnées Work depuis la collection Document.

    Args:
        client: Connected Weaviate client.
        works_data: Dict to enrich in-place.
    """
    print("📊 Enrichissement depuis la collection Document...")

    doc_collection = client.collections.get("Document")
    docs_response = doc_collection.query.fetch_objects(
        limit=1000,
        # Nested objects retournés automatiquement
    )

    print(f"   ✓ {len(docs_response.objects)} documents récupérés")

    enriched_count = 0

    for doc_obj in docs_response.objects:
        props = doc_obj.properties

        # Extraire work depuis nested object
        if "work" in props and isinstance(props["work"], dict):
            work = props["work"]
            title = work.get("title")
            author = work.get("author")

            if title and author:
                key = (title, author)

                if key in works_data:
                    # Enrichir avec pages (total de tous les documents de cette œuvre)
                    if "total_pages" not in works_data[key]:
                        works_data[key]["total_pages"] = 0

                    pages = props.get("pages", 0)
                    if pages:
                        works_data[key]["total_pages"] += pages

                    # Enrichir avec éditions
                    if "editions" not in works_data[key]:
                        works_data[key]["editions"] = []

                    edition = props.get("edition")
                    if edition:
                        works_data[key]["editions"].append(edition)

                    enriched_count += 1

    print(f"   ✓ {enriched_count} œuvres enrichies")
    print()


def display_works_report(works_data: Dict[Tuple[str, str], Dict[str, Any]]) -> None:
    """Afficher un rapport des œuvres détectées.

    Args:
        works_data: Dict mapping (title, author) to work metadata.
    """
    print("=" * 80)
    print("ŒUVRES UNIQUES DÉTECTÉES")
    print("=" * 80)
    print()

    total_chunks = sum(work["chunk_count"] for work in works_data.values())

    print(f"📌 {len(works_data)} œuvres uniques")
    print(f"📌 {total_chunks:,} chunks au total")
    print()

    for i, ((title, author), work_info) in enumerate(sorted(works_data.items()), 1):
        print(f"[{i}/{len(works_data)}] {title}")
        print("─" * 80)
        print(f"   Auteur : {author}")
        print(f"   Chunks : {work_info['chunk_count']:,}")

        if work_info.get("languages"):
            langs = ", ".join(sorted(work_info["languages"]))
            print(f"   Langues : {langs}")

        if work_info.get("total_pages"):
            print(f"   Pages totales : {work_info['total_pages']:,}")

        if work_info.get("editions"):
            print(f"   Éditions : {len(work_info['editions'])}")
            for edition in work_info["editions"][:3]:  # Max 3 pour éviter spam
                print(f"      • {edition}")
            if len(work_info["editions"]) > 3:
                print(f"      ... et {len(work_info['editions']) - 3} autres")

        print()

    print("=" * 80)
    print()


def check_work_collection(client: weaviate.WeaviateClient) -> bool:
    """Vérifier que la collection Work existe et est vectorisée.

    Args:
        client: Connected Weaviate client.

    Returns:
        True if Work collection exists and is properly configured.
    """
    collections = client.collections.list_all()

    if "Work" not in collections:
        print("❌ ERREUR : La collection Work n'existe pas !")
        print()
        print("   Créez-la d'abord avec :")
        print("   python migrate_add_work_collection.py")
        print()
        return False

    # Vérifier que Work est vide (sinon risque de doublons)
    work_coll = client.collections.get("Work")
    result = work_coll.aggregate.over_all(total_count=True)

    if result.total_count > 0:
        print(f"⚠️  ATTENTION : La collection Work contient déjà {result.total_count} objets !")
        print()
        response = input("Continuer quand même ? (oui/non) : ").strip().lower()
        if response not in ["oui", "yes", "o", "y"]:
            print("❌ Annulé par l'utilisateur.")
            return False
        print()

    return True


def insert_works(
    client: weaviate.WeaviateClient,
    works_data: Dict[Tuple[str, str], Dict[str, Any]],
    dry_run: bool = True,
) -> Dict[str, int]:
    """Insérer les œuvres dans la collection Work.

    Args:
        client: Connected Weaviate client.
        works_data: Dict mapping (title, author) to work metadata.
        dry_run: If True, only simulate (don't actually insert).

    Returns:
        Dict with statistics: inserted, errors.
    """
    stats = {
        "inserted": 0,
        "errors": 0,
    }

    if dry_run:
        print("🔍 MODE DRY-RUN (simulation, aucune insertion réelle)")
    else:
        print("⚠️  MODE EXÉCUTION (insertion réelle)")

    print("=" * 80)
    print()

    work_collection = client.collections.get("Work")

    for (title, author), work_info in sorted(works_data.items()):
        print(f"Traitement de '{title}' par {author}...")

        # Préparer l'objet Work
        work_obj = {
            "title": title,
            "author": author,
            # Champs optionnels
            "originalTitle": None,  # Pas disponible dans nested objects
            "year": None,  # Pas disponible dans nested objects
            "language": None,  # Multiple langues possibles, difficile à choisir
            "genre": None,  # Pas disponible
        }

        # Si une seule langue, l'utiliser
        if work_info.get("languages") and len(work_info["languages"]) == 1:
            work_obj["language"] = list(work_info["languages"])[0]

        if dry_run:
            print(f"   🔍 [DRY-RUN] Insérerait : {work_obj}")
            stats["inserted"] += 1
        else:
            try:
                uuid = work_collection.data.insert(work_obj)
                print(f"   ✅ Inséré UUID {uuid}")
                stats["inserted"] += 1
            except Exception as e:
                print(f"   ⚠️  Erreur insertion : {e}")
                stats["errors"] += 1

        print()

    print("=" * 80)
    print("RÉSUMÉ")
    print("=" * 80)
    print(f"   Works insérés : {stats['inserted']}")
    print(f"   Erreurs : {stats['errors']}")
    print()

    return stats


def verify_insertion(client: weaviate.WeaviateClient) -> None:
    """Vérifier le résultat de l'insertion.

    Args:
        client: Connected Weaviate client.
    """
    print("=" * 80)
    print("VÉRIFICATION POST-INSERTION")
    print("=" * 80)
    print()

    work_coll = client.collections.get("Work")
    result = work_coll.aggregate.over_all(total_count=True)

    print(f"📊 Works dans la collection : {result.total_count}")

    # Lister les works
    if result.total_count > 0:
        works_response = work_coll.query.fetch_objects(
            limit=100,
            return_properties=["title", "author", "language"],
        )

        print()
        print("📚 Works créés :")
        for i, work_obj in enumerate(works_response.objects, 1):
            props = work_obj.properties
            lang = props.get("language", "N/A")
            print(f"   {i:2d}. {props['title']}")
            print(f"       Auteur : {props['author']}")
            if lang != "N/A":
                print(f"       Langue : {lang}")
            print()

    print("=" * 80)
    print()


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Peupler la collection Work depuis les nested objects des Chunks"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Exécuter l'insertion (par défaut: dry-run)",
    )

    args = parser.parse_args()

    # Fix encoding for Windows console
    if sys.platform == "win32" and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 80)
    print("PEUPLEMENT DE LA COLLECTION WORK")
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

        # Vérifier que Work collection existe
        if not check_work_collection(client):
            sys.exit(1)

        # Étape 1 : Extraire les œuvres uniques depuis Chunks
        works_data = extract_unique_works_from_chunks(client)

        if not works_data:
            print("❌ Aucune œuvre détectée dans les chunks !")
            sys.exit(1)

        # Étape 2 : Enrichir depuis Documents
        enrich_works_from_documents(client, works_data)

        # Étape 3 : Afficher le rapport
        display_works_report(works_data)

        # Étape 4 : Insérer (ou simuler)
        if args.execute:
            print("⚠️  ATTENTION : Les œuvres vont être INSÉRÉES dans la collection Work !")
            print()
            response = input("Continuer ? (oui/non) : ").strip().lower()
            if response not in ["oui", "yes", "o", "y"]:
                print("❌ Annulé par l'utilisateur.")
                sys.exit(0)
            print()

        stats = insert_works(client, works_data, dry_run=not args.execute)

        # Étape 5 : Vérifier le résultat (seulement si exécution réelle)
        if args.execute:
            verify_insertion(client)
        else:
            print("=" * 80)
            print("💡 NEXT STEP")
            print("=" * 80)
            print()
            print("Pour exécuter l'insertion, lancez :")
            print("   python populate_work_collection.py --execute")
            print()

    finally:
        client.close()


if __name__ == "__main__":
    main()
