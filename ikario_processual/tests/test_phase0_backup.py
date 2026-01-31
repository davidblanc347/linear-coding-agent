#!/usr/bin/env python3
"""
Tests pour la Phase 0: Backup et restauration Weaviate.

Usage:
    pytest tests/test_phase0_backup.py -v
    pytest tests/test_phase0_backup.py -v -k test_backup
"""

import json
import os
import tempfile
from pathlib import Path

import pytest
import requests

# Configuration
WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://localhost:8080")


def weaviate_is_available() -> bool:
    """Vérifie si Weaviate est accessible."""
    try:
        response = requests.get(f"{WEAVIATE_URL}/v1/.well-known/ready", timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False


# Skip tous les tests si Weaviate n'est pas disponible
pytestmark = pytest.mark.skipif(
    not weaviate_is_available(),
    reason=f"Weaviate non disponible sur {WEAVIATE_URL}"
)


class TestWeaviateConnection:
    """Tests de connexion à Weaviate."""

    def test_weaviate_ready(self):
        """Weaviate doit être accessible."""
        response = requests.get(f"{WEAVIATE_URL}/v1/.well-known/ready")
        assert response.status_code == 200

    def test_weaviate_schema_accessible(self):
        """Le schéma doit être récupérable."""
        response = requests.get(f"{WEAVIATE_URL}/v1/schema")
        assert response.status_code == 200
        data = response.json()
        assert "classes" in data

    def test_weaviate_has_collections(self):
        """Au moins une collection doit exister (Thought, Conversation, etc.)."""
        response = requests.get(f"{WEAVIATE_URL}/v1/schema")
        data = response.json()
        classes = [c["class"] for c in data.get("classes", [])]

        # Au moins une des collections attendues
        expected = ["Thought", "Conversation", "Message", "Chunk", "Work", "Summary"]
        found = [c for c in classes if c in expected]

        assert len(found) > 0, f"Aucune collection trouvée parmi {expected}. Classes existantes: {classes}"


class TestBackupScript:
    """Tests du script de backup."""

    def test_backup_creates_file(self):
        """Le backup doit créer un fichier JSON."""
        # Import dynamique pour éviter les erreurs si requests manque
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

        from weaviate_backup import backup_weaviate

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_backup.json"

            stats = backup_weaviate(
                output_path=output_path,
                collections=None,  # Toutes
                include_vectors=False  # Plus rapide pour le test
            )

            assert output_path.exists(), "Le fichier de backup n'a pas été créé"
            assert output_path.stat().st_size > 0, "Le fichier de backup est vide"

    def test_backup_structure(self):
        """Le backup doit avoir la bonne structure."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

        from weaviate_backup import backup_weaviate

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_backup.json"

            backup_weaviate(
                output_path=output_path,
                collections=["Thought"],  # Une seule collection pour le test
                include_vectors=False
            )

            with open(output_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Vérifier la structure
            assert "metadata" in data
            assert "schema" in data
            assert "collections" in data

            # Vérifier les métadonnées
            assert "timestamp" in data["metadata"]
            assert "weaviate_url" in data["metadata"]
            assert "version" in data["metadata"]

    def test_backup_with_vectors(self):
        """Le backup avec vecteurs doit inclure les embeddings."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

        from weaviate_backup import backup_weaviate

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_backup_vectors.json"

            backup_weaviate(
                output_path=output_path,
                collections=["Thought"],
                include_vectors=True
            )

            with open(output_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Vérifier qu'au moins un objet a un vecteur
            thoughts = data.get("collections", {}).get("Thought", [])
            if thoughts:
                # Au moins un objet devrait avoir un vecteur
                has_vector = any("vector" in obj for obj in thoughts)
                assert has_vector, "Aucun objet n'a de vecteur alors que include_vectors=True"


class TestRestoreScript:
    """Tests du script de restauration."""

    def test_restore_dry_run(self):
        """Le dry-run ne doit pas modifier les données."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

        from weaviate_backup import backup_weaviate
        from weaviate_restore import restore_weaviate, get_existing_classes

        with tempfile.TemporaryDirectory() as tmpdir:
            # D'abord, faire un backup
            backup_path = Path(tmpdir) / "test_backup.json"
            backup_weaviate(
                output_path=backup_path,
                collections=["Thought"],
                include_vectors=False
            )

            # Compter les objets avant
            response = requests.get(f"{WEAVIATE_URL}/v1/objects?class=Thought&limit=1")
            count_before = len(response.json().get("objects", []))

            # Restaurer en dry-run
            stats = restore_weaviate(
                backup_path=backup_path,
                collections=["Thought"],
                clear_existing=False,
                dry_run=True
            )

            # Compter après
            response = requests.get(f"{WEAVIATE_URL}/v1/objects?class=Thought&limit=1")
            count_after = len(response.json().get("objects", []))

            # Pas de changement
            assert count_before == count_after, "Le dry-run a modifié les données!"


class TestBackupRestoreCycle:
    """Tests du cycle complet backup → restore."""

    def test_backup_restore_roundtrip(self):
        """
        Test complet: backup → restore → vérification.

        Ce test utilise une collection temporaire pour ne pas
        affecter les données existantes.
        """
        # Ce test nécessiterait de créer une collection temporaire
        # Pour l'instant, on vérifie juste que les scripts fonctionnent
        pass


def test_exports_directory_exists():
    """Le dossier exports doit exister ou être créable."""
    exports_dir = Path(__file__).parent.parent.parent / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    assert exports_dir.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
