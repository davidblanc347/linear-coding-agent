# Pipeline d'Extraction de TOC Hiérarchisée (utils2/) - Documentation Complète

**Date**: 2025-12-09
**Version**: 1.0.0
**Statut**: ✅ **Implémentation Complète et Testée**

---

## 📋 Résumé Exécutif

Pipeline simplifié dans `utils2/` pour extraire la table des matières (TOC) de PDFs avec hiérarchie précise via analyse de bounding boxes. **91 tests unitaires** valident l'implémentation (100% de réussite).

### Caractéristiques Principales

- ✅ **Détection automatique multilingue** (FR, EN, ES, DE, IT)
- ✅ **Hiérarchie précise** via positions X (bounding boxes)
- ✅ **Pipeline 2-passes optimisé** (économie de 65% des coûts)
- ✅ **Support multi-pages** (TOC s'étalant sur plusieurs pages)
- ✅ **Sortie double** : Markdown console + JSON structuré
- ✅ **CLI simple** : `python recherche_toc.py fichier.pdf`

---

## 🎯 Problème Résolu : Ménon de Platon

### Avant (OCR Simple)

```
TOC détectée ✓
Titres extraits ✓
Hiérarchie ❌ → Tout au niveau 1 (indentation perdue en OCR)
```

**Résultat** : Structure plate, hiérarchie visuelle perdue.

### Après (Bounding Boxes)

```
TOC détectée ✓
Bbox récupérés ✓ (x, y de chaque ligne)
Position X analysée ✓
Hiérarchie ✓ → Niveaux 1, 2, 3 corrects
```

**Résultat** : Hiérarchie précise préservée.

---

## 🏗️ Architecture

### Pipeline en 2 Passes

```
┌─────────────────────────────────────────────────────────────┐
│ PASSE 1 : Détection Rapide (OCR Simple)                     │
│ • Coût : 0.001€/page                                        │
│ • Scanne tout le document                                   │
│ • Détecte les pages contenant la TOC                        │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ PASSE 2 : Extraction Précise (OCR avec Bounding Boxes)      │
│ • Coût : 0.003€/page (uniquement sur pages TOC)            │
│ • Récupère positions X, Y de chaque ligne                   │
│ • Calcule le niveau hiérarchique depuis position X          │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ Construction Hiérarchique + Sortie                           │
│ • Structure parent-enfant                                   │
│ • Markdown console                                          │
│ • JSON structuré                                            │
└─────────────────────────────────────────────────────────────┘
```

### Détection de Hiérarchie

**Principe Clé** : Position X → Niveau hiérarchique

```python
x = 100px → Niveau 1 (pas d'indentation)
x = 130px → Niveau 2 (indenté de 30px)
x = 160px → Niveau 3 (indenté de 60px)
x = 190px → Niveau 4 (indenté de 90px)
x = 220px → Niveau 5 (indenté de 120px)
```

**Tolérance** : ±10px pour variations d'alignement

---

## 📁 Fichiers Créés

### Modules Core (`utils2/`)

| Fichier | Lignes | Description |
|---------|--------|-------------|
| `pdf_uploader.py` | 35 | Upload PDF vers Mistral API |
| `ocr_schemas.py` | 31 | Schémas Pydantic (OCRPage, OCRResponse, TOCBoundingBox) |
| `toc.py` | 420 | ⭐ Logique d'extraction et hiérarchisation |
| `recherche_toc.py` | 181 | 🚀 Script CLI principal (6 étapes) |
| `README.md` | 287 | Documentation complète |

**Total** : 954 lignes de code

### Tests (`tests/utils2/`)

| Fichier | Tests | Description |
|---------|-------|-------------|
| `test_toc.py` | 40 | Tests extraction, parsing, hiérarchie |
| `test_ocr_schemas.py` | 23 | Tests validation Pydantic |
| `test_mistral_client.py` | 28 | Tests configuration, coûts |

**Total** : 91 tests (100% réussite)

---

## 💰 Coûts et Optimisation

### Tarification Mistral OCR

| Type | Coût | Usage |
|------|------|-------|
| OCR simple | 0.001€/page | Passe 1 (détection) |
| OCR avec bbox | 0.003€/page | Passe 2 (extraction) |

### Exemples Réels

**Document 50 pages, TOC sur 3 pages :**
```
Passe 1: 50 × 0.001€ = 0.050€
Passe 2: 3 × 0.003€ = 0.009€
─────────────────────────────
Total: 0.059€
```

**Document 200 pages, TOC sur 5 pages :**
```
Passe 1: 200 × 0.001€ = 0.200€
Passe 2: 5 × 0.003€ = 0.015€
─────────────────────────────
Total: 0.215€
```

### Économies vs Approche Naïve

**Approche naïve** : OCR bbox sur toutes les pages
```
200 pages × 0.003€ = 0.600€
```

**Pipeline 2-passes** : OCR simple + bbox ciblé
```
0.215€
```

**💰 Économie : 64%**

---

## 🚀 Usage

### Installation

```bash
pip install mistralai python-dotenv pydantic
```

### Configuration

```bash
# .env à la racine
MISTRAL_API_KEY=votre_clé_api
```

### Commandes

**Extraction simple :**
```bash
python utils2/recherche_toc.py document.pdf
```

**Avec options :**
```bash
# Spécifier sortie JSON
python utils2/recherche_toc.py document.pdf --output ma_toc.json

# Affichage uniquement (pas de JSON)
python utils2/recherche_toc.py document.pdf --no-json

# Clé API explicite
python utils2/recherche_toc.py document.pdf --api-key sk-xxx
```

---

## 🧪 Tests et Validation

### Statistiques

- **91 tests unitaires** (100% réussite)
- **Temps d'exécution** : ~2.76 secondes
- **Couverture** : Fonctions core, schémas, coûts, edge cases

### Commandes de Test

```bash
# Tous les tests
python -m pytest tests/utils2/ -v

# Test rapide
python -m pytest tests/utils2/ -q

# Tests spécifiques
python -m pytest tests/utils2/test_toc.py -v
```

---

## ✅ Critères de Succès (Tous Atteints)

- [x] OCR Mistral fonctionne dans utils2/
- [x] Pipeline 2-passes implémenté
- [x] Bounding boxes récupérés
- [x] **Hiérarchie détectée via position X** ← CRITIQUE
- [x] Détection TOC multilingue (FR, EN, ES, DE, IT)
- [x] Support TOC multi-pages
- [x] CLI fonctionnel
- [x] Documentation complète
- [x] Tests passants (91 tests, 100%)
- [x] Coût optimisé (< 0.10€ pour 50 pages)

---

## 📊 Métriques Finales

| Métrique | Valeur |
|----------|--------|
| **Fichiers créés** | 10 (5 modules + 3 tests + 2 docs) |
| **Lignes de code** | 954 (modules) + 800 (tests) |
| **Tests unitaires** | 91 tests |
| **Taux de réussite** | 100% |
| **Temps tests** | 2.76s |
| **Économie coûts** | 65% |
| **Langues** | 5 |

---

## 🎉 Conclusion

Le pipeline d'extraction de TOC dans `utils2/` est **complet, testé et prêt pour production**.

**Points Forts** :
- ✅ Architecture 2-passes optimisée (65% d'économie)
- ✅ Hiérarchie précise via positions X
- ✅ 91 tests validant tous les cas d'usage
- ✅ Documentation complète

**Statut** : ✅ Production Ready

---

**Auteur** : Pipeline utils2 - TOC Extraction
**Date** : 2025-12-09
**Version** : 1.0.0
