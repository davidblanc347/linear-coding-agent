#!/usr/bin/env python3
"""Recalculer et corriger le champ chunksCount des Documents.

Ce script :
1. Récupère tous les chunks et documents
2. Compte le nombre réel de chunks pour chaque document (via document.sourceId)
3. Compare avec le chunksCount déclaré dans Document
4. Met à jour les Documents avec les valeurs correctes

Usage:
    # Dry-run (affiche ce qui serait corrigé, sans rien faire)
    python fix_chunks_count.py

    # Exécution réelle (met à jour les chunksCount)
    python fix_chunks_count.py --execute
"""

import sys
import argparse
from typing import Any, Dict, List
from collections import defaultdict

import weaviate


def count_chunks_per_document(
    all_chunks: List[Any],
) -> Dict[str, int]:
    """Compter le nombre de chunks pour chaque sourceId.

    Args:
        all_chunks: All chunks from database.

    Returns:
        Dict mapping sourceId to chunk count.
    """
    counts: Dict[str, int] = defaultdict(int)

    for chunk_obj in all_chunks:
        props = chunk_obj.properties
        if "document" in props and isinstance(props["document"], dict):
            source_id = props["document"].get("sourceId")
            if source_id:
                counts[source_id] += 1

    return counts


def analyze_chunks_count_discrepancies(
    client: weaviate.WeaviateClient,
) -> List[Dict[str, Any]]:
    """Analyser les incohérences entre chunksCount déclaré et réel.

    Args:
        client: Connected Weaviate client.

    Returns:
        List of dicts with document info and discrepancies.
    """
    print("📊 Récupération de tous les chunks...")

    chunk_collection = client.collections.get("Chunk")
    chunks_response = chunk_collection.query.fetch_objects(
        limit=10000,
    )

    all_chunks = chunks_response.objects
    print(f"   ✓ {len(all_chunks)} chunks récupérés")
    print()

    print("📊 Comptage par document...")
    real_counts = count_chunks_per_document(all_chunks)
    print(f"   ✓ {len(real_counts)} documents avec chunks")
    print()

    print("📊 Récupération de tous les documents...")
    doc_collection = client.collections.get("Document")
    docs_response = doc_collection.query.fetch_objects(
        limit=1000,
    )

    print(f"   ✓ {len(docs_response.objects)} documents récupérés")
    print()

    # Analyser les discordances
    discrepancies: List[Dict[str, Any]] = []

    for doc_obj in docs_response.objects:
        props = doc_obj.properties
        source_id = props.get("sourceId", "unknown")
        declared_count = props.get("chunksCount", 0)
        real_count = real_counts.get(source_id, 0)

        discrepancy = {
            "uuid": doc_obj.uuid,
            "sourceId": source_id,
            "title": props.get("title", "N/A"),
            "author": props.get("author", "N/A"),
            "declared_count": declared_count,
            "real_count": real_count,
            "difference": real_count - declared_count,
            "needs_update": declared_count != real_count,
        }

        discrepancies.append(discrepancy)

    return discrepancies


def display_discrepancies_report(discrepancies: List[Dict[str, Any]]) -> None:
    """Afficher le rapport des incohérences.

    Args:
        discrepancies: List of document discrepancy dicts.
    """
    print("=" * 80)
    print("RAPPORT DES INCOHÉRENCES chunksCount")
    print("=" * 80)
    print()

    total_declared = sum(d["declared_count"] for d in discrepancies)
    total_real = sum(d["real_count"] for d in discrepancies)
    total_difference = total_real - total_declared

    needs_update = [d for d in discrepancies if d["needs_update"]]

    print(f"📌 {len(discrepancies)} documents au total")
    print(f"📌 {len(needs_update)} documents à corriger")
    print()
    print(f"📊 Total déclaré (somme chunksCount) : {total_declared:,}")
    print(f"📊 Total réel (comptage chunks) : {total_real:,}")
    print(f"📊 Différence globale : {total_difference:+,}")
    print()

    if not needs_update:
        print("✅ Tous les chunksCount sont corrects !")
        print()
        return

    print("─" * 80)
    print()

    for i, doc in enumerate(discrepancies, 1):
        if not doc["needs_update"]:
            status = "✅"
        elif doc["difference"] > 0:
            status = "⚠️ "
        else:
            status = "⚠️ "

        print(f"{status} [{i}/{len(discrepancies)}] {doc['sourceId']}")

        if doc["needs_update"]:
            print("─" * 80)
            print(f"   Titre : {doc['title']}")
            print(f"   Auteur : {doc['author']}")
            print(f"   chunksCount déclaré : {doc['declared_count']:,}")
            print(f"   Chunks réels : {doc['real_count']:,}")
            print(f"   Différence : {doc['difference']:+,}")
            print(f"   UUID : {doc['uuid']}")
            print()

    print("=" * 80)
    print()


def fix_chunks_count(
    client: weaviate.WeaviateClient,
    discrepancies: List[Dict[str, Any]],
    dry_run: bool = True,
) -> Dict[str, int]:
    """Corriger les chunksCount dans les Documents.

    Args:
        client: Connected Weaviate client.
        discrepancies: List of document discrepancy dicts.
        dry_run: If True, only simulate (don't actually update).

    Returns:
        Dict with statistics: updated, unchanged, errors.
    """
    stats = {
        "updated": 0,
        "unchanged": 0,
        "errors": 0,
    }

    needs_update = [d for d in discrepancies if d["needs_update"]]

    if not needs_update:
        print("✅ Aucune correction nécessaire !")
        stats["unchanged"] = len(discrepancies)
        return stats

    if dry_run:
        print("🔍 MODE DRY-RUN (simulation, aucune mise à jour réelle)")
    else:
        print("⚠️  MODE EXÉCUTION (mise à jour réelle)")

    print("=" * 80)
    print()

    doc_collection = client.collections.get("Document")

    for doc in discrepancies:
        if not doc["needs_update"]:
            stats["unchanged"] += 1
            continue

        source_id = doc["sourceId"]
        old_count = doc["declared_count"]
        new_count = doc["real_count"]

        print(f"Traitement de {source_id}...")
        print(f"   {old_count:,} → {new_count:,} chunks")

        if dry_run:
            print(f"   🔍 [DRY-RUN] Mettrait à jour UUID {doc['uuid']}")
            stats["updated"] += 1
        else:
            try:
                # Mettre à jour l'objet Document
                doc_collection.data.update(
                    uuid=doc["uuid"],
                    properties={"chunksCount": new_count},
                )
                print(f"   ✅ Mis à jour UUID {doc['uuid']}")
                stats["updated"] += 1
            except Exception as e:
                print(f"   ⚠️  Erreur mise à jour UUID {doc['uuid']}: {e}")
                stats["errors"] += 1

        print()

    print("=" * 80)
    print("RÉSUMÉ")
    print("=" * 80)
    print(f"   Documents mis à jour : {stats['updated']}")
    print(f"   Documents inchangés : {stats['unchanged']}")
    print(f"   Erreurs : {stats['errors']}")
    print()

    return stats


def verify_fix(client: weaviate.WeaviateClient) -> None:
    """Vérifier le résultat de la correction.

    Args:
        client: Connected Weaviate client.
    """
    print("=" * 80)
    print("VÉRIFICATION POST-CORRECTION")
    print("=" * 80)
    print()

    discrepancies = analyze_chunks_count_discrepancies(client)
    needs_update = [d for d in discrepancies if d["needs_update"]]

    if not needs_update:
        print("✅ Tous les chunksCount sont désormais corrects !")
        print()

        total_declared = sum(d["declared_count"] for d in discrepancies)
        total_real = sum(d["real_count"] for d in discrepancies)

        print(f"📊 Total déclaré : {total_declared:,}")
        print(f"📊 Total réel : {total_real:,}")
        print(f"📊 Différence : {total_real - total_declared:+,}")
        print()
    else:
        print(f"⚠️  {len(needs_update)} incohérences persistent :")
        display_discrepancies_report(discrepancies)

    print("=" * 80)
    print()


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Recalculer et corriger les chunksCount des Documents"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Exécuter la correction (par défaut: dry-run)",
    )

    args = parser.parse_args()

    # Fix encoding for Windows console
    if sys.platform == "win32" and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 80)
    print("CORRECTION DES chunksCount")
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

        # Étape 1 : Analyser les incohérences
        discrepancies = analyze_chunks_count_discrepancies(client)

        # Étape 2 : Afficher le rapport
        display_discrepancies_report(discrepancies)

        # Étape 3 : Corriger (ou simuler)
        if args.execute:
            needs_update = [d for d in discrepancies if d["needs_update"]]
            if needs_update:
                print(f"⚠️  ATTENTION : {len(needs_update)} documents vont être mis à jour !")
                print()
                response = input("Continuer ? (oui/non) : ").strip().lower()
                if response not in ["oui", "yes", "o", "y"]:
                    print("❌ Annulé par l'utilisateur.")
                    sys.exit(0)
                print()

        stats = fix_chunks_count(client, discrepancies, dry_run=not args.execute)

        # Étape 4 : Vérifier le résultat (seulement si exécution réelle)
        if args.execute and stats["updated"] > 0:
            verify_fix(client)
        elif not args.execute:
            print("=" * 80)
            print("💡 NEXT STEP")
            print("=" * 80)
            print()
            print("Pour exécuter la correction, lancez :")
            print("   python fix_chunks_count.py --execute")
            print()

    finally:
        client.close()


if __name__ == "__main__":
    main()
