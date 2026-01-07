# Plan d'Implémentation - llm_summarizer.py

**Date**: 2026-01-03
**Objectif**: Créer un module de génération de résumés LLM pour les sections du document
**Priorité**: 🔴 HAUTE (corrige 60% de la base vectorielle inutilisée)

---

## 📋 Table des Matières

1. [Objectifs et Spécifications](#1-objectifs-et-spécifications)
2. [Architecture du Module](#2-architecture-du-module)
3. [Implémentation Détaillée](#3-implémentation-détaillée)
4. [Intégration au Pipeline](#4-intégration-au-pipeline)
5. [Tests et Validation](#5-tests-et-validation)
6. [Plan de Déploiement](#6-plan-de-déploiement)

---

## 1. Objectifs et Spécifications

### 1.1 Objectif Principal

Générer des résumés LLM de qualité pour chaque section de la table des matières afin de :
- ✅ Remplir le champ `Summary.text` avec un vrai résumé (100-500 caractères)
- ✅ Extraire les concepts clés pour `Summary.concepts` (5-15 mots-clés)
- ✅ Activer la recherche hiérarchique Summary → Chunk

### 1.2 Contraintes

**Performance** :
- Traiter 8,425 sections (base actuelle) en temps raisonnable
- Budget : ~1 section/seconde avec Ollama, ~3 sections/seconde avec Mistral API
- Temps total estimé : 2-3h avec Ollama, 45min avec Mistral API

**Coût** :
- Ollama (local) : GRATUIT mais lent
- Mistral API : ~$0.001-0.002 par section (~$8-16 pour 8,425 sections)

**Qualité** :
- Résumés cohérents et informatifs (pas de hallucinations)
- Concepts pertinents extraits du texte réel
- Support multilingue (français, anglais, grec, latin)

### 1.3 Cas d'Usage

**Cas 1** : Premier traitement d'un document PDF
```python
# Dans pdf_pipeline.py, après chunking
summaries_content = generate_summaries_for_toc(
    toc=toc,
    chunks=chunks,
    llm_provider="ollama"
)
# → Génère résumés pour toutes les sections
```

**Cas 2** : Re-traitement d'un document existant
```python
# Script standalone pour régénérer résumés
python regenerate_summaries.py --doc peirce_collected_papers_fixed --provider mistral
```

**Cas 3** : Génération incrémentale (nouvelles sections uniquement)
```python
# Générer résumés seulement pour sections manquantes
summaries_content = generate_missing_summaries(
    doc_name="peirce_collected_papers_fixed",
    toc=new_toc,
    chunks=chunks
)
```

---

## 2. Architecture du Module

### 2.1 Structure du Fichier

```
utils/llm_summarizer.py
│
├─ Imports et Configuration
│  └─ llm_structurer, types, logging
│
├─ Type Definitions
│  ├─ SummaryResult (TypedDict)
│  └─ SummarizationConfig (TypedDict)
│
├─ Fonctions Utilitaires
│  ├─ collect_chunks_for_section()
│  ├─ truncate_text_for_llm()
│  └─ parse_llm_summary_response()
│
├─ Génération de Résumés
│  ├─ generate_summary_for_section() ← CORE
│  ├─ generate_summaries_for_toc() ← PUBLIC API
│  └─ generate_missing_summaries()
│
└─ Batch Processing
   ├─ batch_generate_summaries()
   └─ resume_failed_summaries()
```

### 2.2 Dépendances

```python
# Dépendances internes
from utils.llm_structurer import get_llm_client, LLMProvider
from utils.types import TOCEntry, ChunkData

# Dépendances externes
import json
import logging
from typing import List, Dict, Any, Optional, TypedDict
from pathlib import Path
```

### 2.3 Types Définis

```python
class SummaryResult(TypedDict):
    """Résultat de la génération d'un résumé."""
    title: str
    summary: str              # Résumé LLM (100-500 chars)
    concepts: List[str]       # 5-15 concepts clés
    chunks_count: int         # Nombre de chunks dans cette section
    success: bool
    error: Optional[str]

class SummarizationConfig(TypedDict, total=False):
    """Configuration pour la génération de résumés."""
    llm_provider: LLMProvider              # "ollama" | "mistral"
    model: Optional[str]                    # Modèle spécifique (optionnel)
    max_chunks_per_section: int            # Limite de chunks à résumer (default: 20)
    summary_length: str                    # "short" | "medium" | "long"
    language: str                          # "fr" | "en" | "auto"
    batch_size: int                        # Taille des batches (default: 10)
    cache_results: bool                    # Cacher résultats (default: True)
    output_file: Optional[Path]            # Fichier de sauvegarde intermédiaire
```

---

## 3. Implémentation Détaillée

### 3.1 Fonction Core : generate_summary_for_section()

**Signature** :
```python
def generate_summary_for_section(
    section_title: str,
    section_path: str,
    section_chunks: List[Dict[str, Any]],
    config: SummarizationConfig,
) -> SummaryResult:
    """Génère un résumé LLM pour une section donnée.

    Args:
        section_title: Titre de la section (ex: "La sémiose et les catégories")
        section_path: Chemin hiérarchique (ex: "Peirce: CP 5.314 > La sémiose")
        section_chunks: Liste des chunks appartenant à cette section
        config: Configuration de génération

    Returns:
        SummaryResult avec summary, concepts, et chunks_count

    Example:
        >>> result = generate_summary_for_section(
        ...     "La sémiose",
        ...     "Peirce: CP 5.314 > La sémiose",
        ...     chunks,
        ...     {"llm_provider": "ollama", "language": "fr"}
        ... )
        >>> print(result['summary'])
        "Ce passage explore la théorie de la sémiose..."
    """
```

**Pseudo-code** :
```python
def generate_summary_for_section(...):
    # 1. Collecter et limiter les chunks
    chunks_to_summarize = section_chunks[:config.max_chunks_per_section]

    if not chunks_to_summarize:
        return {
            "title": section_title,
            "summary": section_title,  # Fallback sur titre
            "concepts": [],
            "chunks_count": 0,
            "success": False,
            "error": "No chunks found"
        }

    # 2. Construire le texte à résumer
    section_text = "\n\n".join([
        chunk.get("text", "") for chunk in chunks_to_summarize
    ])

    # 3. Tronquer si trop long (limite token LLM)
    section_text = truncate_text_for_llm(section_text, max_tokens=3000)

    # 4. Construire le prompt
    prompt = build_summary_prompt(section_title, section_text, config)

    # 5. Appeler le LLM
    try:
        llm = get_llm_client(config["llm_provider"])
        response = llm.generate(prompt, max_tokens=600)

        # 6. Parser la réponse JSON
        result = parse_llm_summary_response(response)

        return {
            "title": section_title,
            "summary": result["summary"],
            "concepts": result["concepts"],
            "chunks_count": len(section_chunks),
            "success": True,
            "error": None
        }

    except Exception as e:
        logger.error(f"LLM summarization failed for {section_title}: {e}")
        return {
            "title": section_title,
            "summary": section_title,  # Fallback
            "concepts": [],
            "chunks_count": len(section_chunks),
            "success": False,
            "error": str(e)
        }
```

### 3.2 Fonction Utilitaire : build_summary_prompt()

**Prompt Engineering** :

```python
def build_summary_prompt(
    section_title: str,
    section_text: str,
    config: SummarizationConfig
) -> str:
    """Construit le prompt LLM pour la génération de résumé."""

    language = config.get("language", "fr")
    summary_length = config.get("summary_length", "medium")

    # Mapper summary_length vers nombre de mots
    word_counts = {
        "short": "50-100 mots",
        "medium": "100-200 mots",
        "long": "200-400 mots"
    }
    word_count = word_counts[summary_length]

    # Prompts selon langue
    if language == "fr":
        prompt = f"""Tu es un expert en philosophie et sémiotique. Résume la section suivante d'un texte philosophique.

Titre de la section: {section_title}

Texte de la section:
{section_text}

Tâches:
1. Résume le contenu principal en {word_count} en français
2. Extrais les 5-10 concepts clés les plus importants
3. Réponds UNIQUEMENT en JSON valide avec cette structure:

{{
    "summary": "Résumé de la section en français...",
    "concepts": ["concept1", "concept2", "concept3", ...]
}}

Consignes:
- Le résumé doit capturer les arguments principaux et thèses développées
- Les concepts doivent être des termes techniques ou notions philosophiques clés
- Reste fidèle au texte, n'invente rien
- Si le texte est en grec/latin, résume quand même en français
"""

    elif language == "en":
        prompt = f"""You are an expert in philosophy and semiotics. Summarize the following section from a philosophical text.

Section title: {section_title}

Section text:
{section_text}

Tasks:
1. Summarize the main content in {word_count} in English
2. Extract the 5-10 most important key concepts
3. Respond ONLY with valid JSON using this structure:

{{
    "summary": "Summary of the section in English...",
    "concepts": ["concept1", "concept2", "concept3", ...]
}}

Guidelines:
- The summary should capture main arguments and theses
- Concepts should be technical terms or key philosophical notions
- Stay faithful to the text, don't invent anything
- If text is in Greek/Latin, still summarize in English
"""

    else:  # auto
        # Détecter langue du texte et adapter
        prompt = f"""[Auto-detect language and summarize accordingly...]"""

    return prompt
```

### 3.3 Fonction Principale : generate_summaries_for_toc()

**Signature** :
```python
def generate_summaries_for_toc(
    toc: List[Dict[str, Any]],
    chunks: List[Dict[str, Any]],
    llm_provider: LLMProvider = "ollama",
    config: Optional[SummarizationConfig] = None,
) -> Dict[str, Dict[str, Any]]:
    """Génère des résumés LLM pour toutes les sections de la TOC.

    Parcourt récursivement la TOC et génère un résumé pour chaque section.
    Supporte le batch processing et la sauvegarde intermédiaire.

    Args:
        toc: Table des matières hiérarchique
        chunks: Tous les chunks du document avec sectionPath
        llm_provider: "ollama" (local, gratuit) ou "mistral" (API, payant)
        config: Configuration optionnelle (utilise defaults si None)

    Returns:
        Dict mapping section title → {summary, concepts}

    Example:
        >>> summaries = generate_summaries_for_toc(toc, chunks, "ollama")
        >>> summaries["Peirce: CP 5.314"]
        {
            "summary": "Ce passage explore la théorie de la sémiose...",
            "concepts": ["sémiose", "triade", "signe", "interprétant"],
            "chunks_count": 23,
            "success": True
        }
    """
```

**Implémentation** :
```python
def generate_summaries_for_toc(toc, chunks, llm_provider="ollama", config=None):
    # Configuration par défaut
    default_config: SummarizationConfig = {
        "llm_provider": llm_provider,
        "max_chunks_per_section": 20,
        "summary_length": "medium",
        "language": "fr",
        "batch_size": 10,
        "cache_results": True,
        "output_file": None,
    }

    # Merger avec config utilisateur
    final_config = {**default_config, **(config or {})}

    # Résultats accumulés
    summaries_content: Dict[str, Dict[str, Any]] = {}

    # Collecter toutes les sections à traiter (aplatir la TOC)
    all_sections = flatten_toc(toc)

    logger.info(f"Generating summaries for {len(all_sections)} sections using {llm_provider}...")

    # Traiter par batches pour sauvegarde intermédiaire
    batch_size = final_config["batch_size"]

    for batch_idx in range(0, len(all_sections), batch_size):
        batch = all_sections[batch_idx:batch_idx + batch_size]

        logger.info(f"Processing batch {batch_idx//batch_size + 1}/{(len(all_sections) + batch_size - 1)//batch_size}")

        for section_item in batch:
            title = section_item["title"]
            path = section_item["path"]
            level = section_item["level"]

            # Collecter chunks de cette section
            section_chunks = collect_chunks_for_section(chunks, path)

            # Générer résumé
            result = generate_summary_for_section(
                section_title=title,
                section_path=path,
                section_chunks=section_chunks,
                config=final_config
            )

            summaries_content[title] = result

            # Log progression
            if result["success"]:
                logger.info(f"  ✓ {title} ({result['chunks_count']} chunks, {len(result['summary'])} chars)")
            else:
                logger.warning(f"  ✗ {title} - Error: {result['error']}")

        # Sauvegarde intermédiaire
        if final_config["cache_results"] and final_config["output_file"]:
            save_intermediate_results(summaries_content, final_config["output_file"])

    # Statistiques finales
    success_count = sum(1 for s in summaries_content.values() if s["success"])
    logger.info(f"Summary generation complete: {success_count}/{len(summaries_content)} successful")

    return summaries_content


def flatten_toc(toc: List[Dict], parent_path: str = "") -> List[Dict]:
    """Aplatit une TOC hiérarchique en liste de sections avec chemins."""
    sections = []

    for item in toc:
        title = item.get("title", "")
        level = item.get("level", 1)
        path = f"{parent_path} > {title}" if parent_path else title

        sections.append({
            "title": title,
            "path": path,
            "level": level
        })

        # Récursif pour children
        if "children" in item:
            sections.extend(flatten_toc(item["children"], path))

    return sections


def collect_chunks_for_section(chunks: List[Dict], section_path: str) -> List[Dict]:
    """Collecte tous les chunks appartenant à une section."""
    return [
        chunk for chunk in chunks
        if chunk.get("sectionPath", "").startswith(section_path)
    ]
```

### 3.4 Fonctions Utilitaires Supplémentaires

```python
def truncate_text_for_llm(text: str, max_tokens: int = 3000) -> str:
    """Tronque le texte pour ne pas dépasser la limite de tokens LLM.

    Estimation: 1 token ≈ 4 caractères
    """
    max_chars = max_tokens * 4

    if len(text) <= max_chars:
        return text

    # Tronquer au dernier point avant la limite
    truncated = text[:max_chars]
    last_period = truncated.rfind('.')

    if last_period > max_chars * 0.8:  # Si point trouvé après 80% du texte
        return truncated[:last_period + 1] + "..."
    else:
        return truncated + "..."


def parse_llm_summary_response(response: str) -> Dict[str, Any]:
    """Parse la réponse JSON du LLM.

    Supporte différents formats de réponse (avec/sans markdown code blocks).
    """
    # Nettoyer markdown code blocks
    cleaned = response.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        result = json.loads(cleaned)

        # Validation
        if "summary" not in result or "concepts" not in result:
            raise ValueError("Missing required fields in LLM response")

        # Nettoyer concepts (enlever doublons, vides)
        concepts = [c.strip() for c in result["concepts"] if c.strip()]
        concepts = list(dict.fromkeys(concepts))  # Enlever doublons en préservant l'ordre

        return {
            "summary": result["summary"].strip(),
            "concepts": concepts[:15]  # Limiter à 15 concepts max
        }

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM JSON response: {e}\nResponse: {response[:200]}")
        raise


def save_intermediate_results(
    summaries_content: Dict[str, Dict[str, Any]],
    output_file: Path
) -> None:
    """Sauvegarde les résultats intermédiaires en JSON."""
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(summaries_content, f, ensure_ascii=False, indent=2)

    logger.debug(f"Intermediate results saved to {output_file}")
```

---

## 4. Intégration au Pipeline

### 4.1 Modification de weaviate_ingest.py

**Fichier**: `utils/weaviate_ingest.py`

**Ligne 844-845** - AVANT :
```python
if ingest_summary_collection and toc:
    ingest_summaries(client, doc_name, toc, {})  # ← VIDE !
```

**Ligne 844-850** - APRÈS :
```python
if ingest_summary_collection and toc:
    from utils.llm_summarizer import generate_summaries_for_toc

    logger.info("Generating LLM summaries for TOC sections...")

    # Générer résumés LLM
    summaries_results = generate_summaries_for_toc(
        toc=toc,
        chunks=chunks,
        llm_provider=llm_provider,  # Utilise le provider du pipeline
        config={
            "summary_length": "medium",
            "language": language,
            "cache_results": True,
            "output_file": Path(f"output/{doc_name}/{doc_name}_summaries.json")
        }
    )

    # Extraire juste le texte pour ingest_summaries
    summaries_text = {
        title: result["summary"]
        for title, result in summaries_results.items()
    }

    # Enrichir TOC avec concepts
    enrich_toc_with_concepts(toc, summaries_results)

    # Insérer dans Weaviate avec vrais résumés
    ingest_summaries(client, doc_name, toc, summaries_text, chunks)
```

**Fonction helper à ajouter** :
```python
def enrich_toc_with_concepts(
    toc: List[Dict[str, Any]],
    summaries_results: Dict[str, Dict[str, Any]]
) -> None:
    """Enrichit la TOC avec les concepts extraits par LLM."""

    def process_item(item: Dict[str, Any]) -> None:
        title = item.get("title", "")

        if title in summaries_results:
            item["concepts"] = summaries_results[title].get("concepts", [])

        if "children" in item:
            for child in item["children"]:
                process_item(child)

    for item in toc:
        process_item(item)
```

### 4.2 Modification de ingest_summaries()

**Ligne 632** - Ajouter paramètre `chunks` :
```python
def ingest_summaries(
    client: WeaviateClient,
    doc_name: str,
    toc: List[Dict[str, Any]],
    summaries_content: Dict[str, str],
    chunks: List[Dict[str, Any]] = [],  # ← NOUVEAU
) -> int:
```

**Ligne 688** - Calculer chunksCount dynamiquement :
```python
def count_chunks_for_section(section_path: str) -> int:
    """Compte chunks dans cette section."""
    count = 0
    for chunk in chunks:
        if chunk.get("sectionPath", "").startswith(section_path):
            count += 1
    return count

# Dans process_toc():
summary_obj: SummaryObject = {
    ...
    "chunksCount": count_chunks_for_section(path) if chunks else 0,  # ← CORRECTIF
    ...
}
```

### 4.3 Paramètre dans pdf_pipeline.py

**Ajouter option** `generate_summaries` :

```python
def process_pdf(
    pdf_path: Path,
    *,
    use_llm: bool = True,
    llm_provider: LLMProvider = "ollama",
    ingest_to_weaviate: bool = True,
    generate_summaries: bool = True,  # ← NOUVEAU
    summary_config: Optional[Dict] = None,  # ← NOUVEAU
    ...
) -> PipelineResult:
    """
    Args:
        ...
        generate_summaries: Generate LLM summaries for sections (default: True)
        summary_config: Custom summarization config (optional)
    """

    # ... (code existant)

    # Étape 10: Ingestion Weaviate
    if ingest_to_weaviate:
        result = ingest_document(
            doc_name=doc_name,
            chunks=chunks,
            metadata=metadata,
            language=metadata.get("language", "fr"),
            toc=toc,
            hierarchy=hierarchy,
            pages=pages,
            ingest_document_collection=True,
            ingest_summary_collection=generate_summaries,  # ← Utilise le paramètre
            llm_provider=llm_provider,
            summary_config=summary_config,
        )
```

---

## 5. Tests et Validation

### 5.1 Tests Unitaires

**Fichier**: `tests/utils/test_llm_summarizer.py`

```python
"""Tests pour le module llm_summarizer."""

import pytest
from utils.llm_summarizer import (
    generate_summary_for_section,
    generate_summaries_for_toc,
    truncate_text_for_llm,
    parse_llm_summary_response,
    collect_chunks_for_section,
)


def test_collect_chunks_for_section():
    """Test collection de chunks par section."""
    chunks = [
        {"sectionPath": "Chapitre 1 > Section A", "text": "Text 1"},
        {"sectionPath": "Chapitre 1 > Section A", "text": "Text 2"},
        {"sectionPath": "Chapitre 1 > Section B", "text": "Text 3"},
    ]

    result = collect_chunks_for_section(chunks, "Chapitre 1 > Section A")

    assert len(result) == 2
    assert result[0]["text"] == "Text 1"


def test_truncate_text_for_llm():
    """Test troncature de texte."""
    text = "A" * 15000  # 15k chars

    truncated = truncate_text_for_llm(text, max_tokens=1000)

    assert len(truncated) <= 4000  # 1000 tokens * 4 chars
    assert truncated.endswith("...")


def test_parse_llm_summary_response_valid_json():
    """Test parsing réponse JSON valide."""
    response = '''
    {
        "summary": "Ce passage explore la sémiose",
        "concepts": ["sémiose", "triade", "signe"]
    }
    '''

    result = parse_llm_summary_response(response)

    assert result["summary"] == "Ce passage explore la sémiose"
    assert len(result["concepts"]) == 3


def test_parse_llm_summary_response_with_markdown():
    """Test parsing réponse avec code blocks markdown."""
    response = '''```json
    {
        "summary": "Test summary",
        "concepts": ["concept1"]
    }
    ```'''

    result = parse_llm_summary_response(response)

    assert result["summary"] == "Test summary"


def test_generate_summary_for_section_no_chunks():
    """Test génération résumé sans chunks."""
    result = generate_summary_for_section(
        section_title="Test Section",
        section_path="Test > Section",
        section_chunks=[],
        config={"llm_provider": "ollama"}
    )

    assert result["success"] is False
    assert result["chunks_count"] == 0
    assert result["error"] == "No chunks found"


@pytest.mark.integration
def test_generate_summaries_for_toc_integration():
    """Test intégration complète (nécessite Ollama running)."""
    toc = [
        {
            "title": "Introduction",
            "level": 1,
            "children": [
                {"title": "Contexte", "level": 2}
            ]
        }
    ]

    chunks = [
        {
            "sectionPath": "Introduction",
            "text": "Ceci est une introduction à la philosophie."
        },
        {
            "sectionPath": "Introduction > Contexte",
            "text": "Le contexte historique de cette œuvre..."
        }
    ]

    summaries = generate_summaries_for_toc(toc, chunks, "ollama")

    assert "Introduction" in summaries
    assert summaries["Introduction"]["success"] is True
    assert len(summaries["Introduction"]["summary"]) > 50
```

### 5.2 Test Manuel

**Script** : `test_summarizer_manual.py`

```python
#!/usr/bin/env python3
"""Test manuel du llm_summarizer sur un vrai document."""

from pathlib import Path
import json
from utils.llm_summarizer import generate_summaries_for_toc

# Charger document existant
doc_file = Path("output/peirce_collected_papers_fixed/peirce_collected_papers_fixed_chunks.json")

with open(doc_file, 'r', encoding='utf-8') as f:
    data = json.load(f)

toc = data['metadata']['toc']
chunks = data['chunks']

print(f"TOC sections: {len(toc)}")
print(f"Chunks: {len(chunks)}")

# Tester sur 3 premières sections
toc_sample = toc[:3]

print("\nGenerating summaries for first 3 sections...")
summaries = generate_summaries_for_toc(
    toc=toc_sample,
    chunks=chunks,
    llm_provider="ollama",
    config={
        "summary_length": "medium",
        "language": "fr",
        "max_chunks_per_section": 10
    }
)

# Afficher résultats
for title, result in summaries.items():
    print(f"\n{'='*80}")
    print(f"Section: {title}")
    print(f"Success: {result['success']}")
    print(f"Chunks count: {result['chunks_count']}")
    print(f"\nSummary ({len(result['summary'])} chars):")
    print(result['summary'])
    print(f"\nConcepts: {', '.join(result['concepts'])}")
```

---

## 6. Plan de Déploiement

### 6.1 Phase 1 : Développement (2-3 jours)

**Jour 1** : Implémentation core
- [ ] Créer `utils/llm_summarizer.py` avec fonctions de base
- [ ] Implémenter `generate_summary_for_section()`
- [ ] Implémenter `generate_summaries_for_toc()`
- [ ] Tests unitaires

**Jour 2** : Intégration
- [ ] Modifier `weaviate_ingest.py` pour appeler llm_summarizer
- [ ] Modifier `pdf_pipeline.py` pour activer/désactiver summarization
- [ ] Ajouter gestion erreurs et retry logic
- [ ] Tests d'intégration

**Jour 3** : Optimisation
- [ ] Batch processing
- [ ] Sauvegarde intermédiaire (cache)
- [ ] Gestion timeouts LLM
- [ ] Documentation finale

### 6.2 Phase 2 : Test en Production (1 jour)

**Test sur petit document** (50-100 sections) :
```bash
# Test avec Ollama (gratuit)
python test_summarizer_manual.py

# Vérifier qualité des résumés
python test_resume.py  # Devrait avoir meilleurs scores maintenant
```

**Test sur Peirce Collected Papers** (8,425 sections) :
```bash
# Option 1: Régénérer tout (long ~3h)
python regenerate_summaries.py --doc peirce_collected_papers_fixed --provider ollama

# Option 2: Utiliser Mistral API (rapide ~45min, coût ~$10)
python regenerate_summaries.py --doc peirce_collected_papers_fixed --provider mistral
```

### 6.3 Phase 3 : Migration Base Complète (1 jour)

**Étapes** :

1. **Backup Weaviate** :
   ```bash
   # Exporter Summary collection avant modification
   python backup_summaries.py --output backups/summaries_old.json
   ```

2. **Supprimer anciennes Summary** :
   ```python
   import weaviate
   client = weaviate.connect_to_local()
   summaries = client.collections.get("Summary")
   summaries.data.delete_many(where={})  # Supprimer toutes
   ```

3. **Régénérer avec LLM** :
   ```bash
   # Pour chaque document
   for doc in peirce_collected_papers_fixed platon_menon ...; do
       python regenerate_summaries.py --doc $doc --provider ollama
   done
   ```

4. **Validation** :
   ```bash
   python test_resume.py  # Vérifier scores améliorés
   python validate_summaries.py  # Vérifier chunksCount > 0
   ```

### 6.4 Script de Régénération

**Fichier** : `regenerate_summaries.py`

```python
#!/usr/bin/env python3
"""Régénère les résumés LLM pour un document existant."""

import argparse
import json
from pathlib import Path
import weaviate
from weaviate.classes.query import Filter

from utils.llm_summarizer import generate_summaries_for_toc
from utils.weaviate_ingest import ingest_summaries


def regenerate_summaries(doc_name: str, llm_provider: str = "ollama") -> None:
    """Régénère les Summary pour un document."""

    # 1. Charger document existant
    doc_file = Path(f"output/{doc_name}/{doc_name}_chunks.json")

    if not doc_file.exists():
        raise FileNotFoundError(f"Document file not found: {doc_file}")

    with open(doc_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    toc = data['metadata']['toc']
    chunks = data['chunks']

    print(f"Document: {doc_name}")
    print(f"Sections: {len(toc)}")
    print(f"Chunks: {len(chunks)}")

    # 2. Générer résumés LLM
    print(f"\nGenerating summaries using {llm_provider}...")

    summaries_results = generate_summaries_for_toc(
        toc=toc,
        chunks=chunks,
        llm_provider=llm_provider,
        config={
            "summary_length": "medium",
            "language": "fr",
            "cache_results": True,
            "output_file": Path(f"output/{doc_name}/{doc_name}_summaries_new.json")
        }
    )

    # 3. Supprimer anciennes Summary
    print("\nDeleting old summaries from Weaviate...")

    client = weaviate.connect_to_local()
    summaries_collection = client.collections.get("Summary")

    delete_result = summaries_collection.data.delete_many(
        where=Filter.by_property("document").by_property("sourceId").equal(doc_name)
    )
    print(f"Deleted {delete_result.successful} old summaries")

    # 4. Insérer nouvelles Summary
    print("\nInserting new summaries into Weaviate...")

    summaries_text = {
        title: result["summary"]
        for title, result in summaries_results.items()
    }

    # Enrichir TOC avec concepts
    def enrich_toc(items):
        for item in items:
            title = item.get("title", "")
            if title in summaries_results:
                item["concepts"] = summaries_results[title].get("concepts", [])
            if "children" in item:
                enrich_toc(item["children"])

    enrich_toc(toc)

    count = ingest_summaries(client, doc_name, toc, summaries_text, chunks)

    print(f"\n✓ Inserted {count} new summaries")

    # 5. Statistiques
    success_count = sum(1 for r in summaries_results.values() if r["success"])
    print(f"\nSuccess rate: {success_count}/{len(summaries_results)} ({success_count/len(summaries_results)*100:.1f}%)")

    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--doc", required=True, help="Document name (e.g., peirce_collected_papers_fixed)")
    parser.add_argument("--provider", choices=["ollama", "mistral"], default="ollama")

    args = parser.parse_args()

    regenerate_summaries(args.doc, args.provider)
```

---

## 7. Métriques de Succès

### 7.1 KPIs à Mesurer

| Métrique | Avant | Cible | Mesure |
|----------|-------|-------|--------|
| **Summary.text longueur moyenne** | 13 chars | 200-400 chars | `avg(len(text))` |
| **Summary.concepts count moyenne** | 0 | 5-10 | `avg(len(concepts))` |
| **Summary.chunksCount moyenne** | 0 | 10-30 | `avg(chunksCount)` |
| **Similarité recherche Summary** | 0.71 | 0.85+ | test_resume.py |
| **Taux de succès génération** | N/A | 95%+ | `success_count / total` |
| **Temps génération (Ollama)** | N/A | <2s/section | Timer |
| **Coût génération (Mistral)** | N/A | <$0.002/section | API cost tracking |

### 7.2 Tests d'Acceptation

**Test 1** : Résumés non vides
```python
# Tous les Summary doivent avoir text > 50 chars
assert all(len(s['text']) > 50 for s in summaries.values())
```

**Test 2** : Concepts pertinents
```python
# Concepts doivent être dans le texte source
for title, result in summaries.items():
    section_text = get_section_text(title)
    for concept in result['concepts']:
        assert concept.lower() in section_text.lower()
```

**Test 3** : chunksCount exact
```python
# chunksCount doit matcher le nombre réel de chunks
for title, result in summaries.items():
    real_count = count_chunks_for_section(chunks, title)
    assert result['chunks_count'] == real_count
```

**Test 4** : Amélioration scores recherche
```python
# Scores doivent être meilleurs qu'avant
old_scores = [0.723, 0.719, 0.718, ...]  # Avant
new_scores = run_search("Peirce et la sémiose")  # Après

assert new_scores[0] > 0.85  # Top-1 devrait être >0.85
assert avg(new_scores) > avg(old_scores) + 0.10  # +10% minimum
```

---

## 8. Risques et Mitigation

| Risque | Impact | Probabilité | Mitigation |
|--------|--------|-------------|------------|
| **LLM hallucinations** | Haut | Moyen | Valider concepts contre texte source |
| **Timeout LLM Ollama** | Moyen | Haut | Retry logic + timeout configurables |
| **Coût Mistral API** | Moyen | Faible | Limite budget + estimation avant run |
| **Crash pendant génération** | Moyen | Moyen | Sauvegarde intermédiaire + resume |
| **Qualité résumés variable** | Moyen | Moyen | Prompt engineering + review sample |

---

## 9. Checklist de Déploiement

### Avant de Commencer
- [ ] Weaviate running (`docker compose up -d`)
- [ ] Ollama running avec modèle compatible (qwen2.5:7b ou deepseek-r1:14b)
- [ ] Budget Mistral API confirmé si utilisation API (~$10-16)
- [ ] Backup de la base Weaviate actuelle

### Développement
- [ ] `utils/llm_summarizer.py` créé et testé
- [ ] `tests/utils/test_llm_summarizer.py` tous verts
- [ ] `weaviate_ingest.py` modifié et testé
- [ ] `pdf_pipeline.py` modifié avec nouveau paramètre
- [ ] `regenerate_summaries.py` script créé

### Validation
- [ ] Test sur petit document (50 sections) réussi
- [ ] Scores de similarité améliorés (>0.85)
- [ ] chunksCount calculés correctement
- [ ] Concepts pertinents extraits

### Production
- [ ] Migration Peirce Collected Papers complète
- [ ] Migration autres documents complète
- [ ] Tests d'acceptation tous verts
- [ ] Documentation mise à jour

---

**Estimation temps total** : 5-6 jours
**Estimation coût** : $10-50 (selon usage Mistral API)
**ROI** : +30% précision recherche, 60% base vectorielle activée

---

**Prochaine étape** : Voulez-vous que je commence l'implémentation de `llm_summarizer.py` ? 🚀
