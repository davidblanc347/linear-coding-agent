"""
Module de génération de résumés LLM pour les sections hiérarchiques.

Ce module génère des résumés sémantiques enrichis avec extraction de concepts
pour chaque section du document (niveau 1, 2, 3 de la hiérarchie).

Usage:
    from utils.llm_summarizer import generate_summaries_for_toc

    summaries = generate_summaries_for_toc(
        toc=toc,
        chunks=chunks,
        provider="claude",
        model="claude-sonnet-4-5-20250929"
    )
"""

import json
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path
import anthropic
import os

# Configuration logging
logger = logging.getLogger(__name__)


def build_summary_prompt(section_title: str, section_text: str, language: str = "fr") -> str:
    """
    Construit le prompt pour générer un résumé de section.

    Args:
        section_title: Titre de la section (ex: "Peirce: CP 5.314 > La sémiose")
        section_text: Texte complet de la section (concaténation des chunks)
        language: Langue du résumé ("fr" ou "en")

    Returns:
        Prompt formaté pour le LLM
    """
    if language == "fr":
        prompt = f"""Tu es un expert en philosophie et sémiotique. Ta tâche est de résumer la section suivante d'un texte académique.

Titre de la section: {section_title}

Texte de la section:
{section_text}

Tâches:
1. Rédige un résumé en français de 150-300 mots qui capture:
   - Les idées principales et arguments centraux
   - Les concepts philosophiques clés
   - Le contexte intellectuel et les références
   - La contribution originale de l'auteur

2. Extrais 5-10 concepts clés (mots ou courtes expressions) qui représentent les idées centrales.
   Les concepts doivent être:
   - Des termes philosophiques importants
   - Des noms de penseurs/auteurs mentionnés
   - Des notions théoriques centrales
   - En français (même si le texte source est en anglais)

IMPORTANT: Réponds UNIQUEMENT avec un JSON valide au format suivant, sans markdown ni autre texte:

{{
    "summary": "Ton résumé détaillé en français...",
    "concepts": ["concept1", "concept2", "concept3", ...]
}}
"""
    else:  # English
        prompt = f"""You are an expert in philosophy and semiotics. Your task is to summarize the following section from an academic text.

Section title: {section_title}

Section text:
{section_text}

Tasks:
1. Write a summary of 150-300 words in English that captures:
   - Main ideas and central arguments
   - Key philosophical concepts
   - Intellectual context and references
   - Original contribution of the author

2. Extract 5-10 key concepts (words or short phrases) representing central ideas.
   Concepts should be:
   - Important philosophical terms
   - Names of thinkers/authors mentioned
   - Central theoretical notions
   - In English

IMPORTANT: Respond ONLY with valid JSON in this format, without markdown or other text:

{{
    "summary": "Your detailed summary in English...",
    "concepts": ["concept1", "concept2", "concept3", ...]
}}
"""

    return prompt


def call_claude_api(
    prompt: str,
    model: str = "claude-sonnet-4-5-20250929",
    max_tokens: int = 1000,
    temperature: float = 0.3,
) -> Dict[str, Any]:
    """
    Appelle l'API Claude pour générer un résumé.

    Args:
        prompt: Le prompt construit
        model: Modèle Claude à utiliser
        max_tokens: Nombre maximum de tokens
        temperature: Température de génération

    Returns:
        Dict avec:
        - summary: str - Le résumé généré
        - concepts: List[str] - Les concepts extraits
        - usage: Dict - Tokens utilisés (input_tokens, output_tokens)

    Raises:
        ValueError: Si ANTHROPIC_API_KEY n'est pas définie
        Exception: Si l'appel API échoue
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY non définie dans .env")

    client = anthropic.Anthropic(api_key=api_key)

    logger.info(f"Appel Claude API - modèle: {model}")

    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}]
        )

        # Extraire le contenu texte
        content = response.content[0].text

        # Parser le JSON
        # Nettoyer le markdown si présent
        if content.startswith("```json"):
            content = content.replace("```json", "").replace("```", "").strip()
        elif content.startswith("```"):
            content = content.replace("```", "").strip()

        result = json.loads(content)

        # Valider la structure
        if "summary" not in result or "concepts" not in result:
            raise ValueError(f"Réponse Claude invalide: {content}")

        # Ajouter les statistiques d'usage
        result["usage"] = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens
        }

        logger.info(
            f"Claude summary généré: {len(result['summary'])} chars, "
            f"{len(result['concepts'])} concepts, "
            f"{response.usage.input_tokens} in / {response.usage.output_tokens} out tokens"
        )

        return result

    except json.JSONDecodeError as e:
        logger.error(f"Erreur parsing JSON Claude: {e}")
        logger.error(f"Contenu brut: {content}")
        raise

    except Exception as e:
        logger.error(f"Erreur appel Claude API: {e}")
        raise


def generate_summary_for_section(
    section_title: str,
    chunks: List[Dict[str, Any]],
    provider: str = "claude",
    model: str = "claude-sonnet-4-5-20250929",
    language: str = "fr",
    max_text_length: int = 15000,
) -> Dict[str, Any]:
    """
    Génère un résumé pour une section donnée.

    Args:
        section_title: Titre complet de la section (ex: "Peirce: CP 5.314 > La sémiose")
        chunks: Liste des chunks appartenant à cette section
        provider: Provider LLM ("claude" uniquement pour l'instant)
        model: Modèle à utiliser
        language: Langue du résumé ("fr" ou "en")
        max_text_length: Longueur maximale du texte à résumer (pour éviter les timeouts)

    Returns:
        Dict avec:
        - summary: str - Le résumé généré
        - concepts: List[str] - Les concepts extraits
        - chunks_count: int - Nombre de chunks dans cette section
        - usage: Dict - Statistiques d'usage (tokens, etc.)
        - success: bool - Si la génération a réussi
        - error: Optional[str] - Message d'erreur si échec
    """
    if not chunks:
        logger.warning(f"Aucun chunk pour la section '{section_title}'")
        return {
            "summary": section_title,
            "concepts": [],
            "chunks_count": 0,
            "usage": {},
            "success": False,
            "error": "No chunks found"
        }

    # Concaténer le texte de tous les chunks de cette section
    section_text = "\n\n".join([chunk.get("text", "") for chunk in chunks])

    # Tronquer si trop long (éviter les timeouts et coûts excessifs)
    if len(section_text) > max_text_length:
        logger.warning(
            f"Section '{section_title}' trop longue ({len(section_text)} chars), "
            f"troncature à {max_text_length} chars"
        )
        section_text = section_text[:max_text_length] + "...\n\n[Texte tronqué]"

    # Construire le prompt
    prompt = build_summary_prompt(section_title, section_text, language)

    # Appeler l'API
    try:
        if provider == "claude":
            result = call_claude_api(prompt, model=model)
        else:
            raise ValueError(f"Provider '{provider}' non supporté (uniquement 'claude')")

        return {
            "summary": result["summary"],
            "concepts": result["concepts"],
            "chunks_count": len(chunks),
            "usage": result.get("usage", {}),
            "success": True,
            "error": None
        }

    except Exception as e:
        logger.error(f"Erreur génération résumé pour '{section_title}': {e}")
        return {
            "summary": section_title,  # Fallback: juste le titre
            "concepts": [],
            "chunks_count": len(chunks),
            "usage": {},
            "success": False,
            "error": str(e)
        }


def generate_summaries_for_toc(
    toc: List[Dict[str, Any]],
    chunks: List[Dict[str, Any]],
    provider: str = "claude",
    model: str = "claude-sonnet-4-5-20250929",
    language: str = "fr",
) -> Dict[str, Dict[str, Any]]:
    """
    Génère des résumés pour toutes les sections de la table des matières.

    Cette fonction:
    1. Parcourt récursivement la TOC hiérarchique
    2. Pour chaque section, trouve les chunks correspondants
    3. Génère un résumé avec concepts
    4. Retourne un dictionnaire title -> summary_data

    Args:
        toc: Table des matières hiérarchique (liste de TOCEntry)
        chunks: Tous les chunks du document
        provider: Provider LLM ("claude")
        model: Modèle à utiliser
        language: Langue des résumés ("fr" ou "en")

    Returns:
        Dict[section_title, summary_data] où summary_data contient:
        - summary: str
        - concepts: List[str]
        - chunks_count: int
        - level: int (niveau hiérarchique 1/2/3)
        - usage: Dict (tokens)
        - success: bool

    Example:
        >>> summaries = generate_summaries_for_toc(toc, chunks)
        >>> summaries["Peirce: CP 5.314"]["summary"]
        "Cette section explore la théorie de la sémiose..."
    """
    summaries = {}

    # Créer un index chunks par sectionPath pour accès rapide
    chunks_by_section: Dict[str, List[Dict[str, Any]]] = {}
    for chunk in chunks:
        section_path = chunk.get("sectionPath", "")
        if section_path:
            if section_path not in chunks_by_section:
                chunks_by_section[section_path] = []
            chunks_by_section[section_path].append(chunk)

    def process_toc_entry(entry: Dict[str, Any], level: int, parent_path: str = ""):
        """Traite récursivement une entrée TOC."""
        title = entry.get("title", "")
        if not title:
            return

        # Construire le sectionPath (même logique que dans weaviate_ingest.py)
        if parent_path:
            section_path = f"{parent_path} > {title}"
        else:
            section_path = title

        # Récupérer les chunks de cette section
        section_chunks = chunks_by_section.get(section_path, [])

        if section_chunks:
            logger.info(
                f"Génération résumé pour '{section_path}' "
                f"(level {level}, {len(section_chunks)} chunks)..."
            )

            summary_data = generate_summary_for_section(
                section_title=section_path,
                chunks=section_chunks,
                provider=provider,
                model=model,
                language=language
            )

            # Ajouter le niveau hiérarchique
            summary_data["level"] = level

            # Stocker dans le dictionnaire
            summaries[title] = summary_data

        else:
            logger.warning(
                f"Aucun chunk trouvé pour '{section_path}' (level {level})"
            )
            # Créer un résumé vide
            summaries[title] = {
                "summary": title,
                "concepts": [],
                "chunks_count": 0,
                "level": level,
                "usage": {},
                "success": False,
                "error": "No chunks found"
            }

        # Traiter récursivement les sous-sections
        children = entry.get("children", [])
        for child in children:
            process_toc_entry(child, level + 1, section_path)

    # Traiter toutes les entrées de niveau 1
    for entry in toc:
        process_toc_entry(entry, level=1)

    # Statistiques finales
    total_summaries = len(summaries)
    successful = sum(1 for s in summaries.values() if s["success"])
    total_input_tokens = sum(s.get("usage", {}).get("input_tokens", 0) for s in summaries.values())
    total_output_tokens = sum(s.get("usage", {}).get("output_tokens", 0) for s in summaries.values())

    # Calculer le coût (Claude Sonnet 4.5: $3/M input, $15/M output)
    cost_input = total_input_tokens * 0.003 / 1000
    cost_output = total_output_tokens * 0.015 / 1000
    total_cost = cost_input + cost_output

    logger.info("=" * 80)
    logger.info("RÉSUMÉS GÉNÉRÉS - STATISTIQUES")
    logger.info("=" * 80)
    logger.info(f"Total sections: {total_summaries}")

    if total_summaries > 0:
        logger.info(f"Succès: {successful} ({successful/total_summaries*100:.1f}%)")
        logger.info(f"Échecs: {total_summaries - successful}")
    else:
        logger.info("Succès: 0 (0.0%)")
        logger.info("Échecs: 0")

    logger.info(f"Tokens input: {total_input_tokens:,}")
    logger.info(f"Tokens output: {total_output_tokens:,}")
    logger.info(f"Coût total: ${total_cost:.4f}")
    logger.info("=" * 80)

    return summaries


if __name__ == "__main__":
    # Test rapide
    logging.basicConfig(level=logging.INFO)

    # Exemple de test avec un chunk fictif
    test_chunks = [
        {
            "text": "To erect a philosophical edifice that shall outlast the vicissitudes of time...",
            "sectionPath": "Peirce: CP 1.1 > PREFACE"
        }
    ]

    result = generate_summary_for_section(
        section_title="Peirce: CP 1.1 > PREFACE",
        chunks=test_chunks,
        provider="claude",
        language="fr"
    )

    print(json.dumps(result, indent=2, ensure_ascii=False))
