#!/usr/bin/env python3
"""
Script pour creer toutes les directions de projection dans Weaviate.

Usage:
    python scripts/create_all_directions.py [--reset]

Options:
    --reset  Supprimer et recreer la collection (attention: perte de donnees!)
"""

import sys
import time
from pathlib import Path

# Ajouter le parent au path
sys.path.insert(0, str(Path(__file__).parent.parent))

from projection_directions import (
    DIRECTIONS_CONFIG,
    create_projection_direction_collection,
    delete_projection_direction_collection,
    create_direction_by_contrast,
    save_direction,
    get_all_directions,
    get_existing_classes,
)


def main():
    reset = "--reset" in sys.argv

    print("=" * 70)
    print("CREATION DES DIRECTIONS DE PROJECTION")
    print("=" * 70)
    print(f"Total directions configurees: {len(DIRECTIONS_CONFIG)}")
    print()

    # Verifier Weaviate
    try:
        classes = get_existing_classes()
        print(f"[OK] Weaviate accessible, {len(classes)} classes existantes")
    except Exception as e:
        print(f"[ERREUR] Weaviate non accessible: {e}")
        print("Assurez-vous que Weaviate est en cours d'execution sur localhost:8080")
        return 1

    # Reset si demande
    if reset:
        print("\n[RESET] Suppression de la collection ProjectionDirection...")
        if delete_projection_direction_collection():
            print("[OK] Collection supprimee")
        else:
            print("[INFO] Collection n'existait pas")

    # Creer la collection si necessaire
    print("\n[INFO] Creation de la collection ProjectionDirection...")
    if create_projection_direction_collection():
        print("[OK] Collection creee")
    else:
        print("[INFO] Collection existe deja")

    # Charger le modele d'embedding
    print("\n[INFO] Chargement du modele BGE-M3...")
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer('BAAI/bge-m3')
        print("[OK] Modele charge")
    except Exception as e:
        print(f"[ERREUR] Impossible de charger le modele: {e}")
        return 1

    # Verifier les directions existantes
    existing_directions = get_all_directions()
    existing_names = {d["name"] for d in existing_directions}
    print(f"\n[INFO] {len(existing_names)} directions existantes")

    # Compter les categories
    categories = {}
    for name, config in DIRECTIONS_CONFIG.items():
        cat = config["category"]
        categories[cat] = categories.get(cat, 0) + 1

    print("\nDirections par categorie:")
    for cat, count in sorted(categories.items()):
        print(f"  - {cat}: {count}")

    # Creer les directions manquantes
    new_directions = [name for name in DIRECTIONS_CONFIG if name not in existing_names]
    print(f"\n[INFO] {len(new_directions)} nouvelles directions a creer")

    if not new_directions:
        print("[OK] Toutes les directions existent deja!")
        return 0

    # Creation
    print("\n" + "-" * 70)
    print("CREATION DES DIRECTIONS")
    print("-" * 70)

    created = 0
    errors = 0
    start_time = time.time()

    for i, name in enumerate(new_directions, 1):
        config = DIRECTIONS_CONFIG[name]

        print(f"\n[{i}/{len(new_directions)}] {name} ({config['category']})")

        try:
            # Creer le vecteur direction par contraste
            direction_vector = create_direction_by_contrast(
                config["positive_examples"],
                config["negative_examples"],
                model
            )

            # Sauvegarder dans Weaviate
            obj_id = save_direction(name, config, direction_vector)

            if obj_id:
                print(f"  [OK] Cree: {obj_id[:8]}...")
                created += 1
            else:
                print(f"  [ERREUR] Echec de sauvegarde")
                errors += 1

        except Exception as e:
            print(f"  [ERREUR] {e}")
            errors += 1

    elapsed = time.time() - start_time

    # Resume
    print("\n" + "=" * 70)
    print("RESUME")
    print("=" * 70)
    print(f"Directions creees: {created}")
    print(f"Erreurs: {errors}")
    print(f"Temps: {elapsed:.1f}s ({elapsed/max(1,created):.1f}s par direction)")

    # Verification finale
    final_directions = get_all_directions()
    print(f"\nTotal directions dans Weaviate: {len(final_directions)}")

    # Afficher par categorie
    final_categories = {}
    for d in final_directions:
        cat = d.get("category", "unknown")
        final_categories[cat] = final_categories.get(cat, 0) + 1

    print("\nDirections par categorie (final):")
    for cat, count in sorted(final_categories.items()):
        print(f"  - {cat}: {count}")

    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
