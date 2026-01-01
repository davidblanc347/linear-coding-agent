#!/usr/bin/env python3
"""Supprimer les Works orphelins (sans chunks associés).

Un Work est orphelin si aucun chunk ne référence cette œuvre dans son nested object.

Usage:
    # Dry-run (affiche ce qui serait supprimé, sans rien faire)
    python clean_orphan_works.py

    # Exécution réelle (supprime les Works orphelins)
    python clean_orphan_works.py --execute
"""

import sys
import argparse
from typing import Any, Dict, List, Set, Tuple

import weaviate


def get_works_from_chunks(client: weaviate.WeaviateClient) -> Set[Tuple[str, str]]:
    """Extraire les œuvres uniques depuis les chunks.

    Args:
        client: Connected Weaviate client.

    Returns:
        Set of (title, author) tuples for works that have chunks.
    """
    print("📊 Récupération de tous les chunks...")

    chunk_collection = client.collections.get("Chunk")
    chunks_response = chunk_collection.query.fetch_objects(
        limit=10000,
    )

    print(f"   ✓ {len(chunks_response.objects)} chunks récupérés")
    print()

    # Extraire les œuvres uniques (normalisation pour comparaison)
    works_with_chunks: Set[Tuple[str, str]] = set()

    for chunk_obj in chunks_response.objects:
        props = chunk_obj.properties

        if "work" in props and isinstance(props["work"], dict):
            work = props["work"]
            title = work.get("title")
            author = work.get("author")

            if title and author:
                # Normaliser pour comparaison (lowercase pour ignorer casse)
                works_with_chunks.add((title.lower(), author.lower()))

    print(f"📚 {len(works_with_chunks)} œuvres uniques dans les chunks")
    print()

    return works_with_chunks


def identify_orphan_works(
    client: weaviate.WeaviateClient,
    works_with_chunks: Set[Tuple[str, str]],
) -> List[Any]:
    """Identifier les Works orphelins (sans chunks).

    Args:
        client: Connected Weaviate client.
        works_with_chunks: Set of (title, author) that have chunks.

    Returns:
        List of orphan Work objects.
    """
    print("📊 Récupération de tous les Works...")

    work_collection = client.collections.get("Work")
    works_response = work_collection.query.fetch_objects(
        limit=1000,
    )

    print(f"   ✓ {len(works_response.objects)} Works récupérés")
    print()

    # Identifier les orphelins
    orphan_works: List[Any] = []

    for work_obj in works_response.objects:
        props = work_obj.properties
        title = props.get("title")
        author = props.get("author")

        if title and author:
            # Normaliser pour comparaison (lowercase)
            if (title.lower(), author.lower()) not in works_with_chunks:
                orphan_works.append(work_obj)

    print(f"🔍 {len(orphan_works)} Works orphelins détectés")
    print()

    return orphan_works


def display_orphans_report(orphan_works: List[Any]) -> None:
    """Afficher le rapport des Works orphelins.

    Args:
        orphan_works: List of orphan Work objects.
    """
    if not orphan_works:
        print("✅ Aucun Work orphelin détecté !")
        print()
        return

    print("=" * 80)
    print("WORKS ORPHELINS DÉTECTÉS")
    print("=" * 80)
    print()

    print(f"📌 {len(orphan_works)} Works sans chunks associés")
    print()

    for i, work_obj in enumerate(orphan_works, 1):
        props = work_obj.properties
        print(f"[{i}/{len(orphan_works)}] {props.get('title', 'N/A')}")
        print("─" * 80)
        print(f"   Auteur : {props.get('author', 'N/A')}")

        if props.get("year"):
            year = props["year"]
            if year < 0:
                print(f"   Année : {abs(year)} av. J.-C.")
            else:
                print(f"   Année : {year}")

        if props.get("language"):
            print(f"   Langue : {props['language']}")

        if props.get("genre"):
            print(f"   Genre : {props['genre']}")

        print(f"   UUID : {work_obj.uuid}")
        print()

    print("=" * 80)
    print()


def delete_orphan_works(
    client: weaviate.WeaviateClient,
    orphan_works: List[Any],
    dry_run: bool = True,
) -> Dict[str, int]:
    """Supprimer les Works orphelins.

    Args:
        client: Connected Weaviate client.
        orphan_works: List of orphan Work objects.
        dry_run: If True, only simulate (don't actually delete).

    Returns:
        Dict with statistics: deleted, errors.
    """
    stats = {
        "deleted": 0,
        "errors": 0,
    }

    if not orphan_works:
        print("✅ Aucun Work à supprimer (pas d'orphelins)")
        return stats

    if dry_run:
        print("🔍 MODE DRY-RUN (simulation, aucune suppression réelle)")
    else:
        print("⚠️  MODE EXÉCUTION (suppression réelle)")

    print("=" * 80)
    print()

    work_collection = client.collections.get("Work")

    for work_obj in orphan_works:
        props = work_obj.properties
        title = props.get("title", "N/A")
        author = props.get("author", "N/A")

        print(f"Traitement de '{title}' par {author}...")

        if dry_run:
            print(f"   🔍 [DRY-RUN] Supprimerait UUID {work_obj.uuid}")
            stats["deleted"] += 1
        else:
            try:
                work_collection.data.delete_by_id(work_obj.uuid)
                print(f"   ❌ Supprimé UUID {work_obj.uuid}")
                stats["deleted"] += 1
            except Exception as e:
                print(f"   ⚠️  Erreur suppression UUID {work_obj.uuid}: {e}")
                stats["errors"] += 1

        print()

    print("=" * 80)
    print("RÉSUMÉ")
    print("=" * 80)
    print(f"   Works supprimés : {stats['deleted']}")
    print(f"   Erreurs : {stats['errors']}")
    print()

    return stats


def verify_cleanup(client: weaviate.WeaviateClient) -> None:
    """Vérifier le résultat du nettoyage.

    Args:
        client: Connected Weaviate client.
    """
    print("=" * 80)
    print("VÉRIFICATION POST-NETTOYAGE")
    print("=" * 80)
    print()

    works_with_chunks = get_works_from_chunks(client)
    orphan_works = identify_orphan_works(client, works_with_chunks)

    if not orphan_works:
        print("✅ Aucun Work orphelin restant !")
        print()

        # Statistiques finales
        work_coll = client.collections.get("Work")
        work_result = work_coll.aggregate.over_all(total_count=True)

        print(f"📊 Works totaux : {work_result.total_count}")
        print(f"📊 Œuvres avec chunks : {len(works_with_chunks)}")
        print()

        if work_result.total_count == len(works_with_chunks):
            print("✅ Cohérence parfaite : 1 Work = 1 œuvre avec chunks")
            print()
    else:
        print(f"⚠️  {len(orphan_works)} Works orphelins persistent")
        print()

    print("=" * 80)
    print()


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Supprimer les Works orphelins (sans chunks associés)"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Exécuter la suppression (par défaut: dry-run)",
    )

    args = parser.parse_args()

    # Fix encoding for Windows console
    if sys.platform == "win32" and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 80)
    print("NETTOYAGE DES WORKS ORPHELINS")
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

        # Étape 1 : Identifier les œuvres avec chunks
        works_with_chunks = get_works_from_chunks(client)

        # Étape 2 : Identifier les Works orphelins
        orphan_works = identify_orphan_works(client, works_with_chunks)

        # Étape 3 : Afficher le rapport
        display_orphans_report(orphan_works)

        if not orphan_works:
            print("✅ Aucune action nécessaire (pas d'orphelins)")
            sys.exit(0)

        # Étape 4 : Supprimer (ou simuler)
        if args.execute:
            print(f"⚠️  ATTENTION : {len(orphan_works)} Works vont être supprimés !")
            print()
            response = input("Continuer ? (oui/non) : ").strip().lower()
            if response not in ["oui", "yes", "o", "y"]:
                print("❌ Annulé par l'utilisateur.")
                sys.exit(0)
            print()

        stats = delete_orphan_works(client, orphan_works, dry_run=not args.execute)

        # Étape 5 : Vérifier le résultat (seulement si exécution réelle)
        if args.execute and stats["deleted"] > 0:
            verify_cleanup(client)
        else:
            print("=" * 80)
            print("💡 NEXT STEP")
            print("=" * 80)
            print()
            print("Pour exécuter le nettoyage, lancez :")
            print("   python clean_orphan_works.py --execute")
            print()

    finally:
        client.close()


if __name__ == "__main__":
    main()
