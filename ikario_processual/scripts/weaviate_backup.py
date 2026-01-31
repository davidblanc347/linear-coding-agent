#!/usr/bin/env python3
"""
Backup complet de toutes les collections Weaviate.

Usage:
    python weaviate_backup.py
    python weaviate_backup.py --output exports/backup_20260131.json
    python weaviate_backup.py --collections Thought,Conversation

Ce script exporte:
- Le schéma complet (classes et propriétés)
- Tous les objets de chaque collection
- Les vecteurs (embeddings) de chaque objet
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
DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent.parent / "exports"


def check_weaviate_ready() -> bool:
    """Vérifie que Weaviate est accessible."""
    try:
        response = requests.get(f"{WEAVIATE_URL}/v1/.well-known/ready", timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False


def get_schema() -> dict:
    """Récupère le schéma complet de Weaviate."""
    response = requests.get(f"{WEAVIATE_URL}/v1/schema")
    response.raise_for_status()
    return response.json()


def get_all_objects(class_name: str, include_vector: bool = True) -> list[dict]:
    """
    Récupère tous les objets d'une classe avec pagination.

    Args:
        class_name: Nom de la collection
        include_vector: Inclure les vecteurs (embeddings)

    Returns:
        Liste de tous les objets
    """
    objects = []
    limit = 100
    offset = 0

    include_param = "vector" if include_vector else ""

    while True:
        url = f"{WEAVIATE_URL}/v1/objects?class={class_name}&limit={limit}&offset={offset}"
        if include_param:
            url += f"&include={include_param}"

        response = requests.get(url)

        if response.status_code != 200:
            print(f"  Erreur lors de la récupération de {class_name}: {response.status_code}")
            break

        data = response.json()
        batch = data.get("objects", [])

        if not batch:
            break

        objects.extend(batch)
        offset += limit

        # Progress
        print(f"  {class_name}: {len(objects)} objets récupérés...", end="\r")

    print(f"  {class_name}: {len(objects)} objets au total")
    return objects


def backup_weaviate(
    output_path: Path,
    collections: list[str] | None = None,
    include_vectors: bool = True
) -> dict:
    """
    Effectue un backup complet de Weaviate.

    Args:
        output_path: Chemin du fichier de sortie
        collections: Liste des collections à exporter (None = toutes)
        include_vectors: Inclure les vecteurs

    Returns:
        Statistiques du backup
    """
    print("=" * 60)
    print("BACKUP WEAVIATE")
    print("=" * 60)
    print(f"URL: {WEAVIATE_URL}")
    print(f"Output: {output_path}")
    print(f"Include vectors: {include_vectors}")
    print("-" * 60)

    # Vérifier la connexion
    if not check_weaviate_ready():
        print("ERREUR: Weaviate n'est pas accessible")
        print(f"Vérifiez que le serveur tourne sur {WEAVIATE_URL}")
        sys.exit(1)

    print("Weaviate connecte [OK]")

    # Récupérer le schéma
    print("\n[1/3] Récupération du schéma...")
    schema = get_schema()
    all_classes = [c["class"] for c in schema.get("classes", [])]
    print(f"  Classes trouvées: {', '.join(all_classes)}")

    # Filtrer les collections si spécifié
    if collections:
        classes_to_backup = [c for c in all_classes if c in collections]
        print(f"  Collections sélectionnées: {', '.join(classes_to_backup)}")
    else:
        classes_to_backup = all_classes

    # Récupérer les objets de chaque classe
    print("\n[2/3] Récupération des objets...")
    backup_data = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "weaviate_url": WEAVIATE_URL,
            "include_vectors": include_vectors,
            "version": "1.0"
        },
        "schema": schema,
        "collections": {}
    }

    stats = {}
    for class_name in classes_to_backup:
        objects = get_all_objects(class_name, include_vector=include_vectors)
        backup_data["collections"][class_name] = objects
        stats[class_name] = len(objects)

    # Sauvegarder
    print(f"\n[3/3] Sauvegarde dans {output_path}...")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(backup_data, f, indent=2, ensure_ascii=False)

    file_size = output_path.stat().st_size / (1024 * 1024)  # MB

    # Résumé
    print("\n" + "=" * 60)
    print("BACKUP TERMINÉ")
    print("=" * 60)
    print(f"Fichier: {output_path}")
    print(f"Taille: {file_size:.2f} MB")
    print("\nStatistiques par collection:")
    total = 0
    for class_name, count in stats.items():
        print(f"  - {class_name}: {count} objets")
        total += count
    print(f"\nTotal: {total} objets")

    return stats


def main():
    global WEAVIATE_URL  # Declare global at start of function

    parser = argparse.ArgumentParser(
        description="Backup complet de Weaviate",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  python weaviate_backup.py
  python weaviate_backup.py --output backup.json
  python weaviate_backup.py --collections Thought,Conversation
  python weaviate_backup.py --no-vectors
        """
    )

    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Chemin du fichier de sortie (defaut: exports/backup_YYYYMMDD_HHMMSS.json)"
    )

    parser.add_argument(
        "--collections", "-c",
        type=str,
        default=None,
        help="Collections a exporter (separees par des virgules)"
    )

    parser.add_argument(
        "--no-vectors",
        action="store_true",
        help="Ne pas inclure les vecteurs (plus rapide, fichier plus petit)"
    )

    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help=f"URL Weaviate (defaut: {WEAVIATE_URL})"
    )

    args = parser.parse_args()

    # URL Weaviate
    if args.url:
        WEAVIATE_URL = args.url

    # Chemin de sortie
    if args.output:
        output_path = args.output
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = DEFAULT_OUTPUT_DIR / f"backup_{timestamp}.json"

    # Collections
    collections = None
    if args.collections:
        collections = [c.strip() for c in args.collections.split(",")]

    # Exécuter le backup
    backup_weaviate(
        output_path=output_path,
        collections=collections,
        include_vectors=not args.no_vectors
    )


if __name__ == "__main__":
    main()
