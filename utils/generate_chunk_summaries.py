"""Script de génération de résumés pour les chunks existants.

Ce script:
1. Liste les œuvres disponibles dans Weaviate
2. Permet à l'utilisateur de sélectionner une œuvre
3. Récupère tous les chunks de cette œuvre
4. Génère un résumé pour chaque chunk avec Ollama (qwen2.5:7b)
5. Met à jour les chunks dans Weaviate avec les résumés générés

Usage:
    python utils/generate_chunk_summaries.py
"""

import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import ollama
import weaviate
from tqdm import tqdm

# Configuration logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("chunk_summaries.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

# Configuration Ollama
OLLAMA_MODEL = "qwen2.5:7b"
BATCH_SIZE = 50  # Nombre de chunks à traiter par batch
MAX_RETRIES = 3  # Nombre de tentatives en cas d'erreur


def get_available_works(client: weaviate.WeaviateClient) -> List[Dict[str, Any]]:
    """Récupère la liste des œuvres disponibles.

    Args:
        client: Client Weaviate connecté.

    Returns:
        Liste des œuvres avec titre, auteur et nombre de chunks.
    """
    logger.info("Récupération des œuvres disponibles...")

    works_collection = client.collections.get("Work")
    works = works_collection.query.fetch_objects(limit=100)

    # Pour chaque œuvre, compter les chunks
    works_with_counts = []
    for work in works.objects:
        title = work.properties.get("title", "Sans titre")
        author = work.properties.get("author", "Auteur inconnu")

        # Compter les chunks de cette œuvre
        chunk_collection = client.collections.get("Chunk")
        result = chunk_collection.aggregate.over_all(
            filters=weaviate.classes.query.Filter.by_property("work").by_property("title").equal(title)
        )
        chunks_count = result.total_count

        works_with_counts.append({
            "title": title,
            "author": author,
            "chunks_count": chunks_count
        })

    return works_with_counts


def select_work(works: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Affiche les œuvres et demande à l'utilisateur de choisir.

    Args:
        works: Liste des œuvres disponibles.

    Returns:
        L'œuvre sélectionnée.
    """
    print("\n" + "=" * 80)
    print("ŒUVRES DISPONIBLES")
    print("=" * 80)

    for i, work in enumerate(works, 1):
        print(f"{i}. {work['title']} - {work['author']} ({work['chunks_count']} chunks)")

    print("=" * 80)

    while True:
        try:
            choice = int(input(f"\nChoisissez une œuvre (1-{len(works)}): "))
            if 1 <= choice <= len(works):
                return works[choice - 1]
            else:
                print(f"Veuillez entrer un nombre entre 1 et {len(works)}")
        except ValueError:
            print("Veuillez entrer un nombre valide")


def generate_summary(chunk_text: str, work_title: str, author: str) -> str:
    """Génère un résumé dense pour un chunk avec Ollama.

    Args:
        chunk_text: Texte du chunk à résumer.
        work_title: Titre de l'œuvre (non utilisé dans le prompt).
        author: Auteur de l'œuvre (non utilisé dans le prompt).

    Returns:
        Résumé dense généré (100-150 mots).
    """
    prompt = f"""TEXTE À RÉSUMER:
{chunk_text}

CONSIGNES STRICTES:
- Résumé direct de 100-150 mots maximum
- INTERDIT: formulations méta ("Ce passage souligne...", "L'auteur affirme...", "Peirce dit que...")
- Reformule les idées au style direct et impersonnel
- Densité conceptuelle maximale: chaque mot compte
- Conserve TOUS les concepts, termes techniques et noms propres
- Structure: thèse → arguments → implications
- Aucune perte d'information philosophique

RÉSUMÉ DENSE:"""

    response = ollama.generate(
        model=OLLAMA_MODEL,
        prompt=prompt,
        options={
            "temperature": 0.2,  # Très peu de créativité pour rester fidèle au texte
            "num_predict": 250,  # ~150 mots maximum
        }
    )

    return response["response"].strip()


def process_work_chunks(
    client: weaviate.WeaviateClient,
    work: Dict[str, Any]
) -> None:
    """Traite tous les chunks d'une œuvre pour générer des résumés.

    Args:
        client: Client Weaviate connecté.
        work: Œuvre sélectionnée.
    """
    title = work["title"]
    author = work["author"]
    total_chunks = work["chunks_count"]

    logger.info(f"Traitement de '{title}' - {total_chunks} chunks")

    # Récupérer tous les chunks de l'œuvre
    chunk_collection = client.collections.get("Chunk")

    # Pagination pour récupérer tous les chunks
    all_chunks = []
    cursor = None
    fetch_batch_size = 500

    logger.info("Récupération des chunks...")
    while True:
        if cursor:
            response = chunk_collection.query.fetch_objects(
                limit=fetch_batch_size,
                after=cursor,
                filters=weaviate.classes.query.Filter.by_property("work").by_property("title").equal(title)
            )
        else:
            response = chunk_collection.query.fetch_objects(
                limit=fetch_batch_size,
                filters=weaviate.classes.query.Filter.by_property("work").by_property("title").equal(title)
            )

        if not response.objects:
            break

        for obj in response.objects:
            all_chunks.append({
                "uuid": str(obj.uuid),
                "text": obj.properties.get("text", ""),
                "summary": obj.properties.get("summary", "")
            })

        if len(response.objects) < fetch_batch_size:
            break

        cursor = response.objects[-1].uuid

    logger.info(f"✓ {len(all_chunks)} chunks récupérés")

    # Filtrer les chunks sans résumé
    chunks_to_process = [c for c in all_chunks if not c["summary"]]

    if not chunks_to_process:
        logger.info("✓ Tous les chunks ont déjà un résumé !")
        return

    logger.info(f"→ {len(chunks_to_process)} chunks à traiter (résumés manquants)")

    # Générer les résumés avec barre de progression
    print("\nGénération des résumés...")
    successful = 0
    failed = 0

    for chunk in tqdm(chunks_to_process, desc="Chunks"):
        retry_count = 0

        while retry_count < MAX_RETRIES:
            try:
                # Générer le résumé
                summary = generate_summary(chunk["text"], title, author)

                # Mettre à jour le chunk dans Weaviate
                chunk_collection.data.update(
                    uuid=chunk["uuid"],
                    properties={"summary": summary}
                )

                successful += 1
                break  # Succès, sortir de la boucle de retry

            except Exception as e:
                retry_count += 1
                logger.error(f"Erreur chunk {chunk['uuid']} (tentative {retry_count}/{MAX_RETRIES}): {e}")

                if retry_count < MAX_RETRIES:
                    time.sleep(2)  # Pause avant retry
                else:
                    failed += 1
                    logger.error(f"✗ Échec définitif pour chunk {chunk['uuid']}")

    # Résumé final
    print("\n" + "=" * 80)
    print("RÉSULTATS")
    print("=" * 80)
    print(f"✓ Résumés générés avec succès: {successful}")
    print(f"✗ Échecs: {failed}")
    print(f"Total traité: {len(chunks_to_process)}")
    print("=" * 80)


def main() -> None:
    """Fonction principale."""
    logger.info("=" * 80)
    logger.info("GÉNÉRATION DE RÉSUMÉS POUR CHUNKS WEAVIATE")
    logger.info("=" * 80)

    # Vérifier que Ollama est disponible
    logger.info("\n[1/4] Vérification d'Ollama...")
    try:
        ollama.list()
        logger.info(f"  ✓ Ollama disponible, modèle: {OLLAMA_MODEL}")
    except Exception as e:
        logger.error(f"  ✗ Ollama non disponible: {e}")
        logger.error("  → Vérifiez qu'Ollama est lancé (ollama serve)")
        sys.exit(1)

    # Connexion à Weaviate
    logger.info("\n[2/4] Connexion à Weaviate...")
    try:
        client = weaviate.connect_to_local(
            host="localhost",
            port=8080,
            grpc_port=50051,
        )
        logger.info("  ✓ Connexion établie")
    except Exception as e:
        logger.error(f"  ✗ Erreur de connexion: {e}")
        logger.error("  → Vérifiez que Weaviate est lancé (docker compose up -d)")
        sys.exit(1)

    try:
        # Récupérer les œuvres
        logger.info("\n[3/4] Récupération des œuvres disponibles...")
        works = get_available_works(client)

        if not works:
            logger.error("  ✗ Aucune œuvre trouvée dans la base")
            sys.exit(1)

        logger.info(f"  ✓ {len(works)} œuvres disponibles")

        # Sélection de l'œuvre
        selected_work = select_work(works)
        logger.info(f"\n→ Œuvre sélectionnée: {selected_work['title']} ({selected_work['chunks_count']} chunks)")

        # Traitement
        logger.info("\n[4/4] Génération des résumés...")
        process_work_chunks(client, selected_work)

        logger.info("\n✓ TERMINÉ !")

    finally:
        client.close()
        logger.info("\n✓ Connexion Weaviate fermée")


if __name__ == "__main__":
    # Fix encoding pour Windows
    if sys.platform == "win32" and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    main()
