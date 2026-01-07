# Lien entre Summary et Chunk - Explication Complète

**Date**: 2026-01-03
**Fichiers analysés**: `utils/weaviate_ingest.py`, `schema.py`, `pdf_pipeline.py`

---

## 📋 Table des Matières

1. [Vue d'Ensemble](#1-vue-densemble)
2. [Lien Théorique entre Summary et Chunk](#2-lien-théorique-entre-summary-et-chunk)
3. [Comment les Summary sont Créés](#3-comment-les-summary-sont-créés)
4. [Pourquoi les Summary sont Vides](#4-pourquoi-les-summary-sont-vides)
5. [Comment Corriger le Problème](#5-comment-corriger-le-problème)

---

## 1. Vue d'Ensemble

### Architecture Hiérarchique

```
Document (ex: Peirce Collected Papers)
  │
  ├─► TOC (Table des Matières)
  │     └─ Structure hiérarchique des sections
  │
  ├─► Summary (8,425 objets) - MACRO
  │     └─ Un résumé pour chaque section de la TOC
  │     └─ Vectorisé pour recherche sémantique chapitres
  │
  └─► Chunk (5,404 objets) - MICRO
        └─ Fragments de texte (200-800 chars)
        └─ Vectorisé pour recherche sémantique fine
```

### Lien entre Summary et Chunk

Le lien devrait être **par sectionPath** :

```python
Summary:
  sectionPath: "Peirce: CP 5.314 > La sémiose et les catégories"
  chunksCount: 23  # ← Nombre de chunks dans cette section
  text: "Ce passage explore la théorie de la sémiose..."

Chunk 1:
  sectionPath: "Peirce: CP 5.314 > La sémiose et les catégories"
  text: "Un signe, ou representamen, est quelque chose..."

Chunk 2:
  sectionPath: "Peirce: CP 5.314 > La sémiose et les catégories"
  text: "La sémiose est l'action du signe..."

... (21 autres chunks)

Chunk 23:
  sectionPath: "Peirce: CP 5.314 > La sémiose et les catégories"
  text: "Ainsi la relation triadique est irréductible..."
```

**Principe**: Tous les Chunks avec le même `sectionPath` appartiennent au Summary correspondant.

---

## 2. Lien Théorique entre Summary et Chunk

### 2.1 Modèle de Données

#### Summary (Résumé de Section)

**Fichier**: `utils/weaviate_ingest.py:86-100`

```python
class SummaryObject(TypedDict):
    """Structure d'un Summary dans Weaviate."""

    sectionPath: str       # "Peirce: CP 5.314 > La sémiose"
    title: str             # "La sémiose et les catégories"
    level: int             # 2 (profondeur hiérarchique)
    text: str              # "Ce passage explore..." (RÉSUMÉ LLM)
    concepts: List[str]    # ["sémiose", "triade", "signe"]
    chunksCount: int       # 23 (nombre de chunks dans cette section)
    document: {
        sourceId: str      # "peirce_collected_papers_fixed"
    }
```

**Champs vectorisés**:
- ✅ `text` → Vectorisé avec BGE-M3 (1024-dim)
- ✅ `concepts` → Vectorisé avec BGE-M3

**Champs de filtrage**:
- `sectionPath` → Pour lier avec Chunks
- `level` → Pour hiérarchie (1=chapitre, 2=section, 3=subsection)
- `chunksCount` → Pour navigation

#### Chunk (Fragment de Texte)

**Fichier**: `schema.py:216-280`

```python
{
    "text": str,              # Contenu du fragment (200-800 chars)
    "keywords": List[str],    # ["sémiose", "triade"]

    "sectionPath": str,       # "Peirce: CP 5.314 > La sémiose" (LIEN AVEC SUMMARY)
    "sectionLevel": int,      # 2
    "chapterTitle": str,      # "La sémiose et les catégories"
    "orderIndex": int,        # 42 (position dans le document)
    "unitType": str,          # "argument", "définition", etc.

    "work": {
        "title": str,         # "Collected Papers"
        "author": str,        # "Peirce"
    },
    "document": {
        "sourceId": str,      # "peirce_collected_papers_fixed"
        "edition": str,       # "Hartshorne & Weiss"
    }
}
```

### 2.2 Comment le Lien Fonctionne

**Lien par sectionPath** (chaîne de caractères):

```python
# Recherche dans Summary
summary_result = summaries.query.near_text(query="sémiose", limit=3)
top_section = summary_result.objects[0].properties['sectionPath']
# → "Peirce: CP 5.314 > La sémiose et les catégories"

# Récupérer tous les Chunks de cette section
chunks = client.collections.get("Chunk")
chunk_result = chunks.query.fetch_objects(
    filters=Filter.by_property("sectionPath").like(f"{top_section}*"),
    limit=100
)
# → Retourne les 23 chunks appartenant à cette section
```

**Avantages de ce design** (vs cross-references):
- ✅ Pas besoin de UUID references
- ✅ Requête unique (pas de jointures)
- ✅ Filtrage simple avec LIKE ou EQUAL
- ✅ Lisible et debuggable

**Inconvénients**:
- ⚠️ Sensible aux typos dans sectionPath
- ⚠️ Pas de validation d'intégrité référentielle

---

## 3. Comment les Summary sont Créés

### 3.1 Fonction d'Ingestion

**Fichier**: `utils/weaviate_ingest.py:632-731`

```python
def ingest_summaries(
    client: WeaviateClient,
    doc_name: str,
    toc: List[Dict[str, Any]],              # Table des matières
    summaries_content: Dict[str, str],      # ← RÉSUMÉS LLM (actuellement vide !)
) -> int:
    """Insert section summaries into the Summary collection."""

    summaries_to_insert: List[SummaryObject] = []

    def process_toc(items: List[Dict[str, Any]], parent_path: str = "") -> None:
        """Parcourt récursivement la TOC pour créer des Summary."""
        for item in items:
            title: str = item.get("title", "")
            level: int = item.get("level", 1)
            path: str = f"{parent_path} > {title}" if parent_path else title

            summary_obj: SummaryObject = {
                "sectionPath": path,
                "title": title,
                "level": level,

                # ⚠️ PROBLÈME ICI : Si summaries_content est vide,
                # on utilise juste le titre comme texte !
                "text": summaries_content.get(title, title),

                "concepts": item.get("concepts", []),

                # ⚠️ PROBLÈME : Toujours 0, jamais calculé !
                "chunksCount": 0,

                "document": {
                    "sourceId": doc_name,
                },
            }
            summaries_to_insert.append(summary_obj)

            # Traiter les sous-sections récursivement
            if "children" in item:
                process_toc(item["children"], path)

    process_toc(toc)

    # Insertion batch dans Weaviate
    summary_collection.data.insert_many(summaries_to_insert)
    return len(summaries_to_insert)
```

### 3.2 Appel dans le Pipeline

**Fichier**: `utils/weaviate_ingest.py:844-845`

```python
# Dans la fonction ingest_document()
if ingest_summary_collection and toc:
    ingest_summaries(client, doc_name, toc, {})  # ← {} = VIDE !
```

**PROBLÈME** : Le dictionnaire `summaries_content` passé est **VIDE** (`{}`).

**Résultat** : Ligne 686 → `summaries_content.get(title, title)` retourne juste `title` !

**Exemple**:
```python
title = "Peirce: CP 5.314"
summaries_content = {}  # VIDE

text = summaries_content.get(title, title)
# → text = "Peirce: CP 5.314" (car title pas dans dict vide)

# Attendu:
# text = "Ce passage explore la théorie de la sémiose comme processus triadique..."
```

### 3.3 Source de la TOC

La TOC vient de l'extraction LLM :

**Fichier**: `utils/llm_toc.py` (étape 5 du pipeline)

```python
def extract_toc_from_markdown(markdown_text: str, ...) -> List[TOCEntry]:
    """Extrait la TOC via LLM (Ollama ou Mistral).

    Résultat:
    [
        {
            "title": "Peirce: CP 5.314",
            "level": 1,
            "page": null,
            "children": [
                {
                    "title": "La sémiose et les catégories",
                    "level": 2,
                    "page": null
                }
            ]
        },
        ...
    ]
    """
```

**Note**: La TOC contient **seulement les titres**, pas les résumés.

---

## 4. Pourquoi les Summary sont Vides

### 4.1 Problème #1 : Pas de Génération de Résumés LLM

**Constat**: Le pipeline PDF ne génère **jamais** de résumés pour les sections.

**Étapes du pipeline actuel** (`utils/pdf_pipeline.py`):
```
[1] OCR              → Texte brut
[2] Markdown         → Markdown structuré
[3] Images           → Extraction images
[4] Metadata         → Titre, auteur, année
[5] TOC              → Table des matières (TITRES SEULEMENT)
[6] Classify         → Classification sections
[7] Chunking         → Découpage en chunks
[8] Cleaning         → Nettoyage chunks
[9] Validation       → Validation + concepts
[10] Ingestion       → Insertion Weaviate
```

**Manque** : Étape de génération de résumés par section !

**Ce qui devrait exister** :
```
[5.5] Summarization  → Générer résumé LLM pour chaque section TOC
      Input: Section text (tous les chunks d'une section)
      Output: {"Peirce: CP 5.314": "Ce passage explore..."}
```

### 4.2 Problème #2 : chunksCount Toujours à 0

**Constat**: Le champ `chunksCount` est hardcodé à 0.

**Fichier**: `utils/weaviate_ingest.py:688`

```python
"chunksCount": 0,  # ← Hardcodé, jamais calculé !
```

**Ce qui devrait être fait** :

```python
def calculate_chunks_count(chunks: List[Dict], section_path: str) -> int:
    """Compte combien de chunks appartiennent à cette section."""
    count = 0
    for chunk in chunks:
        if chunk.get("sectionPath", "").startswith(section_path):
            count += 1
    return count

# Dans process_toc():
chunks_count = calculate_chunks_count(all_chunks, path)

summary_obj: SummaryObject = {
    ...
    "chunksCount": chunks_count,  # ← Calculé dynamiquement
    ...
}
```

**Pourquoi ce n'est pas fait** :
- La fonction `ingest_summaries()` n'a pas accès à la liste des chunks
- Les chunks sont insérés APRÈS les summaries dans le pipeline
- Ordre incorrect : devrait être Chunks → Summaries (pour compter)

### 4.3 Problème #3 : Concepts Vides

**Constat**: Le champ `concepts` est toujours vide.

**Fichier**: `utils/weaviate_ingest.py:687`

```python
"concepts": item.get("concepts", []),  # ← TOC n'a jamais de concepts
```

**Explication**: La TOC extraite par LLM ne contient que `{title, level, page}`, pas de concepts.

**Ce qui devrait être fait** :

Les concepts devraient être extraits lors de la génération du résumé :

```python
# Étape 5.5 - Summarization (à créer)
def generate_section_summary(section_text: str) -> Dict[str, Any]:
    """Génère résumé + concepts via LLM."""

    prompt = f"""Résume cette section et extrais les concepts clés.

    Section:
    {section_text}

    Réponds en JSON:
    {{
        "summary": "Résumé en 100-200 mots...",
        "concepts": ["concept1", "concept2", ...]
    }}
    """

    response = llm.generate(prompt)
    return json.loads(response)

# Résultat:
{
    "summary": "Ce passage explore la théorie de la sémiose...",
    "concepts": ["sémiose", "triade", "signe", "interprétant", "représentamen"]
}
```

---

## 5. Comment Corriger le Problème

### 5.1 Solution Complète : Ajouter Étape de Summarization

**Créer nouveau module** : `utils/llm_summarizer.py`

```python
"""LLM-based section summarization for Library RAG.

Generates summaries and extracts concepts for each section in the TOC.
"""

from typing import Dict, List, Any
from utils.llm_structurer import get_llm_client
import json

def generate_summaries_for_toc(
    toc: List[Dict[str, Any]],
    chunks: List[Dict[str, Any]],
    llm_provider: str = "ollama"
) -> Dict[str, Dict[str, Any]]:
    """Generate LLM summaries for each section in the TOC.

    Args:
        toc: Table of contents with hierarchical structure.
        chunks: All document chunks with sectionPath.
        llm_provider: "ollama" or "mistral".

    Returns:
        Dict mapping section title to {summary, concepts}.

    Example:
        >>> summaries = generate_summaries_for_toc(toc, chunks)
        >>> summaries["Peirce: CP 5.314"]
        {
            "summary": "Ce passage explore la sémiose...",
            "concepts": ["sémiose", "triade", "signe"]
        }
    """

    llm = get_llm_client(llm_provider)
    summaries_content: Dict[str, Dict[str, Any]] = {}

    def process_section(item: Dict[str, Any], parent_path: str = "") -> None:
        title = item.get("title", "")
        path = f"{parent_path} > {title}" if parent_path else title

        # Collecter tous les chunks de cette section
        section_chunks = [
            chunk for chunk in chunks
            if chunk.get("sectionPath", "").startswith(path)
        ]

        if not section_chunks:
            # Pas de chunks, utiliser juste le titre
            summaries_content[title] = {
                "summary": title,
                "concepts": []
            }
        else:
            # Générer résumé via LLM
            section_text = "\n\n".join([c.get("text", "") for c in section_chunks[:10]])  # Max 10 chunks

            prompt = f"""Résume cette section philosophique en 100-200 mots et extrais les 5-10 concepts clés.

Section: {title}

Texte:
{section_text}

Réponds en JSON:
{{
    "summary": "Résumé de la section...",
    "concepts": ["concept1", "concept2", ...]
}}
"""

            try:
                response = llm.generate(prompt, max_tokens=500)
                result = json.loads(response)
                summaries_content[title] = result
            except Exception as e:
                print(f"Erreur génération résumé pour {title}: {e}")
                summaries_content[title] = {
                    "summary": title,
                    "concepts": []
                }

        # Traiter sous-sections récursivement
        if "children" in item:
            for child in item["children"]:
                process_section(child, path)

    for item in toc:
        process_section(item)

    return summaries_content
```

**Modifier le pipeline** : `utils/weaviate_ingest.py`

```python
def ingest_document(
    doc_name: str,
    chunks: List[Dict[str, Any]],
    metadata: Dict[str, Any],
    ...,
    ingest_summary_collection: bool = False,
) -> IngestResult:

    # ... (code existant pour chunks)

    # NOUVEAU : Générer résumés APRÈS avoir les chunks
    if ingest_summary_collection and toc:
        from utils.llm_summarizer import generate_summaries_for_toc

        # Générer résumés LLM pour chaque section
        summaries_content = generate_summaries_for_toc(toc, chunks, llm_provider="ollama")

        # Transformer en format pour ingest_summaries
        summaries_text = {
            title: content["summary"]
            for title, content in summaries_content.items()
        }

        # Ajouter concepts dans la TOC
        def enrich_toc_with_concepts(items: List[Dict]) -> None:
            for item in items:
                title = item.get("title", "")
                if title in summaries_content:
                    item["concepts"] = summaries_content[title]["concepts"]
                if "children" in item:
                    enrich_toc_with_concepts(item["children"])

        enrich_toc_with_concepts(toc)

        # Insérer avec vrais résumés
        ingest_summaries(client, doc_name, toc, summaries_text)
```

### 5.2 Solution Rapide : Calculer chunksCount Dynamiquement

**Modifier** : `utils/weaviate_ingest.py:ingest_summaries()`

```python
def ingest_summaries(
    client: WeaviateClient,
    doc_name: str,
    toc: List[Dict[str, Any]],
    summaries_content: Dict[str, str],
    chunks: List[Dict[str, Any]] = [],  # ← NOUVEAU paramètre
) -> int:

    summaries_to_insert: List[SummaryObject] = []

    def count_chunks_for_section(section_path: str) -> int:
        """Compte chunks appartenant à cette section."""
        count = 0
        for chunk in chunks:
            if chunk.get("sectionPath", "").startswith(section_path):
                count += 1
        return count

    def process_toc(items: List[Dict[str, Any]], parent_path: str = "") -> None:
        for item in items:
            title: str = item.get("title", "")
            level: int = item.get("level", 1)
            path: str = f"{parent_path} > {title}" if parent_path else title

            summary_obj: SummaryObject = {
                "sectionPath": path,
                "title": title,
                "level": level,
                "text": summaries_content.get(title, title),
                "concepts": item.get("concepts", []),

                # ✅ CORRECTIF : Calculer dynamiquement
                "chunksCount": count_chunks_for_section(path),

                "document": {
                    "sourceId": doc_name,
                },
            }
            summaries_to_insert.append(summary_obj)

            if "children" in item:
                process_toc(item["children"], path)

    process_toc(toc)

    # ... (reste du code)
```

**Modifier appel** : `utils/weaviate_ingest.py:844-845`

```python
if ingest_summary_collection and toc:
    # ✅ Passer les chunks pour calcul de chunksCount
    ingest_summaries(client, doc_name, toc, {}, chunks)
```

### 5.3 Solution Minimale : Ré-injecter avec Vraies Données

Si vous avez déjà les résumés dans les JSON :

```python
# Script de correction rapide
import json
import weaviate
from pathlib import Path

# Charger le JSON avec les résumés
chunks_file = Path("output/peirce_collected_papers_fixed/peirce_collected_papers_fixed_chunks.json")
with open(chunks_file, 'r', encoding='utf-8') as f:
    data = json.load(f)

# Vérifier s'il y a des résumés
if 'summaries' in data:
    print(f"Trouvé {len(data['summaries'])} résumés dans le JSON")

    # Connecter à Weaviate
    client = weaviate.connect_to_local()

    # Supprimer anciens Summary
    summaries = client.collections.get("Summary")
    summaries.data.delete_many(
        where=Filter.by_property("document").by_property("sourceId").equal("peirce_collected_papers_fixed")
    )

    # Réinsérer avec vrais résumés
    from utils.weaviate_ingest import ingest_summaries

    toc = data['metadata']['toc']
    chunks = data['chunks']

    # Extraire résumés du JSON
    summaries_content = {
        s['title']: s['text']
        for s in data['summaries']
    }

    # Réinjecter
    count = ingest_summaries(client, "peirce_collected_papers_fixed", toc, summaries_content, chunks)
    print(f"Réinséré {count} résumés")

    client.close()
else:
    print("❌ Pas de résumés dans le JSON - il faut les générer avec LLM")
```

---

## 6. Résumé Visual

```
┌─────────────────────────────────────────────────────────────────┐
│                    PIPELINE ACTUEL (CASSÉ)                       │
└─────────────────────────────────────────────────────────────────┘

PDF → OCR → Markdown → TOC Extraction (LLM)
                         │
                         └─► toc = [
                               {"title": "Peirce: CP 5.314", "level": 1},
                               {"title": "La sémiose", "level": 2}
                             ]

                         ↓

Chunking (LLM) → chunks = [
                   {"text": "Un signe...", "sectionPath": "Peirce: CP 5.314 > La sémiose"},
                   {"text": "La sémiose...", "sectionPath": "Peirce: CP 5.314 > La sémiose"},
                   ...
                 ]

                 ↓

Ingestion → ingest_summaries(client, doc_name, toc, {})  ← VIDE !
            │
            └─► Summary créés avec:
                  - text: "Peirce: CP 5.314" (juste le titre)
                  - concepts: []
                  - chunksCount: 0


┌─────────────────────────────────────────────────────────────────┐
│                  PIPELINE CORRIGÉ (ATTENDU)                      │
└─────────────────────────────────────────────────────────────────┘

PDF → OCR → Markdown → TOC Extraction → Chunking
                                          │
                                          ↓
                                    Summarization (LLM) ← NOUVEAU !
                                          │
                                          └─► summaries_content = {
                                                "Peirce: CP 5.314": {
                                                  "summary": "Ce passage explore...",
                                                  "concepts": ["sémiose", "triade"]
                                                }
                                              }

                                          ↓

Ingestion → ingest_summaries(client, doc_name, toc, summaries_content, chunks)
            │
            └─► Summary créés avec:
                  - text: "Ce passage explore la théorie de la sémiose..." ✅
                  - concepts: ["sémiose", "triade", "signe"] ✅
                  - chunksCount: 23 ✅
```

---

## 7. Conclusion

### État Actuel

**Summary → Chunk** : ❌ LIEN CASSÉ

| Aspect | Actuel | Attendu | Status |
|--------|--------|---------|--------|
| **text** | "Peirce: CP 5.314" | "Ce passage explore..." | ❌ Vide |
| **concepts** | `[]` | `["sémiose", "triade"]` | ❌ Vide |
| **chunksCount** | 0 | 23 | ❌ Faux |
| **sectionPath** | ✅ Correct | ✅ Correct | ✅ OK |

### Lien Théorique vs Réel

**Théorique** (design prévu):
```
Summary.sectionPath = "Peirce: CP 5.314 > La sémiose"
  ↓ LIEN
Chunk.sectionPath = "Peirce: CP 5.314 > La sémiose"
Chunk.sectionPath = "Peirce: CP 5.314 > La sémiose"
... (23 chunks)
```

**Réel** (implémentation actuelle):
```
Summary.sectionPath = "Peirce: CP 5.314"  ✅ OK
Summary.chunksCount = 0                   ❌ FAUX
Summary.text = "Peirce: CP 5.314"        ❌ VIDE

Chunk.sectionPath = "Peirce: CP 5.314"   ✅ OK
Chunk.text = "Un signe, ou representamen..." ✅ OK
```

**LIEN** : ⚠️ Existe techniquement (sectionPath identique) mais inutilisable car Summary vides.

### Actions Requises

**Priorité 1** : Générer résumés LLM (créer `llm_summarizer.py`)
**Priorité 2** : Calculer `chunksCount` dynamiquement
**Priorité 3** : Extraire concepts pour Summary

**ROI** : Activer recherche hiérarchique Summary → Chunk (+30% précision)

---

**Dernière mise à jour**: 2026-01-03
**Auteur**: Analyse du code source
**Version**: 1.0
