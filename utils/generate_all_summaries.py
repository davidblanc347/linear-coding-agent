"""Script pour générer des résumés pour TOUS les chunks sans résumé.

Ce script génère des résumés densifiés pour tous les chunks de la base Weaviate
qui n'ont pas encore de résumé (summary="").

Usage:
    python utils/generate_all_summaries.py

Fonctionnalités:
- Reprend automatiquement là où il s'est arrêté (peut être interrompu)
- Affiche progression en temps réel
- Estimation du temps restant
- Logging détaillé
- Gestion des erreurs avec retry
"""

import json
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any

import ollama
import weaviate
from tqdm import tqdm

# Configuration
OLLAMA_MODEL = "qwen2.5:7b"
MAX_RETRIES = 3
PROGRESS_FILE = Path("summary_generation_progress.json")

# Configuration logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("generate_all_summaries.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)


def load_progress() -> Dict[str, Any]:
    """Charge la progression depuis le fichier."""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"processed_uuids": [], "last_update": None, "total_processed": 0}


def save_progress(progress: Dict[str, Any]) -> None:
    """Sauvegarde la progression."""
    progress["last_update"] = datetime.now().isoformat()
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, indent=2)


def generate_summary(chunk_text: str) -> str:
    """Génère un résumé dense avec Ollama."""
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
            "temperature": 0.2,
            "num_predict": 250,
        }
    )
    return response["response"].strip()


def get_chunks_without_summary(client: weaviate.WeaviateClient) -> List[Dict[str, Any]]:
    """Récupère tous les chunks sans résumé."""
    logger.info("Récupération des chunks sans résumé...")

    chunk_collection = client.collections.get("Chunk")
    all_chunks = []
    cursor = None
    batch_size = 1000

    while True:
        if cursor:
            response = chunk_collection.query.fetch_objects(
                limit=batch_size,
                after=cursor
            )
        else:
            response = chunk_collection.query.fetch_objects(limit=batch_size)

        if not response.objects:
            break

        for obj in response.objects:
            summary = obj.properties.get("summary", "")
            if not summary:  # Pas de résumé ou résumé vide
                all_chunks.append({
                    "uuid": str(obj.uuid),
                    "text": obj.properties.get("text", ""),
                    "work": obj.properties.get("work", {}).get("title", "Unknown"),
                    "order": obj.properties.get("orderIndex", 0)
                })

        if len(response.objects) < batch_size:
            break

        cursor = response.objects[-1].uuid

    logger.info(f"  ✓ {len(all_chunks)} chunks sans résumé trouvés")
    return all_chunks


def process_all_chunks(client: weaviate.WeaviateClient) -> None:
    """Traite tous les chunks sans résumé."""

    # Charger la progression
    progress = load_progress()
    processed_set = set(progress["processed_uuids"])

    if processed_set:
        logger.info(f"Reprise: {len(processed_set)} chunks déjà traités")

    # Récupérer les chunks
    all_chunks = get_chunks_without_summary(client)

    # Filtrer ceux déjà traités
    chunks_to_process = [c for c in all_chunks if c["uuid"] not in processed_set]

    if not chunks_to_process:
        logger.info("✓ Tous les chunks ont déjà un résumé !")
        return

    logger.info(f"→ {len(chunks_to_process)} chunks à traiter")

    # Statistiques
    successful = 0
    failed = 0
    start_time = time.time()

    chunk_collection = client.collections.get("Chunk")

    # Barre de progression
    pbar = tqdm(chunks_to_process, desc="Génération résumés", unit="chunk")

    for i, chunk in enumerate(pbar, 1):
        retry_count = 0

        while retry_count < MAX_RETRIES:
            try:
                # Générer le résumé
                summary = generate_summary(chunk["text"])

                # Mettre à jour dans Weaviate
                chunk_collection.data.update(
                    uuid=chunk["uuid"],
                    properties={"summary": summary}
                )

                # Marquer comme traité
                processed_set.add(chunk["uuid"])
                successful += 1

                # Mettre à jour barre de progression
                elapsed = time.time() - start_time
                avg_time_per_chunk = elapsed / successful if successful > 0 else 0
                remaining_chunks = len(chunks_to_process) - i
                eta_seconds = avg_time_per_chunk * remaining_chunks
                eta = timedelta(seconds=int(eta_seconds))

                pbar.set_postfix({
                    "OK": successful,
                    "FAIL": failed,
                    "ETA": str(eta)
                })

                # Sauvegarder la progression tous les 10 chunks
                if successful % 10 == 0:
                    progress["processed_uuids"] = list(processed_set)
                    progress["total_processed"] = successful
                    save_progress(progress)

                break  # Succès, passer au suivant

            except KeyboardInterrupt:
                logger.info("\n⚠ Interruption utilisateur")
                progress["processed_uuids"] = list(processed_set)
                progress["total_processed"] = successful
                save_progress(progress)
                raise

            except Exception as e:
                retry_count += 1
                logger.error(f"Erreur chunk {chunk['uuid']} (tentative {retry_count}/{MAX_RETRIES}): {e}")

                if retry_count < MAX_RETRIES:
                    time.sleep(2)
                else:
                    failed += 1
                    logger.error(f"✗ Échec définitif pour chunk {chunk['uuid']}")

    # Sauvegarder la progression finale
    progress["processed_uuids"] = list(processed_set)
    progress["total_processed"] = successful
    save_progress(progress)

    # Résumé final
    total_time = time.time() - start_time
    avg_time = total_time / successful if successful > 0 else 0

    logger.info("\n" + "=" * 80)
    logger.info("RÉSULTATS FINAUX")
    logger.info("=" * 80)
    logger.info(f"✓ Succès          : {successful}")
    logger.info(f"✗ Échecs          : {failed}")
    logger.info(f"Total traité      : {len(chunks_to_process)}")
    logger.info(f"Temps total       : {timedelta(seconds=int(total_time))}")
    logger.info(f"Temps moyen/chunk : {avg_time:.1f}s")
    logger.info("=" * 80)


def main() -> None:
    """Fonction principale."""
    logger.info("=" * 80)
    logger.info("GÉNÉRATION DE RÉSUMÉS POUR TOUS LES CHUNKS")
    logger.info("=" * 80)

    # Vérifier Ollama
    logger.info("\n[1/3] Vérification d'Ollama...")
    try:
        ollama.list()
        logger.info(f"  ✓ Ollama disponible, modèle: {OLLAMA_MODEL}")
    except Exception as e:
        logger.error(f"  ✗ Ollama non disponible: {e}")
        logger.error("  → Vérifiez qu'Ollama est lancé (ollama serve)")
        sys.exit(1)

    # Connexion Weaviate
    logger.info("\n[2/3] Connexion à Weaviate...")
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
        # Traitement
        logger.info("\n[3/3] Génération des résumés...")
        logger.info("(Appuyez sur Ctrl+C pour interrompre - la progression sera sauvegardée)\n")
        process_all_chunks(client)

        logger.info("\n✓ TERMINÉ !")

    except KeyboardInterrupt:
        logger.info("\n⚠ Arrêt demandé par l'utilisateur")
        logger.info("→ Relancez le script pour reprendre là où vous vous êtes arrêté")

    finally:
        client.close()
        logger.info("\n✓ Connexion Weaviate fermée")


if __name__ == "__main__":
    # Fix encoding pour Windows
    if sys.platform == "win32" and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    main()
