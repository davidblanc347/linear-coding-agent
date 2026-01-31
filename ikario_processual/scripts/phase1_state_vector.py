#!/usr/bin/env python3
"""
Phase 1 : Creation de la collection StateVector et de S(0).

Ce script:
1. Cree la collection StateVector dans Weaviate
2. Recupere et filtre les pensees (exclut les tests)
3. Recupere et filtre les messages d'Ikario (assistant uniquement)
4. Calcule l'embedding agrege avec BGE-M3
5. Cree l'etat initial S(0)

Usage:
    python phase1_state_vector.py
    python phase1_state_vector.py --dry-run
    python phase1_state_vector.py --reset  # Supprime et recree
"""

import argparse
import sys
from pathlib import Path

# Ajouter le parent au path
sys.path.insert(0, str(Path(__file__).parent.parent))

from state_vector import (
    check_weaviate_ready,
    get_existing_classes,
    create_state_vector_collection,
    delete_state_vector_collection,
    get_all_thoughts,
    get_all_messages,
    filter_thoughts,
    filter_assistant_messages,
    compute_aggregate_embedding,
    create_initial_state,
    get_current_state_id,
    get_state_vector,
)


def print_section(title: str):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Phase 1: Creation StateVector et S(0)"
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

    print_section("PHASE 1 : STATEVECTOR ET S(0)")

    # 1. Verifier Weaviate
    print("\n[1/6] Verification Weaviate...")
    if not check_weaviate_ready():
        print("ERREUR: Weaviate non accessible")
        sys.exit(1)
    print("  Weaviate [OK]")

    # 2. Gerer la collection StateVector
    print("\n[2/6] Collection StateVector...")
    existing = get_existing_classes()

    if "StateVector" in existing:
        if args.reset:
            print("  Suppression de la collection existante...")
            if not args.dry_run:
                delete_state_vector_collection()
                print("  Collection supprimee")
            else:
                print("  [DRY-RUN] Suppression simulee")
        else:
            # Verifier si S(0) existe deja
            current_id = get_current_state_id()
            if current_id >= 0:
                print(f"  Collection existe avec {current_id + 1} etat(s)")
                print("  Utilisez --reset pour reinitialiser")
                sys.exit(0)

    # Creer la collection
    if args.dry_run:
        print("  [DRY-RUN] Creation collection simulee")
    else:
        if "StateVector" not in get_existing_classes():
            create_state_vector_collection()

    # 3. Recuperer et filtrer les pensees
    print("\n[3/6] Recuperation des pensees...")
    all_thoughts = get_all_thoughts()
    print(f"  Total pensees: {len(all_thoughts)}")

    filtered_thoughts = filter_thoughts(all_thoughts)
    excluded = len(all_thoughts) - len(filtered_thoughts)
    print(f"  Pensees filtrees: {len(filtered_thoughts)} (exclues: {excluded})")

    # Afficher quelques exemples de pensees gardees
    if filtered_thoughts:
        print("\n  Exemples de pensees gardees:")
        for t in filtered_thoughts[:3]:
            content = t.get("properties", {}).get("content", "")[:80]
            print(f"    - {content}...")

    # 4. Recuperer et filtrer les messages
    print("\n[4/6] Recuperation des messages...")
    all_messages = get_all_messages()
    print(f"  Total messages: {len(all_messages)}")

    filtered_messages = filter_assistant_messages(all_messages)
    excluded = len(all_messages) - len(filtered_messages)
    print(f"  Messages Ikario: {len(filtered_messages)} (exclues: {excluded})")

    # Afficher quelques exemples
    if filtered_messages:
        print("\n  Exemples de messages Ikario:")
        for m in filtered_messages[:3]:
            content = m.get("properties", {}).get("content", "")[:80]
            print(f"    - {content}...")

    # 5. Calculer l'embedding agrege
    print("\n[5/6] Calcul de l'embedding agrege...")

    if args.dry_run:
        print("  [DRY-RUN] Embedding simule (1024 dims)")
        embedding = None
    else:
        # Charger le modele BGE-M3
        print("  Chargement du modele BGE-M3...")
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer('BAAI/bge-m3')
            print("  Modele charge [OK]")
        except ImportError:
            print("ERREUR: sentence-transformers non installe")
            print("  pip install sentence-transformers")
            sys.exit(1)

        # Calculer l'embedding
        print("  Calcul de l'embedding agrege...")
        embedding = compute_aggregate_embedding(
            filtered_thoughts,
            filtered_messages,
            model
        )
        print(f"  Embedding calcule: {embedding.shape} (norme: {embedding.sum():.4f})")

    # 6. Creer S(0)
    print("\n[6/6] Creation de S(0)...")

    if args.dry_run:
        print("  [DRY-RUN] S(0) simule")
        print(f"    - {len(filtered_thoughts)} pensees")
        print(f"    - {len(filtered_messages)} messages")
    else:
        s0 = create_initial_state(
            filtered_thoughts,
            filtered_messages,
            embedding
        )
        print(f"  S(0) cree avec succes!")
        print(f"    - ID: {s0.get('id', 'N/A')}")
        print(f"    - Pensees sources: {s0['source_thoughts_count']}")
        print(f"    - Messages sources: {s0['source_messages_count']}")

    # Resume
    print_section("PHASE 1 TERMINEE")

    if args.dry_run:
        print("\n[DRY-RUN] Aucune modification effectuee")
    else:
        print("\nResultat:")
        print(f"  - Collection StateVector creee")
        print(f"  - S(0) cree a partir de:")
        print(f"      {len(filtered_thoughts)} pensees")
        print(f"      {len(filtered_messages)} messages")

    print("\nTests de validation:")
    print("  curl -s http://localhost:8080/v1/schema | jq '.classes[] | select(.class == \"StateVector\")'")
    print("  curl -s 'http://localhost:8080/v1/objects?class=StateVector&limit=1' | jq '.objects[0].properties'")

    print("\nProchaine etape:")
    print("  python scripts/phase2_projection_directions.py")


if __name__ == "__main__":
    main()
