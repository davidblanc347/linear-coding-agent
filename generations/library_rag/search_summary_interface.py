"""Interface de recherche optimisée utilisant Summary comme collection primaire.

Cette implémentation utilise la collection Summary comme point d'entrée principal
pour la recherche sémantique, car elle offre 90% de visibilité des documents riches
vs 10% pour la recherche directe dans Chunks (domination Peirce).

Usage:
    python search_summary_interface.py "What is pragmatism?"
    python search_summary_interface.py "Can virtue be taught?"
"""

import sys
import io
import argparse
from typing import List, Dict, Any
import weaviate
import weaviate.classes.query as wvq

# Fix Windows encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


def search_summaries(
    query: str,
    limit: int = 10,
    min_similarity: float = 0.65
) -> List[Dict[str, Any]]:
    """Recherche sémantique dans la collection Summary.

    Args:
        query: Question de l'utilisateur
        limit: Nombre maximum de résultats
        min_similarity: Seuil de similarité minimum (0-1)

    Returns:
        Liste de dictionnaires contenant les résultats avec métadonnées
    """
    client = weaviate.connect_to_local()

    try:
        summaries = client.collections.get("Summary")

        # Recherche sémantique
        results = summaries.query.near_text(
            query=query,
            limit=limit,
            return_metadata=wvq.MetadataQuery(distance=True)
        )

        # Formater les résultats
        formatted_results = []
        for obj in results.objects:
            similarity = 1 - obj.metadata.distance

            # Filtrer par seuil de similarité
            if similarity < min_similarity:
                continue

            props = obj.properties

            result = {
                "similarity": similarity,
                "document": props["document"]["sourceId"],
                "title": props["title"],
                "summary": props.get("text", ""),
                "concepts": props.get("concepts", []),
                "section_path": props.get("sectionPath", ""),
                "chunks_count": props.get("chunksCount", 0),
                "author": props["document"].get("author", ""),
                "year": props["document"].get("year", 0),
            }

            formatted_results.append(result)

        return formatted_results

    finally:
        client.close()


def display_results(query: str, results: List[Dict[str, Any]]) -> None:
    """Affiche les résultats de recherche de manière formatée.

    Args:
        query: Question originale
        results: Liste des résultats de search_summaries()
    """
    print("=" * 100)
    print(f"RECHERCHE: '{query}'")
    print("=" * 100)
    print()

    if not results:
        print("❌ Aucun résultat trouvé")
        print()
        return

    print(f"✅ {len(results)} résultat(s) trouvé(s)")
    print()

    for i, result in enumerate(results, 1):
        # Icône par document
        doc_id = result["document"].lower()
        if "tiercelin" in doc_id:
            icon = "🟡"
            doc_name = "Tiercelin"
        elif "platon" in doc_id or "menon" in doc_id:
            icon = "🟢"
            doc_name = "Platon"
        elif "haugeland" in doc_id:
            icon = "🟣"
            doc_name = "Haugeland"
        elif "logique" in doc_id:
            icon = "🔵"
            doc_name = "Logique de la science"
        else:
            icon = "⚪"
            doc_name = "Peirce"

        similarity_pct = result["similarity"] * 100

        print(f"[{i}] {icon} {doc_name} - Similarité: {result['similarity']:.3f} ({similarity_pct:.1f}%)")
        print(f"    Titre: {result['title']}")

        # Afficher auteur/année si disponible
        if result["author"]:
            author_info = f"{result['author']}"
            if result["year"]:
                author_info += f" ({result['year']})"
            print(f"    Auteur: {author_info}")

        # Concepts clés
        if result["concepts"]:
            concepts_str = ", ".join(result["concepts"][:5])  # Top 5 concepts
            if len(result["concepts"]) > 5:
                concepts_str += f" (+{len(result['concepts']) - 5} autres)"
            print(f"    Concepts: {concepts_str}")

        # Résumé
        summary = result["summary"]
        if len(summary) > 300:
            summary = summary[:297] + "..."

        if summary:
            print(f"    Résumé: {summary}")
        else:
            print(f"    Résumé: [Titre de section sans résumé]")

        # Chunks disponibles
        if result["chunks_count"] > 0:
            print(f"    📄 {result['chunks_count']} chunk(s) disponible(s) pour lecture détaillée")

        print()

    print("-" * 100)
    print()


def get_chunks_for_section(
    document_id: str,
    section_path: str,
    limit: int = 5
) -> List[Dict[str, Any]]:
    """Récupère les chunks détaillés d'une section spécifique.

    Utilisé quand l'utilisateur veut lire le contenu détaillé d'un résumé.

    Args:
        document_id: ID du document (sourceId)
        section_path: Chemin de la section
        limit: Nombre maximum de chunks

    Returns:
        Liste de chunks avec texte complet
    """
    client = weaviate.connect_to_local()

    try:
        chunks = client.collections.get("Chunk")

        # Récupérer tous les chunks (pas de filtrage nested object possible)
        all_chunks = list(chunks.iterator())

        # Filtrer en Python
        section_chunks = [
            c for c in all_chunks
            if c.properties.get("document", {}).get("sourceId") == document_id
            and c.properties.get("sectionPath", "").startswith(section_path)
        ]

        # Trier par orderIndex si disponible
        section_chunks.sort(
            key=lambda c: c.properties.get("orderIndex", 0)
        )

        # Limiter
        section_chunks = section_chunks[:limit]

        # Formater
        formatted_chunks = []
        for chunk in section_chunks:
            props = chunk.properties
            formatted_chunks.append({
                "text": props.get("text", ""),
                "section": props.get("sectionPath", ""),
                "chapter": props.get("chapterTitle", ""),
                "keywords": props.get("keywords", []),
                "order": props.get("orderIndex", 0),
            })

        return formatted_chunks

    finally:
        client.close()


def interactive_mode():
    """Mode interactif pour recherche continue."""
    print("=" * 100)
    print("INTERFACE DE RECHERCHE RAG - Collection Summary")
    print("=" * 100)
    print()
    print("Mode: Summary-first (90% de visibilité démontrée)")
    print("Tapez 'quit' pour quitter")
    print()

    while True:
        try:
            query = input("Votre question: ").strip()

            if query.lower() in ["quit", "exit", "q"]:
                print("Au revoir!")
                break

            if not query:
                continue

            print()
            results = search_summaries(query, limit=10, min_similarity=0.65)
            display_results(query, results)

        except KeyboardInterrupt:
            print("\nAu revoir!")
            break
        except Exception as e:
            print(f"❌ Erreur: {e}")
            print()


def main():
    """Point d'entrée principal."""
    parser = argparse.ArgumentParser(
        description="Recherche sémantique optimisée via Summary collection"
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="Question de recherche (optionnel - lance mode interactif si absent)"
    )
    parser.add_argument(
        "-n", "--limit",
        type=int,
        default=10,
        help="Nombre maximum de résultats (défaut: 10)"
    )
    parser.add_argument(
        "-s", "--min-similarity",
        type=float,
        default=0.65,
        help="Seuil de similarité minimum 0-1 (défaut: 0.65)"
    )

    args = parser.parse_args()

    if args.query:
        # Mode requête unique
        results = search_summaries(
            args.query,
            limit=args.limit,
            min_similarity=args.min_similarity
        )
        display_results(args.query, results)
    else:
        # Mode interactif
        interactive_mode()


if __name__ == "__main__":
    main()
