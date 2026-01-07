"""Script pour restaurer les données depuis un backup spécifique.

Usage:
    python restore_from_backup.py backup_migration_20260105_174349
"""

import json
import logging
import re
import sys
import time
from pathlib import Path

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


def import_collection(
    client: weaviate.WeaviateClient,
    collection_name: str,
    backup_file: Path,
    add_summary_field: bool = False
) -> int:
    """Importe les données d'un fichier JSON vers une collection Weaviate."""
    logger.info(f"Import de la collection '{collection_name}'...")

    if not backup_file.exists():
        logger.warning(f"  ⚠ Fichier {backup_file} introuvable, skip")
        return 0

    try:
        with open(backup_file, "r", encoding="utf-8") as f:
            objects = json.load(f)

        if not objects:
            logger.info(f"  ⚠ Aucun objet à importer pour {collection_name}")
            return 0

        collection = client.collections.get(collection_name)

        # Préparer les objets pour l'insertion
        objects_to_insert = []
        for obj in objects:
            props = obj["properties"]

            # Ajouter le champ summary vide pour les chunks
            if add_summary_field:
                props["summary"] = ""

            # Fixer les formats de date (ISO8601 → RFC3339)
            props = fix_dates_in_object(props)

            objects_to_insert.append(props)

        # Insertion par batch (petite taille pour éviter OOM du conteneur)
        batch_size = 20
        total_inserted = 0

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
                logger.error(f"  ✗ Erreur lors de l'insertion du batch {i//batch_size + 1}: {e}")

        logger.info(f"  ✓ {total_inserted} objets importés dans {collection_name}")
        return total_inserted

    except Exception as e:
        logger.error(f"  ✗ Erreur lors de l'import de {collection_name}: {e}")
        return 0


def main():
    if len(sys.argv) < 2:
        print("Usage: python restore_from_backup.py <backup_directory>")
        sys.exit(1)

    backup_dir = Path(sys.argv[1])

    if not backup_dir.exists():
        logger.error(f"Backup directory '{backup_dir}' does not exist")
        sys.exit(1)

    logger.info("=" * 80)
    logger.info(f"RESTORATION DEPUIS {backup_dir}")
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
        # Import dans l'ordre
        import_collection(client, "Work", backup_dir / "work_backup.json")
        import_collection(client, "Document", backup_dir / "document_backup.json")
        import_collection(
            client,
            "Chunk",
            backup_dir / "chunk_backup.json",
            add_summary_field=True  # Ajouter summary=""
        )
        import_collection(client, "Summary", backup_dir / "summary_backup.json")

        logger.info("\n" + "=" * 80)
        logger.info("RESTORATION TERMINÉE AVEC SUCCÈS!")
        logger.info("=" * 80)

    finally:
        client.close()
        logger.info("\n✓ Connexion fermée")


if __name__ == "__main__":
    # Fix encoding for Windows
    if sys.platform == "win32" and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    main()
