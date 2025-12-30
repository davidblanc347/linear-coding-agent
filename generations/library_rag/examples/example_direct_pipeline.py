#!/usr/bin/env python3
"""
Exemple d'utilisation DIRECTE du pipeline PDF (sans MCP).

Plus simple et plus de contrôle sur les paramètres!
"""

from pathlib import Path
from utils.pdf_pipeline import process_pdf, process_pdf_bytes
import weaviate
from weaviate.classes.query import Filter


def example_process_local_file():
    """Traiter un fichier local (PDF ou Markdown)."""

    result = process_pdf(
        pdf_path=Path("md/peirce_collected_papers_fixed.md"),
        output_dir=Path("output"),

        # Paramètres personnalisables
        skip_ocr=True,                      # Déjà en Markdown
        use_llm=False,                      # Pas besoin de LLM pour Peirce
        use_semantic_chunking=False,        # Chunking basique (rapide)
        ingest_to_weaviate=True,            # Ingérer dans Weaviate
    )

    if result.get("success"):
        print(f"✓ {result['document_name']}: {result['chunks_count']} chunks")
        print(f"  Coût total: {result['cost_total']:.4f}€")
    else:
        print(f"✗ Erreur: {result.get('error')}")


def example_process_from_url():
    """Télécharger et traiter depuis une URL."""

    import httpx

    url = "https://example.com/document.pdf"

    # Télécharger
    response = httpx.get(url, follow_redirects=True)
    pdf_bytes = response.content

    # Traiter
    result = process_pdf_bytes(
        file_bytes=pdf_bytes,
        filename="document.pdf",
        output_dir=Path("output"),

        # Paramètres optimaux
        use_llm=True,
        llm_provider="mistral",             # Ou "ollama"
        use_semantic_chunking=True,
        ingest_to_weaviate=True,
    )

    return result


def example_search():
    """Rechercher directement dans Weaviate."""

    client = weaviate.connect_to_local()

    try:
        collection = client.collections.get('Chunk')

        # Recherche sémantique
        response = collection.query.near_text(
            query="nominalism and realism",
            limit=10,
        )

        print(f"Trouvé {len(response.objects)} résultats:")
        for obj in response.objects[:3]:
            props = obj.properties
            print(f"\n- {props.get('sectionPath', 'N/A')}")
            print(f"  {props.get('text', '')[:150]}...")

    finally:
        client.close()


if __name__ == "__main__":
    # Choisir un exemple

    # example_process_local_file()
    # example_process_from_url()
    example_search()
