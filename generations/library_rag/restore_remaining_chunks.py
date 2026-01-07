"""Script pour restaurer uniquement les chunks manquants.

Ce script:
1. Récupère tous les chunks déjà présents dans Weaviate
2. Compare avec le backup pour identifier les chunks manquants
3. Importe uniquement les chunks manquants

Usage:
    python restore_remaining_chunks.py backup_migration_20260105_174349
"""

import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Set

import weaviate

# Configuration logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def fix_date_format(value):
    """Convertit les dates ISO8601 en RFC3339 (remplace espace par T)."""
    if isinstance(value, str) and re.match(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', value):
        return value.replace(' ', 'T', 1)
    return value


def fix_dates_in_object(obj):
    """Parcourt récursivement un objet et fixe les formats de date."""
    if isinstance(obj, dict):
        return {k: fix_dates_in_object(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [fix_dates_in_object(item) for item in obj]
    else:
        return fix_date_format(obj)


def get_existing_chunk_texts(client: weaviate.WeaviateClient) -> Set[str]:
    """Récupère les textes de tous les chunks existants pour comparaison.

    On utilise les premiers 100 caractères du texte comme clé unique.
    """
    logger.info("Récupération des chunks existants...")

    chunk_collection = client.collections.get("Chunk")
    existing_texts = set()

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
            text = obj.properties.get("text", "")
            # Utiliser les 100 premiers caractères comme clé unique
            text_key = text[:100] if text else ""
            existing_texts.add(text_key)

        if len(response.objects) < batch_size:
            break

        cursor = response.objects[-1].uuid

    logger.info(f"  ✓ {len(existing_texts)} chunks existants récupérés")
    return existing_texts


def import_missing_chunks(
    client: weaviate.WeaviateClient,
    backup_file: Path,
    existing_texts: Set[str]
) -> int:
    """Importe uniquement les chunks manquants."""

    logger.info(f"Chargement du backup depuis {backup_file}...")

    if not backup_file.exists():
        logger.error(f"  ✗ Fichier {backup_file} introuvable")
        return 0

    try:
        with open(backup_file, "r", encoding="utf-8") as f:
            objects = json.load(f)

        logger.info(f"  ✓ {len(objects)} chunks dans le backup")

        # Filtrer les chunks manquants
        missing_chunks = []
        for obj in objects:
            text = obj["properties"].get("text", "")
            text_key = text[:100] if text else ""

            if text_key not in existing_texts:
                missing_chunks.append(obj)

        logger.info(f"  → {len(missing_chunks)} chunks manquants à restaurer")

        if not missing_chunks:
            logger.info("  ✓ Aucun chunk manquant !")
            return 0

        # Préparer les objets pour l'insertion
        collection = client.collections.get("Chunk")
        objects_to_insert = []

        for obj in missing_chunks:
            props = obj["properties"]

            # Ajouter le champ summary vide
            props["summary"] = ""

            # Fixer les formats de date
            props = fix_dates_in_object(props)

            objects_to_insert.append(props)

        # Insertion par batch
        batch_size = 20  # Petit batch pour éviter OOM
        total_inserted = 0

        logger.info("\nInsertion des chunks manquants...")
        for i in range(0, len(objects_to_insert), batch_size):
            batch = objects_to_insert[i:i + batch_size]

            try:
                collection.data.insert_many(batch)
                total_inserted += len(batch)

                if (i // batch_size + 1) % 10 == 0:
                    logger.info(f"  → {total_inserted}/{len(objects_to_insert)} objets insérés...")

                # Pause entre batches pour éviter surcharge mémoire
                time.sleep(0.1)

            except Exception as e:
                logger.error(f"  ✗ Erreur batch {i//batch_size + 1}: {e}")

                # En cas d'erreur, attendre plus longtemps et continuer
                time.sleep(5)

        logger.info(f"\n  ✓ {total_inserted} chunks manquants importés")
        return total_inserted

    except Exception as e:
        logger.error(f"  ✗ Erreur lors de l'import: {e}")
        return 0


def main():
    if len(sys.argv) < 2:
        print("Usage: python restore_remaining_chunks.py <backup_directory>")
        sys.exit(1)

    backup_dir = Path(sys.argv[1])

    if not backup_dir.exists():
        logger.error(f"Backup directory '{backup_dir}' does not exist")
        sys.exit(1)

    logger.info("=" * 80)
    logger.info(f"RESTORATION DES CHUNKS MANQUANTS DEPUIS {backup_dir}")
    logger.info("=" * 80)

    # Connexion à Weaviate
    logger.info("\nConnexion à Weaviate...")
    try:
        client = weaviate.connect_to_local(
            host="localhost",
            port=8080,
            grpc_port=50051,
        )
        logger.info("  ✓ Connexion établie")
    except Exception as e:
        logger.error(f"  ✗ Erreur de connexion: {e}")
        sys.exit(1)

    try:
        # Étape 1: Récupérer les chunks existants
        existing_texts = get_existing_chunk_texts(client)

        # Étape 2: Importer les chunks manquants
        backup_file = backup_dir / "chunk_backup.json"
        total_imported = import_missing_chunks(client, backup_file, existing_texts)

        # Étape 3: Vérification finale
        logger.info("\nVérification finale...")
        chunk_collection = client.collections.get("Chunk")
        result = chunk_collection.aggregate.over_all()
        final_count = result.total_count

        logger.info(f"  ✓ Total de chunks dans Weaviate: {final_count}")

        logger.info("\n" + "=" * 80)
        logger.info("RESTORATION DES CHUNKS MANQUANTS TERMINÉE !")
        logger.info("=" * 80)
        logger.info(f"✓ Chunks importés: {total_imported}")
        logger.info(f"✓ Total final: {final_count}/5246")
        logger.info("=" * 80)

    finally:
        client.close()
        logger.info("\n✓ Connexion fermée")


if __name__ == "__main__":
    # Fix encoding for Windows
    if sys.platform == "win32" and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    main()
