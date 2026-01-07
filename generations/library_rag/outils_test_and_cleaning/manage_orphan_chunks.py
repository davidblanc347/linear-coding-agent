#!/usr/bin/env python3
"""Gérer les chunks orphelins (sans document parent).

Un chunk est orphelin si son document.sourceId ne correspond à aucun objet
dans la collection Document.

Ce script offre 3 options :
1. SUPPRIMER les chunks orphelins (perte définitive)
2. CRÉER les documents manquants (restauration)
3. LISTER seulement (ne rien faire)

Usage:
    # Lister les orphelins (par défaut)
    python manage_orphan_chunks.py

    # Créer les documents manquants pour les orphelins
    python manage_orphan_chunks.py --create-documents

    # Supprimer les chunks orphelins (ATTENTION: perte de données)
    python manage_orphan_chunks.py --delete-orphans
"""

import sys
import argparse
from typing import Any, Dict, List, Set
from collections import defaultdict
from datetime import datetime

import weaviate


def identify_orphan_chunks(
    client: weaviate.WeaviateClient,
) -> Dict[str, List[Any]]:
    """Identifier les chunks orphelins (sans document parent).

    Args:
        client: Connected Weaviate client.

    Returns:
        Dict mapping orphan sourceId to list of orphan chunks.
    """
    print("📊 Récupération de tous les chunks...")

    chunk_collection = client.collections.get("Chunk")
    chunks_response = chunk_collection.query.fetch_objects(
        limit=10000,
    )

    all_chunks = chunks_response.objects
    print(f"   ✓ {len(all_chunks)} chunks récupérés")
    print()

    print("📊 Récupération de tous les documents...")

    doc_collection = client.collections.get("Document")
    docs_response = doc_collection.query.fetch_objects(
        limit=1000,
    )

    print(f"   ✓ {len(docs_response.objects)} documents récupérés")
    print()

    # Construire un set des sourceIds existants
    existing_source_ids: Set[str] = set()
    for doc_obj in docs_response.objects:
        source_id = doc_obj.properties.get("sourceId")
        if source_id:
            existing_source_ids.add(source_id)

    print(f"📊 {len(existing_source_ids)} sourceIds existants dans Document")
    print()

    # Identifier les orphelins
    orphan_chunks_by_source: Dict[str, List[Any]] = defaultdict(list)
    orphan_source_ids: Set[str] = set()

    for chunk_obj in all_chunks:
        props = chunk_obj.properties
        if "document" in props and isinstance(props["document"], dict):
            source_id = props["document"].get("sourceId")

            if source_id and source_id not in existing_source_ids:
                orphan_chunks_by_source[source_id].append(chunk_obj)
                orphan_source_ids.add(source_id)

    print(f"🔍 {len(orphan_source_ids)} sourceIds orphelins détectés")
    print(f"🔍 {sum(len(chunks) for chunks in orphan_chunks_by_source.values())} chunks orphelins au total")
    print()

    return orphan_chunks_by_source


def display_orphans_report(orphan_chunks: Dict[str, List[Any]]) -> None:
    """Afficher le rapport des chunks orphelins.

    Args:
        orphan_chunks: Dict mapping sourceId to list of orphan chunks.
    """
    if not orphan_chunks:
        print("✅ Aucun chunk orphelin détecté !")
        print()
        return

    print("=" * 80)
    print("CHUNKS ORPHELINS DÉTECTÉS")
    print("=" * 80)
    print()

    total_orphans = sum(len(chunks) for chunks in orphan_chunks.values())

    print(f"📌 {len(orphan_chunks)} sourceIds orphelins")
    print(f"📌 {total_orphans:,} chunks orphelins au total")
    print()

    for i, (source_id, chunks) in enumerate(sorted(orphan_chunks.items()), 1):
        print(f"[{i}/{len(orphan_chunks)}] {source_id}")
        print("─" * 80)
        print(f"   Chunks orphelins : {len(chunks):,}")

        # Extraire métadonnées depuis le premier chunk
        if chunks:
            first_chunk = chunks[0].properties
            work = first_chunk.get("work", {})

            if isinstance(work, dict):
                title = work.get("title", "N/A")
                author = work.get("author", "N/A")
                print(f"   Œuvre : {title}")
                print(f"   Auteur : {author}")

            # Langues détectées
            languages = set()
            for chunk in chunks:
                lang = chunk.properties.get("language")
                if lang:
                    languages.add(lang)

            if languages:
                print(f"   Langues : {', '.join(sorted(languages))}")

        print()

    print("=" * 80)
    print()


def create_missing_documents(
    client: weaviate.WeaviateClient,
    orphan_chunks: Dict[str, List[Any]],
    dry_run: bool = True,
) -> Dict[str, int]:
    """Créer les documents manquants pour les chunks orphelins.

    Args:
        client: Connected Weaviate client.
        orphan_chunks: Dict mapping sourceId to list of orphan chunks.
        dry_run: If True, only simulate (don't actually create).

    Returns:
        Dict with statistics: created, errors.
    """
    stats = {
        "created": 0,
        "errors": 0,
    }

    if not orphan_chunks:
        print("✅ Aucun document à créer (pas d'orphelins)")
        return stats

    if dry_run:
        print("🔍 MODE DRY-RUN (simulation, aucune création réelle)")
    else:
        print("⚠️  MODE EXÉCUTION (création réelle)")

    print("=" * 80)
    print()

    doc_collection = client.collections.get("Document")

    for source_id, chunks in sorted(orphan_chunks.items()):
        print(f"Traitement de {source_id}...")

        # Extraire métadonnées depuis les chunks
        if not chunks:
            print(f"   ⚠️  Aucun chunk, skip")
            continue

        first_chunk = chunks[0].properties
        work = first_chunk.get("work", {})

        # Construire l'objet Document avec métadonnées minimales
        doc_obj: Dict[str, Any] = {
            "sourceId": source_id,
            "title": "N/A",
            "author": "N/A",
            "edition": None,
            "language": "en",
            "pages": 0,
            "chunksCount": len(chunks),
            "toc": None,
            "hierarchy": None,
            "createdAt": datetime.now(),
        }

        # Enrichir avec métadonnées work si disponibles
        if isinstance(work, dict):
            if work.get("title"):
                doc_obj["title"] = work["title"]
            if work.get("author"):
                doc_obj["author"] = work["author"]

            # Nested object work
            doc_obj["work"] = {
                "title": work.get("title", "N/A"),
                "author": work.get("author", "N/A"),
            }

        # Détecter langue
        languages = set()
        for chunk in chunks:
            lang = chunk.properties.get("language")
            if lang:
                languages.add(lang)

        if len(languages) == 1:
            doc_obj["language"] = list(languages)[0]

        print(f"   Chunks : {len(chunks):,}")
        print(f"   Titre : {doc_obj['title']}")
        print(f"   Auteur : {doc_obj['author']}")
        print(f"   Langue : {doc_obj['language']}")

        if dry_run:
            print(f"   🔍 [DRY-RUN] Créerait Document : {doc_obj}")
            stats["created"] += 1
        else:
            try:
                uuid = doc_collection.data.insert(doc_obj)
                print(f"   ✅ Créé UUID {uuid}")
                stats["created"] += 1
            except Exception as e:
                print(f"   ⚠️  Erreur création : {e}")
                stats["errors"] += 1

        print()

    print("=" * 80)
    print("RÉSUMÉ")
    print("=" * 80)
    print(f"   Documents créés : {stats['created']}")
    print(f"   Erreurs : {stats['errors']}")
    print()

    return stats


def delete_orphan_chunks(
    client: weaviate.WeaviateClient,
    orphan_chunks: Dict[str, List[Any]],
    dry_run: bool = True,
) -> Dict[str, int]:
    """Supprimer les chunks orphelins.

    Args:
        client: Connected Weaviate client.
        orphan_chunks: Dict mapping sourceId to list of orphan chunks.
        dry_run: If True, only simulate (don't actually delete).

    Returns:
        Dict with statistics: deleted, errors.
    """
    stats = {
        "deleted": 0,
        "errors": 0,
    }

    if not orphan_chunks:
        print("✅ Aucun chunk à supprimer (pas d'orphelins)")
        return stats

    total_to_delete = sum(len(chunks) for chunks in orphan_chunks.values())

    if dry_run:
        print("🔍 MODE DRY-RUN (simulation, aucune suppression réelle)")
    else:
        print("⚠️  MODE EXÉCUTION (suppression réelle)")

    print("=" * 80)
    print()

    chunk_collection = client.collections.get("Chunk")

    for source_id, chunks in sorted(orphan_chunks.items()):
        print(f"Traitement de {source_id} ({len(chunks):,} chunks)...")

        for chunk_obj in chunks:
            if dry_run:
                # En dry-run, compter seulement
                stats["deleted"] += 1
            else:
                try:
                    chunk_collection.data.delete_by_id(chunk_obj.uuid)
                    stats["deleted"] += 1
                except Exception as e:
                    print(f"   ⚠️  Erreur suppression UUID {chunk_obj.uuid}: {e}")
                    stats["errors"] += 1

        if dry_run:
            print(f"   🔍 [DRY-RUN] Supprimerait {len(chunks):,} chunks")
        else:
            print(f"   ✅ Supprimé {len(chunks):,} chunks")

        print()

    print("=" * 80)
    print("RÉSUMÉ")
    print("=" * 80)
    print(f"   Chunks supprimés : {stats['deleted']:,}")
    print(f"   Erreurs : {stats['errors']}")
    print()

    return stats


def verify_operation(client: weaviate.WeaviateClient) -> None:
    """Vérifier le résultat de l'opération.

    Args:
        client: Connected Weaviate client.
    """
    print("=" * 80)
    print("VÉRIFICATION POST-OPÉRATION")
    print("=" * 80)
    print()

    orphan_chunks = identify_orphan_chunks(client)

    if not orphan_chunks:
        print("✅ Aucun chunk orphelin restant !")
        print()

        # Statistiques finales
        chunk_coll = client.collections.get("Chunk")
        chunk_result = chunk_coll.aggregate.over_all(total_count=True)

        doc_coll = client.collections.get("Document")
        doc_result = doc_coll.aggregate.over_all(total_count=True)

        print(f"📊 Chunks totaux : {chunk_result.total_count:,}")
        print(f"📊 Documents totaux : {doc_result.total_count:,}")
        print()
    else:
        total_orphans = sum(len(chunks) for chunks in orphan_chunks.values())
        print(f"⚠️  {total_orphans:,} chunks orphelins persistent")
        print()

    print("=" * 80)
    print()


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Gérer les chunks orphelins (sans document parent)"
    )
    parser.add_argument(
        "--create-documents",
        action="store_true",
        help="Créer les documents manquants pour les orphelins",
    )
    parser.add_argument(
        "--delete-orphans",
        action="store_true",
        help="Supprimer les chunks orphelins (ATTENTION: perte de données)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Exécuter l'opération (par défaut: dry-run)",
    )

    args = parser.parse_args()

    # Fix encoding for Windows console
    if sys.platform == "win32" and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 80)
    print("GESTION DES CHUNKS ORPHELINS")
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

        # Identifier les orphelins
        orphan_chunks = identify_orphan_chunks(client)

        # Afficher le rapport
        display_orphans_report(orphan_chunks)

        if not orphan_chunks:
            print("✅ Aucune action nécessaire (pas d'orphelins)")
            sys.exit(0)

        # Décider de l'action
        if args.create_documents:
            print("📋 ACTION : Créer les documents manquants")
            print()

            if args.execute:
                print("⚠️  ATTENTION : Les documents vont être créés !")
                print()
                response = input("Continuer ? (oui/non) : ").strip().lower()
                if response not in ["oui", "yes", "o", "y"]:
                    print("❌ Annulé par l'utilisateur.")
                    sys.exit(0)
                print()

            stats = create_missing_documents(client, orphan_chunks, dry_run=not args.execute)

            if args.execute and stats["created"] > 0:
                verify_operation(client)

        elif args.delete_orphans:
            print("📋 ACTION : Supprimer les chunks orphelins")
            print()

            total_orphans = sum(len(chunks) for chunks in orphan_chunks.values())

            if args.execute:
                print(f"⚠️  ATTENTION : {total_orphans:,} chunks vont être SUPPRIMÉS DÉFINITIVEMENT !")
                print("⚠️  Cette opération est IRRÉVERSIBLE !")
                print()
                response = input("Continuer ? (oui/non) : ").strip().lower()
                if response not in ["oui", "yes", "o", "y"]:
                    print("❌ Annulé par l'utilisateur.")
                    sys.exit(0)
                print()

            stats = delete_orphan_chunks(client, orphan_chunks, dry_run=not args.execute)

            if args.execute and stats["deleted"] > 0:
                verify_operation(client)

        else:
            # Mode liste uniquement (par défaut)
            print("=" * 80)
            print("💡 ACTIONS POSSIBLES")
            print("=" * 80)
            print()
            print("Option 1 : Créer les documents manquants (recommandé)")
            print("   python manage_orphan_chunks.py --create-documents --execute")
            print()
            print("Option 2 : Supprimer les chunks orphelins (ATTENTION: perte de données)")
            print("   python manage_orphan_chunks.py --delete-orphans --execute")
            print()
            print("Option 3 : Ne rien faire (laisser orphelins)")
            print("   Les chunks restent accessibles via recherche sémantique")
            print()

    finally:
        client.close()


if __name__ == "__main__":
    main()
