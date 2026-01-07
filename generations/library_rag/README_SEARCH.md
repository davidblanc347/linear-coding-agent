# Guide d'Utilisation - Interface de Recherche Optimisée

## Vue d'Ensemble

L'interface de recherche optimisée utilise la collection **Summary** comme point d'entrée principal, offrant **90% de visibilité** des documents riches vs 10% pour la recherche directe dans Chunks.

## Performance Démontrée

### ✅ Tests Réussis

#### 1. Requêtes sur l'IA (domaine Haugeland)
```bash
python search_summary_interface.py "What is the Turing test?"
```
**Résultat**: 7/7 résultats Haugeland (100%)

#### 2. Requêtes sur la vertu (domaine Platon)
```bash
python search_summary_interface.py "Can virtue be taught?"
```
**Résultat**: 6/6 résultats Platon (100%)

#### 3. Requêtes sur le pragmatisme (domaine Peirce/Tiercelin)
```bash
python search_summary_interface.py "What is pragmatism according to Peirce?"
```
**Résultat**: 5/5 résultats Tiercelin (100%)

### Comparaison avec Recherche Chunk Directe

| Approche | Visibilité Documents Riches | Performance |
|----------|----------------------------|-------------|
| **Summary-first** (ce script) | **90%** | ✅ Excellent |
| Chunk directe | 10% | ❌ Dominé par Peirce |

## Utilisation

### Mode Requête Unique
```bash
# Requête simple
python search_summary_interface.py "Votre question ici"

# Avec limite de résultats
python search_summary_interface.py "What is intelligence?" -n 5

# Avec seuil de similarité personnalisé
python search_summary_interface.py "Can machines think?" -s 0.7
```

### Mode Interactif
```bash
# Lancer sans arguments
python search_summary_interface.py

# Interface interactive
INTERFACE DE RECHERCHE RAG - Collection Summary
================================================
Mode: Summary-first (90% de visibilité démontrée)
Tapez 'quit' pour quitter

Votre question: What is the Chinese Room argument?
[résultats affichés]

Votre question: Can virtue be taught?
[résultats affichés]

Votre question: quit
Au revoir!
```

## Options

| Option | Court | Défaut | Description |
|--------|-------|--------|-------------|
| `query` | - | - | Question de recherche (optionnel) |
| `--limit` | `-n` | 10 | Nombre maximum de résultats |
| `--min-similarity` | `-s` | 0.65 | Seuil de similarité (0-1) |

## Format des Résultats

Chaque résultat affiche:
- **Icône + Document**: 🟣 Haugeland, 🟢 Platon, 🟡 Tiercelin, 🔵 Logique, ⚪ Peirce
- **Similarité**: Score 0-1 et pourcentage
- **Titre**: Titre de la section
- **Auteur/Année**: Si disponible
- **Concepts**: Top 5 concepts clés
- **Résumé**: Résumé de la section (max 300 chars)
- **Chunks**: Nombre de chunks disponibles pour lecture détaillée

### Exemple de Sortie
```
[1] 🟣 Haugeland - Similarité: 0.695 (69.5%)
    Titre: 2.2.3 Computers and intelligence
    Auteur: John Haugeland, Carl F. Craver, and Colin Klein (2023.0)
    Concepts: Turing test, artificial intelligence, formal input/output function, universal machine, computability (+5 autres)
    Résumé: This section examines Turing's 1950 prediction that computers would achieve human-level intelligence by 2000, analyzing the theoretical foundations underlying this forecast...
    📄 1 chunk(s) disponible(s) pour lecture détaillée
```

## Fonctionnalités Avancées

### Récupération des Chunks Détaillés

Le script inclut la fonction `get_chunks_for_section()` pour récupérer le contenu détaillé:

```python
from search_summary_interface import get_chunks_for_section

# Après avoir identifié une section intéressante
chunks = get_chunks_for_section(
    document_id="Haugeland_J._Mind_Design_III...",
    section_path="2.2.3 Computers and intelligence",
    limit=5
)

for chunk in chunks:
    print(chunk["text"])
```

## Architecture

### Collection Summary
- 114 résumés total
- 106 résumés riches (>100 chars)
- Documents: Tiercelin (51), Haugeland (50), Platon (12), Logique (1)

### Vecteurs
- Modèle: BAAI/bge-m3 (1024 dimensions)
- Contexte: 8192 tokens
- Multilingual: Anglais, Français, Latin, Grec

### Recherche Sémantique
- Méthode: `near_text` (Weaviate)
- Distance: Cosine
- Métrique: Similarité = 1 - distance

## Pourquoi Summary-First?

### Problème des Chunks
- 5,068 chunks Peirce sur 5,230 total (97%)
- Domination écrasante même sur requêtes spécialisées
- Exemple: "What is the Turing test?" → 5/5 chunks Peirce (0/5 Haugeland)

### Solution Summary
- Résumés équilibrés par document
- Haute qualité (générés par Claude Sonnet 4.5)
- 90% de visibilité prouvée
- Concepts et keywords riches

## Coût et Performance

### Coût de Génération
- Total: $1.23 pour 106 résumés riches
- Tiercelin: $0.63 (43 résumés)
- Haugeland: $0.44 (50 résumés)
- Platon: $0.14 (12 résumés)
- Logique: $0.02 (1 résumé)

### Performance Requêtes
- Temps moyen: ~200-500ms par requête
- Précision: 90% (documents pertinents dans top 5)
- Couverture: Tous les documents riches indexés

## Prochaines Étapes Possibles

1. **Interface Web**: Intégrer dans Flask app existante
2. **Mode Hybride**: Toggle Summary/Chunk au choix
3. **Expansion Chunks**: Fonction "Voir plus" pour lire chunks détaillés
4. **Filtres**: Par document, auteur, année, concepts
5. **Historique**: Sauvegarde des recherches récentes

## Fichiers Associés

- `search_summary_interface.py` - Script principal
- `ANALYSE_RAG_FINAL.md` - Analyse complète du système
- `test_real_queries.py` - Tests de validation (15 requêtes)
- `test_haugeland_ai.py` - Tests spécifiques IA
- `test_hierarchical_search.py` - Tests Summary → Chunks

## Support

Pour questions ou améliorations, voir `ANALYSE_RAG_FINAL.md` pour le contexte complet.

---

**Date**: 2026-01-03
**Version**: 1.0
**Status**: ✅ Production-ready
