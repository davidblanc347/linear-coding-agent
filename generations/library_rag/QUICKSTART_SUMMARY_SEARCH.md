# Quickstart - Recherche Summary

Guide rapide pour utiliser la nouvelle interface de recherche optimisée.

---

## 🚀 Démarrage Rapide

### 1. Démarrer Weaviate (si pas déjà lancé)
```bash
docker compose up -d
```

### 2. Démarrer l'application Flask
```bash
cd generations/library_rag
python flask_app.py
```

### 3. Accéder à l'interface
Ouvrir dans le navigateur: **http://localhost:5000**

### 4. Utiliser la Recherche Summary
1. Cliquer sur le menu ☰ (hamburger) en haut à gauche
2. Cliquer sur **"📚 Recherche Résumés"** (badge 90%)
3. Entrer une question et cliquer sur **"🔍 Rechercher"**

---

## 💡 Exemples de Recherche

### IA et Philosophie de l'Esprit (Haugeland 🟣)
```
What is the Turing test?
Can machines think?
What is a physical symbol system?
How do connectionist networks work?
```

**Résultat attendu**: Résumés de Haugeland avec icône 🟣

### Vertu et Connaissance (Platon 🟢)
```
Can virtue be taught?
What is the theory of recollection?
How does Socrates define virtue?
```

**Résultat attendu**: Résumés de Platon (Ménon) avec icône 🟢

### Pragmatisme et Sémiotique (Tiercelin 🟡)
```
What is pragmatism according to Peirce?
How does thought work as a sign?
What is the relationship between doubt and inquiry?
```

**Résultat attendu**: Résumés de Tiercelin avec icône 🟡

---

## 🎨 Interface Visuelle

### Ce que vous verrez:

```
┌──────────────────────────────────────────────────────────┐
│ 📚 Recherche par Résumés                                 │
│                                                          │
│ ┌────────────────────────────────────────────────────┐  │
│ │ ✨ Nouvelle interface de recherche optimisée       │  │
│ │ Performance: [📊 90% de visibilité] vs [📉 10%]    │  │
│ └────────────────────────────────────────────────────┘  │
│                                                          │
│ ┌─ Formulaire de recherche ─────────────────────────┐   │
│ │ Votre question: [What is the Turing test?]       │   │
│ │ Nombre: [10 résumés ▼]  Seuil: [65% ▼]           │   │
│ │ [🔍 Rechercher] [Réinitialiser] [🔄 Classique]   │   │
│ └───────────────────────────────────────────────────┘   │
│                                                          │
│ 3 résumés trouvés [📚 Recherche par Résumés]            │
│                                                          │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ 🟣 [Haugeland] John Haugeland (2023) ⚡ 69.5%       │ │
│ │ Computers and intelligence                          │ │
│ │                                                     │ │
│ │ "This section examines Turing's 1950 prediction... │ │
│ │  analyzing the theoretical foundations..."          │ │
│ │                                                     │ │
│ │ Concepts: Turing test | AI | formal function |... │ │
│ │ 📄 1 passage détaillé   Section: 2.2.3...          │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                          │
│ [Plus de résultats...]                                   │
└──────────────────────────────────────────────────────────┘
```

---

## 📊 Comparaison des Modes

| Fonctionnalité | Summary (Nouveau) | Chunk (Ancien) |
|----------------|-------------------|----------------|
| **Visibilité documents riches** | 90% ✅ | 10% ❌ |
| **Vue d'ensemble** | Résumés de sections | Passages courts |
| **Métadonnées** | Riches (concepts, auteur) | Basiques |
| **Exploration** | Excellente | Difficile |
| **Précision citations** | Moyenne | Excellente |
| **Temps de réponse** | Rapide (~300ms) | Rapide (~300ms) |

### Quand utiliser Summary? ✅
- Questions générales
- Découverte de sujets
- Vue d'ensemble d'un document
- Identification de sections pertinentes

### Quand utiliser Chunk? 🔍
- Besoin de citations exactes
- Recherche très précise
- Analyse détaillée d'un passage

---

## 🎯 Paramètres Recommandés

### Exploration Large
```
Résultats: 15-20 résumés
Seuil: 60-65% (plus large)
```
**Utilisation**: Découverte de sujets, brainstorming

### Recherche Précise
```
Résultats: 5-10 résumés
Seuil: 70-75% (très précis)
```
**Utilisation**: Questions spécifiques, confirmation d'informations

### Par Défaut (Recommandé)
```
Résultats: 10 résumés
Seuil: 65% (équilibré)
```
**Utilisation**: Usage général, meilleur compromis

---

## 🔧 Troubleshooting

### "Aucun résumé trouvé"
**Solutions**:
1. Réduire le seuil de similarité (essayer 60%)
2. Reformuler la question en anglais/français
3. Utiliser des termes plus généraux
4. Vérifier que la question porte sur les documents disponibles

### Page ne charge pas
**Solutions**:
1. Vérifier que Flask tourne: `http://localhost:5000`
2. Vérifier que Weaviate tourne: `docker ps | grep weaviate`
3. Consulter les logs Flask dans le terminal

### Résultats non pertinents
**Solutions**:
1. Augmenter le seuil de similarité (essayer 70-75%)
2. Réduire le nombre de résultats
3. Être plus spécifique dans la question

---

## 📚 Documents Disponibles

### 🟣 Haugeland - Mind Design III
**Sujets**: IA, philosophie de l'esprit, Turing test, réseaux de neurones, computation
**Résumés**: 50 sections

### 🟢 Platon - Ménon
**Sujets**: Vertu, connaissance, réminiscence, Socrate, enseignement
**Résumés**: 12 sections

### 🟡 Tiercelin - La Pensée-Signe
**Sujets**: Pragmatisme, Peirce, sémiotique, pensée, signes
**Résumés**: 51 sections

### 🔵 Peirce - La Logique de la Science
**Sujets**: Croyance, doute, méthode scientifique, fixation des croyances
**Résumés**: 1 section

**Total**: 114 résumés (106 riches) indexés et searchables

---

## 🎓 Conseils d'Utilisation

### 1. Formuler de Bonnes Questions
✅ **Bon**: "What is the Turing test and what does it tell us about intelligence?"
❌ **Mauvais**: "turing"

✅ **Bon**: "Can virtue be taught according to Plato?"
❌ **Mauvais**: "plato virtue"

### 2. Explorer les Concepts
Cliquer sur les concepts affichés pour voir les thèmes principaux d'une section.

### 3. Ajuster le Seuil
- Trop de résultats non pertinents? → Augmenter le seuil
- Pas assez de résultats? → Réduire le seuil

### 4. Basculer entre Modes
Utiliser le bouton "🔄 Recherche classique" pour comparer les résultats entre Summary et Chunk.

---

## 🚀 Prochaines Fonctionnalités

Améliorations prévues:
- [ ] Bouton "Voir les passages détaillés" sur chaque résumé
- [ ] Filtres par auteur/document
- [ ] Historique de recherche
- [ ] Export des résultats (JSON/PDF)
- [ ] Suggestions de recherches liées

---

## 📞 Support

- **Documentation complète**: `INTEGRATION_SUMMARY.md`
- **Analyse technique**: `ANALYSE_RAG_FINAL.md`
- **Guide d'utilisation**: `README_SEARCH.md`
- **Tests**: `test_flask_integration.py`

---

**Version**: 1.0
**Date**: 2026-01-03
**Statut**: ✅ Production Ready

Bon usage de la recherche optimisée! 🚀
