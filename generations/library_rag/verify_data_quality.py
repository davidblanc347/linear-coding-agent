#!/usr/bin/env python3
"""Vérification de la qualité des données Weaviate œuvre par œuvre.

Ce script analyse la cohérence entre les 4 collections (Work, Document, Chunk, Summary)
et détecte les incohérences :
- Documents sans chunks/summaries
- Chunks/summaries orphelins
- Works manquants
- Incohérences dans les nested objects

Usage:
    python verify_data_quality.py
"""

import sys
from typing import Any, Dict, List, Set, Optional
from collections import defaultdict

import weaviate
from weaviate.collections import Collection


# =============================================================================
# Data Quality Checks
# =============================================================================


class DataQualityReport:
    """Rapport de qualité des données."""

    def __init__(self) -> None:
        self.total_documents = 0
        self.total_chunks = 0
        self.total_summaries = 0
        self.total_works = 0

        self.documents: List[Dict[str, Any]] = []
        self.issues: List[str] = []
        self.warnings: List[str] = []

        # Tracking des œuvres uniques extraites des nested objects
        self.unique_works: Dict[str, Set[str]] = defaultdict(set)  # title -> set(authors)

    def add_issue(self, severity: str, message: str) -> None:
        """Ajouter un problème détecté."""
        if severity == "ERROR":
            self.issues.append(f"❌ {message}")
        elif severity == "WARNING":
            self.warnings.append(f"⚠️  {message}")

    def add_document(self, doc_data: Dict[str, Any]) -> None:
        """Ajouter les données d'un document analysé."""
        self.documents.append(doc_data)

    def print_report(self) -> None:
        """Afficher le rapport complet."""
        print("\n" + "=" * 80)
        print("RAPPORT DE QUALITÉ DES DONNÉES WEAVIATE")
        print("=" * 80)

        # Statistiques globales
        print("\n📊 STATISTIQUES GLOBALES")
        print("─" * 80)
        print(f"  • Works (collection) :     {self.total_works:>6,} objets")
        print(f"  • Documents :              {self.total_documents:>6,} objets")
        print(f"  • Chunks :                 {self.total_chunks:>6,} objets")
        print(f"  • Summaries :              {self.total_summaries:>6,} objets")
        print()
        print(f"  • Œuvres uniques (nested): {len(self.unique_works):>6,} détectées")

        # Œuvres uniques détectées dans nested objects
        if self.unique_works:
            print("\n📚 ŒUVRES DÉTECTÉES (via nested objects dans Chunks)")
            print("─" * 80)
            for i, (title, authors) in enumerate(sorted(self.unique_works.items()), 1):
                authors_str = ", ".join(sorted(authors))
                print(f"  {i:2d}. {title}")
                print(f"      Auteur(s): {authors_str}")

        # Analyse par document
        print("\n" + "=" * 80)
        print("ANALYSE DÉTAILLÉE PAR DOCUMENT")
        print("=" * 80)

        for i, doc in enumerate(self.documents, 1):
            status = "✅" if doc["chunks_count"] > 0 and doc["summaries_count"] > 0 else "⚠️"
            print(f"\n{status} [{i}/{len(self.documents)}] {doc['sourceId']}")
            print("─" * 80)

            # Métadonnées Document
            if doc.get("work_nested"):
                work = doc["work_nested"]
                print(f"  Œuvre :     {work.get('title', 'N/A')}")
                print(f"  Auteur :    {work.get('author', 'N/A')}")
            else:
                print(f"  Œuvre :     {doc.get('title', 'N/A')}")
                print(f"  Auteur :    {doc.get('author', 'N/A')}")

            print(f"  Édition :   {doc.get('edition', 'N/A')}")
            print(f"  Langue :    {doc.get('language', 'N/A')}")
            print(f"  Pages :     {doc.get('pages', 0):,}")

            # Collections
            print()
            print(f"  📦 Collections :")
            print(f"     • Chunks :    {doc['chunks_count']:>6,} objets")
            print(f"     • Summaries : {doc['summaries_count']:>6,} objets")

            # Work collection
            if doc.get("has_work_object"):
                print(f"     • Work :      ✅ Existe dans collection Work")
            else:
                print(f"     • Work :      ❌ MANQUANT dans collection Work")

            # Cohérence nested objects
            if doc.get("nested_works_consistency"):
                consistency = doc["nested_works_consistency"]
                if consistency["is_consistent"]:
                    print(f"     • Cohérence nested objects : ✅ OK")
                else:
                    print(f"     • Cohérence nested objects : ⚠️  INCOHÉRENCES DÉTECTÉES")
                    if consistency["unique_titles"] > 1:
                        print(f"         → {consistency['unique_titles']} titres différents dans chunks:")
                        for title in consistency["titles"]:
                            print(f"            - {title}")
                    if consistency["unique_authors"] > 1:
                        print(f"         → {consistency['unique_authors']} auteurs différents dans chunks:")
                        for author in consistency["authors"]:
                            print(f"            - {author}")

            # Ratios
            if doc["chunks_count"] > 0:
                ratio = doc["summaries_count"] / doc["chunks_count"]
                print(f"  📊 Ratio Summary/Chunk : {ratio:.2f}")

                if ratio < 0.5:
                    print(f"     ⚠️  Ratio faible (< 0.5) - Peut-être des summaries manquants")
                elif ratio > 3.0:
                    print(f"     ⚠️  Ratio élevé (> 3.0) - Beaucoup de summaries pour peu de chunks")

            # Problèmes spécifiques à ce document
            if doc.get("issues"):
                print(f"\n  ⚠️  Problèmes détectés :")
                for issue in doc["issues"]:
                    print(f"     • {issue}")

        # Problèmes globaux
        if self.issues or self.warnings:
            print("\n" + "=" * 80)
            print("PROBLÈMES DÉTECTÉS")
            print("=" * 80)

            if self.issues:
                print("\n❌ ERREURS CRITIQUES :")
                for issue in self.issues:
                    print(f"  {issue}")

            if self.warnings:
                print("\n⚠️  AVERTISSEMENTS :")
                for warning in self.warnings:
                    print(f"  {warning}")

        # Recommandations
        print("\n" + "=" * 80)
        print("RECOMMANDATIONS")
        print("=" * 80)

        if self.total_works == 0 and len(self.unique_works) > 0:
            print("\n📌 Collection Work vide")
            print(f"   • {len(self.unique_works)} œuvres uniques détectées dans nested objects")
            print(f"   • Recommandation : Peupler la collection Work")
            print(f"   • Commande : python migrate_add_work_collection.py")
            print(f"   • Ensuite : Créer des objets Work depuis les nested objects uniques")

        # Vérifier cohérence counts
        total_chunks_declared = sum(doc.get("chunksCount", 0) for doc in self.documents if "chunksCount" in doc)
        if total_chunks_declared != self.total_chunks:
            print(f"\n⚠️  Incohérence counts")
            print(f"   • Document.chunksCount total : {total_chunks_declared:,}")
            print(f"   • Chunks réels :                {self.total_chunks:,}")
            print(f"   • Différence :                  {abs(total_chunks_declared - self.total_chunks):,}")

        print("\n" + "=" * 80)
        print("FIN DU RAPPORT")
        print("=" * 80)
        print()


def analyze_document_quality(
    all_chunks: List[Any],
    all_summaries: List[Any],
    doc_sourceId: str,
    client: weaviate.WeaviateClient,
) -> Dict[str, Any]:
    """Analyser la qualité des données pour un document spécifique.

    Args:
        all_chunks: All chunks from database (to filter in Python).
        all_summaries: All summaries from database (to filter in Python).
        doc_sourceId: Document identifier to analyze.
        client: Connected Weaviate client.

    Returns:
        Dict containing analysis results.
    """
    result: Dict[str, Any] = {
        "sourceId": doc_sourceId,
        "chunks_count": 0,
        "summaries_count": 0,
        "has_work_object": False,
        "issues": [],
    }

    # Filtrer les chunks associés (en Python car nested objects non filtrables)
    try:
        doc_chunks = [
            chunk for chunk in all_chunks
            if chunk.properties.get("document", {}).get("sourceId") == doc_sourceId
        ]

        result["chunks_count"] = len(doc_chunks)

        # Analyser cohérence nested objects
        if doc_chunks:
            titles: Set[str] = set()
            authors: Set[str] = set()

            for chunk_obj in doc_chunks:
                props = chunk_obj.properties
                if "work" in props and isinstance(props["work"], dict):
                    work = props["work"]
                    if work.get("title"):
                        titles.add(work["title"])
                    if work.get("author"):
                        authors.add(work["author"])

            result["nested_works_consistency"] = {
                "titles": sorted(titles),
                "authors": sorted(authors),
                "unique_titles": len(titles),
                "unique_authors": len(authors),
                "is_consistent": len(titles) <= 1 and len(authors) <= 1,
            }

            # Récupérer work/author pour ce document
            if titles and authors:
                result["work_from_chunks"] = {
                    "title": list(titles)[0] if len(titles) == 1 else titles,
                    "author": list(authors)[0] if len(authors) == 1 else authors,
                }

    except Exception as e:
        result["issues"].append(f"Erreur analyse chunks: {e}")

    # Filtrer les summaries associés (en Python)
    try:
        doc_summaries = [
            summary for summary in all_summaries
            if summary.properties.get("document", {}).get("sourceId") == doc_sourceId
        ]

        result["summaries_count"] = len(doc_summaries)

    except Exception as e:
        result["issues"].append(f"Erreur analyse summaries: {e}")

    # Vérifier si Work existe
    if result.get("work_from_chunks"):
        work_info = result["work_from_chunks"]
        if isinstance(work_info["title"], str):
            try:
                work_collection = client.collections.get("Work")
                work_response = work_collection.query.fetch_objects(
                    filters=weaviate.classes.query.Filter.by_property("title").equal(work_info["title"]),
                    limit=1,
                )

                result["has_work_object"] = len(work_response.objects) > 0

            except Exception as e:
                result["issues"].append(f"Erreur vérification Work: {e}")

    # Détection de problèmes
    if result["chunks_count"] == 0:
        result["issues"].append("Aucun chunk trouvé pour ce document")

    if result["summaries_count"] == 0:
        result["issues"].append("Aucun summary trouvé pour ce document")

    if result.get("nested_works_consistency") and not result["nested_works_consistency"]["is_consistent"]:
        result["issues"].append("Incohérences dans les nested objects work")

    return result


def main() -> None:
    """Main entry point."""
    # Fix encoding for Windows console
    if sys.platform == "win32" and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 80)
    print("VÉRIFICATION DE LA QUALITÉ DES DONNÉES WEAVIATE")
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
        print("✓ Starting data quality analysis...")
        print()

        report = DataQualityReport()

        # Récupérer counts globaux
        try:
            work_coll = client.collections.get("Work")
            work_result = work_coll.aggregate.over_all(total_count=True)
            report.total_works = work_result.total_count
        except Exception as e:
            report.add_issue("ERROR", f"Cannot count Work objects: {e}")

        try:
            chunk_coll = client.collections.get("Chunk")
            chunk_result = chunk_coll.aggregate.over_all(total_count=True)
            report.total_chunks = chunk_result.total_count
        except Exception as e:
            report.add_issue("ERROR", f"Cannot count Chunk objects: {e}")

        try:
            summary_coll = client.collections.get("Summary")
            summary_result = summary_coll.aggregate.over_all(total_count=True)
            report.total_summaries = summary_result.total_count
        except Exception as e:
            report.add_issue("ERROR", f"Cannot count Summary objects: {e}")

        # Récupérer TOUS les chunks et summaries en une fois
        # (car nested objects non filtrables via API Weaviate)
        print("Loading all chunks and summaries into memory...")
        all_chunks: List[Any] = []
        all_summaries: List[Any] = []

        try:
            chunk_coll = client.collections.get("Chunk")
            chunks_response = chunk_coll.query.fetch_objects(
                limit=10000,  # Haute limite pour gros corpus
                # Note: nested objects (work, document) sont retournés automatiquement
            )
            all_chunks = chunks_response.objects
            print(f"  ✓ Loaded {len(all_chunks)} chunks")
        except Exception as e:
            report.add_issue("ERROR", f"Cannot fetch all chunks: {e}")

        try:
            summary_coll = client.collections.get("Summary")
            summaries_response = summary_coll.query.fetch_objects(
                limit=10000,
                # Note: nested objects (document) sont retournés automatiquement
            )
            all_summaries = summaries_response.objects
            print(f"  ✓ Loaded {len(all_summaries)} summaries")
        except Exception as e:
            report.add_issue("ERROR", f"Cannot fetch all summaries: {e}")

        print()

        # Récupérer tous les documents
        try:
            doc_collection = client.collections.get("Document")
            docs_response = doc_collection.query.fetch_objects(
                limit=1000,
                return_properties=["sourceId", "title", "author", "edition", "language", "pages", "chunksCount", "work"],
            )

            report.total_documents = len(docs_response.objects)

            print(f"Analyzing {report.total_documents} documents...")
            print()

            for doc_obj in docs_response.objects:
                props = doc_obj.properties
                doc_sourceId = props.get("sourceId", "unknown")

                print(f"  • Analyzing {doc_sourceId}...", end=" ")

                # Analyser ce document (avec filtrage Python)
                analysis = analyze_document_quality(all_chunks, all_summaries, doc_sourceId, client)

                # Merger props Document avec analysis
                analysis.update({
                    "title": props.get("title"),
                    "author": props.get("author"),
                    "edition": props.get("edition"),
                    "language": props.get("language"),
                    "pages": props.get("pages", 0),
                    "chunksCount": props.get("chunksCount", 0),
                    "work_nested": props.get("work"),
                })

                # Collecter œuvres uniques
                if analysis.get("work_from_chunks"):
                    work_info = analysis["work_from_chunks"]
                    if isinstance(work_info["title"], str) and isinstance(work_info["author"], str):
                        report.unique_works[work_info["title"]].add(work_info["author"])

                report.add_document(analysis)

                # Feedback
                if analysis["chunks_count"] > 0:
                    print(f"✓ ({analysis['chunks_count']} chunks, {analysis['summaries_count']} summaries)")
                else:
                    print("⚠️  (no chunks)")

        except Exception as e:
            report.add_issue("ERROR", f"Cannot fetch documents: {e}")

        # Vérifications globales
        if report.total_works == 0 and report.total_chunks > 0:
            report.add_issue("WARNING", f"Work collection is empty but {report.total_chunks:,} chunks exist")

        if report.total_documents == 0 and report.total_chunks > 0:
            report.add_issue("WARNING", f"No documents but {report.total_chunks:,} chunks exist (orphan chunks)")

        # Afficher le rapport
        report.print_report()

    finally:
        client.close()


if __name__ == "__main__":
    main()
