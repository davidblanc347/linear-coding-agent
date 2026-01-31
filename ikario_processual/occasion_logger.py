#!/usr/bin/env python3
"""
OccasionLogger - Logging des occasions d'expérience.

Chaque occasion est loggée avec:
- Trigger (type, contenu)
- Préhension (pensées/docs récupérés)
- Concrescence (réponse, outils utilisés)
- Satisfaction (nouvel état, paramètres)
- Profils avant/après

Les logs sont stockés en JSON pour analyse et debugging.
"""

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any


@dataclass
class OccasionLog:
    """Structure de log pour une occasion."""

    # Identifiants
    occasion_id: int
    timestamp: str

    # Trigger
    trigger_type: str  # "user", "timer", "event"
    trigger_content: str

    # Préhension
    previous_state_id: int
    prehended_thoughts_count: int
    prehended_docs_count: int
    prehended_thoughts: List[str] = field(default_factory=list)  # Résumés des pensées

    # Concrescence
    response_summary: str
    new_thoughts: List[str] = field(default_factory=list)
    tools_used: List[str] = field(default_factory=list)

    # Satisfaction
    new_state_id: int
    alpha_used: float
    beta_used: float

    # Profils
    profile_before: Dict[str, Dict[str, float]] = field(default_factory=dict)
    profile_after: Dict[str, Dict[str, float]] = field(default_factory=dict)

    # Métriques
    processing_time_ms: int = 0
    token_count: Optional[int] = None


class OccasionLogger:
    """Gère le logging des occasions en fichiers JSON."""

    def __init__(self, log_dir: str = "logs/occasions"):
        """
        Args:
            log_dir: Répertoire de stockage des logs
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def log(self, occasion: OccasionLog) -> Path:
        """
        Enregistre une occasion.

        Args:
            occasion: OccasionLog à enregistrer

        Returns:
            Chemin du fichier créé
        """
        filename = f"occasion_{occasion.occasion_id:06d}.json"
        filepath = self.log_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(asdict(occasion), f, indent=2, ensure_ascii=False)

        print(f"[OccasionLogger] Occasion {occasion.occasion_id} → {filepath}")
        return filepath

    def get_occasion(self, occasion_id: int) -> Optional[OccasionLog]:
        """
        Récupère une occasion par son ID.

        Args:
            occasion_id: ID de l'occasion

        Returns:
            OccasionLog ou None si non trouvé
        """
        filename = f"occasion_{occasion_id:06d}.json"
        filepath = self.log_dir / filename

        if not filepath.exists():
            return None

        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        return OccasionLog(**data)

    def get_recent_occasions(self, limit: int = 10) -> List[OccasionLog]:
        """
        Récupère les N dernières occasions.

        Args:
            limit: Nombre max d'occasions à retourner

        Returns:
            Liste des occasions (plus récentes d'abord)
        """
        files = sorted(self.log_dir.glob("occasion_*.json"), reverse=True)

        occasions = []
        for f in files[:limit]:
            with open(f, 'r', encoding='utf-8') as fp:
                data = json.load(fp)
            occasions.append(OccasionLog(**data))

        return occasions

    def get_last_occasion_id(self) -> int:
        """Retourne l'ID de la dernière occasion (-1 si aucune)."""
        files = sorted(self.log_dir.glob("occasion_*.json"), reverse=True)
        if not files:
            return -1

        # Extraire l'ID du nom de fichier
        filename = files[0].stem  # occasion_000042
        try:
            return int(filename.split('_')[1])
        except (IndexError, ValueError):
            return -1

    def get_profile_evolution(
        self,
        component: str,
        last_n: int = 20
    ) -> List[tuple]:
        """
        Retourne l'évolution d'une composante sur les N dernières occasions.

        Args:
            component: Nom de la composante (ex: "curiosity")
            last_n: Nombre d'occasions à considérer

        Returns:
            Liste de tuples (occasion_id, valeur)
        """
        occasions = self.get_recent_occasions(last_n)

        evolution = []
        for occ in reversed(occasions):  # Ordre chronologique
            # Chercher la composante dans le profil après
            for category, comps in occ.profile_after.items():
                if component in comps:
                    evolution.append((occ.occasion_id, comps[component]))
                    break

        return evolution

    def get_statistics(self, last_n: int = 100) -> Dict[str, Any]:
        """
        Calcule des statistiques sur les occasions récentes.

        Args:
            last_n: Nombre d'occasions à analyser

        Returns:
            Dictionnaire de statistiques
        """
        occasions = self.get_recent_occasions(last_n)

        if not occasions:
            return {"count": 0}

        # Statistiques de base
        processing_times = [o.processing_time_ms for o in occasions]
        thoughts_created = [len(o.new_thoughts) for o in occasions]
        tools_counts = [len(o.tools_used) for o in occasions]

        # Répartition des triggers
        trigger_types = {}
        for o in occasions:
            trigger_types[o.trigger_type] = trigger_types.get(o.trigger_type, 0) + 1

        return {
            "count": len(occasions),
            "processing_time": {
                "avg_ms": sum(processing_times) / len(processing_times),
                "min_ms": min(processing_times),
                "max_ms": max(processing_times),
            },
            "thoughts_created": {
                "total": sum(thoughts_created),
                "avg_per_occasion": sum(thoughts_created) / len(thoughts_created),
            },
            "tools": {
                "avg_per_occasion": sum(tools_counts) / len(tools_counts),
            },
            "trigger_distribution": trigger_types,
        }


# Test
if __name__ == "__main__":
    logger = OccasionLogger("tests/temp_logs")

    # Créer une occasion test
    occasion = OccasionLog(
        occasion_id=1,
        timestamp=datetime.now().isoformat(),
        trigger_type="user",
        trigger_content="Test question sur Whitehead",
        previous_state_id=0,
        prehended_thoughts_count=5,
        prehended_docs_count=2,
        prehended_thoughts=["Pensée 1", "Pensée 2"],
        response_summary="Réponse détaillée sur le processus...",
        new_thoughts=["Nouvelle insight sur le devenir"],
        tools_used=["search_thoughts", "search_library"],
        new_state_id=1,
        alpha_used=0.85,
        beta_used=0.15,
        profile_before={"epistemic": {"curiosity": 0.5, "certainty": 0.3}},
        profile_after={"epistemic": {"curiosity": 0.55, "certainty": 0.32}},
        processing_time_ms=1500
    )

    # Logger
    filepath = logger.log(occasion)
    print(f"Logged to: {filepath}")

    # Relire
    loaded = logger.get_occasion(1)
    print(f"Loaded: trigger_type={loaded.trigger_type}, new_state_id={loaded.new_state_id}")

    # Stats
    print(f"Stats: {logger.get_statistics()}")
