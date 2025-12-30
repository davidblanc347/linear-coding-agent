# 📑 Extraction de la Table des Matières (TOC)

## Vue d'ensemble

Le système Philosophia propose **deux méthodes** pour extraire la table des matières des documents PDF :

1. **Extraction LLM classique** (par défaut) - Analyse sémantique via modèle de langage
2. **Extraction avec analyse d'indentation** (recommandé) - Détection visuelle de la hiérarchie

## 🎯 Méthode recommandée : Analyse d'indentation

### Fonctionnement

Cette méthode analyse le **markdown généré par l'OCR** pour détecter la hiérarchie en comptant les espaces d'indentation :

```
Présentation                   → 0-2 espaces = niveau 1
  Qu'est-ce que la vertu ?     → 3-6 espaces = niveau 2
  Modèles de définition        → 3-6 espaces = niveau 2
Ménon ou de la vertu           → 0-2 espaces = niveau 1
```

### Avantages

- ✅ **Fiable** : Détection basée sur la position réelle du texte
- ✅ **Rapide** : Pas d'appel API supplémentaire
- ✅ **Économique** : Coût zéro (utilise l'OCR déjà effectué)
- ✅ **Hiérarchique** : Construit correctement la structure parent/enfant

### Activation

Dans l'interface Flask, cochez **"Extraction TOC améliorée (analyse indentation)"** lors de l'upload :

```python
# Via API
process_pdf(
    pdf_path,
    use_ocr_annotations=True,  # Active l'analyse d'indentation
)
```

### Algorithme

1. **Détection de la TOC** : Recherche "Table des matières" dans le markdown
2. **Extraction des entrées** : Pattern regex `Titre.....PageNumber`
3. **Comptage des espaces** :
   - `0-2 espaces` → niveau 1 (titre principal)
   - `3-6 espaces` → niveau 2 (sous-section)
   - `7+ espaces` → niveau 3 (sous-sous-section)
4. **Construction hiérarchique** : Utilisation d'une stack pour organiser parent/enfant

### Code source

- **Module principal** : `utils/toc_extractor_markdown.py`
- **Intégration pipeline** : `utils/pdf_pipeline.py` (ligne ~290)
- **Fonction clé** : `extract_toc_from_markdown()`

## 📊 Méthode alternative : Extraction LLM

### Fonctionnement

Envoie le markdown complet à un LLM (Mistral ou Ollama) qui analyse sémantiquement la structure.

### Avantages

- Comprend la structure logique même sans indentation claire
- Peut déduire la hiérarchie du contexte

### Inconvénients

- ❌ **Moins fiable** : Peut mal interpréter la structure
- ❌ **Plus lent** : Appel LLM supplémentaire
- ❌ **Plus cher** : Consomme des tokens
- ❌ **Aplatit parfois** : Tendance à mettre tout au même niveau

### Activation

C'est la méthode par défaut si l'option "Extraction TOC améliorée" n'est **pas** cochée.

## 🔧 Configuration avancée

### Paramètres personnalisables

```python
# Dans toc_extractor_markdown.py
def extract_toc_from_markdown(
    markdown_text: str,
    max_lines: int = 200,  # Lignes à analyser pour trouver la TOC
):
    # Seuils d'indentation personnalisables
    if leading_spaces <= 2:
        level = 1  # Modifier selon votre format
    elif leading_spaces <= 6:
        level = 2
    else:
        level = 3
```

### Pattern TOC personnalisable

Le pattern regex détecte les formats suivants :

- `Titre.....3` (avec points de suite)
- `Titre     3` (avec espaces)
- `Titre..3` (avec quelques points)

Pour modifier, éditer la regex dans `toc_extractor_markdown.py` :

```python
match = re.match(r'^(.+?)\s*\.{2,}\s*(\d+)\s*$', line)
```

## 📈 Résultats comparatifs

### Document test : Ménon de Platon (107 pages)

| Méthode | Entrées | Niveaux | Hiérarchie | Temps | Coût |
|---------|---------|---------|------------|-------|------|
| **LLM classique** | 11 | Tous level 1 | ❌ Plate | ~15s | +0.002€ |
| **Analyse indentation** | 11 | 2 niveaux | ✅ Correcte | <1s | 0€ |

### Exemple de structure obtenue

```json
{
  "title": "Présentation",
  "level": 1,
  "children": [
    {"title": "Qu'est-ce que la vertu ?", "level": 2},
    {"title": "Modèles de définition", "level": 2},
    {"title": "Définition de la vertu", "level": 2},
    ...
  ]
},
{
  "title": "Ménon ou de la vertu",
  "level": 1,
  "children": []
}
```

## 🐛 Dépannage

### La TOC n'est pas détectée

**Problème** : Le message "Table des matières introuvable" apparaît

**Solutions** :
1. Vérifier que le PDF contient bien une TOC explicite
2. Augmenter `max_lines` si la TOC est très loin dans le document
3. Vérifier que la TOC contient le texte "Table des matières" ou variantes

### Tous les titres sont au level 1

**Problème** : Aucune hiérarchie détectée

**Solutions** :
1. Vérifier que les titres ont une **indentation visuelle** dans le PDF original
2. Ajuster les seuils d'espaces dans le code (lignes ~90-95 de `toc_extractor_markdown.py`)
3. Examiner le fichier `.md` pour voir comment l'OCR a préservé l'indentation

### Entrées manquantes

**Problème** : Certains titres n'apparaissent pas

**Solutions** :
1. Vérifier le pattern regex (peut ne pas correspondre au format de votre TOC)
2. Regarder les logs : `logger.debug()` affiche chaque ligne analysée
3. Augmenter la limite de lignes analysées

## 🔬 Mode debug

Pour activer les logs détaillés :

```python
import logging
logging.getLogger('utils.toc_extractor_markdown').setLevel(logging.DEBUG)
```

Vous verrez :
```
Extraction TOC depuis markdown (analyse indentation)
TOC trouvée à la ligne 42
  'Présentation' → 0 espaces → level 1 (page 3)
  'Qu'est-ce que la vertu ?' → 4 espaces → level 2 (page 3)
  ...
✅ 11 entrées extraites depuis markdown
```

## 📚 Références

- **Code source** : `utils/toc_extractor_markdown.py`
- **Tests** : Testé sur Platon - Ménon, Tiercelin - La pensée-signe
- **Format supporté** : PDF avec TOC textuelle indentée
- **Langues** : Français, fonctionne avec toute langue utilisant des espaces

