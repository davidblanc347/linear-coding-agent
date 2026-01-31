#!/usr/bin/env python3
"""
Script de vérification de la Phase 0.

Vérifie que tous les prérequis sont en place:
1. Weaviate est accessible
2. Les collections existent
3. Le backup fonctionne
4. La restauration (dry-run) fonctionne

Usage:
    python verify_phase0.py
"""

import os
import sys
import tempfile
from pathlib import Path

import requests

# Configuration
WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://localhost:8080")

# Couleurs pour l'output (désactivées sur Windows si problème encodage)
import platform
if platform.system() == "Windows":
    GREEN = ""
    RED = ""
    YELLOW = ""
    RESET = ""
    CHECK = "[OK]"
    CROSS = "[FAIL]"
    WARN = "[WARN]"
else:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    RESET = "\033[0m"
    CHECK = "\u2713"
    CROSS = "\u2717"
    WARN = "\u26A0"


def print_ok(msg: str):
    print(f"  {GREEN}{CHECK}{RESET} {msg}")


def print_fail(msg: str):
    print(f"  {RED}{CROSS}{RESET} {msg}")


def print_warn(msg: str):
    print(f"  {YELLOW}{WARN}{RESET} {msg}")


def check_weaviate_connection() -> bool:
    """Vérifie la connexion à Weaviate."""
    print("\n[1/5] Connexion Weaviate...")
    try:
        response = requests.get(f"{WEAVIATE_URL}/v1/.well-known/ready", timeout=5)
        if response.status_code == 200:
            print_ok(f"Weaviate accessible sur {WEAVIATE_URL}")
            return True
        else:
            print_fail(f"Weaviate répond avec status {response.status_code}")
            return False
    except requests.RequestException as e:
        print_fail(f"Impossible de se connecter à Weaviate: {e}")
        return False


def check_collections() -> tuple[bool, list[str]]:
    """Vérifie les collections existantes."""
    print("\n[2/5] Collections Weaviate...")
    try:
        response = requests.get(f"{WEAVIATE_URL}/v1/schema")
        schema = response.json()
        classes = [c["class"] for c in schema.get("classes", [])]

        expected = ["Thought", "Conversation", "Message", "Chunk", "Work", "Summary"]
        found = [c for c in classes if c in expected]
        missing = [c for c in expected if c not in classes]

        if found:
            print_ok(f"Collections trouvées: {', '.join(found)}")
        if missing:
            print_warn(f"Collections manquantes: {', '.join(missing)}")

        # Compter les objets
        for class_name in found:
            response = requests.get(f"{WEAVIATE_URL}/v1/objects?class={class_name}&limit=1")
            # Note: Pour avoir le count exact, il faudrait utiliser l'API aggregate
            objects = response.json().get("objects", [])
            if objects:
                print_ok(f"  {class_name}: contient des objets")
            else:
                print_warn(f"  {class_name}: vide")

        return len(found) > 0, found

    except Exception as e:
        print_fail(f"Erreur lors de la vérification du schéma: {e}")
        return False, []


def check_backup_script() -> bool:
    """Vérifie que le script de backup fonctionne."""
    print("\n[3/5] Script de backup...")

    scripts_dir = Path(__file__).parent
    backup_script = scripts_dir / "weaviate_backup.py"

    if not backup_script.exists():
        print_fail(f"Script non trouvé: {backup_script}")
        return False

    print_ok("Script weaviate_backup.py présent")

    # Tester l'import
    try:
        sys.path.insert(0, str(scripts_dir))
        from weaviate_backup import backup_weaviate, check_weaviate_ready

        if check_weaviate_ready():
            print_ok("Fonction check_weaviate_ready() fonctionne")
        else:
            print_fail("check_weaviate_ready() retourne False")
            return False

    except ImportError as e:
        print_fail(f"Erreur d'import: {e}")
        return False

    # Tester un backup rapide
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_backup.json"

            backup_weaviate(
                output_path=output_path,
                collections=["Thought"],
                include_vectors=False
            )

            if output_path.exists() and output_path.stat().st_size > 0:
                print_ok(f"Backup de test créé ({output_path.stat().st_size} bytes)")
                return True
            else:
                print_fail("Backup de test vide ou non créé")
                return False

    except Exception as e:
        print_fail(f"Erreur lors du backup de test: {e}")
        return False


def check_restore_script() -> bool:
    """Vérifie que le script de restauration fonctionne."""
    print("\n[4/5] Script de restauration...")

    scripts_dir = Path(__file__).parent
    restore_script = scripts_dir / "weaviate_restore.py"

    if not restore_script.exists():
        print_fail(f"Script non trouvé: {restore_script}")
        return False

    print_ok("Script weaviate_restore.py présent")

    # Tester l'import
    try:
        sys.path.insert(0, str(scripts_dir))
        from weaviate_restore import restore_weaviate, get_existing_classes

        classes = get_existing_classes()
        print_ok(f"Fonction get_existing_classes() retourne {len(classes)} classes")
        return True

    except ImportError as e:
        print_fail(f"Erreur d'import: {e}")
        return False


def check_directory_structure() -> bool:
    """Vérifie la structure des dossiers."""
    print("\n[5/5] Structure des dossiers...")

    base_dir = Path(__file__).parent.parent
    required_dirs = [
        base_dir,
        base_dir / "scripts",
        base_dir / "tests",
    ]

    optional_dirs = [
        base_dir.parent / "exports",
    ]

    all_ok = True

    for d in required_dirs:
        if d.exists():
            print_ok(f"Dossier: {d.relative_to(base_dir.parent)}")
        else:
            print_fail(f"Dossier manquant: {d.relative_to(base_dir.parent)}")
            all_ok = False

    for d in optional_dirs:
        if d.exists():
            print_ok(f"Dossier: {d.relative_to(base_dir.parent)}")
        else:
            print_warn(f"Dossier optionnel absent: {d.relative_to(base_dir.parent)}")
            # Créer le dossier
            d.mkdir(parents=True, exist_ok=True)
            print_ok(f"  → Créé: {d.relative_to(base_dir.parent)}")

    return all_ok


def main():
    print("=" * 60)
    print("VÉRIFICATION PHASE 0 - Préparation et Backup")
    print("=" * 60)

    results = {}

    # 1. Connexion Weaviate
    results["weaviate"] = check_weaviate_connection()

    if not results["weaviate"]:
        print("\n" + "=" * 60)
        print(f"{RED}ÉCHEC{RESET}: Weaviate n'est pas accessible.")
        print("Assurez-vous que Weaviate tourne:")
        print("  docker start weaviate")
        print("  # ou")
        print("  docker run -d --name weaviate -p 8080:8080 ...")
        print("=" * 60)
        sys.exit(1)

    # 2. Collections
    results["collections"], found_collections = check_collections()

    # 3. Script backup
    results["backup"] = check_backup_script()

    # 4. Script restore
    results["restore"] = check_restore_script()

    # 5. Structure dossiers
    results["structure"] = check_directory_structure()

    # Résumé
    print("\n" + "=" * 60)
    print("RÉSUMÉ PHASE 0")
    print("=" * 60)

    all_passed = all(results.values())

    for check, passed in results.items():
        status = f"{GREEN}OK{RESET}" if passed else f"{RED}ÉCHEC{RESET}"
        print(f"  {check}: {status}")

    print()

    if all_passed:
        print(f"{GREEN}{CHECK} PHASE 0 VALIDEE{RESET}")
        print("\nProchaines etapes:")
        print("  1. Creer un backup complet:")
        print("     python scripts/weaviate_backup.py --output exports/backup_phase0.json")
        print("  2. Creer la branche git:")
        print("     git checkout -b feature/processual-v3")
        print("  3. Passer a la Phase 1:")
        print("     python scripts/phase1_state_vector.py")
    else:
        print(f"{RED}{CROSS} PHASE 0 INCOMPLETE{RESET}")
        print("\nCorrigez les erreurs ci-dessus avant de continuer.")

    print("=" * 60)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
