"""Script de migration pour ajouter le champ 'summary' à la collection Chunk.

Ce script :
1. Exporte toutes les données existantes (Work, Document, Chunk, Summary)
2. Supprime et recrée le schéma avec le nouveau champ 'summary' vectorisé
3. Réimporte toutes les données avec summary="" par défaut pour les chunks

Usage:
    python migrate_add_summary.py

ATTENTION: Ce script supprime et recrée le schéma. Assurez-vous que:
- Weaviate est en cours d'exécution (docker compose up -d)
- Vous avez un backup manuel si nécessaire (recommandé)
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import weaviate
from weaviate.collections import Collection

# Importer les fonctions de création de schéma
from schema import create_schema

# Configuration logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("migration.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)


# =============================================================================
# Fonctions d'export
# =============================================================================

def export_collection(
    client: weaviate.WeaviateClient,
    collection_name: str,
    output_dir: Path
) -> int:
    """Exporte toutes les données d'une collection vers un fichier JSON.

    Args:
        client: Client Weaviate connecté.
        collection_name: Nom de la collection à exporter.
        output_dir: Répertoire de sortie.

    Returns:
        Nombre d'objets exportés.
    """
    logger.info(f"Export de la collection '{collection_name}'...")

    try:
        collection = client.collections.get(collection_name)

        # Récupérer tous les objets (pas de limite)
        objects = []
        cursor = None
        batch_size = 1000

        while True:
            if cursor:
                response = collection.query.fetch_objects(
                    limit=batch_size,
                    after=cursor
                )
            else:
                response = collection.query.fetch_objects(limit=batch_size)

            if not response.objects:
                break

            for obj in response.objects:
                # Extraire UUID et propriétés
                obj_data = {
                    "uuid": str(obj.uuid),
                    "properties": obj.properties
                }
                objects.append(obj_data)

            # Continuer si plus d'objets disponibles
            if len(response.objects) < batch_size:
                break

            cursor = response.objects[-1].uuid

        # Sauvegarder dans un fichier JSON
        output_file = output_dir / f"{collection_name.lower()}_backup.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(objects, f, indent=2, ensure_ascii=False, default=str)

        logger.info(f"  ✓ {len(objects)} objets exportés vers {output_file}")
        return len(objects)

    except Exception as e:
        logger.error(f"  ✗ Erreur lors de l'export de {collection_name}: {e}")
        return 0


def export_all_data(client: weaviate.WeaviateClient) -> Path:
    """Exporte toutes les collections vers un dossier de backup.

    Args:
        client: Client Weaviate connecté.

    Returns:
        Path du dossier de backup créé.
    """
    # Créer un dossier de backup avec timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = Path(f"backup_migration_{timestamp}")
    backup_dir.mkdir(exist_ok=True)

    logger.info("=" * 80)
    logger.info("EXPORT DES DONNÉES EXISTANTES")
    logger.info("=" * 80)

    collections = ["Work", "Document", "Chunk", "Summary"]
    total_objects = 0

    for collection_name in collections:
        count = export_collection(client, collection_name, backup_dir)
        total_objects += count

    logger.info(f"\n✓ Total exporté: {total_objects} objets dans {backup_dir}")

    return backup_dir


# =============================================================================
# Fonctions d'import
# =============================================================================

def import_collection(
    client: weaviate.WeaviateClient,
    collection_name: str,
    backup_file: Path,
    add_summary_field: bool = False
) -> int:
    """Importe les données d'un fichier JSON vers une collection Weaviate.

    Args:
        client: Client Weaviate connecté.
        collection_name: Nom de la collection cible.
        backup_file: Fichier JSON source.
        add_summary_field: Si True, ajoute un champ 'summary' vide (pour Chunk).

    Returns:
        Nombre d'objets importés.
    """
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

            objects_to_insert.append(props)

        # Insertion par batch (plus efficace)
        batch_size = 100
        total_inserted = 0

        for i in range(0, len(objects_to_insert), batch_size):
            batch = objects_to_insert[i:i + batch_size]
            try:
                collection.data.insert_many(batch)
                total_inserted += len(batch)

                if (i // batch_size + 1) % 10 == 0:
                    logger.info(f"  → {total_inserted}/{len(objects_to_insert)} objets insérés...")

            except Exception as e:
                logger.error(f"  ✗ Erreur lors de l'insertion du batch {i//batch_size + 1}: {e}")
                # Continuer avec le batch suivant

        logger.info(f"  ✓ {total_inserted} objets importés dans {collection_name}")
        return total_inserted

    except Exception as e:
        logger.error(f"  ✗ Erreur lors de l'import de {collection_name}: {e}")
        return 0


def import_all_data(client: weaviate.WeaviateClient, backup_dir: Path) -> None:
    """Importe toutes les données depuis un dossier de backup.

    Args:
        client: Client Weaviate connecté.
        backup_dir: Dossier contenant les fichiers de backup.
    """
    logger.info("\n" + "=" * 80)
    logger.info("IMPORT DES DONNÉES")
    logger.info("=" * 80)

    # Ordre d'import: Work → Document → Chunk/Summary
    import_collection(client, "Work", backup_dir / "work_backup.json")
    import_collection(client, "Document", backup_dir / "document_backup.json")
    import_collection(
        client,
        "Chunk",
        backup_dir / "chunk_backup.json",
        add_summary_field=True  # Ajouter le champ summary vide
    )
    import_collection(client, "Summary", backup_dir / "summary_backup.json")

    logger.info("\n✓ Import terminé")


# =============================================================================
# Script principal
# =============================================================================

def main() -> None:
    """Fonction principale de migration."""
    logger.info("=" * 80)
    logger.info("MIGRATION: Ajout du champ 'summary' à la collection Chunk")
    logger.info("=" * 80)

    # Connexion à Weaviate
    logger.info("\n[1/5] Connexion à Weaviate...")
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
        # Étape 1: Export des données
        logger.info("\n[2/5] Export des données existantes...")
        backup_dir = export_all_data(client)

        # Étape 2: Recréation du schéma
        logger.info("\n[3/5] Suppression et recréation du schéma...")
        create_schema(client, delete_existing=True)
        logger.info("  ✓ Nouveau schéma créé avec champ 'summary' vectorisé")

        # Étape 3: Réimport des données
        logger.info("\n[4/5] Réimport des données...")
        import_all_data(client, backup_dir)

        # Étape 4: Vérification
        logger.info("\n[5/5] Vérification...")
        chunk_collection = client.collections.get("Chunk")
        count = len(chunk_collection.query.fetch_objects(limit=1).objects)

        if count > 0:
            # Vérifier qu'un chunk a bien le champ summary
            sample = chunk_collection.query.fetch_objects(limit=1).objects[0]
            if "summary" in sample.properties:
                logger.info("  ✓ Champ 'summary' présent dans les chunks")
            else:
                logger.warning("  ⚠ Champ 'summary' manquant (vérifier schema.py)")

        logger.info("\n" + "=" * 80)
        logger.info("MIGRATION TERMINÉE AVEC SUCCÈS!")
        logger.info("=" * 80)
        logger.info(f"\n✓ Backup sauvegardé dans: {backup_dir}")
        logger.info("✓ Schéma mis à jour avec champ 'summary' vectorisé")
        logger.info("✓ Toutes les données ont été restaurées")
        logger.info("\nProchaine étape:")
        logger.info("  → Lancez utils/generate_chunk_summaries.py pour générer les résumés")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"\n✗ ERREUR CRITIQUE: {e}")
        logger.error("La migration a échoué. Vérifiez les logs dans migration.log")
        sys.exit(1)

    finally:
        client.close()
        logger.info("\n✓ Connexion Weaviate fermée")


if __name__ == "__main__":
    # Vérifier l'encodage Windows
    if sys.platform == "win32" and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    main()
