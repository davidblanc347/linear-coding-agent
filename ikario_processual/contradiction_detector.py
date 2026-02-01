#!/usr/bin/env python3
"""
Détecteur de Contradictions par NLI (Natural Language Inference).

AMENDEMENT #8 : Détection fiable des hard negatives.

Le problème avec la détection par seuil de similarité :
- "L'IA a une conscience" vs "L'IA n'a pas de conscience"
- Similarité cosine ~0.7 (haute !)
- Mais ce sont des contradictions sémantiques

Solution : Utiliser un modèle NLI pré-entraîné.
- Modèle : facebook/bart-large-mnli (ou cross-encoder/nli-deberta-v3-base)
- Classes : entailment, neutral, contradiction
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple, Any, Dict
import numpy as np

# Lazy import pour éviter de charger le modèle si non utilisé
_classifier = None
_model_name = None


def get_nli_classifier(model_name: str = "facebook/bart-large-mnli"):
    """
    Lazy loader pour le classifieur NLI.

    Utilise transformers pipeline (zero-shot classification).
    """
    global _classifier, _model_name

    if _classifier is not None and _model_name == model_name:
        return _classifier

    try:
        from transformers import pipeline
        _classifier = pipeline(
            "zero-shot-classification",
            model=model_name,
            device=-1  # CPU, utiliser 0 pour GPU
        )
        _model_name = model_name
        return _classifier
    except ImportError:
        raise ImportError(
            "transformers non installé. "
            "Installez avec: pip install transformers torch"
        )
    except Exception as e:
        raise RuntimeError(f"Erreur chargement modèle NLI: {e}")


@dataclass
class ContradictionResult:
    """Résultat de la détection de contradiction."""
    is_contradiction: bool
    confidence: float
    entailment_score: float
    neutral_score: float
    contradiction_score: float
    text1: str
    text2: str


class ContradictionDetector:
    """
    Détecteur de contradictions sémantiques via NLI.

    Usage:
        detector = ContradictionDetector()
        result = detector.detect("L'IA a une conscience", "L'IA n'a pas de conscience")
        print(result.is_contradiction)  # True
    """

    def __init__(
        self,
        model_name: str = "facebook/bart-large-mnli",
        contradiction_threshold: float = 0.5,
        lazy_load: bool = True
    ):
        """
        Args:
            model_name: Nom du modèle HuggingFace NLI
            contradiction_threshold: Seuil pour déclarer contradiction
            lazy_load: Si True, charge le modèle à la première utilisation
        """
        self.model_name = model_name
        self.contradiction_threshold = contradiction_threshold
        self._classifier = None

        if not lazy_load:
            self._load_model()

    def _load_model(self):
        """Charge le modèle NLI."""
        if self._classifier is None:
            self._classifier = get_nli_classifier(self.model_name)

    def detect_contradiction(
        self,
        premise: str,
        hypothesis: str
    ) -> Tuple[bool, float]:
        """
        Vérifie si deux textes sont en contradiction.

        Args:
            premise: Premier texte (la "vérité" de référence)
            hypothesis: Second texte (ce qui est testé)

        Returns:
            (is_contradiction, confidence_score)
        """
        self._load_model()

        # Construire l'entrée pour NLI
        # Format: "premise" + " " + "hypothesis"
        # Le classifieur évalue si hypothesis est impliqué/neutre/contredit par premise

        result = self._classifier(
            premise,
            candidate_labels=["entailment", "neutral", "contradiction"],
            hypothesis_template="{}",  # hypothesis brut
            multi_label=False
        )

        # Extraire les scores
        labels = result['labels']
        scores = result['scores']

        score_dict = dict(zip(labels, scores))
        contradiction_score = score_dict.get('contradiction', 0.0)

        is_contradiction = contradiction_score > self.contradiction_threshold

        return (is_contradiction, contradiction_score)

    def detect(self, text1: str, text2: str) -> ContradictionResult:
        """
        Détection complète avec tous les scores.

        Args:
            text1: Premier texte
            text2: Second texte

        Returns:
            ContradictionResult avec tous les détails
        """
        self._load_model()

        result = self._classifier(
            text1,
            candidate_labels=["entailment", "neutral", "contradiction"],
            hypothesis_template="{}",
        )

        labels = result['labels']
        scores = result['scores']
        score_dict = dict(zip(labels, scores))

        contradiction_score = score_dict.get('contradiction', 0.0)

        return ContradictionResult(
            is_contradiction=contradiction_score > self.contradiction_threshold,
            confidence=contradiction_score,
            entailment_score=score_dict.get('entailment', 0.0),
            neutral_score=score_dict.get('neutral', 0.0),
            contradiction_score=contradiction_score,
            text1=text1[:200],
            text2=text2[:200],
        )

    def detect_batch(
        self,
        premise: str,
        hypotheses: List[str]
    ) -> List[ContradictionResult]:
        """
        Détecte les contradictions pour plusieurs hypothèses.

        Args:
            premise: Texte de référence
            hypotheses: Liste de textes à tester

        Returns:
            Liste de ContradictionResult
        """
        return [self.detect(premise, h) for h in hypotheses]


class HybridContradictionDetector:
    """
    Détecteur hybride : cosine + NLI.

    Combine la similarité cosine (rapide) et NLI (précis).

    Logique:
    1. Si similarité < 0.1 → hard negative certain
    2. Si similarité > 0.7 → probablement OK (sauf si NLI dit contradiction)
    3. Si 0.1 <= similarité <= 0.7 → utiliser NLI pour trancher
    """

    def __init__(
        self,
        nli_detector: Optional[ContradictionDetector] = None,
        low_sim_threshold: float = 0.1,
        high_sim_threshold: float = 0.7,
        nli_threshold: float = 0.5
    ):
        """
        Args:
            nli_detector: Détecteur NLI (créé si None)
            low_sim_threshold: En dessous = contradiction certaine
            high_sim_threshold: Au dessus = vérifier avec NLI seulement si score > 0.8
            nli_threshold: Seuil NLI pour contradiction
        """
        self.nli_detector = nli_detector
        self.low_sim_threshold = low_sim_threshold
        self.high_sim_threshold = high_sim_threshold
        self.nli_threshold = nli_threshold

    def _get_nli_detector(self) -> ContradictionDetector:
        """Lazy load du détecteur NLI."""
        if self.nli_detector is None:
            self.nli_detector = ContradictionDetector(
                contradiction_threshold=self.nli_threshold
            )
        return self.nli_detector

    def detect(
        self,
        input_text: str,
        input_vector: np.ndarray,
        candidate_text: str,
        candidate_vector: np.ndarray
    ) -> Dict[str, Any]:
        """
        Détecte si input contredit candidate.

        Args:
            input_text: Texte de l'entrée
            input_vector: Vecteur de l'entrée (1024-dim)
            candidate_text: Texte du candidat (corpus)
            candidate_vector: Vecteur du candidat

        Returns:
            Dict avec is_hard_negative, similarity, nli_score, method
        """
        # Étape 1 : Similarité cosine
        norm1 = np.linalg.norm(input_vector)
        norm2 = np.linalg.norm(candidate_vector)

        if norm1 == 0 or norm2 == 0:
            similarity = 0.0
        else:
            similarity = float(np.dot(input_vector, candidate_vector) / (norm1 * norm2))

        result = {
            'similarity': similarity,
            'is_hard_negative': False,
            'nli_score': None,
            'method': 'cosine_only',
        }

        # Étape 2 : Décision basée sur similarité
        if similarity < self.low_sim_threshold:
            # Très différent → hard negative certain
            result['is_hard_negative'] = True
            result['method'] = 'low_similarity'
            return result

        if similarity > self.high_sim_threshold:
            # Très similaire → probablement pas contradiction
            # Mais on peut quand même vérifier avec NLI si les textes sont fournis
            if input_text and candidate_text:
                nli = self._get_nli_detector()
                is_contradiction, score = nli.detect_contradiction(
                    input_text, candidate_text
                )
                result['nli_score'] = score
                if is_contradiction and score > 0.8:  # Seuil élevé car très similaire
                    result['is_hard_negative'] = True
                    result['method'] = 'nli_high_confidence'
            return result

        # Étape 3 : Zone grise (0.1-0.7) → utiliser NLI
        if input_text and candidate_text:
            nli = self._get_nli_detector()
            is_contradiction, score = nli.detect_contradiction(
                input_text, candidate_text
            )
            result['nli_score'] = score
            result['is_hard_negative'] = is_contradiction
            result['method'] = 'nli_zone_grise'
        else:
            # Pas de texte disponible → fallback sur similarité
            result['is_hard_negative'] = similarity < 0.3
            result['method'] = 'cosine_fallback'

        return result


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def is_contradiction(text1: str, text2: str, threshold: float = 0.5) -> bool:
    """
    Fonction utilitaire simple pour vérifier une contradiction.

    Args:
        text1: Premier texte
        text2: Second texte
        threshold: Seuil de confiance

    Returns:
        True si contradiction détectée
    """
    detector = ContradictionDetector(contradiction_threshold=threshold)
    is_contra, _ = detector.detect_contradiction(text1, text2)
    return is_contra


def find_contradictions(
    reference: str,
    candidates: List[str],
    threshold: float = 0.5
) -> List[Tuple[str, float]]:
    """
    Trouve les contradictions dans une liste de candidats.

    Args:
        reference: Texte de référence
        candidates: Liste de textes à vérifier
        threshold: Seuil de confiance

    Returns:
        Liste de (texte, score) pour les contradictions détectées
    """
    detector = ContradictionDetector(contradiction_threshold=threshold)
    results = []

    for candidate in candidates:
        is_contra, score = detector.detect_contradiction(reference, candidate)
        if is_contra:
            results.append((candidate, score))

    return sorted(results, key=lambda x: x[1], reverse=True)
