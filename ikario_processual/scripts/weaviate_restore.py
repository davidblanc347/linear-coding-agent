#!/usr/bin/env python3
"""
Restauration de collections Weaviate depuis un backup.

Usage:
    python weaviate_restore.py backup.json
    python weaviate_restore.py backup.json --collections Thought,Conversation
    python weaviate_restore.py backup.json --dry-run
    python weaviate_restore.py backup.json --clear-existing

ATTENTION: Ce script peut supprimer des données existantes!
           Utilisez --dry-run pour prévisualiser les actions.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

# Configuration par défaut
WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://localhost:8080")


def check_weaviate_ready() -> bool:
    """Vérifie que Weaviate est accessible."""
    try:
        response = requests.get(f"{WEAVIATE_URL}/v1/.well-known/ready", timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False


def get_existing_classes() -> list[str]:
    """Récupère la liste des classes existantes."""
    response = requests.get(f"{WEAVIATE_URL}/v1/schema")
    response.raise_for_status()
    schema = response.json()
    return [c["class"] for c in schema.get("classes", [])]


def delete_class(class_name: str) -> bool:
    """Supprime une classe et tous ses objets."""
    response = requests.delete(f"{WEAVIATE_URL}/v1/schema/{class_name}")
    return response.status_code == 200


def create_class(class_schema: dict) -> bool:
    """Crée une classe avec son schéma."""
    response = requests.post(
        f"{WEAVIATE_URL}/v1/schema",
        json=class_schema,
        headers={"Content-Type": "application/json"}
    )
    return response.status_code == 200


def insert_object(class_name: str, obj: dict) -> bool:
    """
    Insère un objet dans une classe.

    Args:
        class_name: Nom de la classe
        obj: Objet complet du backup (avec id, properties, vector)
    """
    data = {
        "class": class_name,
        "properties": obj.get("properties", {}),
    }

    # Préserver l'ID original si présent
    if "id" in obj:
        data["id"] = obj["id"]

    # Inclure le vecteur si présent
    if "vector" in obj:
        data["vector"] = obj["vector"]

    response = requests.post(
        f"{WEAVIATE_URL}/v1/objects",
        json=data,
        headers={"Content-Type": "application/json"}
    )

    return response.status_code in [200, 201]


def batch_insert_objects(class_name: str, objects: list[dict], batch_size: int = 100) -> tuple[int, int]:
    """
    Insère des objets par batch.

    Returns:
        (succès, échecs)
    """
    success = 0
    failures = 0

    for i in range(0, len(objects), batch_size):
        batch = objects[i:i + batch_size]

        batch_data = {
            "objects": [
                {
                    "class": class_name,
                    "properties": obj.get("properties", {}),
                    **({"id": obj["id"]} if "id" in obj else {}),
                    **({"vector": obj["vector"]} if "vector" in obj else {}),
                }
                for obj in batch
            ]
        }

        response = requests.post(
            f"{WEAVIATE_URL}/v1/batch/objects",
            json=batch_data,
            headers={"Content-Type": "application/json"}
        )

        if response.status_code == 200:
            result = response.json()
            for item in result:
                if item.get("result", {}).get("status") == "SUCCESS":
                    success += 1
                else:
                    failures += 1
                    error = item.get("result", {}).get("errors", {})
                    if error:
                        print(f"    Erreur: {error}")
        else:
            failures += len(batch)
            print(f"    Erreur batch: {response.status_code}")

        # Progress
        progress = min(i + batch_size, len(objects))
        print(f"  {class_name}: {progress}/{len(objects)} objets traités...", end="\r")

    print(f"  {class_name}: {success} succès, {failures} échecs" + " " * 20)
    return success, failures


def restore_weaviate(
    backup_path: Path,
    collections: list[str] | None = None,
    clear_existing: bool = False,
    dry_run: bool = False
) -> dict:
    """
    Restaure des collections depuis un backup.

    Args:
        backup_path: Chemin du fichier de backup
        collections: Collections à restaurer (None = toutes)
        clear_existing: Supprimer les collections existantes avant restauration
        dry_run: Prévisualiser sans effectuer les actions

    Returns:
        Statistiques de la restauration
    """
    print("=" * 60)
    print("RESTAURATION WEAVIATE")
    if dry_run:
        print("*** MODE DRY-RUN - Aucune modification ***")
    print("=" * 60)
    print(f"URL: {WEAVIATE_URL}")
    print(f"Backup: {backup_path}")
    print(f"Clear existing: {clear_existing}")
    print("-" * 60)

    # Vérifier la connexion
    if not check_weaviate_ready():
        print("ERREUR: Weaviate n'est pas accessible")
        print(f"Vérifiez que le serveur tourne sur {WEAVIATE_URL}")
        sys.exit(1)

    print("Weaviate connecté ✓")

    # Charger le backup
    print(f"\n[1/4] Chargement du backup...")
    with open(backup_path, "r", encoding="utf-8") as f:
        backup_data = json.load(f)

    metadata = backup_data.get("metadata", {})
    print(f"  Timestamp: {metadata.get('timestamp', 'N/A')}")
    print(f"  Source: {metadata.get('weaviate_url', 'N/A')}")
    print(f"  Vectors inclus: {metadata.get('include_vectors', False)}")

    schema = backup_data.get("schema", {})
    backup_collections = backup_data.get("collections", {})

    # Déterminer les collections à restaurer
    if collections:
        classes_to_restore = [c for c in collections if c in backup_collections]
    else:
        classes_to_restore = list(backup_collections.keys())

    print(f"\n  Collections à restaurer: {', '.join(classes_to_restore)}")

    # Vérifier les collections existantes
    print(f"\n[2/4] Vérification des collections existantes...")
    existing_classes = get_existing_classes()
    print(f"  Collections existantes: {', '.join(existing_classes) or '(aucune)'}")

    conflicts = [c for c in classes_to_restore if c in existing_classes]
    if conflicts:
        print(f"  Conflits détectés: {', '.join(conflicts)}")
        if clear_existing:
            print("  → Seront supprimées (--clear-existing)")
        else:
            print("  → Seront ignorées (utilisez --clear-existing pour les remplacer)")
            classes_to_restore = [c for c in classes_to_restore if c not in conflicts]

    if not classes_to_restore:
        print("\nAucune collection à restaurer.")
        return {}

    # Préparer le schéma
    print(f"\n[3/4] Préparation du schéma...")
    schema_classes = {c["class"]: c for c in schema.get("classes", [])}

    # Supprimer les collections existantes si demandé
    if clear_existing and conflicts:
        print("\n  Suppression des collections existantes...")
        for class_name in conflicts:
            if dry_run:
                print(f"    [DRY-RUN] Suppression de {class_name}")
            else:
                if delete_class(class_name):
                    print(f"    Supprimé: {class_name}")
                else:
                    print(f"    ERREUR suppression: {class_name}")

    # Créer les classes
    print("\n  Création des classes...")
    for class_name in classes_to_restore:
        if class_name in schema_classes:
            class_schema = schema_classes[class_name]
            if dry_run:
                print(f"    [DRY-RUN] Création de {class_name}")
            else:
                # Vérifier si existe déjà (après clear)
                current_classes = get_existing_classes()
                if class_name not in current_classes:
                    if create_class(class_schema):
                        print(f"    Créé: {class_name}")
                    else:
                        print(f"    ERREUR création: {class_name}")
                else:
                    print(f"    Existe déjà: {class_name}")
        else:
            print(f"    Schéma manquant pour: {class_name}")

    # Insérer les objets
    print(f"\n[4/4] Insertion des objets...")
    stats = {"success": 0, "failures": 0, "by_class": {}}

    for class_name in classes_to_restore:
        objects = backup_collections.get(class_name, [])
        if not objects:
            print(f"  {class_name}: 0 objets")
            continue

        if dry_run:
            print(f"  [DRY-RUN] {class_name}: {len(objects)} objets à insérer")
            stats["by_class"][class_name] = {"success": len(objects), "failures": 0}
            stats["success"] += len(objects)
        else:
            success, failures = batch_insert_objects(class_name, objects)
            stats["by_class"][class_name] = {"success": success, "failures": failures}
            stats["success"] += success
            stats["failures"] += failures

    # Résumé
    print("\n" + "=" * 60)
    print("RESTAURATION TERMINÉE" + (" (DRY-RUN)" if dry_run else ""))
    print("=" * 60)
    print("\nStatistiques par collection:")
    for class_name, class_stats in stats.get("by_class", {}).items():
        print(f"  - {class_name}: {class_stats['success']} succès, {class_stats['failures']} échecs")

    print(f"\nTotal: {stats['success']} succès, {stats['failures']} échecs")

    return stats


def main():
    global WEAVIATE_URL  # Declare global at start of function

    parser = argparse.ArgumentParser(
        description="Restauration de Weaviate depuis un backup",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  python weaviate_restore.py backup.json
  python weaviate_restore.py backup.json --dry-run
  python weaviate_restore.py backup.json --collections Thought,Conversation
  python weaviate_restore.py backup.json --clear-existing

ATTENTION: --clear-existing supprime les donnees existantes!
        """
    )

    parser.add_argument(
        "backup",
        type=Path,
        help="Chemin du fichier de backup"
    )

    parser.add_argument(
        "--collections", "-c",
        type=str,
        default=None,
        help="Collections à restaurer (séparées par des virgules)"
    )

    parser.add_argument(
        "--clear-existing",
        action="store_true",
        help="Supprimer les collections existantes avant restauration"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Prévisualiser les actions sans les exécuter"
    )

    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help=f"URL Weaviate (défaut: {WEAVIATE_URL})"
    )

    args = parser.parse_args()

    # Vérifier que le fichier existe
    if not args.backup.exists():
        print(f"ERREUR: Fichier non trouvé: {args.backup}")
        sys.exit(1)

    # URL Weaviate
    if args.url:
        WEAVIATE_URL = args.url

    # Collections
    collections = None
    if args.collections:
        collections = [c.strip() for c in args.collections.split(",")]

    # Confirmation si clear_existing et pas dry_run
    if args.clear_existing and not args.dry_run:
        print("⚠️  ATTENTION: --clear-existing va SUPPRIMER des données!")
        print("    Utilisez --dry-run pour prévisualiser.")
        response = input("    Continuer? [y/N] ")
        if response.lower() != "y":
            print("Annulé.")
            sys.exit(0)

    # Exécuter la restauration
    restore_weaviate(
        backup_path=args.backup,
        collections=collections,
        clear_existing=args.clear_existing,
        dry_run=args.dry_run
    )


if __name__ == "__main__":
    main()
