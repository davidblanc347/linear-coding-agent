#!/usr/bin/env python3
"""
Phase 2 : Creation des directions de projection.

Ce script:
1. Cree la collection ProjectionDirection dans Weaviate
2. Genere les vecteurs de direction par contraste (BGE-M3)
3. Sauvegarde les directions dans Weaviate
4. Calcule et affiche le profil de S(0)

Usage:
    python phase2_projection_directions.py
    python phase2_projection_directions.py --dry-run
    python phase2_projection_directions.py --reset
"""

import argparse
import sys
from pathlib import Path

import numpy as np

# Ajouter le parent au path
sys.path.insert(0, str(Path(__file__).parent.parent))

from state_vector import (
    check_weaviate_ready,
    get_state_vector,
)
from projection_directions import (
    get_existing_classes,
    create_projection_direction_collection,
    delete_projection_direction_collection,
    create_direction_by_contrast,
    save_direction,
    get_all_directions,
    get_state_profile,
    format_profile,
    DIRECTIONS_CONFIG,
)


def print_section(title: str):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Phase 2: Creation des directions de projection"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simuler sans creer"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Supprimer et recreer la collection"
    )

    args = parser.parse_args()

    print_section("PHASE 2 : DIRECTIONS DE PROJECTION")

    # 1. Verifier Weaviate
    print("\n[1/5] Verification Weaviate...")
    if not check_weaviate_ready():
        print("ERREUR: Weaviate non accessible")
        sys.exit(1)
    print("  Weaviate [OK]")

    # 2. Gerer la collection ProjectionDirection
    print("\n[2/5] Collection ProjectionDirection...")
    existing = get_existing_classes()

    if "ProjectionDirection" in existing:
        if args.reset:
            print("  Suppression de la collection existante...")
            if not args.dry_run:
                delete_projection_direction_collection()
                print("  Collection supprimee")
            else:
                print("  [DRY-RUN] Suppression simulee")
        else:
            # Verifier combien de directions existent
            directions = get_all_directions()
            if len(directions) > 0:
                print(f"  Collection existe avec {len(directions)} directions")
                print("  Utilisez --reset pour reinitialiser")

                # Afficher le profil de S(0) quand meme
                print("\n[INFO] Affichage du profil S(0) existant...")
                s0 = get_state_vector(0)
                if s0:
                    state_vec = np.array(s0.get("_additional", {}).get("vector", []))
                    if len(state_vec) > 0:
                        profile = get_state_profile(state_vec)
                        print(format_profile(profile))
                sys.exit(0)

    # Creer la collection
    if args.dry_run:
        print("  [DRY-RUN] Creation collection simulee")
    else:
        if "ProjectionDirection" not in get_existing_classes():
            create_projection_direction_collection()

    # 3. Charger le modele
    print("\n[3/5] Chargement du modele BGE-M3...")
    if args.dry_run:
        print("  [DRY-RUN] Chargement simule")
        model = None
    else:
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer('BAAI/bge-m3')
            print("  Modele charge [OK]")
        except ImportError:
            print("ERREUR: sentence-transformers non installe")
            print("  pip install sentence-transformers")
            sys.exit(1)

    # 4. Creer les directions
    print("\n[4/5] Creation des directions par contraste...")
    print(f"  {len(DIRECTIONS_CONFIG)} directions a creer")
    print()

    created_count = 0
    for name, config in DIRECTIONS_CONFIG.items():
        category = config["category"]
        positive = config["positive_examples"]
        negative = config["negative_examples"]

        if args.dry_run:
            print(f"  [DRY-RUN] {name} ({category})")
            print(f"            + {len(positive)} exemples positifs")
            print(f"            - {len(negative)} exemples negatifs")
            created_count += 1
        else:
            # Calculer la direction
            direction_vec = create_direction_by_contrast(positive, negative, model)

            # Sauvegarder
            obj_id = save_direction(name, config, direction_vec)

            if obj_id:
                print(f"  [OK] {name} ({category})")
                created_count += 1
            else:
                print(f"  [FAIL] {name}")

    print(f"\n  Total: {created_count}/{len(DIRECTIONS_CONFIG)} directions creees")

    # 5. Calculer le profil de S(0)
    print("\n[5/5] Calcul du profil de S(0)...")

    if args.dry_run:
        print("  [DRY-RUN] Profil simule")
    else:
        # Recuperer S(0)
        s0 = get_state_vector(0)
        if not s0:
            print("  ERREUR: S(0) non trouve. Executez d'abord phase1_state_vector.py")
            sys.exit(1)

        state_vec = np.array(s0.get("_additional", {}).get("vector", []))
        if len(state_vec) == 0:
            print("  ERREUR: S(0) n'a pas de vecteur")
            sys.exit(1)

        # Calculer le profil
        profile = get_state_profile(state_vec)

        print("\n  PROFIL DE S(0) - Etat initial d'Ikario")
        print("  " + "-" * 50)
        print(format_profile(profile))

    # Resume
    print_section("PHASE 2 TERMINEE")

    if args.dry_run:
        print("\n[DRY-RUN] Aucune modification effectuee")
    else:
        print("\nResultat:")
        print(f"  - Collection ProjectionDirection creee")
        print(f"  - {created_count} directions creees:")

        # Grouper par categorie
        by_category = {}
        for name, config in DIRECTIONS_CONFIG.items():
            cat = config["category"]
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(name)

        for cat, names in sorted(by_category.items()):
            print(f"      {cat}: {', '.join(names)}")

    print("\nTests de validation:")
    print("  curl -s 'http://localhost:8080/v1/objects?class=ProjectionDirection' | jq '.objects | length'")
    print("  python -c \"from projection_directions import *; print(get_all_directions())\"")

    print("\nProchaine etape:")
    print("  python scripts/phase3_transformation.py")


if __name__ == "__main__":
    main()
