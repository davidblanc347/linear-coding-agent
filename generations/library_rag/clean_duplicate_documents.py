#!/usr/bin/env python3
"""Nettoyage des documents dupliqués dans Weaviate.

Ce script détecte et supprime les doublons dans la collection Document.
Les doublons sont identifiés par leur sourceId (même valeur = doublon).

Pour chaque groupe de doublons :
- Garde le plus récent (basé sur createdAt)
- Supprime les autres

Les chunks et summaries ne sont PAS affectés car ils utilisent des nested objects
(pas de cross-references), ils pointent vers sourceId (string) pas l'objet Document.

Usage:
    # Dry-run (affiche ce qui serait supprimé, sans rien faire)
    python clean_duplicate_documents.py

    # Exécution réelle (supprime les doublons)
    python clean_duplicate_documents.py --execute
"""

import sys
import argparse
from typing import Any, Dict, List, Set
from collections import defaultdict
from datetime import datetime

import weaviate
from weaviate.classes.query import Filter


def detect_duplicates(client: weaviate.WeaviateClient) -> Dict[str, List[Any]]:
    """Détecter les documents dupliqués par sourceId.

    Args:
        client: Connected Weaviate client.

    Returns:
        Dict mapping sourceId to list of duplicate document objects.
        Only includes sourceIds with 2+ documents.
    """
    print("📊 Récupération de tous les documents...")

    doc_collection = client.collections.get("Document")
    docs_response = doc_collection.query.fetch_objects(
        limit=1000,
        return_properties=["sourceId", "title", "author", "createdAt", "pages"],
    )

    total_docs = len(docs_response.objects)
    print(f"   ✓ {total_docs} documents récupérés")

    # Grouper par sourceId
    by_source_id: Dict[str, List[Any]] = defaultdict(list)
    for doc_obj in docs_response.objects:
        source_id = doc_obj.properties.get("sourceId", "unknown")
        by_source_id[source_id].append(doc_obj)

    # Filtrer seulement les doublons (2+ docs avec même sourceId)
    duplicates = {
        source_id: docs
        for source_id, docs in by_source_id.items()
        if len(docs) > 1
    }

    print(f"   ✓ {len(by_source_id)} sourceIds uniques")
    print(f"   ✓ {len(duplicates)} sourceIds avec doublons")
    print()

    return duplicates


def display_duplicates_report(duplicates: Dict[str, List[Any]]) -> None:
    """Afficher un rapport des doublons détectés.

    Args:
        duplicates: Dict mapping sourceId to list of duplicate documents.
    """
    if not duplicates:
        print("✅ Aucun doublon détecté !")
        return

    print("=" * 80)
    print("DOUBLONS DÉTECTÉS")
    print("=" * 80)
    print()

    total_duplicates = sum(len(docs) for docs in duplicates.values())
    total_to_delete = sum(len(docs) - 1 for docs in duplicates.values())

    print(f"📌 {len(duplicates)} sourceIds avec doublons")
    print(f"📌 {total_duplicates} documents au total (dont {total_to_delete} à supprimer)")
    print()

    for i, (source_id, docs) in enumerate(sorted(duplicates.items()), 1):
        print(f"[{i}/{len(duplicates)}] {source_id}")
        print("─" * 80)
        print(f"   Nombre de doublons : {len(docs)}")
        print(f"   À supprimer : {len(docs) - 1}")
        print()

        # Trier par createdAt (plus récent en premier)
        sorted_docs = sorted(
            docs,
            key=lambda d: d.properties.get("createdAt", datetime.min),
            reverse=True,
        )

        for j, doc in enumerate(sorted_docs):
            props = doc.properties
            created_at = props.get("createdAt", "N/A")
            if isinstance(created_at, datetime):
                created_at = created_at.strftime("%Y-%m-%d %H:%M:%S")

            status = "✅ GARDER" if j == 0 else "❌ SUPPRIMER"
            print(f"      {status} - UUID: {doc.uuid}")
            print(f"         Titre : {props.get('title', 'N/A')}")
            print(f"         Auteur : {props.get('author', 'N/A')}")
            print(f"         Créé le : {created_at}")
            print(f"         Pages : {props.get('pages', 0):,}")
            print()

    print("=" * 80)
    print()


def clean_duplicates(
    client: weaviate.WeaviateClient,
    duplicates: Dict[str, List[Any]],
    dry_run: bool = True,
) -> Dict[str, int]:
    """Nettoyer les documents dupliqués.

    Args:
        client: Connected Weaviate client.
        duplicates: Dict mapping sourceId to list of duplicate documents.
        dry_run: If True, only simulate (don't actually delete).

    Returns:
        Dict with statistics: deleted, kept, errors.
    """
    stats = {
        "deleted": 0,
        "kept": 0,
        "errors": 0,
    }

    if dry_run:
        print("🔍 MODE DRY-RUN (simulation, aucune suppression réelle)")
    else:
        print("⚠️  MODE EXÉCUTION (suppression réelle)")

    print("=" * 80)
    print()

    doc_collection = client.collections.get("Document")

    for source_id, docs in sorted(duplicates.items()):
        print(f"Traitement de {source_id}...")

        # Trier par createdAt (plus récent en premier)
        sorted_docs = sorted(
            docs,
            key=lambda d: d.properties.get("createdAt", datetime.min),
            reverse=True,
        )

        # Garder le premier (plus récent), supprimer les autres
        for i, doc in enumerate(sorted_docs):
            if i == 0:
                # Garder
                print(f"   ✅ Garde UUID {doc.uuid} (plus récent)")
                stats["kept"] += 1
            else:
                # Supprimer
                if dry_run:
                    print(f"   🔍 [DRY-RUN] Supprimerait UUID {doc.uuid}")
                    stats["deleted"] += 1
                else:
                    try:
                        doc_collection.data.delete_by_id(doc.uuid)
                        print(f"   ❌ Supprimé UUID {doc.uuid}")
                        stats["deleted"] += 1
                    except Exception as e:
                        print(f"   ⚠️  Erreur suppression UUID {doc.uuid}: {e}")
                        stats["errors"] += 1

        print()

    print("=" * 80)
    print("RÉSUMÉ")
    print("=" * 80)
    print(f"   Documents gardés : {stats['kept']}")
    print(f"   Documents supprimés : {stats['deleted']}")
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

    duplicates = detect_duplicates(client)

    if not duplicates:
        print("✅ Aucun doublon restant !")
        print()

        # Compter les documents uniques
        doc_collection = client.collections.get("Document")
        docs_response = doc_collection.query.fetch_objects(
            limit=1000,
            return_properties=["sourceId"],
        )

        unique_source_ids = set(
            doc.properties.get("sourceId") for doc in docs_response.objects
        )

        print(f"📊 Documents dans la base : {len(docs_response.objects)}")
        print(f"📊 SourceIds uniques : {len(unique_source_ids)}")
        print()
    else:
        print("⚠️  Des doublons persistent :")
        display_duplicates_report(duplicates)


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Nettoyer les documents dupliqués dans Weaviate"
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
    print("NETTOYAGE DES DOCUMENTS DUPLIQUÉS")
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

        # Étape 1 : Détecter les doublons
        duplicates = detect_duplicates(client)

        if not duplicates:
            print("✅ Aucun doublon détecté !")
            print()
            sys.exit(0)

        # Étape 2 : Afficher le rapport
        display_duplicates_report(duplicates)

        # Étape 3 : Nettoyer (ou simuler)
        if args.execute:
            print("⚠️  ATTENTION : Les doublons vont être SUPPRIMÉS définitivement !")
            print("⚠️  Les chunks et summaries ne seront PAS affectés (nested objects).")
            print()
            response = input("Continuer ? (oui/non) : ").strip().lower()
            if response not in ["oui", "yes", "o", "y"]:
                print("❌ Annulé par l'utilisateur.")
                sys.exit(0)
            print()

        stats = clean_duplicates(client, duplicates, dry_run=not args.execute)

        # Étape 4 : Vérifier le résultat (seulement si exécution réelle)
        if args.execute:
            verify_cleanup(client)
        else:
            print("=" * 80)
            print("💡 NEXT STEP")
            print("=" * 80)
            print()
            print("Pour exécuter le nettoyage, lancez :")
            print("   python clean_duplicate_documents.py --execute")
            print()

    finally:
        client.close()


if __name__ == "__main__":
    main()
