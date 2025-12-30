# Format JSON des Chunks - Explication Complète

## Comparaison : Format Actuel vs Format Complet

### ❌ Format ACTUEL (Peirce chunks - INCOMPLET)

```json
{
  "chunk_id": "chunk_00000",
  "text": "To erect a philosophical edifice...",
  "section": "1. PREFACE",
  "section_level": 2,
  "type": "main_content",
  "concepts": []
}
```

**Champs manquants** : `canonicalReference`, `chapterTitle`, `sectionPath`, `orderIndex`, `keywords`, `unitType`, `confidence`

### ✅ Format COMPLET (Requis pour Weaviate enrichi)

```json
{
  "chunk_id": "chunk_00000",
  "text": "To erect a philosophical edifice...",

  "section": "1. PREFACE",
  "section_level": 2,
  "type": "main_content",

  "canonicalReference": "CP 1.1",
  "chapterTitle": "Peirce: CP 1.1",
  "sectionPath": "Peirce: CP 1.1 > 1. PREFACE",
  "orderIndex": 0,

  "keywords": ["philosophical edifice", "Aristotle", "matter and form"],
  "concepts": ["philosophy as architecture", "Aristotelian foundations"],

  "unitType": "argument",
  "confidence": 0.95
}
```

---

## Description des Champs

### 🔵 Champs de BASE (générés par chunker)

| Champ | Type | Obligatoire | Description | Exemple |
|-------|------|-------------|-------------|---------|
| `chunk_id` | string | ✅ Oui | Identifiant unique du chunk | `"chunk_00000"` |
| `text` | string | ✅ Oui | Texte complet du chunk (VECTORISÉ) | `"To erect a philosophical..."` |
| `section` | string | ✅ Oui | Titre de la section source | `"1. PREFACE"` |
| `section_level` | int | ✅ Oui | Niveau hiérarchique (1-6) | `2` |
| `type` | string | ✅ Oui | Type de section | `"main_content"` |

**Types de section possibles** :
- `main_content` : Contenu principal
- `preface` : Préface
- `introduction` : Introduction
- `conclusion` : Conclusion
- `bibliography` : Bibliographie
- `appendix` : Annexes
- `notes` : Notes
- `table_of_contents` : Table des matières
- `index` : Index
- `acknowledgments` : Remerciements
- `abstract` : Résumé
- `ignore` : À ignorer

### 🟢 Champs d'ENRICHISSEMENT TOC (ajoutés par toc_enricher)

| Champ | Type | Obligatoire | Description | Exemple |
|-------|------|-------------|-------------|---------|
| `canonicalReference` | string | ⭐ **CRITIQUE** | Référence académique standard | `"CP 1.628"` |
| `chapterTitle` | string | ⭐ **CRITIQUE** | Titre du chapitre parent | `"Peirce: CP 1.1"` |
| `sectionPath` | string | ⭐ **CRITIQUE** | Chemin hiérarchique complet | `"Peirce: CP 1.628 > 628. It is..."` |
| `orderIndex` | int | ⭐ **CRITIQUE** | Index séquentiel (0-based) | `627` |

**Importance** : Ces champs permettent :
- Citation académique précise (canonicalReference)
- Navigation dans la structure du document
- Tri et organisation des résultats de recherche
- Reconstruction de l'ordre original du texte

### 🟡 Champs LLM (ajoutés par llm_validator)

| Champ | Type | Obligatoire | Description | Exemple |
|-------|------|-------------|-------------|---------|
| `keywords` | string[] | 🔶 Important | Mots-clés extraits (VECTORISÉ) | `["instincts", "sentiments", "soul"]` |
| `concepts` | string[] | 🔶 Important | Concepts philosophiques (VECTORISÉ) | `["soul as instinct", "depth psychology"]` |
| `unitType` | string | 🔶 Important | Type d'unité argumentative | `"argument"` |
| `confidence` | float | ⚪ Optionnel | Confiance LLM (0-1) | `0.95` |

**Types d'unité (unitType)** :
- `argument` : Argument complet
- `definition` : Définition d'un concept
- `example` : Exemple illustratif
- `citation` : Citation d'un autre auteur
- `question` : Question philosophique
- `objection` : Objection à un argument
- `response` : Réponse à une objection
- `analysis` : Analyse d'un concept
- `synthesis` : Synthèse d'idées
- `transition` : Transition entre sections

### 🔴 Champs de MÉTADONNÉES (au niveau document)

```json
{
  "metadata": {
    "title": "Collected papers",
    "author": "Charles Sanders PEIRCE",
    "year": 1931,
    "language": "en",
    "genre": "Philosophy"
  },
  "toc": [...],
  "hierarchy": {...},
  "pages": 548,
  "chunks_count": 5180,
  "chunks": [...]
}
```

---

## Mapping Weaviate

### Collection `Chunk`

| Champ JSON | Propriété Weaviate | Vectorisé | Indexé | Type |
|------------|-------------------|-----------|---------|------|
| `text` | `text` | ✅ Oui | ✅ Oui | text |
| `keywords` | `keywords` | ✅ Oui | ✅ Oui | text[] |
| `concepts` | `concepts` | ✅ Oui | ✅ Oui | text[] |
| `canonicalReference` | `canonicalReference` | ❌ Non | ✅ Oui | text |
| `chapterTitle` | `chapterTitle` | ❌ Non | ✅ Oui | text |
| `sectionPath` | `sectionPath` | ❌ Non | ✅ Oui | text |
| `orderIndex` | `orderIndex` | ❌ Non | ✅ Oui | int |
| `unitType` | `unitType` | ❌ Non | ✅ Oui | text |
| `section` | `section` | ❌ Non | ✅ Oui | text |
| `type` | `type` | ❌ Non | ✅ Oui | text |

**Nested Objects** (dénormalisés pour performance) :

```json
{
  "work": {
    "title": "Collected papers",
    "author": "Charles Sanders PEIRCE",
    "year": 1931,
    "language": "en",
    "genre": "Philosophy"
  },
  "document": {
    "sourceId": "peirce_collected_papers_fixed",
    "edition": "Harvard University Press"
  }
}
```

---

## Validation des Champs

### Règles de validation

1. **text** :
   - Min : 100 caractères (après nettoyage)
   - Max : 8000 caractères (limite BGE-M3)
   - Pas de texte vide ou whitespace seulement

2. **canonicalReference** :
   - Format Peirce : `CP X.YYY` (ex: `CP 1.628`)
   - Format Stephanus : `Œuvre NNNx` (ex: `Ménon 80a`)
   - Peut être `null` si non applicable

3. **orderIndex** :
   - Entier >= 0
   - Séquentiel (pas de gaps)
   - Unique par document

4. **keywords** et **concepts** :
   - Tableau de strings
   - Min : 0 éléments (peut être vide)
   - Max : 20 éléments recommandé
   - Pas de doublons

5. **unitType** :
   - Doit être l'une des valeurs de l'enum
   - Défaut : `"argument"` si non spécifié

---

## Exemple Complet pour Peirce

```json
{
  "metadata": {
    "title": "Collected papers",
    "author": "Charles Sanders PEIRCE",
    "year": 1931,
    "language": "en",
    "genre": "Philosophy"
  },
  "toc": [
    {"title": "Peirce: CP 1.1", "level": 1},
    {"title": "1. PREFACE", "level": 2},
    {"title": "Peirce: CP 1.628", "level": 1},
    {"title": "628. It is the instincts...", "level": 2}
  ],
  "hierarchy": {"type": "flat"},
  "pages": 548,
  "chunks_count": 5180,
  "chunks": [
    {
      "chunk_id": "chunk_00627",
      "text": "It is the instincts, the sentiments, that make the substance of the soul. Cognition is only its surface, its locus of contact with what is external to it. All that is admirable in it is not only ours by nature, every creature has it; but all consciousness of it, and all that makes it valuable to us, comes to us from without, through the senses.",

      "section": "628. It is the instincts, the sentiments, that make the substance of the soul",
      "section_level": 2,
      "type": "main_content",

      "canonicalReference": "CP 1.628",
      "chapterTitle": "Peirce: CP 1.1",
      "sectionPath": "Peirce: CP 1.628 > 628. It is the instincts, the sentiments, that make the substance of the soul",
      "orderIndex": 627,

      "keywords": [
        "instincts",
        "sentiments",
        "soul",
        "substance",
        "cognition",
        "surface",
        "external",
        "consciousness",
        "senses"
      ],
      "concepts": [
        "soul as instinct and sentiment",
        "cognition as surface phenomenon",
        "external origin of consciousness",
        "sensory foundation of value"
      ],

      "unitType": "argument",
      "confidence": 0.94
    }
  ],
  "cost_ocr": 1.644,
  "cost_llm": 0.523,
  "cost_total": 2.167
}
```

---

## Checklist avant Ingestion Weaviate

✅ Champs obligatoires présents :
- [ ] `text` (non vide, 100-8000 chars)
- [ ] `orderIndex` (séquentiel, unique)
- [ ] `section` et `section_level`
- [ ] `type` (valeur enum valide)

✅ Champs d'enrichissement :
- [ ] `canonicalReference` (format valide ou null)
- [ ] `chapterTitle` (présent si TOC disponible)
- [ ] `sectionPath` (hiérarchie complète)

✅ Champs LLM (si `use_llm=True`) :
- [ ] `keywords` (array de strings)
- [ ] `concepts` (array de strings)
- [ ] `unitType` (valeur enum valide)

✅ Métadonnées document :
- [ ] `metadata.author` (présent et valide)
- [ ] `metadata.title` (présent et valide)
- [ ] TOC avec au moins 1 entrée

---

## Commande pour Vérifier un Fichier

```python
python check_chunk_fields.py
```

Affiche :
- Champs présents dans les chunks
- Champs manquants pour Weaviate
- État du TOC et hiérarchie
- Exemple de premier chunk
