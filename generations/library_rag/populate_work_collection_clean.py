#!/usr/bin/env python3
"""Peupler la collection Work avec nettoyage des doublons et corrections.

Ce script :
1. Extrait les œuvres uniques depuis les nested objects des Chunks
2. Applique un mapping de corrections pour résoudre les incohérences :
   - Variations de titres (ex: Darwin - 3 titres différents)
   - Variations d'auteurs (ex: Peirce - 3 orthographes)
   - Titres génériques à corriger
3. Consolide les œuvres par (canonical_title, canonical_author)
4. Insère les Works canoniques dans la collection Work

Usage:
    # Dry-run (affiche ce qui serait inséré, sans rien faire)
    python populate_work_collection_clean.py

    # Exécution réelle (insère les Works)
    python populate_work_collection_clean.py --execute
"""

import sys
import argparse
from typing import Any, Dict, List, Set, Tuple, Optional
from collections import defaultdict

import weaviate


# =============================================================================
# Mapping de corrections manuelles
# =============================================================================

# Corrections de titres : original_title -> canonical_title
TITLE_CORRECTIONS = {
    # Peirce : titre générique → titre correct
    "Titre corrigé si nécessaire (ex: 'The Fixation of Belief')": "The Fixation of Belief",

    # Darwin : variations du même ouvrage (Historical Sketch)
    "An Historical Sketch of the Progress of Opinion on the Origin of Species":
        "An Historical Sketch of the Progress of Opinion on the Origin of Species",
    "An Historical Sketch of the Progress of Opinion on the Origin of Species, Previously to the Publication of the First Edition of This Work":
        "An Historical Sketch of the Progress of Opinion on the Origin of Species",

    # Darwin : On the Origin of Species (titre complet -> titre court)
    "On the Origin of Species BY MEANS OF NATURAL SELECTION, OR THE PRESERVATION OF FAVOURED RACES IN THE STRUGGLE FOR LIFE.":
        "On the Origin of Species",
}

# Corrections d'auteurs : original_author -> canonical_author
AUTHOR_CORRECTIONS = {
    # Peirce : 3 variations → 1 seule
    "Charles Sanders PEIRCE": "Charles Sanders Peirce",
    "C. S. Peirce": "Charles Sanders Peirce",

    # Darwin : MAJUSCULES → Capitalisé
    "Charles DARWIN": "Charles Darwin",
}

# Métadonnées supplémentaires pour certaines œuvres (optionnel)
WORK_METADATA = {
    ("On the Origin of Species", "Charles Darwin"): {
        "originalTitle": "On the Origin of Species by Means of Natural Selection",
        "year": 1859,
        "language": "en",
        "genre": "scientific treatise",
    },
    ("The Fixation of Belief", "Charles Sanders Peirce"): {
        "year": 1877,
        "language": "en",
        "genre": "philosophical article",
    },
    ("Collected papers", "Charles Sanders Peirce"): {
        "originalTitle": "Collected Papers of Charles Sanders Peirce",
        "year": 1931,  # Publication date of volumes 1-6
        "language": "en",
        "genre": "collected works",
    },
    ("La pensée-signe. Études sur C. S. Peirce", "Claudine Tiercelin"): {
        "year": 1993,
        "language": "fr",
        "genre": "philosophical study",
    },
    ("Platon - Ménon", "Platon"): {
        "originalTitle": "Μένων",
        "year": -380,  # Environ 380 avant J.-C.
        "language": "gr",
        "genre": "dialogue",
    },
    ("Mind Design III: Philosophy, Psychology, and Artificial Intelligence (si confirmation)",
     "John Haugeland, Carl F. Craver, and Colin Klein"): {
        "year": 2023,
        "language": "en",
        "genre": "anthology",
    },
    ("Artificial Intelligence: The Very Idea (1985)", "John Haugeland"): {
        "originalTitle": "Artificial Intelligence: The Very Idea",
        "year": 1985,
        "language": "en",
        "genre": "philosophical monograph",
    },
    ("Between Past and Future", "Hannah Arendt"): {
        "year": 1961,
        "language": "en",
        "genre": "political philosophy",
    },
    ("On a New List of Categories", "Charles Sanders Peirce"): {
        "year": 1867,
        "language": "en",
        "genre": "philosophical article",
    },
    ("La logique de la science", "Charles Sanders Peirce"): {
        "year": 1878,
        "language": "fr",
        "genre": "philosophical article",
    },
    ("An Historical Sketch of the Progress of Opinion on the Origin of Species", "Charles Darwin"): {
        "year": 1861,
        "language": "en",
        "genre": "historical sketch",
    },
}


def apply_corrections(title: str, author: str) -> Tuple[str, str]:
    """Appliquer les corrections de titre et auteur.

    Args:
        title: Original title from nested object.
        author: Original author from nested object.

    Returns:
        Tuple of (canonical_title, canonical_author).
    """
    canonical_title = TITLE_CORRECTIONS.get(title, title)
    canonical_author = AUTHOR_CORRECTIONS.get(author, author)
    return (canonical_title, canonical_author)


def extract_unique_works_from_chunks(
    client: weaviate.WeaviateClient
) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """Extraire les œuvres uniques depuis les nested objects des Chunks (avec corrections).

    Args:
        client: Connected Weaviate client.

    Returns:
        Dict mapping (canonical_title, canonical_author) to work metadata.
    """
    print("📊 Récupération de tous les chunks...")

    chunk_collection = client.collections.get("Chunk")
    chunks_response = chunk_collection.query.fetch_objects(
        limit=10000,
    )

    print(f"   ✓ {len(chunks_response.objects)} chunks récupérés")
    print()

    # Extraire les œuvres uniques avec corrections
    works_data: Dict[Tuple[str, str], Dict[str, Any]] = {}
    corrections_applied: Dict[Tuple[str, str], Tuple[str, str]] = {}  # original -> canonical

    for chunk_obj in chunks_response.objects:
        props = chunk_obj.properties

        if "work" in props and isinstance(props["work"], dict):
            work = props["work"]
            original_title = work.get("title")
            original_author = work.get("author")

            if original_title and original_author:
                # Appliquer corrections
                canonical_title, canonical_author = apply_corrections(original_title, original_author)
                canonical_key = (canonical_title, canonical_author)
                original_key = (original_title, original_author)

                # Tracker les corrections
                if original_key != canonical_key:
                    corrections_applied[original_key] = canonical_key

                # Initialiser si première occurrence
                if canonical_key not in works_data:
                    works_data[canonical_key] = {
                        "title": canonical_title,
                        "author": canonical_author,
                        "chunk_count": 0,
                        "languages": set(),
                        "original_titles": set(),
                        "original_authors": set(),
                    }

                # Compter les chunks
                works_data[canonical_key]["chunk_count"] += 1

                # Collecter les langues
                if "language" in props and props["language"]:
                    works_data[canonical_key]["languages"].add(props["language"])

                # Tracker les titres/auteurs originaux (pour rapport)
                works_data[canonical_key]["original_titles"].add(original_title)
                works_data[canonical_key]["original_authors"].add(original_author)

    print(f"📚 {len(works_data)} œuvres uniques (après corrections)")
    print(f"🔧 {len(corrections_applied)} corrections appliquées")
    print()

    return works_data


def display_corrections_report(works_data: Dict[Tuple[str, str], Dict[str, Any]]) -> None:
    """Afficher un rapport des corrections appliquées.

    Args:
        works_data: Dict mapping (canonical_title, canonical_author) to work metadata.
    """
    print("=" * 80)
    print("CORRECTIONS APPLIQUÉES")
    print("=" * 80)
    print()

    corrections_found = False

    for (title, author), work_info in sorted(works_data.items()):
        original_titles = work_info.get("original_titles", set())
        original_authors = work_info.get("original_authors", set())

        # Si plus d'un titre ou auteur original, il y a eu consolidation
        if len(original_titles) > 1 or len(original_authors) > 1:
            corrections_found = True
            print(f"✅ {title}")
            print("─" * 80)

            if len(original_titles) > 1:
                print(f"   Titres consolidés ({len(original_titles)}) :")
                for orig_title in sorted(original_titles):
                    if orig_title != title:
                        print(f"      • {orig_title}")

            if len(original_authors) > 1:
                print(f"   Auteurs consolidés ({len(original_authors)}) :")
                for orig_author in sorted(original_authors):
                    if orig_author != author:
                        print(f"      • {orig_author}")

            print(f"   Chunks total : {work_info['chunk_count']:,}")
            print()

    if not corrections_found:
        print("Aucune consolidation nécessaire.")
        print()

    print("=" * 80)
    print()


def display_works_report(works_data: Dict[Tuple[str, str], Dict[str, Any]]) -> None:
    """Afficher un rapport des œuvres à insérer.

    Args:
        works_data: Dict mapping (title, author) to work metadata.
    """
    print("=" * 80)
    print("ŒUVRES À INSÉRER DANS WORK COLLECTION")
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

        # Métadonnées enrichies
        enriched = WORK_METADATA.get((title, author))
        if enriched:
            if enriched.get("year"):
                year = enriched["year"]
                if year < 0:
                    print(f"   Année : {abs(year)} av. J.-C.")
                else:
                    print(f"   Année : {year}")
            if enriched.get("genre"):
                print(f"   Genre : {enriched['genre']}")

        print()

    print("=" * 80)
    print()


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

        # Préparer l'objet Work avec métadonnées enrichies
        work_obj: Dict[str, Any] = {
            "title": title,
            "author": author,
            "originalTitle": None,
            "year": None,
            "language": None,
            "genre": None,
        }

        # Si une seule langue détectée, l'utiliser
        if work_info.get("languages") and len(work_info["languages"]) == 1:
            work_obj["language"] = list(work_info["languages"])[0]

        # Enrichir avec métadonnées manuelles si disponibles
        enriched = WORK_METADATA.get((title, author))
        if enriched:
            work_obj.update(enriched)

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

    if result.total_count > 0:
        works_response = work_coll.query.fetch_objects(
            limit=100,
        )

        print()
        print("📚 Works créés :")
        for i, work_obj in enumerate(works_response.objects, 1):
            props = work_obj.properties
            print(f"   {i:2d}. {props['title']}")
            print(f"       Auteur : {props['author']}")

            if props.get("year"):
                year = props["year"]
                if year < 0:
                    print(f"       Année : {abs(year)} av. J.-C.")
                else:
                    print(f"       Année : {year}")

            if props.get("language"):
                print(f"       Langue : {props['language']}")

            if props.get("genre"):
                print(f"       Genre : {props['genre']}")

            print()

    print("=" * 80)
    print()


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Peupler la collection Work avec corrections des doublons"
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
    print("PEUPLEMENT DE LA COLLECTION WORK (AVEC CORRECTIONS)")
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
        collections = client.collections.list_all()
        if "Work" not in collections:
            print("❌ ERREUR : La collection Work n'existe pas !")
            print()
            print("   Créez-la d'abord avec :")
            print("   python migrate_add_work_collection.py")
            print()
            sys.exit(1)

        # Étape 1 : Extraire les œuvres avec corrections
        works_data = extract_unique_works_from_chunks(client)

        if not works_data:
            print("❌ Aucune œuvre détectée dans les chunks !")
            sys.exit(1)

        # Étape 2 : Afficher le rapport des corrections
        display_corrections_report(works_data)

        # Étape 3 : Afficher le rapport des œuvres à insérer
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
            print("   python populate_work_collection_clean.py --execute")
            print()

    finally:
        client.close()


if __name__ == "__main__":
    main()
